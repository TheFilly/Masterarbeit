"""Handwriting-asset rendering for pixel injection."""

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from injection_pipeline.engine.geometry import (
    _MASK_ALPHA_THRESHOLD,
    _coerce_position,
    _mask_bounds_to_corners,
    _require_mask_bounds,
    _serialize_mask_bounds,
    _thresholded_mask_bounds,
    _validate_rotation,
)
from injection_pipeline.engine.prepared_overlay import PreparedOverlay
from injection_pipeline.engine.segments import (
    _normalize_text_segments,
    _split_segment_text,
)


# Input: `base_image` mit Zielbild, `annotation` mit Handschrift-Asset und
# optionales `prepared_overlay`.
# Output: Gerendertes Bild und Annotation mit Ink-Mask-Geometrie.
# Die Funktion komponiert das Asset und nutzt ein vorbereitetes Overlay aus dem
# Placement-Pass, wenn es vorhanden ist. Segmentgeometrie wird aus getrennten
# Masken gebildet, damit Prefix/Suffix nicht als PII annotiert werden.
def _render_handwriting_annotation(
    base_image: Image.Image,
    annotation: dict[str, Any],
    *,
    prepared_overlay: PreparedOverlay | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    position = _coerce_position(annotation["position"])
    overlay = (
        prepared_overlay
        if prepared_overlay is not None
        else _prepare_handwriting_asset_overlay(annotation)
    )
    composed = base_image.convert("RGBA")
    composed.alpha_composite(overlay["rotated_layer"], dest=position)

    record = {
        "label": overlay["label"],
        "category": annotation.get("category", overlay["label"]),
        "text": overlay["pii_text"],
        "rendered_text": overlay["text"],
        "generic_text": overlay["generic_text"],
        "pii_text": overlay["pii_text"],
        "prefix": overlay["prefix_text"],
        "suffix": overlay["suffix_text"],
        "region": annotation.get("region", overlay["region"]),
        "rotation_degrees": overlay["rotation_degrees"],
        "corners": _mask_bounds_to_corners(position, overlay["pii_rotated_bounds"]),
        "label_corners": _optional_mask_corners(
            position,
            overlay["label_rotated_bounds"],
        ),
        "prefix_corners": _optional_mask_corners(
            position,
            overlay["label_rotated_bounds"],
        ),
        "suffix_corners": _optional_mask_corners(
            position,
            overlay["suffix_rotated_bounds"],
        ),
        "render_metadata": {
            "position": {"x": position[0], "y": position[1]},
            **overlay["render_metadata"],
            "rendered_text_corners": _mask_bounds_to_corners(
                position,
                overlay["text_rotated_bounds"],
            ),
        },
    }
    return composed.convert("RGB"), record


# Input: `annotation` mit Manifest-Asset und Renderoptionen.
# Output: Gerenderter Handschrift-Layer samt transformierter Ink-Maske.
# Die Funktion laedt PNG und Maske aus dem Asset-Paket, erzeugt segmentierte
# Masken fuer Ground Truth und rotiert alle Masken synchron zum Bild.
def _prepare_handwriting_asset_overlay(annotation: dict[str, Any]) -> PreparedOverlay:
    asset = annotation.get("asset")
    if not isinstance(asset, dict):
        raise ValueError("Handwriting annotation requires an asset mapping.")

    rotation = int(annotation.get("rotation_degrees", 0))
    _validate_rotation(rotation)
    image_path = Path(asset["image_path"])
    mask_path = Path(asset["mask_path"])
    layer = Image.open(image_path).convert("RGBA")
    mask = Image.open(mask_path).convert("L")
    if layer.size != mask.size:
        raise ValueError("Handwriting image and mask must have the same size.")

    rotated_layer = layer.rotate(
        rotation, expand=True, resample=Image.Resampling.BICUBIC
    )
    rotated_mask = mask.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    mask_bounds = _require_mask_bounds(rotated_mask, "handwriting ink mask")
    source_mask_bounds = _require_mask_bounds(mask, "handwriting ink mask")
    text = str(asset.get("text", annotation.get("text", "")))
    text_segments = _normalize_text_segments(annotation, text)
    prefix_text, pii_text, suffix_text = _split_segment_text(text_segments)
    prefix_mask, pii_mask, suffix_mask = _derive_handwriting_segment_masks(
        mask,
        text_segments,
    )
    pii_mask_rotated = pii_mask.rotate(
        rotation,
        expand=True,
        resample=Image.Resampling.BICUBIC,
    )
    prefix_mask_rotated = prefix_mask.rotate(
        rotation,
        expand=True,
        resample=Image.Resampling.BICUBIC,
    )
    suffix_mask_rotated = suffix_mask.rotate(
        rotation,
        expand=True,
        resample=Image.Resampling.BICUBIC,
    )
    prefix_source_bounds = _thresholded_mask_bounds(prefix_mask)
    suffix_source_bounds = _thresholded_mask_bounds(suffix_mask)
    prefix_rotated_bounds = _thresholded_mask_bounds(prefix_mask_rotated)
    suffix_rotated_bounds = _thresholded_mask_bounds(suffix_mask_rotated)
    pii_rotated_bounds = _require_mask_bounds(
        pii_mask_rotated,
        "handwriting pii mask",
    )

    return {
        "label": annotation.get("label", "visible_text"),
        "text": text,
        "generic_text": prefix_text,
        "pii_text": pii_text,
        "prefix_text": prefix_text,
        "suffix_text": suffix_text,
        "region": annotation.get("region", "top_left_overlay"),
        "rotation_degrees": rotation,
        "rotated_layer": rotated_layer,
        "rotated_size": rotated_layer.size,
        "text_box_size": layer.size,
        "text_source_bounds": source_mask_bounds,
        "pii_source_bounds": _require_mask_bounds(pii_mask, "handwriting pii mask"),
        "label_source_bounds": prefix_source_bounds,
        "suffix_source_bounds": suffix_source_bounds,
        "text_rotated_bounds": mask_bounds,
        "pii_rotated_bounds": pii_rotated_bounds,
        "label_rotated_bounds": prefix_rotated_bounds,
        "suffix_rotated_bounds": suffix_rotated_bounds,
        "render_metadata": {
            "renderer_type": "handwriting_asset",
            "asset_id": asset.get("asset_id"),
            "asset_path": str(image_path),
            "mask_path": str(mask_path),
            "ink_color": asset.get("ink_color"),
            "background_mode": asset.get("background_mode"),
            "geometry_source": "transformed_ink_mask",
            "segment_geometry_source": "text_advance_clipped_ink_mask",
            "mask_coordinate_space": "rotated_overlay_pixels",
            "mask_alpha_threshold": _MASK_ALPHA_THRESHOLD,
            "text_segments": text_segments,
            "pii_mask_bounds": _serialize_mask_bounds(pii_rotated_bounds),
            "text_mask_bounds": _serialize_mask_bounds(mask_bounds),
            "label_mask_bounds": _serialize_mask_bounds(prefix_rotated_bounds),
            "prefix_mask_bounds": _serialize_mask_bounds(prefix_rotated_bounds),
            "suffix_mask_bounds": _serialize_mask_bounds(suffix_rotated_bounds),
            "text_box_size": {"width": layer.size[0], "height": layer.size[1]},
            "rotated_box_size": {
                "width": rotated_layer.size[0],
                "height": rotated_layer.size[1],
            },
        },
    }


# Input: Position und optionale Masken-Bounds im rotierten Overlay.
# Output: Absolute Ecken oder `None`.
# Die Funktion verhindert, dass leere Prefix-/Suffix-Segmente als Volltextbox
# in die Annotation serialisiert werden.
def _optional_mask_corners(
    position: tuple[int, int],
    bounds: tuple[int, int, int, int] | None,
) -> list[dict[str, float]] | None:
    if bounds is None:
        return None
    return _mask_bounds_to_corners(position, bounds)


# Input: Handschrift-Gesamtmaske und normalisierte Textsegmente.
# Output: Prefix-, PII- und Suffix-Masken im Asset-Koordinatensystem.
# Die Funktion clippt die tatsaechliche Ink-Maske entlang textbasierter
# Fortschrittsgrenzen und annotiert nie den kompletten Satz als PII-Fallback.
def _derive_handwriting_segment_masks(
    mask: Image.Image,
    text_segments: list[dict[str, str]],
) -> tuple[Image.Image, Image.Image, Image.Image]:
    full_bounds = _require_mask_bounds(mask, "handwriting ink mask")
    segment_ranges = _segment_x_ranges(mask.size, full_bounds, text_segments)
    prefix_mask = Image.new("L", mask.size, 0)
    pii_mask = Image.new("L", mask.size, 0)
    suffix_mask = Image.new("L", mask.size, 0)
    pii_seen = False

    for segment, (start_x, end_x) in zip(text_segments, segment_ranges, strict=True):
        if start_x >= end_x or not segment["text"]:
            continue
        if segment["kind"] == "pii":
            target_mask = pii_mask
            pii_seen = True
        else:
            target_mask = suffix_mask if pii_seen else prefix_mask
        clipped = mask.crop((start_x, 0, end_x, mask.height))
        target_mask.paste(clipped, (start_x, 0))

    _require_mask_bounds(pii_mask, "handwriting pii mask")
    return prefix_mask, pii_mask, suffix_mask


# Input: Maskengroesse, Ink-Bounds und Textsegmente.
# Output: X-Intervalle fuer jedes Segment.
# Die Funktion misst relative Textfortschritte mit Pillow und projiziert sie
# auf die reale Ink-Breite des Handschrift-Assets.
def _segment_x_ranges(
    mask_size: tuple[int, int],
    full_bounds: tuple[int, int, int, int],
    text_segments: list[dict[str, str]],
) -> list[tuple[int, int]]:
    del mask_size
    left, _, right, _ = full_bounds
    ink_width = max(1, right - left)
    advances = _measure_segment_advances(text_segments)
    total_advance = max(sum(advances), 1.0)

    ranges: list[tuple[int, int]] = []
    consumed = 0.0
    for index, advance in enumerate(advances):
        start_x = left + round(ink_width * consumed / total_advance)
        consumed += advance
        end_x = (
            right
            if index == len(advances) - 1
            else left + round(ink_width * consumed / total_advance)
        )
        ranges.append((max(left, start_x), min(right, end_x)))
    return ranges


# Input: Normalisierte Textsegmente.
# Output: Relative Textbreiten fuer die Segmentaufteilung.
# Die Funktion nutzt nur lokale Pillow-Messung; Leerzeichen bleiben messbar und
# damit Teil der API-Prefix-/Suffix-Geometrie.
def _measure_segment_advances(text_segments: list[dict[str, str]]) -> list[float]:
    font = ImageFont.load_default()
    drawer = ImageDraw.Draw(Image.new("L", (1, 1), 0))
    advances: list[float] = []
    for segment in text_segments:
        text = segment["text"]
        if not text:
            advances.append(0.0)
            continue
        advances.append(max(float(drawer.textlength(text, font=font)), 0.0))
    return advances
