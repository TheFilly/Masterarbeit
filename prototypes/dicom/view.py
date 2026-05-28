"""Preview helpers for rendered DICOM prototype outputs."""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
import pydicom
from PIL import Image

from pixel_injection import extract_preview_frame


DEFAULT_DICOM_PATH = Path(
    "DycomData/Anonymization/original_data/"
    "patient_10080695_23273240/echo/91180014_0001.dcm"
)
DEFAULT_PREVIEW_PATH = Path("prototypes/dicom/output/preview.png")


def create_preview(
    source_path: Union[str, Path],
    output_path: Union[str, Path] = DEFAULT_PREVIEW_PATH,
    visible_annotations: Optional[List[Dict[str, Any]]] = None,
    title: Optional[str] = None,
    show: bool = False,
) -> Path:
    """Render and save a standardized preview for a prototype DICOM file.

    Args:
        dicom_path: Path to the DICOM file.
        output_path: Destination for the preview image.
        visible_annotations: Optional box annotations to outline on the preview.
        title: Optional preview title. Defaults to PatientName if available.

    Returns:
        Saved preview image path.
    """
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


def preview_with_annotations(
    source_path: Union[str, Path],
    visible_annotations: List[Dict[str, Any]],
    output_path: Union[str, Path] = DEFAULT_PREVIEW_PATH,
    title: Optional[str] = None,
) -> Tuple[Path, List[Dict[str, Any]]]:
    """Outline visible annotations on an existing DICOM preview artifact."""
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


def _load_annotations_json(path: Union[str, Path]) -> List[Dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Visible annotation file must contain a JSON list.")
    return payload


def _draw_red_bounding_boxes(axis: Any, annotations: List[Dict[str, Any]]) -> None:
    """Draw the main PII bounding boxes in red."""
    for annotation in annotations:
        _draw_box(axis, annotation.get("corners"), color="red", linewidth=1.0)


def _draw_label_bounding_boxes(axis: Any, annotations: List[Dict[str, Any]]) -> None:
    """Draw optional generic-prefix bounding boxes in blue."""
    for annotation in annotations:
        _draw_box(axis, annotation.get("label_corners"), color="blue", linewidth=1.0)


def create_annotated_preview(
    source_path: Union[str, Path],
    box_annotations: List[Dict[str, Any]],
    output_path: Union[str, Path],
    title: Optional[str] = None,
    show_label_boxes: bool = False,
) -> Path:
    """Render and save a preview with red bounding boxes around injected text.

    Args:
        source_path: Path to the injected DICOM or JPG file.
        box_annotations: Box annotations with ``corners`` geometry.
        output_path: Destination for the annotated preview image.
        title: Optional title. Defaults to PatientName if available.
        show_label_boxes: Whether generic label-prefix boxes should be shown.

    Returns:
        Saved preview image path.
    """
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


def _draw_annotation_outlines(axis: Any, annotations: List[Dict[str, Any]]) -> None:
    for annotation in annotations:
        _draw_box(axis, annotation.get("corners"), color="lime", linewidth=1.5)


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


def _load_preview_source(source_path: Union[str, Path]) -> tuple[Any, str]:
    source = Path(source_path)
    if source.suffix.lower() == ".dcm":
        ds = pydicom.dcmread(str(source))
        return extract_preview_frame(ds), str(getattr(ds, "PatientName", "DICOM Preview"))
    image = Image.open(source).convert("RGB")
    return np.asarray(image), source.name


def main() -> None:
    """CLI entry point for standardized DICOM preview export."""
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
