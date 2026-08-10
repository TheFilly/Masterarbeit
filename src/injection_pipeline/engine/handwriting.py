"""Handwriting-asset rendering for pixel injection."""

from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from injection_pipeline.engine.geometry import (
    _MASK_ALPHA_THRESHOLD,
    _coerce_position,
    _require_mask_bounds,
    _rotated_corners,
    _serialize_mask_bounds,
    _thresholded_mask_bounds,
    _validate_rotation,
)
from injection_pipeline.engine.prepared_overlay import PreparedOverlay
from injection_pipeline.engine.segments import (
    _normalize_text_segments,
    _split_segment_text,
)

_SOURCE_BOUNDS_KEY = Literal[
    "text_source_bounds",
    "pii_source_bounds",
    "label_source_bounds",
    "suffix_source_bounds",
]

HANDWRITING_INK_COLOR_CHOICES: tuple[str, ...] = (
    "auto",
    "black",
    "gray",
    "white",
)
HANDWRITING_CONTRAST_MODE_CHOICES: tuple[str, ...] = ("none", "halo")
_HANDWRITING_INK_RGB: dict[str, tuple[int, int, int]] = {
    "black": (20, 20, 20),
    "gray": (110, 110, 110),
    "white": (255, 255, 255),
}
_AUTO_LUMINANCE_THRESHOLD = 128.0
_MIN_AUTO_CONTRAST = 64.0
_MAX_AUTO_LUMINANCE_SPREAD = 96.0
_MIN_LUMINANCE_SAMPLES = 8
_HALO_RADIUS = 2


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
    handwriting_ink_color: str = "auto",
    handwriting_contrast_mode: str = "none",
    sampling_image: Image.Image | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    position = _coerce_position(annotation["position"])
    overlay = (
        prepared_overlay
        if prepared_overlay is not None
        else _prepare_handwriting_asset_overlay(annotation)
    )
    appearance = _resolve_handwriting_appearance(
        base_image if sampling_image is None else sampling_image,
        overlay,
        position,
        requested_ink_color=handwriting_ink_color,
        requested_contrast_mode=handwriting_contrast_mode,
    )
    composed = base_image.convert("RGBA")
    composed.alpha_composite(appearance["layer"], dest=position)

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
        "corners": _rotated_mask_corners(position, overlay, "pii_source_bounds"),
        "label_corners": _optional_mask_corners(
            position,
            overlay,
            "label_source_bounds",
        ),
        "prefix_corners": _optional_mask_corners(
            position,
            overlay,
            "label_source_bounds",
        ),
        "suffix_corners": _optional_mask_corners(
            position,
            overlay,
            "suffix_source_bounds",
        ),
        "render_metadata": {
            "position": {"x": position[0], "y": position[1]},
            **overlay["render_metadata"],
            "ink_color": appearance["selected_ink_color"],
            "background_mode": "transparent",
            "selected_ink_color": appearance["selected_ink_color"],
            "contrast_mode": appearance["contrast_mode"],
            "sampled_luminance": appearance["sampled_luminance"],
            "luminance_spread": appearance["luminance_spread"],
            "contrast_decision_reason": appearance["decision_reason"],
            "rendered_text_corners": _rotated_mask_corners(
                position, overlay, "text_source_bounds"
            ),
        },
    }
    return composed.convert("RGB"), record


