"""Ground-truth annotation models shared by document formats."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from injection_pipeline.models.geometry import Quad


class BoxAnnotation(BaseModel):
    """A visible PII box with optional generic-prefix/suffix geometry."""

    model_config = ConfigDict(extra="forbid")

    label: str
    category: str | None = None
    text: str
    rendered_text: str
    prefix: str = ""
    suffix: str = ""
    region: str
    corners: Quad
    label_corners: Quad | None
    prefix_corners: Quad | None = None
    suffix_corners: Quad | None = None
    rotation_degrees: int
    frame_index: int
    font_size_pct: int

    @model_validator(mode="after")
    # Input: `self` mit neuer oder alter sichtbarer Annotation.
    # Output: Normalisierte `BoxAnnotation` mit Kompatibilitaetsfeldern.
    # Die Funktion fuellt neue Felder aus alten Records, damit bestehende
    # Ground-Truth-Fixtures lesbar bleiben und neue JSONs vollstaendig sind.
    def _normalize_new_fields(self) -> "BoxAnnotation":
        if self.category is None:
            self.category = self.label
        if self.prefix_corners is None:
            self.prefix_corners = self.label_corners
        if not self.prefix and not self.suffix and self.text in self.rendered_text:
            prefix_text, _, suffix_text = self.rendered_text.partition(self.text)
            self.prefix = prefix_text
            self.suffix = suffix_text
        return self


class DicomTagAnnotation(BaseModel):
    """A ground-truth entry for one injected DICOM tag."""

    model_config = ConfigDict(extra="forbid")

    label: str
    category: str | None = None
    tag_address: str = Field(pattern=r"^[0-9A-F]{4},[0-9A-F]{4}$")
    tag_keyword: str
    dicom_vr: str = Field(pattern=r"^[A-Z]{2}$")
    value: str
    identity_field: str
    identity_id: str
    source_file: Path
    output_file: Path


class SpanAnnotation(BaseModel):
    """A provisional text-span annotation for future text formats."""

    model_config = ConfigDict(extra="forbid")

    label: str
    text: str
    start: int
    end: int
    identity_field: str
