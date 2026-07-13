"""Thin pixel-engine facade for the runner stage boundary."""

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from injection_pipeline.engine.pixel_injection import (
    _inject_visible_text_into_frame,
    inject_visible_text,
    inject_visible_text_into_image,
)
from injection_pipeline.models.adapters import SourceDocument

_FRAME_RENDERER_NAMES = {
    "dcm": "pixel_injection.inject_visible_text",
    "jpg": "pixel_injection.inject_visible_text_into_image",
}


# Input: `result` aus dem Pixelrenderer und dessen oeffentlicher Renderername.
# Output: Normalisiertes Resultat fuer Ground Truth und Preview-Erzeugung.
# Die Funktion bewahrt die bisherigen Schluessel und Renderer-Namen bytegleich.
def normalize_pixel_result(
    result: dict[str, Any],
    renderer_name: str,
) -> dict[str, Any]:
    return {
        "status": result.get("status", "rendered"),
        "renderer_name": renderer_name,
        "box_annotations": result.get("box_annotations", []),
        "preview_file": result.get("preview_file"),
        "render_metadata": result.get("render_metadata", {}),
    }


# Input: `document` mit Adapter-Frame, sichtbarer Renderplan und Renderoptionen.
# Output: Gerenderter Frame und normalisiertes Pixel-Resultat.
# Die Funktion nutzt den gemeinsamen Frame-Renderer und bewahrt die bisherigen
# Renderer-Namen fuer DICOM- und JPG-Run-Records.
def run_document_pixel_injection(
    *,
    document: SourceDocument,
    visible_injections: list[dict[str, Any]],
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    font_size_pct: int,
    placement_mode: str,
    font_family: str,
    text_background: str | None,
) -> tuple[np.ndarray, dict[str, Any]]:
    result = _inject_visible_text_into_frame(
        frame=np.asarray(document.frame),
        visible_injections=visible_injections,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
        frame_count=document.frame_count,
    )
    renderer_name = _FRAME_RENDERER_NAMES.get(
        document.format_id,
        "pixel_injection._inject_visible_text_into_frame",
    )
    return np.asarray(result["output_array"]), normalize_pixel_result(
        result,
        renderer_name,
    )


# Input: `ds` mit DICOM-Dataset, sichtbarer Renderplan und Ausgabeparameter.
# Output: Mutiertes Dataset und normalisiertes Pixel-Resultat.
# Die Funktion delegiert an den DICOM-Pixelrenderer und vereinheitlicht dessen
# Rueckgabe fuer den Orchestrator.
def run_dicom_pixel_injection(
    *,
    ds: Any,
    visible_injections: list[dict[str, Any]],
    output_path: Path,
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    example_type: str,
    font_size_pct: int,
    placement_mode: str,
    font_family: str,
    text_background: str | None,
) -> tuple[Any, dict[str, Any]]:
    result = inject_visible_text(
        ds=ds,
        visible_injections=visible_injections,
        output_path=output_path,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        example_type=example_type,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
    )
    return result.get("dataset", ds), normalize_pixel_result(
        result,
        "pixel_injection.inject_visible_text",
    )


# Input: `image` mit Rasterbild, sichtbarer Renderplan und Renderoptionen.
# Output: Gerendertes Bild und normalisiertes Pixel-Resultat.
# Die Funktion nutzt denselben sichtbaren Renderer fuer JPG-Eingaben und
# vereinheitlicht dessen Rueckgabe fuer den Orchestrator.
def run_jpg_pixel_injection(
    *,
    image: Image.Image,
    visible_injections: list[dict[str, Any]],
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    font_size_pct: int,
    placement_mode: str,
    font_family: str,
    text_background: str | None,
) -> tuple[Image.Image, dict[str, Any]]:
    result = inject_visible_text_into_image(
        image=image,
        visible_injections=visible_injections,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
    )
    return result["image"], normalize_pixel_result(
        result,
        "pixel_injection.inject_visible_text_into_image",
    )
