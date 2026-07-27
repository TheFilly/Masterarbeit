"""Pydantic models for PDF placement and annotation sidecars."""

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    field_validator,
    model_validator,
)

from injection_pipeline.models.annotations import BoxAnnotation
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


class PdfMakeTextInput(BaseModel):
    """One text requested for direct placement in a composed PDF."""

    model_config = ConfigDict(extra="forbid")

    category: str
    value: str
    prefix: str
    suffix: str
    handwritten: StrictBool


class PdfMakeImageAnnotationInput(BaseModel):
    """One existing image-space annotation for an already injected image."""

    model_config = ConfigDict(extra="forbid")

    category: str
    value: str
    prefix: str
    suffix: str
    rendered_text: str
    image_corners: Quad
    prefix_corners: Quad | None = None
    suffix_corners: Quad | None = None

    @model_validator(mode="before")
    @classmethod
    # Input: Neues Annotation-Mapping oder bestehende `BoxAnnotation`-Daten.
    # Output: Auf den make_pdf-Eingabevertrag normalisierte Annotation.
    # Die Funktion akzeptiert alte Ground-Truth-Schluessel wie `label`, `text`
    # und `corners`, entfernt nur bekannte Legacy-Felder und laesst neue Extras
    # verboten.
    def _normalize_legacy_annotation(cls, data: object) -> object:
        if isinstance(data, cls):
            return data
        if isinstance(data, BoxAnnotation):
            data = data.model_dump()
        if not isinstance(data, Mapping):
            return data

        normalized = dict(data)
        if ("category" not in normalized or normalized["category"] is None) and (
            label := normalized.get("label")
        ) is not None:
            normalized["category"] = label
        if "value" not in normalized and "text" in normalized:
            normalized["value"] = normalized["text"]
        if "image_corners" not in normalized and "corners" in normalized:
            normalized["image_corners"] = normalized["corners"]
        if normalized.get("prefix") is None:
            normalized["prefix"] = ""
        if normalized.get("suffix") is None:
            normalized["suffix"] = ""
        if normalized.get("prefix_corners") is None and "label_corners" in normalized:
            normalized["prefix_corners"] = normalized["label_corners"]

        rendered_text = normalized.get("rendered_text")
        value = normalized.get("value")
        prefix = normalized.get("prefix")
        suffix = normalized.get("suffix")
        if rendered_text is None:
            if (
                isinstance(prefix, str)
                and isinstance(value, str)
                and isinstance(suffix, str)
            ):
                normalized["rendered_text"] = prefix + value + suffix
        elif (
            isinstance(rendered_text, str)
            and isinstance(value, str)
            and normalized.get("prefix") == ""
            and normalized.get("suffix") == ""
            and value in rendered_text
        ):
            prefix_text, _, suffix_text = rendered_text.partition(value)
            normalized["prefix"] = prefix_text
            normalized["suffix"] = suffix_text

        for legacy_key in (
            "label",
            "text",
            "corners",
            "label_corners",
            "region",
            "rotation_degrees",
            "frame_index",
            "font_size_pct",
            "rendered_text_corners",
        ):
            normalized.pop(legacy_key, None)
        return normalized


class PdfMakeImageInput(BaseModel):
    """One already injected image and its image-space annotations."""

    model_config = ConfigDict(extra="forbid")

    path: Path
    annotations: list[PdfMakeImageAnnotationInput]


class PdfMakeLayoutPlacement(BaseModel):
    """Final page-space placement for one composed make_pdf item."""

    model_config = ConfigDict(extra="forbid")

    item_type: Literal["image", "text"]
    source_index: int = Field(ge=0)
    page_index: int = Field(ge=0)
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    rotation_degrees: float
    arrangement: Literal["beside", "stacked"] | None = None


class PdfMakeLayoutDecision(BaseModel):
    """Recorded deterministic layout decision for one placed item."""

    model_config = ConfigDict(extra="forbid")

    placement: PdfMakeLayoutPlacement
    page_size: tuple[float, float]
    occupied_corners: PdfQuad


class PdfMakeOutputFiles(BaseModel):
    """All files emitted by one make_pdf composition run."""

    model_config = ConfigDict(extra="forbid")

    clean_pdf: Path
    annotated_pdf: Path
    annotation_json: Path


class PdfMakeImageAnnotation(BaseModel):
    """One image annotation transformed from image space into PDF space."""

    model_config = ConfigDict(extra="forbid")

    source_image_index: int = Field(ge=0)
    source_annotation_index: int = Field(ge=0)
    category: str
    value: str
    prefix: str
    suffix: str
    rendered_text: str
    image_corners: Quad
    pdf_corners: PdfQuad
    prefix_corners: Quad | None = None
    prefix_pdf_corners: PdfQuad | None = None
    suffix_corners: Quad | None = None
    suffix_pdf_corners: PdfQuad | None = None
    placement: PdfMakeLayoutPlacement


class PdfMakeTextAnnotation(BaseModel):
    """One directly placed text annotation in PDF page coordinates."""

    model_config = ConfigDict(extra="forbid")

    source_text_index: int = Field(ge=0)
    category: str
    value: str
    prefix: str
    suffix: str
    rendered_text: str
    handwritten: StrictBool
    pdf_corners: PdfQuad
    placement: PdfMakeLayoutPlacement


class PdfMakeAnnotationRecord(BaseModel):
    """Machine-readable ground truth for a make_pdf composition run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0-pdf-make"
    record_type: str = "pdf_make_run"
    source_pdf: Path
    output_dir: Path
    seed: int
    outputs: PdfMakeOutputFiles
    template: PdfTemplate
    images: list[PdfMakeImageInput]
    texts: list[PdfMakeTextInput]
    layout_decisions: list[PdfMakeLayoutDecision]
    image_annotations: list[PdfMakeImageAnnotation]
    text_annotations: list[PdfMakeTextAnnotation]


class PdfMakeArtifacts(BaseModel):
    """Paths and sidecar record emitted by the make_pdf API."""

    model_config = ConfigDict(extra="forbid")

    clean_pdf: Path
    annotated_pdf: Path
    annotation_json: Path
    record: PdfMakeAnnotationRecord
