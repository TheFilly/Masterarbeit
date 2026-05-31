"""Prototype helpers for visible pixel injection in DICOM ultrasound previews."""

import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import pydicom
from PIL import Image, ImageDraw, ImageFont
from pydicom.uid import ExplicitVRLittleEndian

# Conservative prototype-only angle set. This keeps annotation geometry easy to
# validate while still exercising rotated overlays.
ALLOWED_ROTATIONS_DEGREES: tuple[int, ...] = (0, 20, 90, 180, 270)

_DEFAULT_FONT_SIZE_PX: int = 18
_VALID_PLACEMENT_MODES: tuple[str, ...] = ("free", "corners")
_FONT_PATHS: dict[str, str] = {
    "arial": "C:/Windows/Fonts/arial.ttf",
    "calibri": "C:/Windows/Fonts/calibri.ttf",
    "tahoma": "C:/Windows/Fonts/tahoma.ttf",
    "consolas": "C:/Windows/Fonts/consola.ttf",
}
_TEXT_BACKGROUND_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
}
_MASK_ALPHA_THRESHOLD: int = 8


# Convert a font-size percentage to an absolute pixel size.
def _resolve_font_size_px(font_size_pct: int) -> int:
    if font_size_pct < 1:
        raise ValueError("font_size_pct must be >= 1")
    return max(1, round(_DEFAULT_FONT_SIZE_PX * font_size_pct / 100))


# Input: `ds` mit geladenem DICOM-Dataset.
# Output: Numpy-Array mit dem ersten darstellbaren Preview-Frame.
# Die Funktion reduziert mehrdimensionale Pixelarrays auf den Prototyp-Frame.
def extract_preview_frame(ds: pydicom.Dataset) -> np.ndarray:
    pixel_array = np.asarray(ds.pixel_array)
    if pixel_array.ndim == 4:
        return pixel_array[0]
    if pixel_array.ndim == 3 and pixel_array.shape[-1] in {3, 4}:
        return pixel_array
    if pixel_array.ndim == 3:
        return pixel_array[0]
    return pixel_array


# Normalize a grayscale or RGB frame to uint8 for preview rendering.
def normalize_to_uint8(frame: np.ndarray) -> np.ndarray:
    array = np.asarray(frame)
    if array.dtype == np.uint8:
        return array

    working = array.astype(np.float32)
    min_value = float(np.min(working))
    max_value = float(np.max(working))
    if math.isclose(min_value, max_value):
        return np.zeros_like(array, dtype=np.uint8)

    normalized = (working - min_value) / (max_value - min_value)
    return np.clip(normalized * 255.0, 0, 255).astype(np.uint8)


# Convert a DICOM preview frame to a PIL image.
def frame_to_image(frame: np.ndarray) -> Image.Image:
    normalized = normalize_to_uint8(frame)
    if normalized.ndim == 2:
        return Image.fromarray(normalized, mode="L").convert("RGB")
    return Image.fromarray(normalized).convert("RGB")


