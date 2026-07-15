"""Deterministic overlay placement for pixel injection."""

import random
from typing import Any

import numpy as np

from injection_pipeline.engine.fonts import _DEFAULT_FONT_SIZE_PX, load_default_font
from injection_pipeline.engine.handwriting import _prepare_handwriting_asset_overlay
from injection_pipeline.engine.overlay import _prepare_annotation_overlay
from injection_pipeline.engine.prepared_overlay import (
    PreparedOverlay,
    with_prepared_overlay,
)

_VALID_PLACEMENT_MODES: tuple[str, ...] = ("free", "corners")
_HANDWRITING_FONT_FAMILY = "handwriting"


# Input: sichtbare Injektionen, Preview-Frame und Renderkonfiguration.
# Output: Injektionen mit finalen Pixelpositionen und internem Prepared-Overlay.
# Die Platzierung basiert auf derselben maskenbasierten Overlay-Geometrie wie die
# spaetere Annotation, damit keine Offsets zur Ground Truth entstehen. Fonts
# werden nur fuer Font-Renderer geladen; reine Handschriftlaeufe umgehen den
# Fontpfad vollstaendig.
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
    font: Any | None = None

    prepared_overlays: list[PreparedOverlay] = []
    sizes: list[tuple[int, int]] = []
    for injection in visible_injections:
        if injection.get("renderer_type") != "handwriting_asset" and font is None:
            if font_family == _HANDWRITING_FONT_FAMILY:
                raise ValueError(
                    "font_family='handwriting' requires handwriting assets for "
                    "all visible annotations."
                )
            font = load_default_font(
                font_family=font_family,
                font_size_px=font_size_px,
            )
        overlay = _prepare_overlay_for_placement(
            {**injection, "padding": padding, "stroke_width": 1},
            font=font,
            font_family=font_family,
            text_background=text_background,
        )
        prepared_overlays.append(overlay)
        sizes.append(overlay["rotated_size"])

    positioned_annotations: list[dict[str, Any]] = []

    if placement_mode == "corners":
        corner = rng.choice(["top_left", "top_right", "bottom_left", "bottom_right"])

        if corner in ("bottom_left", "bottom_right"):
            total_height = sum(rot_h for _, rot_h in sizes) + vertical_gap * max(
                0, len(sizes) - 1
            )
            current_y = max(v_margin, image_height - v_margin - total_height)
        else:
            current_y = v_margin

        for injection, (rot_w, rot_h), overlay in zip(
            visible_injections,
            sizes,
            prepared_overlays,
            strict=True,
        ):
            if corner in ("top_right", "bottom_right"):
                x = max(h_margin, image_width - h_margin - rot_w)
            else:
                x = h_margin
            positioned_annotations.append(
                with_prepared_overlay(
                    {
                        **injection,
                        "position": (x, current_y),
                        "region": corner,
                        "padding": padding,
                        "stroke_width": 1,
                    },
                    overlay,
                )
            )
            current_y += rot_h + vertical_gap

    elif placement_mode == "free":
        for injection, (rot_w, rot_h), overlay in zip(
            visible_injections,
            sizes,
            prepared_overlays,
            strict=True,
        ):
            x_max = max(h_margin, image_width - rot_w - h_margin)
            y_max = max(v_margin, image_height - rot_h - v_margin)
            x = rng.randint(h_margin, x_max)
            y = rng.randint(v_margin, y_max)
            positioned_annotations.append(
                with_prepared_overlay(
                    {
                        **injection,
                        "position": (x, y),
                        "region": "free",
                        "padding": padding,
                        "stroke_width": 1,
                    },
                    overlay,
                )
            )

    return positioned_annotations


# Input: `annotation` mit Renderer-Typ und Font-Konfiguration.
# Output: Typisiertes vorbereitetes Overlay mit `rotated_size`.
# Die Funktion waehlt den Font- oder Handschrift-Renderer fuer die Messung aus,
# ohne dass `overlay` das Handschriftmodul importieren muss.
def _prepare_overlay_for_placement(
    annotation: dict[str, Any],
    *,
    font: Any | None,
    font_family: str,
    text_background: str | None,
) -> PreparedOverlay:
    if annotation.get("renderer_type") == "handwriting_asset":
        return _prepare_handwriting_asset_overlay(annotation)
    if font is None:
        raise ValueError("Font renderer placement requires a loaded font.")
    return _prepare_annotation_overlay(
        annotation,
        font,
        font_family=font_family,
        text_background=text_background,
    )