# Input: `base_image`, vorbereitetes Handschrift-Overlay, Position und
# Darstellungsoptionen.
# Output: RGBA-Layer und reproduzierbare Kontrastentscheidung.
# Die Funktion analysiert nur Bildpixel unter der tatsächlichen Ink-Maske und
# erzeugt Farbe sowie Halo erst im finalen Renderpass.
def _resolve_handwriting_appearance(
    base_image: Image.Image,
    overlay: PreparedOverlay,
    position: tuple[int, int],
    *,
    requested_ink_color: str,
    requested_contrast_mode: str,
) -> dict[str, Any]:
    _validate_handwriting_appearance_options(
        requested_ink_color,
        requested_contrast_mode,
    )
    sampled_luminance, luminance_spread = _sample_background_luminance(
        base_image,
        overlay["rotated_mask"],
        position,
    )

    if requested_ink_color == "auto":
        if sampled_luminance is None:
            selected_ink_color = "white"
            decision_reason = "auto_insufficient_samples_fallback"
        else:
            selected_ink_color = (
                "white"
                if sampled_luminance < _AUTO_LUMINANCE_THRESHOLD
                else "black"
            )
            decision_reason = "auto_median_luminance"
    else:
        selected_ink_color = requested_ink_color
        decision_reason = "manual_override"

    auto_uncertain = _auto_contrast_is_uncertain(
        selected_ink_color,
        sampled_luminance,
        luminance_spread,
    )
    use_halo = requested_contrast_mode == "halo" or (
        requested_ink_color == "auto" and auto_uncertain
    )
    if use_halo and requested_ink_color == "auto" and auto_uncertain:
        decision_reason = f"{decision_reason}_halo_fallback"

    layer = _compose_handwriting_layer(
        overlay["rotated_mask"],
        selected_ink_color,
        use_halo,
    )
    return {
        "layer": layer,
        "selected_ink_color": selected_ink_color,
        "contrast_mode": "halo" if use_halo else "none",
        "sampled_luminance": sampled_luminance,
        "luminance_spread": luminance_spread,
        "decision_reason": decision_reason,
    }


# Input: angeforderte Handschriftfarbe und Kontrastmodus.
# Output: Keine Rueckgabe.
# Die Funktion validiert die neuen Renderoptionen zentral, damit CLI, API und
# direkte Engine-Aufrufe denselben Vertrag verwenden.
def _validate_handwriting_appearance_options(
    requested_ink_color: str,
    requested_contrast_mode: str,
) -> None:
    if requested_ink_color not in HANDWRITING_INK_COLOR_CHOICES:
        raise ValueError(
            "handwriting_ink_color must be one of "
            f"{HANDWRITING_INK_COLOR_CHOICES}, got {requested_ink_color!r}."
        )
    if requested_contrast_mode not in HANDWRITING_CONTRAST_MODE_CHOICES:
        raise ValueError(
            "handwriting_contrast_mode must be one of "
            f"{HANDWRITING_CONTRAST_MODE_CHOICES}, got "
            f"{requested_contrast_mode!r}."
        )


# Input: RGB-Bild, rotiertes Ink-Maske und Overlay-Position.
# Output: Median-Luminanz und p10-p90-Luminanzspread oder zweimal `None`.
# Die Stichprobe bleibt auf sichtbare Overlaypixel beschränkt und ignoriert
# außerhalb des Bildes liegende Bereiche.
def _sample_background_luminance(
    base_image: Image.Image,
    rotated_mask: Image.Image,
    position: tuple[int, int],
) -> tuple[float | None, float | None]:
    image = np.asarray(base_image.convert("RGB"), dtype=np.float32)
    mask = np.asarray(rotated_mask, dtype=np.uint8)
    image_width, image_height = base_image.size
    x, y = position
    left = max(0, x)
    top = max(0, y)
    right = min(image_width, x + rotated_mask.width)
    bottom = min(image_height, y + rotated_mask.height)
    if left >= right or top >= bottom:
        return None, None

    mask_left = left - x
    mask_top = top - y
    mask_right = mask_left + (right - left)
    mask_bottom = mask_top + (bottom - top)
    sample_mask = mask[mask_top:mask_bottom, mask_left:mask_right]
    valid = sample_mask > _MASK_ALPHA_THRESHOLD
    if int(valid.sum()) < _MIN_LUMINANCE_SAMPLES:
        return None, None

    sample_image = image[top:bottom, left:right]
    luminance = (
        0.2126 * sample_image[:, :, 0]
        + 0.7152 * sample_image[:, :, 1]
        + 0.0722 * sample_image[:, :, 2]
    )
    values = luminance[valid]
    spread = np.percentile(values, 90) - np.percentile(values, 10)
    return float(np.median(values)), float(spread)


