"""PDF writer that merges an injected DICOM preview onto a PDF template."""

import io
import json
from pathlib import Path

from pypdf import PdfReader
from pypdf import PdfWriter as PypdfWriter
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

from injection_pipeline.loaders.dicom import DicomLoader
from injection_pipeline.models import ImagePoint, load_run_record
from injection_pipeline.models.geometry import Quad
from injection_pipeline.pdf.geometry import image_to_pdf_point, placement_for_image
from injection_pipeline.pdf.models import (
    PdfAnnotationRecord,
    PdfCompositionArtifacts,
    PdfPageAnnotation,
    PdfPlacement,
    PdfQuad,
    PdfTemplate,
)


class PdfWriterAdapter:
    """Write merged PDF artifacts while keeping source files read-only."""

    format_id = "pdf"
    output_suffix = ".pdf"

    # Input: `template`, DICOM-/Ground-Truth-Pfade und Ausgabeparameter.
    # Output: `PdfCompositionArtifacts` mit zwei PDFs und Sidecar.
    # Die Methode laedt und validiert das DICOM, transformiert alle Bildboxen
    # und schreibt neue Dateien unter einem parameterisierten Ausgabeordner.
    def write(
        self,
        template: PdfTemplate,
        dicom_path: Path,
        annotation_path: Path,
        output_root: Path,
        slot: str = "top_left",
        page_index: int = 0,
    ) -> PdfCompositionArtifacts:
        if page_index < 0 or page_index >= template.page_count:
            raise ValueError("PDF page_index is outside the input document.")
        record = load_run_record(annotation_path)
        DicomLoader().load(dicom_path)
        preview_path = _resolve_preview_path(annotation_path, record.preview_file)
        if not preview_path.is_file():
            raise FileNotFoundError(f"Preview image does not exist: {preview_path}")

        page_size = template.page_sizes[page_index]
        placement = placement_for_image(preview_path, page_size, slot, page_index)
        annotations = []
        for index, annotation in enumerate(record.box_annotations):
            image_corners = [
                ImagePoint(x=point.x, y=point.y) for point in annotation.corners.root
            ]
            _validate_image_corners(
                image_corners,
                placement.image_width_px,
                placement.image_height_px,
            )
            pdf_corners = [
                image_to_pdf_point(point, placement) for point in image_corners
            ]
            annotations.append(
                PdfPageAnnotation(
                    source_index=index,
                    label=annotation.label,
                    text=annotation.text,
                    image_corners=Quad.model_validate(image_corners),
                    pdf_corners=PdfQuad.model_validate(pdf_corners),
                    page_index=page_index,
                )
            )

        run_id = record.run_id
        template_id = template.source_file.stem
        output_dir = output_root / "pdf" / run_id / f"{template_id}-{slot}"
        output_dir.mkdir(parents=True, exist_ok=True)
        clean_pdf = output_dir / "pdf_injected.pdf"
        annotated_pdf = output_dir / "pdf_injected_annotated.pdf"
        annotation_json = output_dir / "pdf_annotations.json"
        placement = placement.model_copy(update={"page_index": page_index})
        sidecar = PdfAnnotationRecord(
            source_pdf=template.source_file,
            source_dicom=dicom_path,
            source_dicom_annotation=annotation_path,
            source_run_id=record.run_id,
            source_seed=record.seed,
            source_schema_version=record.schema_version,
            output_pdf=clean_pdf,
            output_annotated_pdf=annotated_pdf,
            template=template,
            placement=placement,
            annotations=annotations,
        )
        _merge_overlay(template, preview_path, placement, clean_pdf, annotations=None)
        _merge_overlay(template, preview_path, placement, annotated_pdf, annotations)
        annotation_json.write_text(
            json.dumps(sidecar.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
        return PdfCompositionArtifacts(
            clean_pdf=clean_pdf,
            annotated_pdf=annotated_pdf,
            annotation_json=annotation_json,
            record=sidecar,
        )


PdfWriter = PdfWriterAdapter


# Input: `annotation_path` und im Record gespeicherter Previewpfad.
# Output: Absoluter oder relativ aufgeloester Previewpfad.
# Relative Pfade werden gegen die Ground-Truth-Datei aufgeloest.
def _resolve_preview_path(annotation_path: Path, preview_path: Path) -> Path:
    if preview_path.is_absolute():
        return preview_path
    candidates = (preview_path, annotation_path.parent / preview_path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return annotation_path.parent / preview_path


# Input: `corners` im Bildraum sowie die Bildabmessungen in Pixeln.
# Output: Keine Rueckgabe; wirft bei ungueltigen Bounds einen ValueError.
# Die Pruefung verhindert, dass PDF-Ground-Truth ausserhalb des eingebetteten
# DICOM-Bildes liegt.
def _validate_image_corners(
    corners: list[ImagePoint], width: int, height: int
) -> None:
    if any(
        point.x < 0 or point.x > width or point.y < 0 or point.y > height
        for point in corners
    ):
        raise ValueError(
            "DICOM annotation corners must lie inside the preview image."
        )


# Input: Template, Bild, Platzierung, Zielpfad und optionale PDF-Annotationen.
# Output: Keine Rueckgabe; schreibt eine neue PDF-Datei.
# Das Overlay wird mit reportlab erzeugt und anschliessend mit pypdf auf die
# Originalseiten gemergt. Alle Seiten ausser der Zielseite bleiben unveraendert.
def _merge_overlay(
    template: PdfTemplate,
    image_path: Path,
    placement: PdfPlacement,
    output_path: Path,
    annotations: list[PdfPageAnnotation] | None,
) -> None:
    pdf_placement = placement
    page_width, page_height = template.page_sizes[pdf_placement.page_index]
    overlay_bytes = io.BytesIO()
    canvas = Canvas(overlay_bytes, pagesize=(page_width, page_height), invariant=1)
    canvas.drawImage(
        ImageReader(str(image_path)),
        pdf_placement.x,
        pdf_placement.y,
        width=pdf_placement.width,
        height=pdf_placement.height,
        preserveAspectRatio=True,
        mask="auto",
    )
    if annotations is not None:
        canvas.setStrokeColorRGB(1, 0, 0)
        canvas.setLineWidth(1.5)
        for annotation in annotations:
            points = annotation.pdf_corners.root
            canvas.line(points[0].x, points[0].y, points[1].x, points[1].y)
            canvas.line(points[1].x, points[1].y, points[2].x, points[2].y)
            canvas.line(points[2].x, points[2].y, points[3].x, points[3].y)
            canvas.line(points[3].x, points[3].y, points[0].x, points[0].y)
    canvas.save()
    overlay_bytes.seek(0)
    overlay_page = PdfReader(overlay_bytes).pages[0]
    writer = PypdfWriter(clone_from=str(template.source_file))
    writer.pages[pdf_placement.page_index].merge_page(overlay_page)
    with output_path.open("wb") as handle:
        writer.write(handle)
