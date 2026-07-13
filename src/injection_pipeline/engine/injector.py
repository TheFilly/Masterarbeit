"""Pixel-injection orchestration for DICOM and image outputs."""

import random
from pathlib import Path
from typing import Any

import numpy as np
import pydicom
from PIL import Image

from injection_pipeline.engine.fonts import (
    _DEFAULT_FONT_SIZE_PX,
    _FONT_PATHS,
    _resolve_font_size_px,
    load_default_font,
)
from injection_pipeline.engine.frames import (
    extract_preview_frame,
    frame_to_image,
    save_preview_image,
)
from injection_pipeline.engine.geometry import (
    _MASK_ALPHA_THRESHOLD,
    ALLOWED_ROTATIONS_DEGREES,
    _validate_rotation,
)
from injection_pipeline.engine.handwriting import _render_handwriting_annotation
from injection_pipeline.engine.overlay import (
    _TEXT_BACKGROUND_COLORS,
    _render_single_annotation,
)
from injection_pipeline.engine.placement import (
    _VALID_PLACEMENT_MODES,
    _materialize_positions,
)
from injection_pipeline.engine.prepared_overlay import get_prepared_overlay
from injection_pipeline.loaders.dicom import (
    is_multiframe_grayscale,
    resolve_dicom_frame_count,
)
from injection_pipeline.models.annotations import BoxAnnotation
from injection_pipeline.writers.dicom import (
    _coerce_rendered_frame_to_source_shape,
    _write_pixel_array,
)


# Input: `ds` mit DICOM-Dataset, sichtbare Injektionen und Renderoptionen.
# Output: Prototype-Renderpayload fuer den Orchestrator.
# Die Funktion mutiert DICOM-Pixel und schreibt die Preview-Datei als Nebeneffekt.
# Bei Multi-frame-Grayscale-DICOMs wird nur Frame 0 ersetzt.
def inject_visible_text(
    *,
    ds: pydicom.Dataset,
    visible_injections: list[dict[str, Any]],
    output_path: Path,
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    example_type: str,
    font_size_pct: int = 100,
    placement_mode: str = "corners",
    font_family: str = "arial",
    text_background: str | None = None,
) -> dict[str, Any]:
    del output_path
    del example_type
    pixel_array = np.asarray(ds.pixel_array)
    source_frame = extract_preview_frame(ds)
    render_result = _inject_visible_text_into_frame(
        frame=source_frame,
        visible_injections=visible_injections,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
        frame_count=resolve_dicom_frame_count(ds, pixel_array),
    )

    if is_multiframe_grayscale(ds, pixel_array):
        output_array = np.array(pixel_array, copy=True)
        output_array[0] = _coerce_rendered_frame_to_source_shape(
            np.asarray(render_result["output_array"]),
            source_frame,
        ).astype(output_array.dtype, copy=False)
    elif pixel_array.ndim == 4:
        output_array = np.array(pixel_array, copy=True)
        output_array[0] = render_result["output_array"]
    else:
        output_array = render_result["output_array"]

    _write_pixel_array(ds, output_array)
    return {
        "dataset": ds,
        "status": "rendered",
        "preview_file": render_result["preview_file"],
        "box_annotations": render_result["box_annotations"],
        "render_metadata": render_result["render_metadata"],
    }


# Input: `image` mit Rasterdaten, sichtbare Injektionen und Renderoptionen.
# Output: Prototype-Renderpayload mit gerendertem RGB-Bild.
# Die Funktion schreibt die Preview-Datei als Nebeneffekt und mutiert das
# Eingabebild nicht.
def inject_visible_text_into_image(
    *,
    image: Image.Image,
    visible_injections: list[dict[str, Any]],
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    font_size_pct: int = 100,
    placement_mode: str = "corners",
    font_family: str = "arial",
    text_background: str | None = None,
) -> dict[str, Any]:
    render_result = _inject_visible_text_into_frame(
        frame=np.asarray(image.convert("RGB")),
        visible_injections=visible_injections,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
        frame_count=1,
    )
    return {
        "image": Image.fromarray(render_result["output_array"]).convert("RGB"),
        "status": "rendered",
        "preview_file": render_result["preview_file"],
        "box_annotations": render_result["box_annotations"],
        "render_metadata": render_result["render_metadata"],
    }


