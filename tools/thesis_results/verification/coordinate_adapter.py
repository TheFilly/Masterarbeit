"""Batchadapter fuer die bestehende Koordinatenvalidierung."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from tools.thesis_results.coordinate_validation.coordinate_validation import (
    analyse_ground_truth,
    compare_rendered_bbox,
    load_rendered_pixels,
)

from .case_outcomes import CaseProfile, CaseResult


# Input: Ground-Truth-JSON, gerastertes Ausgabedokument und Annotation-Index.
# Output: Echte Pixelmetriken aus der bestehenden Koordinatenvalidierung.
def measure_rendered_annotation(
    ground_truth: Path,
    rendered: Path,
    annotation_index: int,
    *,
    width: int,
    height: int,
    tolerance: float = 0.0,
    frame_index: int = 0,
) -> dict[str, Any]:
    """Misst Mittelpunktfehler, IoU und Toleranz fuer eine reale Ausgabe."""
    payload = json.loads(ground_truth.read_text(encoding="utf-8-sig"))
    annotations = payload.get("box_annotations", [])
    if not isinstance(annotations, list) or annotation_index >= len(annotations):
        raise ValueError("Annotation-Index liegt ausserhalb der Ground Truth.")
    annotation = annotations[annotation_index]
    if not isinstance(annotation, dict) or not isinstance(
        annotation.get("corners"), list
    ):
        raise ValueError("Ground Truth enthaelt keine gueltigen Ecken.")
    pixels = load_rendered_pixels(rendered, frame_index)
    result = compare_rendered_bbox(
        annotation["corners"], pixels, width, height, tolerance
    )
    return {
        "center_error_px": result.center_error_px,
        "iou": result.iou,
        "within_tolerance": result.within_tolerance,
        "pixel_metric_status": "measured",
    }


# Input: erfolgreiche Faelle mit Ground Truth und Profilen.
# Output: Fall-, Block- und Stratum-Aggregate der strukturellen Koordinatenpruefung.
# Die bestehende `analyse_ground_truth`-Implementierung bleibt die einzige Quelle
# fuer Bounds-/Geometrieregeln; Pixelstichproben koennen separat eingespeist werden.
def aggregate_coordinate_cases(
    cases: list[
        tuple[Path, CaseProfile]
        | tuple[Path, CaseProfile, int]
        | tuple[Path, CaseProfile, CaseResult]
    ],
    block_size: int = 100,
    *,
    pixel_sampler: Any | None = None,
    pixel_sample_rate: float = 1.0,
    pixel_seed: int = 42,
) -> dict[str, Any]:
    """Aggregiert Koordinatenmetriken deterministisch nach Fall und Stratum."""
    rows: list[dict[str, Any]] = []
    if not 0.0 <= pixel_sample_rate <= 1.0:
        raise ValueError("pixel_sample_rate muss zwischen 0 und 1 liegen.")
    sampler_random = random.Random(pixel_seed)
    block_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for case_item in cases:
        ground_truth, profile = case_item[0], case_item[1]
        block_number: int | None = None
        if len(case_item) == 3:
            block_value = case_item[2]
            block_number = (
                block_value
                if isinstance(block_value, int)
                else block_value.block_number
            )
        if profile.width is None or profile.height is None:
            continue
        current_rows = analyse_ground_truth(ground_truth, profile.width, profile.height)
        for annotation_index, row in enumerate(current_rows):
            row["annotation_index"] = annotation_index
            row["case_id"] = profile.case_id
            row["block_number"] = block_number
            row["stratum"] = {
                key: getattr(profile, key)
                for key in (
                    "document_type",
                    "photometry",
                    "frame_mode",
                    "placement_mode",
                    "rotation_degrees",
                    "font_or_renderer",
                )
            }
            row["center_error_px"] = None
            row["iou"] = None
            row["within_tolerance"] = None
            row["pixel_sampled"] = False
            row["pixel_metric_reason"] = (
                "Keine gerenderte Ausgabe fuer diesen Fall bereitgestellt"
                if pixel_sampler is None
                else None
            )
            if (
                pixel_sampler is not None
                and sampler_random.random() < pixel_sample_rate
            ):
                pixel_result = pixel_sampler(ground_truth, row, profile)
                if pixel_result is not None:
                    row.update(pixel_result)
                    row["pixel_sampled"] = True
            rows.append(row)
            if block_number is not None:
                block_rows[block_number].append(row)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[json.dumps(row["stratum"], sort_keys=True, default=str)].append(row)

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        sampled = [item for item in items if item.get("pixel_sampled")]
        center_errors = [
            item["center_error_px"]
            for item in sampled
            if item.get("center_error_px") is not None
        ]
        ious = [item["iou"] for item in sampled if item.get("iou") is not None]
        return {
            "annotations": len(items),
            "invalid_positions": sum(not item["within_bounds"] for item in items),
            "clipping_errors": sum(not item["text_not_clipped"] for item in items),
            "geometry_errors": sum(not item["within_bounds"] for item in items),
            "center_error_mean_px": sum(center_errors) / len(center_errors)
            if center_errors
            else None,
            "iou_mean": sum(ious) / len(ious) if ious else None,
            "tolerance_violations": sum(
                item.get("within_tolerance") is False for item in items
            ),
            "tolerance_unknown": sum(
                item.get("within_tolerance") is None for item in items
            ),
            "pixel_sampled": len(sampled),
            "cases": len({item["case_id"] for item in items}),
        }

    return {
        "cases": [
            {
                "case_id": profile.case_id,
                "block_number": (
                    case_item[2]
                    if len(case_item) == 3 and isinstance(case_item[2], int)
                    else case_item[2].block_number
                    if len(case_item) == 3
                    else None
                ),
                "annotations": summarize(
                    [row for row in rows if row["case_id"] == profile.case_id]
                ),
            }
            for case_item in cases
        ],
        "strata": {key: summarize(value) for key, value in sorted(groups.items())},
        "total": summarize(rows),
        "block_size": block_size,
        "pixel_sampling": {"seed": pixel_seed, "rate": pixel_sample_rate},
        "pixel_metric_status": (
            "measured"
            if pixel_sampler is not None and pixel_sample_rate > 0
            else "not_executed"
        ),
        "pixel_metric_reason": (
            None
            if pixel_sampler is not None and pixel_sample_rate > 0
            else "Keine gerenderte BBox bzw. kein Pixel-Sampler bereitgestellt"
        ),
        "blocks": {
            str(block_number): summarize(block_items)
            for block_number, block_items in sorted(block_rows.items())
        },
    }
