"""Font-text overlay rendering for pixel injection."""

from typing import Any, cast

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from injection_pipeline.engine.fonts import _DEFAULT_FONT_SIZE_PX, load_default_font
from injection_pipeline.engine.frames import frame_to_image
from injection_pipeline.engine.geometry import (
    _MASK_ALPHA_THRESHOLD,
    _coerce_position,
    _require_mask_bounds,
    _rotated_corners,
    _serialize_mask_bounds,
    _thresholded_mask_bounds,
    _validate_rotation,
)
from injection_pipeline.engine.prepared_overlay import (
    PreparedOverlay,
    get_prepared_overlay,
)
from injection_pipeline.engine.segments import (
    _draw_segment_masks,
    _normalize_text_segments,
    _split_prefix_and_pii_text,
)

_TEXT_BACKGROUND_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
}


# Input: `frame` mit Preview-Pixeln, `annotations` mit Overlay-Spezifikationen.
# Output: Gerendertes Preview-Bild und sichtbare Annotationen.
# Die Funktion laedt die konfigurierte Schrift und nutzt vorbereitete Overlays,
# falls sie im Placement-Pass intern an Annotationen geheftet wurden.
def render_visible_annotations(
    frame: np.ndarray,
    annotations: list[dict[str, Any]],
    font_family: str = "arial",
    font_size_px: int = _DEFAULT_FONT_SIZE_PX,
    text_background: str | None = None,
) -> tuple[Image.Image, list[dict[str, Any]]]:
    preview = frame_to_image(frame)
    font = load_default_font(font_family=font_family, font_size_px=font_size_px)
    render_records: list[dict[str, Any]] = []

    for annotation in annotations:
        preview, record = _render_single_annotation(
            preview,
            annotation,
            font,
            font_family=font_family,
            text_background=text_background,
            prepared_overlay=get_prepared_overlay(annotation),
        )
        render_records.append(record)

    return preview, render_records


