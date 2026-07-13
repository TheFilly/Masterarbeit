"""Canonical run record and schema-versioned loading."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from injection_pipeline.models.annotations import (
    BoxAnnotation,
    DicomTagAnnotation,
    SpanAnnotation,
)
from injection_pipeline.models.dicom import DicomContext
from injection_pipeline.models.rendering import (
    HandwritingRenderAsset,
    RenderedAnnotation,
    RenderPlanItem,
)

_CURRENT_SCHEMA_VERSION = "0.2.0-prototype"


class RunMetadata(BaseModel):
    """Run-level injection settings and optional DICOM contexts."""

    model_config = ConfigDict(extra="forbid")

    rotation_degrees: int
    placement_mode: str
    pixel_injection_status: str
    pixel_renderer: str
    visible_identity_fields: list[str]
    tag_only_identity_fields: list[str]
    source_dicom_context: DicomContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    output_dicom_context: DicomContext | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class RecordRenderMetadata(BaseModel):
    """Run-record rendering metadata with the engine fields flattened."""

    model_config = ConfigDict(extra="forbid")

    rotation_degrees: int
    placement_mode: str
    font_size_pct: int
    font_family: str
    text_background: str | None
    visible_render_plan: list[RenderPlanItem]
    seed: int
    allowed_rotations_degrees: list[int]
    frame_count: int
    applied_frame_indices: list[int]
    effective_font_family: str
    effective_font_size_px: int
    background_enabled: bool
    background_color: list[int] | None
    geometry_source: str
    renderer_types: list[str]
    handwriting_assets: list[HandwritingRenderAsset]
    geometry_notes: str
    mask_alpha_threshold: int
    visible_annotations: list[RenderedAnnotation]


class RunRecord(BaseModel):
    """Validated ground-truth record for one DICOM or JPG injection run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = _CURRENT_SCHEMA_VERSION
    record_type: str
    run_id: str
    seed: int
    rotation_degrees: int
    source_file: Path
    output_file: Path
    preview_file: Path
    annotated_preview_file: Path
    document_type: str
    example_type: str
    modality: str | None
    identity_id: str
    span_annotations: list[SpanAnnotation]
    box_annotations: list[BoxAnnotation]
    dicom_tag_annotations: list[DicomTagAnnotation]
    run_metadata: RunMetadata
    render_metadata: RecordRenderMetadata


# Input: `path` mit JSON-RunRecord und Schema-Version.
# Output: Validiertes `RunRecord` aus dem JSON-Artefakt.
# Die Funktion prueft die bekannte Prototypversion und verweigert unbekannte
# Versionen, damit kein stilles Schema-Misparsing entsteht.
def load_run_record(path: Path) -> RunRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Run record JSON must contain an object.")
    schema_version = payload.get("schema_version")
    if schema_version != _CURRENT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported run record schema version: {schema_version!r}.")
    return RunRecord.model_validate(payload)
