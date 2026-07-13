"""Handwriting-asset rendering for pixel injection."""

from pathlib import Path
from typing import Any

from PIL import Image

from injection_pipeline.engine.geometry import (
    _MASK_ALPHA_THRESHOLD,
    _coerce_position,
    _mask_bounds_to_corners,
    _require_mask_bounds,
    _serialize_mask_bounds,
    _validate_rotation,
)
from injection_pipeline.engine.prepared_overlay import PreparedOverlay


# Input: `base_image` mit Zielbild, `annotation` mit Handschrift-Asset und
# optionales `prepared_overlay`.
# Output: Gerendertes Bild und Annotation mit Ink-Mask-Geometrie.
# Die Funktion komponiert das Asset und nutzt ein vorbereitetes Overlay aus dem
# Placement-Pass, wenn es vorhanden ist.
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
        "text": overlay["text"],
        "rendered_text": overlay["text"],
        "generic_text": "",
        "pii_text": overlay["text"],
        "region": annotation.get("region", overlay["region"]),
        "rotation_degrees": overlay["rotation_degrees"],
        "corners": _mask_bounds_to_corners(position, overlay["pii_rotated_bounds"]),
        "label_corners": None,
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
# Die Funktion laedt PNG und Maske aus dem Asset-Paket und rotiert beide gleich.
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

    return {
        "label": annotation.get("label", "visible_text"),
        "text": text,
        "generic_text": "",
        "pii_text": text,
        "region": annotation.get("region", "top_left_overlay"),
        "rotation_degrees": rotation,
        "rotated_layer": rotated_layer,
        "rotated_size": rotated_layer.size,
        "text_box_size": layer.size,
        "text_source_bounds": source_mask_bounds,
        "pii_source_bounds": source_mask_bounds,
        "label_source_bounds": None,
        "text_rotated_bounds": mask_bounds,
        "pii_rotated_bounds": mask_bounds,
        "label_rotated_bounds": None,
        "render_metadata": {
            "renderer_type": "handwriting_asset",
            "asset_id": asset.get("asset_id"),
            "asset_path": str(image_path),
            "mask_path": str(mask_path),
            "ink_color": asset.get("ink_color"),
            "background_mode": asset.get("background_mode"),
            "geometry_source": "transformed_ink_mask",
            "mask_coordinate_space": "rotated_overlay_pixels",
            "mask_alpha_threshold": _MASK_ALPHA_THRESHOLD,
            "pii_mask_bounds": _serialize_mask_bounds(mask_bounds),
            "text_mask_bounds": _serialize_mask_bounds(mask_bounds),
            "label_mask_bounds": None,
            "text_box_size": {"width": layer.size[0], "height": layer.size[1]},
            "rotated_box_size": {
                "width": rotated_layer.size[0],
                "height": rotated_layer.size[1],
            },
        },
    }
