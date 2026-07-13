"""Ground-truth record construction and JSON artifact writing."""

import json
from pathlib import Path
from typing import Any

from injection_pipeline.config.identifier_schema import IdentifierSchema
from injection_pipeline.models import (
    BoxAnnotation,
    DicomContext,
    DicomTagAnnotation,
    EngineRenderMetadata,
    Identity,
    RecordRenderMetadata,
    RenderPlanItem,
    RunMetadata,
    RunRecord,
)

SCHEMA_VERSION = "0.2.0-prototype"


# Input: optionale DICOM-Kontexte vor und nach der Injektion.
# Output: Paar von Kontexten oder zwei `None`-Werte.
# Die Funktion erhaelt die Prototype-Regel, dass DICOM-Kontexte nur gemeinsam
# im RunRecord auftauchen.
def attach_dicom_contexts(
    source_dicom_context: DicomContext | None,
    output_dicom_context: DicomContext | None,
) -> tuple[DicomContext | None, DicomContext | None]:
    if source_dicom_context is None or output_dicom_context is None:
        return None, None
    return source_dicom_context, output_dicom_context


# Input: Run-Parameter, Pfade, Identitaet, Annotationen und `pixel_result`.
# Output: Validierter `RunRecord` fuer Ground Truth und Manifest.
# Die Funktion bildet interne Renderergebnisse in die kanonische Modellhierarchie
# ab und nutzt die WP-B-Modelle fuer JSON-sichere Serialisierung.
def build_record(
    *,
    run_id: str,
    seed: int,
    rotation_degrees: int,
    placement_mode: str,
    font_size_pct: int,
    font_family: str,
    text_background: str | None,
    document_type: str,
    example_type: str,
    input_path: Path,
    output_path: Path,
    preview_path: Path,
    annotated_preview_path: Path,
    identity: Identity,
    identifier_schema: IdentifierSchema,
    source_dicom_context: DicomContext | None,
    output_dicom_context: DicomContext | None,
    tag_annotations: list[DicomTagAnnotation],
    box_annotations: list[BoxAnnotation],
    visible_render_plan: list[dict[str, Any]],
    pixel_result: dict[str, Any],
) -> RunRecord:
    source_context, output_context = attach_dicom_contexts(
        source_dicom_context,
        output_dicom_context,
    )
    engine_metadata = EngineRenderMetadata.model_validate(
        pixel_result["render_metadata"]
    )
    render_metadata = RecordRenderMetadata(
        rotation_degrees=rotation_degrees,
        placement_mode=placement_mode,
        font_size_pct=font_size_pct,
        font_family=font_family,
        text_background=text_background,
        visible_render_plan=[
            RenderPlanItem.model_validate(item) for item in visible_render_plan
        ],
        **engine_metadata.model_dump(mode="python", exclude={"rotation_degrees"}),
    )
    return RunRecord(
        schema_version=SCHEMA_VERSION,
        record_type=f"{document_type}_injection_run",
        run_id=run_id,
        seed=seed,
        rotation_degrees=rotation_degrees,
        source_file=input_path,
        output_file=output_path,
        preview_file=Path(pixel_result["preview_file"] or preview_path),
        annotated_preview_file=annotated_preview_path,
        document_type=document_type,
        example_type=example_type,
        modality=(output_context.modality if output_context is not None else None),
        identity_id=identity.identity_id,
        span_annotations=[],
        box_annotations=box_annotations,
        dicom_tag_annotations=tag_annotations,
        run_metadata=RunMetadata(
            rotation_degrees=rotation_degrees,
            placement_mode=placement_mode,
            pixel_injection_status=pixel_result["status"],
            pixel_renderer=pixel_result["renderer_name"],
            visible_identity_fields=[
                field.name for field in identifier_schema.visible_fields
            ],
            tag_only_identity_fields=[
                field.name for field in identifier_schema.tag_only_fields
            ],
            source_dicom_context=source_context,
            output_dicom_context=output_context,
        ),
        render_metadata=render_metadata,
    )


# Input: `record` und Output-Pfade fuer Ground Truth und Manifest.
# Output: Keine Rueckgabe.
# Die Funktion schreibt beide JSON-Artefakte und bewahrt die bestehende
# Newline-Asymmetrie: Ground Truth mit, Manifest ohne abschliessenden Umbruch.
def write_run_artifacts(record: RunRecord, paths: dict[str, Path]) -> None:
    serialized_record = record.model_dump(mode="json")

    with paths["output_json"].open("w", encoding="utf-8") as fh:
        json.dump(serialized_record, fh, indent=2)
        fh.write("\n")

    with paths["output_manifest"].open("w", encoding="utf-8") as fh:
        json.dump(serialized_record, fh, indent=2)
