"""Focused validation and schema round-trip tests for canonical models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from injection_pipeline.models import (
    MaskBounds,
    RenderPlanItem,
    RunRecord,
    TextSegment,
    load_run_record,
)


def test_quad_requires_exactly_four_points() -> None:
    with pytest.raises(ValidationError, match="exactly four"):
        from injection_pipeline.models import Quad

        Quad.model_validate([{"x": 1, "y": 2}] * 3)


def test_mask_bounds_require_consistent_dimensions() -> None:
    with pytest.raises(ValidationError, match="width"):
        MaskBounds(left=2, top=3, right=8, bottom=9, width=5, height=6)


def test_render_plan_requires_reconstructed_nonempty_pii_text() -> None:
    with pytest.raises(ValidationError, match="reconstruct"):
        RenderPlanItem(
            label="PatientID",
            text="SYNTH-123",
            text_segments=[TextSegment(kind="generic", text="SYNTH-")],
            identity_field="patient_id",
            region="corners",
            rotation_degrees=0,
            line_index=0,
        )


def test_load_run_record_round_trips_json(tmp_path: Path) -> None:
    record = RunRecord.model_validate(
        {
            "schema_version": "0.2.0-prototype",
            "record_type": "jpg_injection_run",
            "run_id": "unit-run",
            "seed": 42,
            "rotation_degrees": 0,
            "source_file": "input.jpg",
            "output_file": "output.jpg",
            "preview_file": "preview.png",
            "annotated_preview_file": "preview_annotated.png",
            "document_type": "jpg",
            "example_type": "unit",
            "modality": None,
            "identity_id": "SYNTH-123456",
            "span_annotations": [],
            "box_annotations": [],
            "dicom_tag_annotations": [],
            "run_metadata": {
                "rotation_degrees": 0,
                "placement_mode": "corners",
                "pixel_injection_status": "rendered",
                "pixel_renderer": "unit",
                "visible_identity_fields": ["patient_id"],
                "tag_only_identity_fields": [],
            },
            "render_metadata": {
                "rotation_degrees": 0,
                "placement_mode": "corners",
                "font_size_pct": 100,
                "font_family": "arial",
                "text_background": None,
                "visible_render_plan": [
                    {
                        "label": "PatientID",
                        "text": "123456",
                        "text_segments": [{"kind": "pii", "text": "123456"}],
                        "identity_field": "patient_id",
                        "region": "corners",
                        "rotation_degrees": 0,
                        "line_index": 0,
                    }
                ],
                "seed": 42,
                "allowed_rotations_degrees": [0, 20, 90, 180, 270],
                "frame_count": 1,
                "applied_frame_indices": [0],
                "effective_font_family": "arial",
                "effective_font_size_px": 18,
                "background_enabled": False,
                "background_color": None,
                "geometry_source": "mask_bbox_after_final_rotation",
                "renderer_types": ["font_text"],
                "handwriting_assets": [],
                "geometry_notes": "unit",
                "mask_alpha_threshold": 8,
                "visible_annotations": [],
            },
        }
    )
    path = tmp_path / "ground_truth.json"
    path.write_text(
        json.dumps(record.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )

    loaded = load_run_record(path)

    assert loaded.model_dump(mode="json") == record.model_dump(mode="json")
    assert "source_dicom_context" not in loaded.run_metadata.model_dump(mode="json")