# Input: `base_image` mit Zielbild, `annotation` mit Text und Position,
# `font` mit Schrift und optionales `prepared_overlay`.
# Output: Gerendertes Bild und Annotation mit absoluter Box-Geometrie.
# Die Funktion komponiert genau ein Font-Overlay auf das Bild und leitet PII-,
# Label- und Volltext-Bounds aus dem vorbereiteten Overlay ab.
def _render_single_annotation(
    base_image: Image.Image,
    annotation: dict[str, Any],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    *,
    font_family: str,
    text_background: str | None,
    prepared_overlay: PreparedOverlay | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    position = _coerce_position(annotation["position"])
    overlay = (
        prepared_overlay
        if prepared_overlay is not None
        else _prepare_annotation_overlay(
            annotation,
            font,
            font_family=font_family,
            text_background=text_background,
        )
    )
    composed = base_image.convert("RGBA")
    composed.alpha_composite(overlay["rotated_layer"], dest=position)

    corners = _rotated_corners(
        position,
        overlay["text_box_size"],
        overlay["rotated_size"],
        overlay["rotation_degrees"],
        bounds=overlay["pii_source_bounds"],
    )
    label_corners = _rotated_corners(
        position,
        overlay["text_box_size"],
        overlay["rotated_size"],
        overlay["rotation_degrees"],
        bounds=overlay["label_source_bounds"],
    )

    record = {
        "label": overlay["label"],
        "text": overlay["pii_text"],
        "rendered_text": overlay["text"],
        "generic_text": overlay["generic_text"],
        "pii_text": overlay["pii_text"],
        "region": annotation.get("region", overlay["region"]),
        "rotation_degrees": overlay["rotation_degrees"],
        "corners": corners,
        "label_corners": label_corners,
        "render_metadata": {
            "position": {"x": position[0], "y": position[1]},
            **overlay["render_metadata"],
            "rendered_text_corners": _rotated_corners(
                position,
                overlay["text_box_size"],
                overlay["rotated_size"],
                overlay["rotation_degrees"],
                bounds=overlay["text_source_bounds"],
            ),
        },
    }
    return composed.convert("RGB"), record


# Input: `annotation` mit Textsegmenten und Stiloptionen, `font` fuer das Rendern.
# Output: Gerenderte Overlay-Layer samt maskenbasierter Geometrie.
# Die Funktion erzeugt getrennte Masken fuer Volltext, PII-Teil und optionales
# Praefix und liest die finalen Bounds erst nach der Rotation aus den Masken aus.
def _prepare_annotation_overlay(
    annotation: dict[str, Any],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    *,
    font_family: str,
    text_background: str | None,
) -> PreparedOverlay:
    text = str(annotation["text"])
    text_segments = _normalize_text_segments(annotation, text)
    rotation = int(annotation.get("rotation_degrees", 0))
    _validate_rotation(rotation)

    padding = int(annotation.get("padding", 4))
    background_color = (
        _TEXT_BACKGROUND_COLORS[text_background]
        if text_background is not None
        else None
    )
    if background_color is None:
        fill = tuple(annotation.get("fill", (255, 255, 255)))
        stroke_fill = tuple(annotation.get("stroke_fill", (0, 0, 0)))
        stroke_width = int(annotation.get("stroke_width", 1))
    else:
        fill = (0, 0, 0)
        stroke_fill = fill
        stroke_width = 0

    left, top, right, bottom = cast(tuple[int, int, int, int], font.getbbox(text))
    text_width = max(1, right - left)
    text_height = max(1, bottom - top)
    base_width = text_width + (padding * 2)
    base_height = text_height + (padding * 2)
    text_origin = (padding - left, padding - top)

    text_layer = Image.new("RGBA", (base_width, base_height), (0, 0, 0, 0))
    drawer = ImageDraw.Draw(text_layer)
    if background_color is not None:
        drawer.rectangle(
            [(0, 0), (base_width - 1, base_height - 1)],
            fill=background_color + (255,),
        )
    drawer.text(
        text_origin,
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )

    text_mask = Image.new("L", (base_width, base_height), 0)
    ImageDraw.Draw(text_mask).text(
        text_origin,
        text,
        font=font,
        fill=255,
        stroke_width=stroke_width,
        stroke_fill=255,
    )

    pii_mask = Image.new("L", (base_width, base_height), 0)
    label_mask = Image.new("L", (base_width, base_height), 0)
    _draw_segment_masks(
        text_segments=text_segments,
        font=font,
        origin=text_origin,
        stroke_width=stroke_width,
        pii_mask=pii_mask,
        label_mask=label_mask,
    )

    text_source_bounds = _require_mask_bounds(text_mask, "rendered text mask")
    pii_source_bounds = _require_mask_bounds(pii_mask, "pii text mask")
    label_source_bounds = _thresholded_mask_bounds(label_mask)

    rotated_layer = text_layer.rotate(
        rotation, expand=True, resample=Image.Resampling.BICUBIC
    )
    text_mask_rotated = text_mask.rotate(
        rotation, expand=True, resample=Image.Resampling.BICUBIC
    )
    pii_mask_rotated = pii_mask.rotate(
        rotation, expand=True, resample=Image.Resampling.BICUBIC
    )
    label_mask_rotated = label_mask.rotate(
        rotation, expand=True, resample=Image.Resampling.BICUBIC
    )
    prefix_text, pii_text = _split_prefix_and_pii_text(text_segments)

    return {
        "label": annotation.get("label", "visible_text"),
        "text": text,
        "generic_text": prefix_text,
        "pii_text": pii_text,
        "region": annotation.get("region", "top_left_overlay"),
        "rotation_degrees": rotation,
        "rotated_layer": rotated_layer,
        "rotated_size": rotated_layer.size,
        "text_box_size": (base_width, base_height),
        "text_source_bounds": text_source_bounds,
        "pii_source_bounds": pii_source_bounds,
        "label_source_bounds": label_source_bounds,
        "text_rotated_bounds": _require_mask_bounds(
            text_mask_rotated, "rendered text mask"
        ),
        "pii_rotated_bounds": _require_mask_bounds(pii_mask_rotated, "pii text mask"),
        "label_rotated_bounds": _thresholded_mask_bounds(label_mask_rotated),
        "render_metadata": {
            "font_family": font_family,
            "font_name": getattr(font, "path", "PillowDefaultFont"),
            "font_size": getattr(font, "size", None),
            "padding": padding,
            "fill_rgb": list(fill),
            "stroke_fill_rgb": list(stroke_fill),
            "stroke_width": stroke_width,
            "background_enabled": background_color is not None,
            "background_color": list(background_color) if background_color else None,
            "text_segments": text_segments,
            "geometry_source": "mask_bbox_after_final_rotation",
            "mask_coordinate_space": "rotated_overlay_pixels",
            "mask_alpha_threshold": _MASK_ALPHA_THRESHOLD,
            "text_mask_bounds": _serialize_mask_bounds(
                _thresholded_mask_bounds(text_mask_rotated)
            ),
            "pii_mask_bounds": _serialize_mask_bounds(
                _thresholded_mask_bounds(pii_mask_rotated)
            ),
            "label_mask_bounds": _serialize_mask_bounds(
                _thresholded_mask_bounds(label_mask_rotated)
            ),
            "text_box_size": {"width": base_width, "height": base_height},
            "rotated_box_size": {
                "width": rotated_layer.size[0],
                "height": rotated_layer.size[1],
            },
        },
    }
