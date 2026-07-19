"""Focused tests for visible annotation JSON compatibility."""

import json
from pathlib import Path

from injection_pipeline.models.annotations import BoxAnnotation, DicomTagAnnotation


def test_box_annotation_serializes_prefix_suffix_fields() -> None:
    corners = [{"x": 1.0, "y": 2.0}] * 4
    prefix_corners = [{"x": 3.0, "y": 4.0}] * 4
    suffix_corners = [{"x": 5.0, "y": 6.0}] * 4

    annotation = BoxAnnotation(
        label="Age",
        category="age",
        text="95",
        rendered_text="Patient is 95 years old",
        prefix="Patient is ",
        suffix=" years old",
        region="free",
        corners=corners,
        label_corners=prefix_corners,
        prefix_corners=prefix_corners,
        suffix_corners=suffix_corners,
        rotation_degrees=0,
        frame_index=0,
        font_size_pct=100,
    )
    payload = annotation.model_dump(mode="json")

    assert payload["label"] == "Age"
    assert payload["category"] == "age"
    assert payload["prefix"] == "Patient is "
    assert payload["suffix"] == " years old"
    assert payload["label_corners"] == payload["prefix_corners"]
    assert payload["suffix_corners"] == suffix_corners
    json.dumps(payload)


def test_box_annotation_backfills_new_fields_from_legacy_payload() -> None:
    corners = [{"x": 1.0, "y": 2.0}] * 4
    label_corners = [{"x": 3.0, "y": 4.0}] * 4

    annotation = BoxAnnotation(
        label="PatientID",
        text="123456",
        rendered_text="SYNTH-123456",
        region="corners",
        corners=corners,
        label_corners=label_corners,
        rotation_degrees=0,
        frame_index=0,
        font_size_pct=100,
    )
    payload = annotation.model_dump(mode="json")

    assert payload["category"] == "PatientID"
    assert payload["prefix"] == "SYNTH-"
    assert payload["suffix"] == ""
    assert payload["prefix_corners"] == payload["label_corners"]
    assert payload["suffix_corners"] is None


def test_dicom_tag_annotation_serializes_optional_category() -> None:
    annotation = DicomTagAnnotation(
        label="PatientID",
        category="PatientID",
        tag_address="0010,0020",
        tag_keyword="PatientID",
        dicom_vr="LO",
        value="SYNTH-123456",
        identity_field="patient_id",
        identity_id="SYNTH-123456",
        source_file=Path("source.dcm"),
        output_file=Path("output.dcm"),
    )

    payload = annotation.model_dump(mode="json")

    assert payload["category"] == "PatientID"


def test_dicom_tag_annotation_accepts_legacy_payload_without_category() -> None:
    annotation = DicomTagAnnotation(
        label="PatientID",
        tag_address="0010,0020",
        tag_keyword="PatientID",
        dicom_vr="LO",
        value="SYNTH-123456",
        identity_field="patient_id",
        identity_id="SYNTH-123456",
        source_file=Path("source.dcm"),
        output_file=Path("output.dcm"),
    )

    assert annotation.category is None
