"""Identifier schema loading and validation."""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_IDENTIFIER_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "identifier_schemas"
    / "dicom-prototype.json"
)

_MODEL_CONFIG = ConfigDict(extra="forbid", strict=True)
_DICOM_ADDRESS_PATTERN = re.compile(r"^[0-9A-F]{4},[0-9A-F]{4}$")
_DICOM_VR_PATTERN = re.compile(r"^[A-Z]{2}$")


class GeneratorConfig(BaseModel):
    """Synthetic identity generator provider configuration."""

    model_config = _MODEL_CONFIG

    provider: str
    locale: str
    reference_date: date = date(2026, 7, 10)
    reference_date_policy: str = "faker-date_of_birth-reference-v1"

    @field_validator("provider")
    @classmethod
    # Input: `value` mit Provider-Namen aus dem Identifier-Schema.
    # Output: Validierter Provider-Name.
    # Die Funktion begrenzt WP-C auf den heute implementierten Faker-Provider.
    def _validate_provider(cls, value: str) -> str:
        if value != "faker":
            raise ValueError("generator.provider must be 'faker'.")
        return value

    @field_validator("reference_date", mode="before")
    @classmethod
    # Input: `value` aus JSON oder bereits geparstes Datum.
    # Output: ISO-Referenzdatum fuer datumsbezogene Faker-Rezepte.
    # Die Funktion erlaubt JSON-Strings trotz strikt konfigurierter Modelle und
    # meldet ungueltige Kalenderdaten vor der Identity-Erzeugung.
    def _parse_reference_date(cls, value: Any) -> date:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(
                    "generator.reference_date must be an ISO date."
                ) from exc
        raise ValueError("generator.reference_date must be an ISO date.")

    @field_validator("reference_date_policy")
    @classmethod
    # Input: `value` mit Referenzdatum-Policy aus dem Schema.
    # Output: Nichtleere Policy-Kennung.
    # Die Funktion macht die datumsbezogene Generatorsemantik im Schema
    # versioniert, ohne Pipeline-Logik an Taxonomie zu binden.
    def _validate_reference_date_policy(cls, value: str) -> str:
        if value == "":
            raise ValueError("generator.reference_date_policy must not be empty.")
        return value


class GenerationSpec(BaseModel):
    """Named recipe call and value templating rule for one field."""

    model_config = _MODEL_CONFIG

    recipe: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    value_template: str

    @field_validator("value_template")
    @classmethod
    # Input: `value` mit Format-Template fuer generierte Rezeptwerte.
    # Output: Validiertes Template.
    # Die Funktion erzwingt den Platzhalter, den die Rezeptauswertung ersetzt.
    def _validate_value_template(cls, value: str) -> str:
        if "{value}" not in value:
            raise ValueError("generation.value_template must contain '{value}'.")
        return value


class DicomTagRoute(BaseModel):
    """DICOM keyword, tag address, and VR routing for one field."""

    model_config = _MODEL_CONFIG

    keyword: str
    address: str
    vr: str

    @field_validator("address")
    @classmethod
    # Input: `value` mit DICOM-Tag-Adresse im Schemaformat.
    # Output: Validierte Adresse.
    # Die Funktion akzeptiert nur uppercase Gruppenadressen wie `0010,0020`.
    def _validate_address(cls, value: str) -> str:
        if _DICOM_ADDRESS_PATTERN.fullmatch(value) is None:
            raise ValueError(
                "dicom tag address must match '^[0-9A-F]{4},[0-9A-F]{4}$'."
            )
        return value

    @field_validator("vr")
    @classmethod
    # Input: `value` mit DICOM Value Representation.
    # Output: Validierte VR.
    # Die Funktion akzeptiert die zweibuchstabige uppercase Kurzform.
    def _validate_vr(cls, value: str) -> str:
        if _DICOM_VR_PATTERN.fullmatch(value) is None:
            raise ValueError("dicom vr must match '^[A-Z]{2}$'.")
        return value


class VisiblePixelRoute(BaseModel):
    """Visible pixel routing for one generated identity field."""

    model_config = _MODEL_CONFIG

    enabled: bool
    line_index: int | None

    @model_validator(mode="after")
    # Input: `self` mit Sichtbarkeitsflag und optionalem Zeilenindex.
    # Output: Validierte Pixelroute.
    # Die Funktion koppelt sichtbare Felder an einen nichtnegativen Index und
    # haelt tag-only Felder indexfrei.
    def _validate_line_index(self) -> "VisiblePixelRoute":
        if self.enabled:
            if self.line_index is None:
                raise ValueError("visible pixel routes require line_index.")
            if self.line_index < 0:
                raise ValueError("visible pixel line_index must be >= 0.")
        elif self.line_index is not None:
            raise ValueError("tag-only visible pixel routes must use line_index null.")
        return self