# Input: gewählte Ink-Farbe und lokale Luminanzstatistik.
# Output: `True`, wenn automatische Kontrastverstärkung notwendig ist.
# Die Entscheidung nutzt einen Mindestkontrast und erkennt heterogene
# Hintergrundbereiche über den robusten p10-p90-Spread.
def _auto_contrast_is_uncertain(
    selected_ink_color: str,
    sampled_luminance: float | None,
    luminance_spread: float | None,
) -> bool:
    if sampled_luminance is None or luminance_spread is None:
        return True
    if luminance_spread > _MAX_AUTO_LUMINANCE_SPREAD:
        return True
    ink_luminance = float(np.mean(_HANDWRITING_INK_RGB[selected_ink_color]))
    contrast = (
        255.0 - sampled_luminance
        if selected_ink_color == "white"
        else sampled_luminance - ink_luminance
    )
    return contrast < _MIN_AUTO_CONTRAST


# Input: rotierte Ink-Maske, Zielfarbe und Halo-Schalter.
# Output: RGBA-Handschrift-Layer mit transparentem Hintergrund.
# Der Halo wird aus einer dilatierten Kopie der Ink-Maske erzeugt; die originale
# Maske bleibt unverändert und wird weiterhin für Ground Truth verwendet.
def _compose_handwriting_layer(
    rotated_mask: Image.Image,
    ink_color: str,
    use_halo: bool,
) -> Image.Image:
    ink_rgb = _HANDWRITING_INK_RGB[ink_color]
    layer = Image.new("RGBA", rotated_mask.size, (0, 0, 0, 0))
    if use_halo:
        halo_color = (0, 0, 0) if ink_color == "white" else (255, 255, 255)
        halo_mask = rotated_mask.filter(ImageFilter.MaxFilter(2 * _HALO_RADIUS + 1))
        halo_layer = Image.new("RGBA", rotated_mask.size, halo_color + (0,))
        halo_layer.putalpha(halo_mask)
        layer.alpha_composite(halo_layer)
    ink_layer = Image.new("RGBA", rotated_mask.size, ink_rgb + (0,))
    ink_layer.putalpha(rotated_mask)
    layer.alpha_composite(ink_layer)
    return layer


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
    text_segments = _handwriting_text_segments(annotation, asset, text)
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
        "rotated_layer": _compose_handwriting_layer(rotated_mask, "black", False),
        "rotated_mask": rotated_mask,
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


# Input: `annotation`, Manifest-`asset` und gerenderter Asset-Text.
# Output: Textsegmente, die den tatsaechlich gerenderten Asset-Text rekonstruieren.
# Die Funktion erlaubt ScrabbleGAN-Normalisierung wie `^` zu Leerzeichen, ohne
# Prefix-/PII-Segmente fuer unveraenderte Assets zu verlieren.
def _handwriting_text_segments(
    annotation: dict[str, Any],
    asset: dict[str, Any],
    rendered_text: str,
) -> list[dict[str, str]]:
    try:
        return _normalize_text_segments(annotation, rendered_text)
    except ValueError:
        source_text = asset.get("source_text")
        if source_text == annotation.get("text") and rendered_text != source_text:
            return [{"kind": "pii", "text": rendered_text}]
        raise


# Input: `position`, Overlay-Metadaten und Name der Quellmasken-Bounds.
# Output: Absolute Ecken oder `None`.
# Die Funktion transformiert die engen Bounds der unrotierten Ink-Maske in ein
# rotiertes Quad. Leere Prefix-/Suffix-Segmente bleiben `None`.
def _optional_mask_corners(
    position: tuple[int, int],
    overlay: PreparedOverlay,
    bounds_key: _SOURCE_BOUNDS_KEY,
) -> list[dict[str, float]] | None:
    bounds = overlay[bounds_key]
    if bounds is None:
        return None
    return _rotated_mask_corners(position, overlay, bounds_key)


# Input: `position`, Overlay-Metadaten und Quellmasken-Bounds.
# Output: Vier absolute, rotationskongruente Ecken oder `None`.
# Die Funktion verwendet die enge Bounds-Box der unrotierten Ink-Maske und
# transformiert sie mit exakt derselben Rotation wie das gerenderte Overlay.
def _rotated_mask_corners(
    position: tuple[int, int],
    overlay: PreparedOverlay,
    bounds_key: _SOURCE_BOUNDS_KEY,
) -> list[dict[str, float]] | None:
    bounds = overlay[bounds_key]
    if bounds is None:
        return None
    return _rotated_corners(
        position,
        overlay["text_box_size"],
        overlay["rotated_size"],
        overlay["rotation_degrees"],
        bounds=bounds,
    )


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
