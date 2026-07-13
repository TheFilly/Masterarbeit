"""Faker-based synthetic identity generation."""

from faker import Faker

from injection_pipeline.config.identifier_schema import (
    DEFAULT_IDENTIFIER_SCHEMA_PATH,
    IdentifierSchema,
    load_identifier_schema,
)
from injection_pipeline.identity.recipes import run_recipe
from injection_pipeline.models.identity import Identity


# Input: Optionales `schema` fuer Identity-Erzeugung.
# Output: Validiertes Identifier-Schema.
# Die Funktion laedt nur ohne explizites Schema den Prototype-Default.
def _resolve_schema(schema: IdentifierSchema | None) -> IdentifierSchema:
    if schema is not None:
        return schema
    return load_identifier_schema(DEFAULT_IDENTIFIER_SCHEMA_PATH)


# Input: `template` mit `{value}` und `value` aus einem Rezept.
# Output: Fertiger Feldwert.
# Die Funktion begrenzt Value-Templates auf den einen WP-C-Platzhalter.
def _apply_value_template(template: str, value: str) -> str:
    return template.replace("{value}", value)


# Input: `seed` fuer Faker-Reproduzierbarkeit und optionales Identifier-Schema.
# Output: Synthetische `Identity` nach WP-B-Modell.
# Die Funktion iteriert die Schemafelder in Datei-Reihenfolge; diese Reihenfolge
# und das Schema-Referenzdatum sind Teil des Determinismusvertrags fuer Faker.
def generate_identity(
    seed: int,
    schema: IdentifierSchema | None = None,
) -> Identity:
    active_schema = _resolve_schema(schema)
    fake = Faker(active_schema.generator.locale)
    fake.seed_instance(seed)

    fields: dict[str, str] = {}
    for field in active_schema.fields:
        raw_value = run_recipe(
            field.generation.recipe,
            fake,
            field.generation.arguments,
            active_schema.generator.reference_date,
        )
        fields[field.name] = _apply_value_template(
            field.generation.value_template,
            raw_value,
        )

    return Identity(
        identity_id=fields[active_schema.identity_id_field],
        seed=seed,
        fields=fields,
    )


if __name__ == "__main__":
    identity = generate_identity(seed=42)
    for key, value in identity.fields.items():
        print(f"{key}: {value}")
