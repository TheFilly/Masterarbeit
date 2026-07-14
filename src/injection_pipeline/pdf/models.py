"""Pydantic models for PDF placement and annotation sidecars."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, RootModel, field_validator

from injection_pipeline.models.geometry import PdfPoint, Quad


class PdfQuad(RootModel[list[PdfPoint]]):
    """Four ordered points in PDF page coordinates."""

    @field_validator("root")
    @classmethod
    # Input: `value` mit vier PDF-Punkten.
    # Output: Unveraenderte Punktliste oder Validierungsfehler.
    # Die Funktion stellt die feste Polygon-Arity des PDF-Sidecars sicher.
    def _validate_arity(cls, value: list[PdfPoint]) -> list[PdfPoint]:
        return cls.validate_quad(value)

    @classmethod
    # Input: `value` mit PDF-Punkten.
    # Output: Unveraenderte Punktliste oder Validierungsfehler.
    # Die Funktion kapselt die Arity-Pruefung fuer direkte Modellaufrufe.
    def validate_quad(cls, value: list[PdfPoint]) -> list[PdfPoint]:
        if len(value) != 4:
            raise ValueError("A PDF quad must contain exactly four points.")
        return value


class PdfTemplate(BaseModel):
    """Loaded PDF template metadata used by the writer."""

    model_config = ConfigDict(extra="forbid")

    source_file: Path
    page_count: int
    page_sizes: list[tuple[float, float]]


class PdfPlacement(BaseModel):
    """Actual image rectangle in PDF points after aspect-fit placement."""

    model_config = ConfigDict(extra="forbid")

    page_index: int
    slot: str
    x: float
    y: float
    width: float
    height: float
    scale: float
    image_width_px: int
    image_height_px: int


class PdfPageAnnotation(BaseModel):
    """One source image annotation transformed into PDF coordinates."""

    model_config = ConfigDict(extra="forbid")

    source_index: int
    label: str
    text: str
    image_corners: Quad
    pdf_corners: PdfQuad
    page_index: int


class PdfAnnotationRecord(BaseModel):
    """Machine-readable ground truth for one PDF injection."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.3.0-pdf-prototype"
    record_type: str = "pdf_injection_run"
    source_pdf: Path
    source_dicom: Path
    source_dicom_annotation: Path
    source_run_id: str
    source_seed: int
    source_schema_version: str
    output_pdf: Path
    output_annotated_pdf: Path
    template: PdfTemplate
    placement: PdfPlacement
    annotations: list[PdfPageAnnotation]


class PdfCompositionArtifacts(BaseModel):
    """Paths and sidecar record emitted by the PDF writer."""

    model_config = ConfigDict(extra="forbid")

    clean_pdf: Path
    annotated_pdf: Path
    annotation_json: Path
    record: PdfAnnotationRecord
