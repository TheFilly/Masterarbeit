"""Ground-truth annotation models shared by document formats."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from injection_pipeline.models.geometry import Quad


class BoxAnnotation(BaseModel):
    """A visible PII box with optional generic-prefix geometry."""

    model_config = ConfigDict(extra="forbid")

    label: str
    text: str
    rendered_text: str
    region: str
    corners: Quad
    label_corners: Quad | None
    rotation_degrees: int
    frame_index: int
    font_size_pct: int


class DicomTagAnnotation(BaseModel):
    """A ground-truth entry for one injected DICOM tag."""

    model_config = ConfigDict(extra="forbid")

    label: str
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