class RoutingSpec(BaseModel):
    """DICOM and visible-pixel routing for one field."""

    model_config = _MODEL_CONFIG

    dicom_tag: DicomTagRoute | None
    visible_pixel: VisiblePixelRoute


class FieldSpec(BaseModel):
    """Identifier field definition, generation rule, and routing."""

    model_config = _MODEL_CONFIG

    name: str
    category: str
    generation: GenerationSpec
    generic_prefix: str | None
    routing: RoutingSpec

    @model_validator(mode="after")
    # Input: `self` mit Felddefinition und optionalem generischem Praefix.
    # Output: Validierte Felddefinition.
    # Die Funktion verhindert Praefix-/Template-Kombinationen, die beim Rendern
    # nicht mehr sicher segmentiert werden koennen.
    def _validate_generic_prefix(self) -> "FieldSpec":
        if self.generic_prefix is None:
            return self
        literal_head = self.generation.value_template.split("{value}", 1)[0]
        if not literal_head.startswith(self.generic_prefix):
            raise ValueError("generic_prefix must be a prefix of value_template.")
        return self


class IdentifierSchema(BaseModel):
    """External taxonomy and routing schema for generated identities."""

    model_config = _MODEL_CONFIG

    schema_id: str
    version: str
    description: str | None = None
    identity_id_field: str
    generator: GeneratorConfig
    fields: list[FieldSpec]

    @model_validator(mode="after")
    # Input: `self` mit allen Schemafeldern.
    # Output: Validiertes Identifier-Schema.
    # Die Funktion prueft felduebergreifende Konsistenz, bevor Runner oder
    # Generator Dateien anfassen.
    def _validate_schema(self) -> "IdentifierSchema":
        if not self.fields:
            raise ValueError("identifier schema must contain at least one field.")

        field_names = [field.name for field in self.fields]
        if len(set(field_names)) != len(field_names):
            raise ValueError("identifier schema field names must be unique.")
        if self.identity_id_field not in set(field_names):
            raise ValueError("identity_id_field must reference an existing field.")

        visible_indices: list[int] = []
        for field in self.fields:
            visible_route = field.routing.visible_pixel
            if not visible_route.enabled:
                continue
            if visible_route.line_index is None:
                raise ValueError("visible pixel routes require line_index.")
            visible_indices.append(visible_route.line_index)
        unique_indices = set(visible_indices)
        if len(unique_indices) != len(visible_indices):
            raise ValueError("visible line_index values must be unique.")
        expected_indices = list(range(len(visible_indices)))
        if sorted(unique_indices) != expected_indices:
            raise ValueError("visible line_index values must form 0..n-1.")
        return self

    @property
    # Input: Keine Parameter.
    # Output: Felder mit DICOM-Tag-Route in Schema-Reihenfolge.
    # Die Property dient dem Runner als taxonomiefreie Tag-Planung.
    def dicom_fields(self) -> list[FieldSpec]:
        return [field for field in self.fields if field.routing.dicom_tag is not None]

    @property
    # Input: Keine Parameter.
    # Output: Sichtbare Felder sortiert nach `line_index`.
    # Die Property bewahrt die sichtbare Reihenfolge unabhaengig von der
    # Feldreihenfolge, die die Faker-Aufrufreihenfolge bestimmt.
    def visible_fields(self) -> list[FieldSpec]:
        return sorted(
            (field for field in self.fields if field.routing.visible_pixel.enabled),
            key=lambda field: field.routing.visible_pixel.line_index or 0,
        )

    @property
    # Input: Keine Parameter.
    # Output: DICOM-Felder ohne sichtbare Pixelroute.
    # Die Property ersetzt die hardcodierte Tag-only-Liste im Runner.
    def tag_only_fields(self) -> list[FieldSpec]:
        return [
            field
            for field in self.fields
            if field.routing.dicom_tag is not None
            and not field.routing.visible_pixel.enabled
        ]


# Input: `path` mit JSON-Identifier-Schema.
# Output: Validiertes `IdentifierSchema`.
# Die Funktion liest das externe Schema und meldet strukturelle Fehler vor dem
# Start eines Pipeline-Laufs.
def load_identifier_schema(path: Path | str) -> IdentifierSchema:
    schema_path = Path(path)
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Identifier schema JSON must contain an object.")
    return IdentifierSchema.model_validate(payload)
