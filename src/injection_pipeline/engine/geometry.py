"""Geometry helpers for rotated pixel-injection annotations."""

import math
from typing import Any

import numpy as np
from PIL import Image

# Conservative prototype-only angle set. This keeps annotation geometry easy to
# validate while still exercising rotated overlays.
ALLOWED_ROTATIONS_DEGREES: tuple[int, ...] = (0, 20, 90, 180, 270)
_MASK_ALPHA_THRESHOLD: int = 8


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


# Input: `mask` mit Alpha- oder Graustufenwerten, `mask_name` fuer Fehlertexte.
# Output: Sichtbare Masken-Bounds.
# Die Funktion bricht mit ValueError ab, wenn die Maske keine sichtbaren Pixel
# oberhalb des Prototyp-Schwellwerts enthaelt.
def _require_mask_bounds(
    mask: Image.Image,
    mask_name: str,
) -> tuple[int, int, int, int]:
    bounds = _thresholded_mask_bounds(mask)
    if bounds is None:
        raise ValueError(f"{mask_name} is empty.")
    return bounds


# Input: Optionale Masken-Bounds.
# Output: JSON-taugliches Bounds-Dict oder None.
# Die Funktion ergaenzt Breite und Hoehe aus den exklusiven rechten und unteren
# Grenzen.
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


# Input: `position` als Zieloffset und lokale Masken-Bounds.
# Output: Absolute Rechteck-Ecken oder None.
# Die Funktion projiziert bereits rotierte Masken-Bounds in Bildkoordinaten.
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


# Input: `mask` mit Alpha- oder Graustufenwerten.
# Output: Enge Bounds fuer sichtbare Pixel oder None.
# Die Funktion ignoriert schwache Antialias-Saeume unterhalb des festen
# Prototyp-Schwellwerts.
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