# Load a configured prototype font at the given pixel size.
def load_default_font(
    font_family: str = "arial",
    font_size_px: int = _DEFAULT_FONT_SIZE_PX,
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    font_path = _FONT_PATHS.get(font_family)
    if font_path is None:
        raise ValueError(
            f"font_family must be one of {tuple(_FONT_PATHS)}, got {font_family!r}."
        )
    try:
        return ImageFont.truetype(font_path, size=font_size_px)
    except OSError as error:
        raise RuntimeError(
            f"Configured prototype font {font_family!r} is unavailable at "
            f"{font_path!r}."
        ) from error


# Input: `identity` mit synthetischen Feldern, `rotation_degrees` fuer Overlays.
# Output: Liste von Overlay-Spezifikationen.
# Die Funktion validiert den Rotationswinkel und wirft bei ungueltigen Werten
# ValueError.
def build_visible_text_annotations(
    identity: dict[str, str],
    rotation_degrees: int = 0,
) -> list[dict[str, Any]]:
    _validate_rotation(rotation_degrees)
    return [
        {
            "label": "PatientName",
            "text": identity["patient_name"],
            "text_segments": [{"kind": "pii", "text": identity["patient_name"]}],
            "region": "header_overlay",
            "line_index": 0,
            "rotation_degrees": rotation_degrees,
        },
        {
            "label": "PatientID",
            "text": identity["patient_id"],
            "text_segments": [
                {"kind": "generic", "text": "SYNTH-"},
                {"kind": "pii", "text": identity["patient_id"].removeprefix("SYNTH-")},
            ],
            "region": "header_overlay",
            "line_index": 1,
            "rotation_degrees": rotation_degrees,
        },
        {
            "label": "AccessionNumber",
            "text": identity["accession_number"],
            "text_segments": [
                {"kind": "generic", "text": "ACC-"},
                {
                    "kind": "pii",
                    "text": identity["accession_number"].removeprefix("ACC-"),
                },
            ],
            "region": "header_overlay",
            "line_index": 2,
            "rotation_degrees": rotation_degrees,
        },
    ]


# Input: `frame` mit Preview-Pixeln, `annotations` mit Overlay-Spezifikationen.
# Output: Gerendertes Preview-Bild und sichtbare Annotationen.
# Die Funktion laedt die konfigurierte Schrift und rendert alle Overlays.
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
        )
        render_records.append(record)

    return preview, render_records


# Extract a DICOM preview frame and render visible prototype annotations.
def render_annotations_for_dataset(
    ds: pydicom.Dataset,
    annotations: list[dict[str, Any]],
    font_family: str = "arial",
    font_size_px: int = _DEFAULT_FONT_SIZE_PX,
    text_background: str | None = None,
) -> tuple[Image.Image, list[dict[str, Any]]]:
    return render_visible_annotations(
        extract_preview_frame(ds),
        annotations,
        font_family=font_family,
        font_size_px=font_size_px,
        text_background=text_background,
    )


