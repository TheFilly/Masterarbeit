"""Schema-driven tag and visible-render planning."""

from pathlib import Path
from typing import Any

from injection_pipeline.config.identifier_schema import FieldSpec, IdentifierSchema
from injection_pipeline.models import DicomTagAnnotation, Identity


# Input: `field` aus dem Identifier-Schema.
# Output: Label fuer Tag- oder Pixelannotation.
# Die Funktion nutzt DICOM-Keywords, sofern das Feld eine Tag-Route besitzt,
# und faellt sonst auf den Schemanamen zurueck.
def field_label(field: FieldSpec) -> str:
    dicom_tag = field.routing.dicom_tag
    if dicom_tag is not None:
        return dicom_tag.keyword
    return field.name


# Input: `identity` und `schema` mit DICOM-Routing.
# Output: Mapping von DICOM-Keywords auf einzuschreibende Werte.
# Die Funktion leitet alle Tag-Ziele aus dem Identifier-Schema ab.
def build_tag_map(identity: Identity, schema: IdentifierSchema) -> dict[str, str]:
    tag_map: dict[str, str] = {}
    for field in schema.dicom_fields:
        dicom_tag = field.routing.dicom_tag
        if dicom_tag is None:
            continue
        tag_map[dicom_tag.keyword] = identity.fields[field.name]
    return tag_map


# Input: `identity`, `schema`, `input_path` und `output_path`.
# Output: Liste von Tag-Annotationen fuer den Ground-Truth-Record.
# Die Funktion reichert injizierte Tag-Werte mit schema-definierter Adresse, VR
# und Quellen-/Zieldatei an.
def build_tag_annotations(
    *,
    identity: Identity,
    schema: IdentifierSchema,
    input_path: Path,
    output_path: Path,
) -> list[DicomTagAnnotation]:
    annotations: list[DicomTagAnnotation] = []
    for field in schema.dicom_fields:
        dicom_tag = field.routing.dicom_tag
        if dicom_tag is None:
            continue
        injected_value = identity.fields[field.name]
        annotations.append(
            DicomTagAnnotation(
                label=dicom_tag.keyword,
                tag_address=dicom_tag.address,
                tag_keyword=dicom_tag.keyword,
                dicom_vr=dicom_tag.vr,
                value=injected_value,
                identity_field=field.name,
                identity_id=identity.identity_id,
                source_file=input_path,
                output_file=output_path,
            )
        )
    return annotations


# Input: `identity`, `schema`, Rotation und Platzierungsmodus.
# Output: Renderplan fuer sichtbare Pixel-Injektionen.
# Die Funktion waehlt sichtbare Felder aus dem Schema und bereitet Textsegmente
# fuer PII- und generische Anteile vor.
def build_visible_render_plan(
    *,
    identity: Identity,
    schema: IdentifierSchema,
    rotation_degrees: int,
    placement_mode: str,
) -> list[dict[str, Any]]:
    render_plan: list[dict[str, Any]] = []
    for field in schema.visible_fields:
        visible_route = field.routing.visible_pixel
        if visible_route.line_index is None:
            raise ValueError("Visible schema fields must define line_index.")
        render_text, text_segments = build_text_segments(
            identity.fields[field.name],
            field.generic_prefix,
        )
        render_plan.append(
            {
                "label": field_label(field),
                "text": render_text,
                "text_segments": text_segments,
                "identity_field": field.name,
                "region": placement_mode,
                "rotation_degrees": rotation_degrees,
                "line_index": visible_route.line_index,
            }
        )
    return render_plan


# Input: `value` mit sichtbarem Text und optionalem generischem Praefix.
# Output: Rendertext und segmentierte Textanteile.
# Die Funktion trennt schema-definierte Praefixe von PII-Anteilen und faellt auf
# ein einzelnes PII-Segment zurueck, wenn kein Praefix passt.
def build_text_segments(
    value: str,
    generic_prefix: str | None,
) -> tuple[str, list[dict[str, str]]]:
    if generic_prefix is not None and value.startswith(generic_prefix):
        return value, [
            {"kind": "generic", "text": generic_prefix},
            {"kind": "pii", "text": value.removeprefix(generic_prefix)},
        ]
    return value, [{"kind": "pii", "text": value}]
