"""Preview helpers for rendered DICOM prototype outputs."""

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pydicom
from PIL import Image
from injection_pipeline.engine.pixel_injection import extract_preview_frame

DEFAULT_DICOM_PATH = Path(
    "DycomData/Anonymization/original_data/"
    "patient_10080695_23273240/echo/91180014_0001.dcm"
)
DEFAULT_PREVIEW_PATH = Path("prototypes/dicom/output/preview.png")


# Input: `source_path` mit DICOM- oder Bilddatei, `output_path` mit Zielpfad.
# Output: Pfad zum gespeicherten Preview-Bild.
# Die Funktion rendert optionale Annotationen und schreibt die Preview-Datei.
def create_preview(
    source_path: str | Path,
    output_path: str | Path = DEFAULT_PREVIEW_PATH,
    visible_annotations: list[dict[str, Any]] | None = None,
    title: str | None = None,
    show: bool = False,
) -> Path:
    frame, default_title = _load_preview_source(source_path)

    cmap = "gray" if frame.ndim == 2 else None
    plt.imshow(frame, cmap=cmap)
    if visible_annotations:
        _draw_annotation_outlines(plt.gca(), visible_annotations)

    plt.title(title or default_title)
    plt.axis("off")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(destination, dpi=150, bbox_inches="tight")
    if show:
        plt.show()
    plt.close()
    return destination


# Outline visible annotations on an existing DICOM preview artifact.
def preview_with_annotations(
    source_path: str | Path,
    visible_annotations: list[dict[str, Any]],
    output_path: str | Path = DEFAULT_PREVIEW_PATH,
    title: str | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    frame, default_title = _load_preview_source(source_path)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(8, 8))
    cmap = "gray" if frame.ndim == 2 else None
    axis.imshow(frame, cmap=cmap)
    _draw_annotation_outlines(axis, visible_annotations)
    axis.set_title(title or default_title)
    axis.axis("off")
    figure.savefig(destination, dpi=150, bbox_inches="tight")
    plt.close(figure)

    return destination, visible_annotations


# Input: `path` mit Pfad zu einer JSON-Datei.
# Output: Liste von sichtbaren Annotationen.
# Die Funktion liest Preview-Annotationen fuer die CLI und bricht ab, wenn die
# Datei keinen JSON-Listenwert enthaelt.
def _load_annotations_json(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Visible annotation file must contain a JSON list.")
    return payload


# Draw the main PII bounding boxes in red.
def _draw_red_bounding_boxes(axis: Any, annotations: list[dict[str, Any]]) -> None:
    for annotation in annotations:
        _draw_box(axis, annotation.get("corners"), color="red", linewidth=1.0)


# Draw optional generic-prefix bounding boxes in blue.
def _draw_label_bounding_boxes(axis: Any, annotations: list[dict[str, Any]]) -> None:
    for annotation in annotations:
        _draw_box(axis, annotation.get("label_corners"), color="blue", linewidth=1.0)


# Input: `source_path` mit injizierter Datei, `box_annotations` mit Box-Geometrien.
# Output: Pfad zum gespeicherten annotierten Preview-Bild.
# Die Funktion zeichnet PII-Boxen und optional generische Label-Boxen.
def create_annotated_preview(
    source_path: str | Path,
    box_annotations: list[dict[str, Any]],
    output_path: str | Path,
    title: str | None = None,
    show_label_boxes: bool = False,
) -> Path:
    frame, default_title = _load_preview_source(source_path)

    figure, axis = plt.subplots(figsize=(8, 8))
    cmap = "gray" if frame.ndim == 2 else None
    axis.imshow(frame, cmap=cmap)
    _draw_red_bounding_boxes(axis, box_annotations)
    if show_label_boxes:
        _draw_label_bounding_boxes(axis, box_annotations)
    axis.set_title(title or default_title)
    axis.axis("off")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return destination


# Input: `axis` mit Matplotlib-Achse, `annotations` mit Box-Geometrien.
# Output: Keine Rueckgabe.
# Die Funktion zeichnet alle sichtbaren Annotationen als gruene Umrisse in die
# uebergebene Achse.
def _draw_annotation_outlines(axis: Any, annotations: list[dict[str, Any]]) -> None:
    for annotation in annotations:
        _draw_box(axis, annotation.get("corners"), color="lime", linewidth=1.5)


# Input: `axis` mit Matplotlib-Achse, `corners` mit vier Eckpunkten.
# Output: Keine Rueckgabe.
# Die Funktion zeichnet eine geschlossene Box und ignoriert unvollstaendige
# oder nicht listenfoermige Geometrien als Fallback.
def _draw_box(
    axis: Any,
    corners: Any,
    *,
    color: str,
    linewidth: float,
) -> None:
    if not isinstance(corners, list) or len(corners) != 4:
        return
    x_values = [float(corner["x"]) for corner in corners]
    y_values = [float(corner["y"]) for corner in corners]
    x_values.append(x_values[0])
    y_values.append(y_values[0])
    axis.plot(x_values, y_values, color=color, linewidth=linewidth)


# Input: `source_path` mit Pfad zu DICOM- oder Bilddatei.
# Output: Preview-Frame und Standardtitel.
# Die Funktion laedt DICOM-Pixel ueber pydicom oder Rasterbilder ueber PIL und
# normalisiert die Ausgabe fuer die Preview-Erzeugung.
def _load_preview_source(source_path: str | Path) -> tuple[Any, str]:
    source = Path(source_path)
    if source.suffix.lower() == ".dcm":
        ds = pydicom.dcmread(str(source))
        title = str(getattr(ds, "PatientName", "DICOM Preview"))
        return extract_preview_frame(ds), title
    image = Image.open(source).convert("RGB")
    return np.asarray(image), source.name


# CLI entry point for standardized DICOM preview export.
def main() -> None:
    parser = argparse.ArgumentParser(description="Create a DICOM preview image.")
    parser.add_argument("--dicom", type=str, default=str(DEFAULT_DICOM_PATH))
    parser.add_argument("--output", type=str, default=str(DEFAULT_PREVIEW_PATH))
    parser.add_argument("--annotations-json", type=str, default=None)
    parser.add_argument("--title", type=str, default=None)
    parser.add_argument("--no-show", action="store_true", default=False)
    args = parser.parse_args()

    annotations = (
        _load_annotations_json(args.annotations_json)
        if args.annotations_json is not None
        else None
    )
    create_preview(
        source_path=args.dicom,
        output_path=args.output,
        visible_annotations=annotations,
        title=args.title,
        show=not args.no_show,
    )


if __name__ == "__main__":
    main()