# Input: `frame` mit Pixelarray, `visible_injections` mit Renderplan und Renderoptionen.
# Output: Render-Ergebnis mit Pixelarray, Preview-Pfad, Boxen und Metadaten.
# Die Funktion validiert Optionen, materialisiert Positionen deterministisch aus
# dem Seed und schreibt die Preview-Datei als Nebeneffekt.
def _inject_visible_text_into_frame(
    *,
    frame: np.ndarray,
    visible_injections: list[dict[str, Any]],
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    font_size_pct: int,
    placement_mode: str,
    font_family: str,
    text_background: str | None,
    frame_count: int,
) -> dict[str, Any]:
    # Both DICOM and JPG runs delegate to the same frame-level renderer so that
    # preview output, box geometry, and ground-truth metadata stay aligned.
    _validate_rotation(rotation_degrees)
    if placement_mode not in _VALID_PLACEMENT_MODES:
        raise ValueError(
            "placement_mode must be one of "
            f"{_VALID_PLACEMENT_MODES}, got {placement_mode!r}."
        )
    if font_family not in _FONT_PATHS:
        raise ValueError(f"font_family must be one of {tuple(_FONT_PATHS)}.")
    if text_background is not None and text_background not in _TEXT_BACKGROUND_COLORS:
        raise ValueError(
            "text_background must be None or one of "
            f"{tuple(_TEXT_BACKGROUND_COLORS)}, got {text_background!r}."
        )

    font_size_px = _resolve_font_size_px(font_size_pct)
    rng = random.Random(seed)
    annotations = _materialize_positions(
        visible_injections,
        frame,
        font_family=font_family,
        font_size_px=font_size_px,
        placement_mode=placement_mode,
        text_background=text_background,
        rng=rng,
    )
    output_array, rendered_annotations = _render_frame_with_annotations(
        frame,
        annotations,
        font_family=font_family,
        font_size_px=font_size_px,
        text_background=text_background,
    )
    renderer_types = sorted(
        {
            annotation.get("render_metadata", {}).get("renderer_type", "font_text")
            for annotation in rendered_annotations
        }
    )
    handwriting_assets = [
        {
            "asset_id": annotation["render_metadata"].get("asset_id"),
            "asset_path": annotation["render_metadata"].get("asset_path"),
            "mask_path": annotation["render_metadata"].get("mask_path"),
            "ink_color": annotation["render_metadata"].get("ink_color"),
            "background_mode": annotation["render_metadata"].get("background_mode"),
        }
        for annotation in rendered_annotations
        if annotation.get("render_metadata", {}).get("renderer_type")
        == "handwriting_asset"
    ]
    preview_file = save_preview_image(
        Image.fromarray(output_array).convert("RGB"),
        preview_path,
    )
    return {
        "output_array": output_array,
        "preview_file": str(preview_file),
        "box_annotations": [
            _build_box_annotation(rendered, font_size_pct=font_size_pct)
            for rendered in rendered_annotations
        ],
        "render_metadata": {
            "seed": seed,
            "rotation_degrees": rotation_degrees,
            "allowed_rotations_degrees": list(ALLOWED_ROTATIONS_DEGREES),
            "frame_count": frame_count,
            "applied_frame_indices": [0],
            "effective_font_family": font_family,
            "effective_font_size_px": font_size_px,
            "background_enabled": text_background is not None,
            "background_color": (
                list(_TEXT_BACKGROUND_COLORS[text_background])
                if text_background is not None
                else None
            ),
            "geometry_source": "mask_bbox_after_final_rotation",
            "renderer_types": renderer_types,
            "handwriting_assets": handwriting_assets,
            "geometry_notes": (
                "Bounding boxes are derived from rotated glyph masks. "
                "PII, generic prefix, and rendered-text masks are tracked separately."
            ),
            "mask_alpha_threshold": _MASK_ALPHA_THRESHOLD,
            "visible_annotations": rendered_annotations,
        },
    }


# Input: `frame` mit Preview-Pixeln, `annotations` mit Overlay-Spezifikationen.
# Output: Gerendertes Preview-Bild und sichtbare Annotationen.
# Die Funktion laedt die konfigurierte Schrift und rendert je Annotation den
# Font- oder Handschrift-Renderer. Intern vorbereitete Overlays werden
# wiederverwendet, wenn die Platzierung sie mitgegeben hat.
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
        if annotation.get("renderer_type") == "handwriting_asset":
            preview, record = _render_handwriting_annotation(
                preview,
                annotation,
                prepared_overlay=get_prepared_overlay(annotation),
            )
        else:
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


# Input: `frame` mit Pixelarray, `annotations` mit positionierten Overlays.
# Output: Gerendertes Pixelarray und sichtbare Annotationen.
# Die Funktion ist die Array-orientierte Fassade um den PIL-Renderer und haelt
# Bilddaten und Ground-Truth-Geometrie synchron.
def _render_frame_with_annotations(
    frame: np.ndarray,
    annotations: list[dict[str, Any]],
    font_family: str = "arial",
    font_size_px: int = _DEFAULT_FONT_SIZE_PX,
    text_background: str | None = None,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    preview_image, rendered_annotations = render_visible_annotations(
        frame,
        annotations,
        font_family=font_family,
        font_size_px=font_size_px,
        text_background=text_background,
    )
    return np.asarray(preview_image), rendered_annotations


# Input: `rendered` mit Renderergebnis, `font_size_pct` mit effektiver Schriftgroesse.
# Output: Validierte `BoxAnnotation` fuer Ground Truth und Preview.
# Die Funktion reduziert die Render-Metadaten auf die Felder, die im
# Run-Record als sichtbare Box-Annotation gespeichert werden.
def _build_box_annotation(
    rendered: dict[str, Any],
    *,
    font_size_pct: int,
) -> BoxAnnotation:
    return BoxAnnotation(
        label=rendered["label"],
        text=rendered["text"],
        rendered_text=rendered["rendered_text"],
        region=rendered["region"],
        corners=rendered["corners"],
        label_corners=rendered["label_corners"],
        rotation_degrees=rendered["rotation_degrees"],
        frame_index=0,
        font_size_pct=font_size_pct,
    )
