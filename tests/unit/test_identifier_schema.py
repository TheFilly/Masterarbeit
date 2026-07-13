"""Validation tests for external identifier schemas."""

from copy import deepcopy
from datetime import datetime
from typing import Any

import faker.providers.date_time as faker_date_time
import pytest
from faker import Faker
from pydantic import ValidationError

from injection_pipeline.config import (
    DEFAULT_IDENTIFIER_SCHEMA_PATH,
    IdentifierSchema,
    load_identifier_schema,
)
from injection_pipeline.identity.generator import generate_identity


def _minimal_schema_payload() -> dict[str, Any]:
    return {
        "schema_id": "unit",
        "version": "1.0.0",
        "identity_id_field": "case_id",
        "generator": {"provider": "faker", "locale": "en_US"},
        "fields": [
            {
                "name": "case_id",
                "category": "identifier",
                "generation": {
                    "recipe": "numerify",
                    "arguments": {"text": "##"},
                    "value_template": "CASE-{value}",
                },
                "generic_prefix": "CASE-",
                "routing": {
                    "dicom_tag": {
                        "keyword": "PatientID",
                        "address": "0010,0020",
                        "vr": "LO",
                    },
                    "visible_pixel": {"enabled": True, "line_index": 0},
                },
            },
            {
                "name": "hidden_code",
                "category": "code",
                "generation": {
                    "recipe": "random_element",
                    "arguments": {"elements": ["A", "B"]},
                    "value_template": "{value}",
                },
                "generic_prefix": None,
                "routing": {
                    "dicom_tag": {
                        "keyword": "PatientSex",
                        "address": "0010,0040",
                        "vr": "CS",
                    },
                    "visible_pixel": {"enabled": False, "line_index": None},
                },
            },
        ],
    }


def _freeze_faker_today(
    monkeypatch: pytest.MonkeyPatch,
    frozen: datetime,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            if tz is not None:
                return frozen.replace(tzinfo=tz)
            return frozen

    monkeypatch.setattr(faker_date_time, "datetime", FrozenDateTime)


def _faker_schema_path_birth_date(seed: int) -> str:
    fake = Faker("en_US")
    fake.seed_instance(seed)
    fake.last_name()
    fake.first_name()
    fake.numerify(text="######")
    return fake.date_of_birth(minimum_age=18, maximum_age=90).strftime("%Y%m%d")


def test_default_identifier_schema_loads() -> None:
    schema = load_identifier_schema(DEFAULT_IDENTIFIER_SCHEMA_PATH)

    assert schema.schema_id == "dicom-prototype"
    assert schema.generator.reference_date.isoformat() == "2026-07-10"
    assert schema.generator.reference_date_policy == "faker-date_of_birth-reference-v1"
    assert [field.name for field in schema.visible_fields] == [
        "patient_name",
        "patient_id",
        "accession_number",
    ]
    assert [field.name for field in schema.tag_only_fields] == [
        "patient_birth_date",
        "patient_sex",
    ]


def test_identifier_schema_rejects_duplicate_field_names() -> None:
    payload = _minimal_schema_payload()
    payload["fields"][1]["name"] = "case_id"

    with pytest.raises(ValidationError, match="field names must be unique"):
        IdentifierSchema.model_validate(payload)


def test_identifier_schema_rejects_missing_identity_id_field() -> None:
    payload = _minimal_schema_payload()
    payload["identity_id_field"] = "missing"

    with pytest.raises(ValidationError, match="identity_id_field"):
        IdentifierSchema.model_validate(payload)


def test_identifier_schema_rejects_non_contiguous_visible_indices() -> None:
    payload = _minimal_schema_payload()
    payload["fields"][0]["routing"]["visible_pixel"]["line_index"] = 1

    with pytest.raises(ValidationError, match="0..n-1"):
        IdentifierSchema.model_validate(payload)


def test_identifier_schema_rejects_prefix_template_mismatch() -> None:
    payload = _minimal_schema_payload()
    payload["fields"][0]["generic_prefix"] = "ID-"

    with pytest.raises(ValidationError, match="generic_prefix"):
        IdentifierSchema.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("address", "0010-0020", "address"),
        ("vr", "lo", "vr"),
    ],
)
def test_identifier_schema_rejects_bad_dicom_route_values(
    field_name: str,
    bad_value: str,
    message: str,
) -> None:
    payload = _minimal_schema_payload()
    payload["fields"][0]["routing"]["dicom_tag"][field_name] = bad_value

    with pytest.raises(ValidationError, match=message):
        IdentifierSchema.model_validate(payload)


def test_identifier_schema_forbids_extra_fields() -> None:
    payload = _minimal_schema_payload()
    payload["fields"][0]["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs"):
        IdentifierSchema.model_validate(payload)


def test_identifier_schema_rejects_bad_reference_date() -> None:
    payload = _minimal_schema_payload()
    payload["generator"]["reference_date"] = "2026-02-31"

    with pytest.raises(ValidationError, match="reference_date"):
        IdentifierSchema.model_validate(payload)


def test_schema_driven_identity_matches_legacy_seed_outputs() -> None:
    schema = load_identifier_schema(DEFAULT_IDENTIFIER_SCHEMA_PATH)
    expected = {
        0: {
            "patient_name": "Richard^Katherine",
            "patient_id": "SYNTH-604876",
            "patient_birth_date": "19761019",
            "patient_sex": "F",
            "accession_number": "ACC-5938242",
        },
        1: {
            "patient_name": "Taylor^Melanie",
            "patient_id": "SYNTH-141777",
            "patient_birth_date": "19870309",
            "patient_sex": "M",
            "accession_number": "ACC-1706690",
        },
        42: {
            "patient_name": "Fowler^Angel",
            "patient_id": "SYNTH-433218",
            "patient_birth_date": "19470509",
            "patient_sex": "F",
            "accession_number": "ACC-0013389",
        },
        43: {
            "patient_name": "Johnson^Heather",
            "patient_id": "SYNTH-275179",
            "patient_birth_date": "20030503",
            "patient_sex": "M",
            "accession_number": "ACC-8695986",
        },
    }

    for seed, fields in expected.items():
        identity = generate_identity(seed, schema)
        assert identity.identity_id == fields["patient_id"]
        assert identity.fields == fields


def test_date_of_birth_matches_reference_day_faker_path_and_ignores_execution_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = load_identifier_schema(DEFAULT_IDENTIFIER_SCHEMA_PATH)
    _freeze_faker_today(monkeypatch, datetime(2026, 7, 10, 12, 0, 0))
    expected_birth_date = _faker_schema_path_birth_date(42)

    assert expected_birth_date == "19470509"
    assert generate_identity(42, schema).fields["patient_birth_date"] == (
        expected_birth_date
    )

    _freeze_faker_today(monkeypatch, datetime(2035, 1, 2, 12, 0, 0))

    assert generate_identity(42, schema).fields["patient_birth_date"] == (
        expected_birth_date
    )


def test_unknown_recipe_fails_during_identity_generation() -> None:
    payload = deepcopy(_minimal_schema_payload())
    payload["fields"][0]["generation"]["recipe"] = "missing_recipe"
    schema = IdentifierSchema.model_validate(payload)

    with pytest.raises(ValueError, match="Unknown identity generation recipe"):
        generate_identity(42, schema)