# Save a rendered preview image to disk.
def save_preview_image(image: Image.Image, output_path: str | Path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return destination


# Input: `ds` mit DICOM-Dataset, sichtbare Injektionen und Renderoptionen.
# Output: Prototype-Renderpayload fuer den Orchestrator.
# Die Funktion mutiert DICOM-Pixel und schreibt die Preview-Datei als Nebeneffekt.
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
    render_result = _inject_visible_text_into_frame(
        frame=extract_preview_frame(ds),
        visible_injections=visible_injections,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
        frame_count=int(pixel_array.shape[0]) if pixel_array.ndim == 4 else 1,
    )

    if pixel_array.ndim == 4:
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


# Render visible text into a raster image and save the preview artifact.
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


# Input: `base_image` mit Zielbild, `annotation` mit Text und Position,
# `font` mit Schrift.
# Output: Gerendertes Bild und Annotation mit absoluter Box-Geometrie.
# Die Funktion komponiert genau ein Overlay auf das Bild und leitet PII-, Label-
# und Volltext-Bounds aus den vorbereiteten Masken ab.
def _render_single_annotation(
    base_image: Image.Image,
    annotation: dict[str, Any],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    *,
    font_family: str,
    text_background: str | None,
) -> tuple[Image.Image, dict[str, Any]]:
    if annotation.get("renderer_type") == "handwriting_asset":
        return _render_handwriting_annotation(base_image, annotation)

    position = _coerce_position(annotation["position"])
    overlay = _prepare_annotation_overlay(
        annotation,
        font,
        font_family=font_family,
        text_background=text_background,
    )
    composed = base_image.convert("RGBA")
    composed.alpha_composite(overlay["rotated_layer"], dest=position)

    corners = _mask_bounds_to_corners(position, overlay["pii_rotated_bounds"])
    label_corners = _mask_bounds_to_corners(position, overlay["label_rotated_bounds"])

    record = {
        "label": overlay["label"],
        "text": overlay["pii_text"],
        "rendered_text": overlay["text"],
        "generic_text": overlay["generic_text"],
        "pii_text": overlay["pii_text"],
        "region": overlay["region"],
        "rotation_degrees": overlay["rotation_degrees"],
        "corners": corners,
        "label_corners": label_corners,
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


# Input: `base_image` mit Zielbild, `annotation` mit Handschrift-Asset.
# Output: Gerendertes Bild und Annotation mit Ink-Mask-Geometrie.
# Die Funktion komponiert das Asset und nutzt nur die transformierte Maske fuer
# die PII-Box.
def _render_handwriting_annotation(
    base_image: Image.Image,
    annotation: dict[str, Any],
) -> tuple[Image.Image, dict[str, Any]]:
    position = _coerce_position(annotation["position"])
    overlay = _prepare_handwriting_asset_overlay(annotation)
    composed = base_image.convert("RGBA")
    composed.alpha_composite(overlay["rotated_layer"], dest=position)

    record = {
        "label": overlay["label"],
        "text": overlay["text"],
        "rendered_text": overlay["text"],
        "generic_text": "",
        "pii_text": overlay["text"],
        "region": overlay["region"],
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
) -> dict[str, Any]:
    if annotation.get("renderer_type") == "handwriting_asset":
        return _prepare_handwriting_asset_overlay(annotation)

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

    left, top, right, bottom = font.getbbox(text)
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

    rotated_layer = text_layer.rotate(rotation, expand=True, resample=Image.BICUBIC)
    text_mask_rotated = text_mask.rotate(rotation, expand=True, resample=Image.BICUBIC)
    pii_mask_rotated = pii_mask.rotate(rotation, expand=True, resample=Image.BICUBIC)
    label_mask_rotated = label_mask.rotate(
        rotation, expand=True, resample=Image.BICUBIC
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


# Input: `annotation` mit Manifest-Asset und Renderoptionen.
# Output: Gerenderter Handschrift-Layer samt transformierter Ink-Maske.
# Die Funktion laedt PNG und Maske aus dem Asset-Paket und rotiert beide gleich.
def _prepare_handwriting_asset_overlay(annotation: dict[str, Any]) -> dict[str, Any]:
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

    rotated_layer = layer.rotate(rotation, expand=True, resample=Image.BICUBIC)
    rotated_mask = mask.rotate(rotation, expand=True, resample=Image.BICUBIC)
    mask_bounds = _require_mask_bounds(rotated_mask, "handwriting ink mask")

    return {
        "label": annotation.get("label", "visible_text"),
        "text": str(asset.get("text", annotation.get("text", ""))),
        "region": annotation.get("region", "top_left_overlay"),
        "rotation_degrees": rotation,
        "rotated_layer": rotated_layer,
        "rotated_size": rotated_layer.size,
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


# Input: sichtbare Injektionen, Preview-Frame und Renderkonfiguration.
# Output: Injektionen mit finalen Pixelpositionen.
# Die Platzierung basiert auf derselben maskenbasierten Overlay-Geometrie wie die
# spaetere Annotation, damit keine Offsets zur Ground Truth entstehen.
def _materialize_positions(
    visible_injections: list[dict[str, Any]],
    frame: np.ndarray,
    font_family: str = "arial",
    font_size_px: int = _DEFAULT_FONT_SIZE_PX,
    placement_mode: str = "corners",
    text_background: str | None = None,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    if rng is None:
        rng = random.Random(0)

    image_height, image_width = frame.shape[:2]
    h_margin = max(24, int(image_width * 0.03))
    v_margin = max(24, int(image_height * 0.03))
    vertical_gap = max(10, int(image_height * 0.015))
    padding = 4
    font = load_default_font(font_family=font_family, font_size_px=font_size_px)

    sizes: list[tuple[int, int]] = []
    for injection in visible_injections:
        overlay = _prepare_annotation_overlay(
            {**injection, "padding": padding, "stroke_width": 1},
            font,
            font_family=font_family,
            text_background=text_background,
        )
        sizes.append(overlay["rotated_size"])

    positioned_annotations: list[dict[str, Any]] = []

    if placement_mode == "corners":
        corner = rng.choice(["top_left", "top_right", "bottom_left", "bottom_right"])

        if corner in ("bottom_left", "bottom_right"):
            total_height = (
                sum(rot_h for _, rot_h in sizes) + vertical_gap * max(0, len(sizes) - 1)
            )
            current_y = max(v_margin, image_height - v_margin - total_height)
        else:
            current_y = v_margin

        for injection, (rot_w, rot_h) in zip(
            visible_injections, sizes, strict=True
        ):
            if corner in ("top_right", "bottom_right"):
                x = max(h_margin, image_width - h_margin - rot_w)
            else:
                x = h_margin
            positioned_annotations.append(
                {
                    **injection,
                    "position": (x, current_y),
                    "region": corner,
                    "padding": padding,
                    "stroke_width": 1,
                }
            )
            current_y += rot_h + vertical_gap

    elif placement_mode == "free":
        for injection, (rot_w, rot_h) in zip(
            visible_injections, sizes, strict=True
        ):
            x_max = max(h_margin, image_width - rot_w - h_margin)
            y_max = max(v_margin, image_height - rot_h - v_margin)
            x = rng.randint(h_margin, x_max)
            y = rng.randint(v_margin, y_max)
            positioned_annotations.append(
                {
                    **injection,
                    "position": (x, y),
                    "region": "free",
                    "padding": padding,
                    "stroke_width": 1,
                }
            )

    return positioned_annotations


# Input: `width` und `height` mit Originalgroesse, `rotation_degrees` mit Winkel.
# Output: Geschaetzte Breite und Hoehe nach Rotation.
# Die Funktion berechnet eine konservative Bounding-Box fuer gedrehte Rechtecke
# ohne ein Bildobjekt zu erzeugen.
def _estimate_rotated_size(
    *,
    width: int,
    height: int,
    rotation_degrees: int,
) -> tuple[int, int]:
    radians = math.radians(rotation_degrees)
    cosine = abs(math.cos(radians))
    sine = abs(math.sin(radians))
    rotated_width = int(math.ceil((width * cosine) + (height * sine)))
    rotated_height = int(math.ceil((width * sine) + (height * cosine)))
    return rotated_width, rotated_height


# Persist rendered pixels back into the dataset with matching DICOM metadata.
def _write_pixel_array(ds: pydicom.Dataset, output_array: np.ndarray) -> None:
    contiguous = np.ascontiguousarray(output_array)
    ds.PixelData = contiguous.tobytes()
    if contiguous.ndim == 4:
        ds.NumberOfFrames = contiguous.shape[0]
        ds.Rows = contiguous.shape[1]
        ds.Columns = contiguous.shape[2]
        ds.SamplesPerPixel = contiguous.shape[3]
    elif contiguous.ndim == 3 and contiguous.shape[-1] in {3, 4}:
        ds.Rows = contiguous.shape[0]
        ds.Columns = contiguous.shape[1]
        ds.SamplesPerPixel = contiguous.shape[2]
    else:
        ds.Rows = contiguous.shape[0]
        ds.Columns = contiguous.shape[1]
        ds.SamplesPerPixel = 1

    if contiguous.ndim >= 3 and contiguous.shape[-1] in {3, 4}:
        ds.PhotometricInterpretation = "RGB"
        ds.PlanarConfiguration = 0
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
    else:
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0

    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.is_implicit_VR = False
    ds.is_little_endian = True


# Input: `position` mit zwei Koordinatenwerten.
# Output: Position als Integer-Tupel.
# Die Funktion erzwingt das erwartete Koordinatenformat und meldet ungueltige
# Werte per ValueError.
def _coerce_position(position: Any) -> tuple[int, int]:
    if not isinstance(position, (tuple, list)) or len(position) != 2:
        raise ValueError("Annotation position must be a tuple/list with two items.")
    return int(position[0]), int(position[1])


# Input: `rotation_degrees` mit angefordertem Drehwinkel.
# Output: Keine Rueckgabe.
# Die Funktion akzeptiert nur die prototypeigene Winkelliste und wirft sonst
# einen ValueError.
def _validate_rotation(rotation_degrees: int) -> None:
    if rotation_degrees not in ALLOWED_ROTATIONS_DEGREES:
        raise ValueError(
            "Rotation must be one of "
            f"{ALLOWED_ROTATIONS_DEGREES}, got {rotation_degrees}."
        )


# Input: `position` mit Zieloffset, Groessen, `rotation_degrees` und optionalen Bounds.
# Output: Vier gedrehte Eckpunkte im Bildkoordinatensystem.
# Die Funktion projiziert lokale Rechteckkoordinaten um das Overlay-Zentrum und
# rundet die Ergebniswerte fuer JSON-taugliche Annotationen.
def _rotated_corners(
    position: tuple[int, int],
    unrotated_size: tuple[int, int],
    rotated_size: tuple[int, int],
    rotation_degrees: int,
    bounds: tuple[float, float, float, float] | None = None,
) -> list[dict[str, float]]:
    width, height = unrotated_size
    rotated_width, rotated_height = rotated_size

    original_center = (width / 2.0, height / 2.0)
    rotated_center = (rotated_width / 2.0, rotated_height / 2.0)
    radians = math.radians(rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)

    if bounds is None:
        bounds = (0.0, 0.0, float(width), float(height))
    base_corners = [
        (bounds[0], bounds[1]),
        (bounds[2], bounds[1]),
        (bounds[2], bounds[3]),
        (bounds[0], bounds[3]),
    ]
    rotated_corners: list[dict[str, float]] = []

    for x_value, y_value in base_corners:
        translated_x = x_value - original_center[0]
        translated_y = y_value - original_center[1]
        rotated_x = (translated_x * cosine) + (translated_y * sine)
        rotated_y = -(translated_x * sine) + (translated_y * cosine)
        final_x = position[0] + rotated_center[0] + rotated_x
        final_y = position[1] + rotated_center[1] + rotated_y
        rotated_corners.append({"x": round(final_x, 2), "y": round(final_y, 2)})

    return rotated_corners


# Input: `annotation` mit optionalen Textsegmenten, `full_text` mit Rendertext.
# Output: Normalisierte Textsegmente.
# Die Funktion faellt ohne gueltige Segmente auf ein reines PII-Segment zurueck
# und validiert sonst Rekonstruktion und PII-Anteil.
def _normalize_text_segments(
    annotation: dict[str, Any], full_text: str
) -> list[dict[str, str]]:
    raw_segments = annotation.get("text_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        return [{"kind": "pii", "text": full_text}]

    normalized: list[dict[str, str]] = []
    reconstructed = ""
    pii_seen = False
    for segment in raw_segments:
        if not isinstance(segment, dict):
            continue
        kind = str(segment.get("kind", "generic"))
        text = str(segment.get("text", ""))
        reconstructed += text
        if kind == "pii" and text:
            pii_seen = True
        normalized.append({"kind": kind, "text": text})

    if reconstructed != full_text or not pii_seen:
        raise ValueError(
            f"Invalid text_segments for {annotation.get('label', 'visible_text')!r}."
        )
    return normalized


# Render PII- und Label-Segmente in getrennte Masken bei identischer Textreihenfolge.
def _draw_segment_masks(
    *,
    text_segments: list[dict[str, str]],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    origin: tuple[float, float],
    stroke_width: int,
    pii_mask: Image.Image,
    label_mask: Image.Image,
) -> None:
    cursor_x = origin[0]
    pii_draw = ImageDraw.Draw(pii_mask)
    label_draw = ImageDraw.Draw(label_mask)

    for segment in text_segments:
        segment_text = segment["text"]
        if not segment_text:
            continue

        segment_bounds = _resolve_segment_draw_bounds(
            font=font,
            origin=(cursor_x, origin[1]),
            segment_text=segment_text,
            stroke_width=stroke_width,
        )
        if segment["kind"] == "pii":
            pii_draw.text(
                (cursor_x, origin[1]),
                segment_text,
                font=font,
                fill=255,
                stroke_width=stroke_width,
                stroke_fill=255,
            )
        else:
            label_draw.text(
                (cursor_x, origin[1]),
                segment_text,
                font=font,
                fill=255,
                stroke_width=stroke_width,
                stroke_fill=255,
            )
        cursor_x = segment_bounds[2]


# Input: `text_segments` mit geordneten generischen und PII-Anteilen.
# Output: Generisches Praefix und zusammengefuegter PII-Text.
# Die Funktion sammelt nur vorangestellte Nicht-PII-Segmente als Label und
# verlangt mindestens ein nicht leeres PII-Segment.
def _split_prefix_and_pii_text(
    text_segments: list[dict[str, str]],
) -> tuple[str, str]:
    prefix_text = ""
    pii_text = ""
    for segment in text_segments:
        segment_kind = segment["kind"]
        segment_text = segment["text"]
        if segment_kind == "pii":
            pii_text += segment_text
        elif not pii_text:
            prefix_text += segment_text
    if not pii_text:
        raise ValueError("At least one non-empty pii text segment is required.")
    return prefix_text, pii_text


# Measure where one segment ends so the next segment uses the same text flow.
def _resolve_segment_draw_bounds(
    *,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    origin: tuple[float, float],
    segment_text: str,
    stroke_width: int,
) -> tuple[float, float, float, float]:
    scratch = ImageDraw.Draw(Image.new("L", (1, 1), 0))
    left, top, right, bottom = scratch.textbbox(
        origin,
        segment_text,
        font=font,
        stroke_width=stroke_width,
    )
    return float(left), float(top), float(right), float(bottom)


# Return tight bounds for a rendered mask and fail fast when nothing is visible.
def _require_mask_bounds(
    mask: Image.Image,
    mask_name: str,
) -> tuple[int, int, int, int]:
    bounds = _thresholded_mask_bounds(mask)
    if bounds is None:
        raise ValueError(f"{mask_name} is empty.")
    return bounds


# Serialize optional mask bounds for prototype metadata.
def _serialize_mask_bounds(
    bounds: tuple[int, int, int, int] | None,
) -> dict[str, int] | None:
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    return {
        "left": int(left),
        "top": int(top),
        "right": int(right),
        "bottom": int(bottom),
        "width": int(right - left),
        "height": int(bottom - top),
    }


# Project local mask bounds into absolute image-space rectangle corners.
def _mask_bounds_to_corners(
    position: tuple[int, int],
    bounds: tuple[int, int, int, int] | None,
) -> list[dict[str, float]] | None:
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    return [
        {"x": float(position[0] + left), "y": float(position[1] + top)},
        {"x": float(position[0] + right), "y": float(position[1] + top)},
        {"x": float(position[0] + right), "y": float(position[1] + bottom)},
        {"x": float(position[0] + left), "y": float(position[1] + bottom)},
    ]


# Input: `rendered` mit Renderergebnis, `font_size_pct` mit effektiver Schriftgroesse.
# Output: JSON-taugliche Box-Annotation fuer Ground Truth und Preview.
# Die Funktion reduziert die Render-Metadaten auf die Felder, die im
# Run-Record als sichtbare Box-Annotation gespeichert werden.
def _build_box_annotation(
    rendered: dict[str, Any],
    *,
    font_size_pct: int,
) -> dict[str, Any]:
    return {
        "label": rendered["label"],
        "text": rendered["text"],
        "rendered_text": rendered["rendered_text"],
        "region": rendered["region"],
        "corners": rendered["corners"],
        "label_corners": rendered["label_corners"],
        "rotation_degrees": rendered["rotation_degrees"],
        "frame_index": 0,
        "font_size_pct": font_size_pct,
    }


# Ignore faint anti-alias halos and return bounds for visibly occupied mask pixels.
def _thresholded_mask_bounds(
    mask: Image.Image,
) -> tuple[int, int, int, int] | None:
    mask_array = np.asarray(mask)
    occupied_pixels = np.argwhere(mask_array >= _MASK_ALPHA_THRESHOLD)
    if occupied_pixels.size == 0:
        return None
    top = int(occupied_pixels[:, 0].min())
    bottom = int(occupied_pixels[:, 0].max()) + 1
    left = int(occupied_pixels[:, 1].min())
    right = int(occupied_pixels[:, 1].max()) + 1
    return left, top, right, bottom
