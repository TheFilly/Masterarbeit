# Identifier-Schema Externalization (WP-C)

Status: implemented for the DICOM/JPG core chain, updated 2026-07-12. Implements
ADR-0007 for the prototype schema. Emitted schema provenance remains blocked by
ADR-0008.

## What counts as taxonomy (must move to data)

Everything that answers "which fields exist and what happens to each":
field names, generation recipes, synthetic prefixes, DICOM tag routing,
visible-vs-tag-only routing, render line order, identity-id derivation.

## What stays code (mechanism, not taxonomy)

Faker provider implementations, rendering mechanics, geometry, VR-aware tag
writing, mask/segment machinery, file I/O. The schema *names* a generator
recipe; code implements it.

## File format and location

`configs/identifier_schemas/dicom-prototype.json` — JSON (matches the PDF
plan's config-format decision; no new dependency). Loaded by
`config/identifier_schema.py` into pydantic models (below). The active schema
is selected by a `--identifier-schema` CLI option defaulting to the prototype
file. Recording the resolved schema path and its `schema_id`/`version` in
`run_metadata` remains an additive follow-up that requires the ADR-0008
emission-version gate.

## Schema structure

```jsonc
{
  "schema_id": "dicom-prototype",
  "version": "1.0.0",
  "description": "The five prototype fields, externalized without behaviour change.",
  "identity_id_field": "patient_id",        // which field's value becomes identity_id
  "generator": {
    "provider": "faker",
    "locale": "en_US",                       // today hardcoded in generator.py:9
    "reference_date": "2026-07-10",          // fixed date for date-sensitive Faker recipes
    "reference_date_policy": "faker-date_of_birth-reference-v1"
  },
  "fields": [ /* ordered list — order is the Faker call order (see Determinism) */ ]
}
```

Each field entry:

```jsonc
{
  "name": "patient_id",                      // identity field name (WP-B Identity.fields key)
  "category": "identifier",                  // free-form label for reporting; pipeline logic MUST NOT branch on it
  "generation": {
    "recipe": "numerify",                    // named recipe implemented in identity/
    "arguments": { "text": "######" },
    "value_template": "SYNTH-{value}"        // prefix applied at generation time
  },
  "generic_prefix": "SYNTH-",                // segmentation rule for rendering (ADR-0003); null if none
  "routing": {
    "dicom_tag": {                           // null for non-DICOM-addressable fields
      "keyword": "PatientID",
      "address": "0010,0020",
      "vr": "LO"
    },
    "visible_pixel": { "enabled": true, "line_index": 1 }   // enabled:false = tag-only
  }
}
```

Pydantic models in `config/identifier_schema.py` (all `extra="forbid"`):
`IdentifierSchema`, `GeneratorConfig`, `FieldSpec`, `GenerationSpec`,
`DicomTagRoute`, `VisiblePixelRoute`. Load-time validation: unique field
names; `identity_id_field` exists; `line_index` values unique among
visible-enabled fields and forming `0..n-1`; `generic_prefix`, when set, must
be a prefix of `value_template`'s literal head (so segmentation can never
fail at render time); `address` matches `^[0-9A-F]{4},[0-9A-F]{4}$`; `vr` is
two uppercase letters; `reference_date` is an ISO date; `reference_date_policy`
is non-empty.

## Worked example: today's five fields as data

```jsonc
{
  "schema_id": "dicom-prototype",
  "version": "1.0.0",
  "identity_id_field": "patient_id",
  "generator": {
    "provider": "faker",
    "locale": "en_US",
    "reference_date": "2026-07-10",
    "reference_date_policy": "faker-date_of_birth-reference-v1"
  },
  "fields": [
    {
      "name": "patient_name",
      "category": "person_name",
      "generation": { "recipe": "dicom_person_name", "arguments": {}, "value_template": "{value}" },
      "generic_prefix": null,
      "routing": {
        "dicom_tag": { "keyword": "PatientName", "address": "0010,0010", "vr": "PN" },
        "visible_pixel": { "enabled": true, "line_index": 0 }
      }
    },
    {
      "name": "patient_id",
      "category": "identifier",
      "generation": { "recipe": "numerify", "arguments": { "text": "######" }, "value_template": "SYNTH-{value}" },
      "generic_prefix": "SYNTH-",
      "routing": {
        "dicom_tag": { "keyword": "PatientID", "address": "0010,0020", "vr": "LO" },
        "visible_pixel": { "enabled": true, "line_index": 1 }
      }
    },
    {
      "name": "patient_birth_date",
      "category": "date",
      "generation": { "recipe": "date_of_birth", "arguments": { "minimum_age": 18, "maximum_age": 90, "format": "%Y%m%d" }, "value_template": "{value}" },
      "generic_prefix": null,
      "routing": {
        "dicom_tag": { "keyword": "PatientBirthDate", "address": "0010,0030", "vr": "DA" },
        "visible_pixel": { "enabled": false, "line_index": null }
      }
    },
    {
      "name": "patient_sex",
      "category": "code",
      "generation": { "recipe": "random_element", "arguments": { "elements": ["M", "F"] }, "value_template": "{value}" },
      "generic_prefix": null,
      "routing": {
        "dicom_tag": { "keyword": "PatientSex", "address": "0010,0040", "vr": "CS" },
        "visible_pixel": { "enabled": false, "line_index": null }
      }
    },
    {
      "name": "accession_number",
      "category": "identifier",
      "generation": { "recipe": "numerify", "arguments": { "text": "#######" }, "value_template": "ACC-{value}" },
      "generic_prefix": "ACC-",
      "routing": {
        "dicom_tag": { "keyword": "AccessionNumber", "address": "0008,0050", "vr": "SH" },
        "visible_pixel": { "enabled": true, "line_index": 2 }
      }
    }
  ]
}
```

`dicom_person_name` is a named recipe (code) producing
`f"{last_name}^{first_name}"` — the `^` join is DICOM PN mechanism, not
taxonomy, so it stays a recipe implementation in `identity/recipes.py`.

## Before → after mapping

| Hardcoded constant | Location today | Destination in schema |
|---|---|---|
| `_TAG_META` (keyword → address, VR) | `runner.py:27-33` | `fields[*].routing.dicom_tag.{address,vr}` |
| `_IDENTITY_FIELD_MAP` (keyword → field name) | `runner.py:35-41` | implicit: `fields[*].name` + `routing.dicom_tag.keyword` (one entry, two views) |
| `_VISIBLE_PIXEL_KEYWORDS` + order | `runner.py:43-47`, order via `enumerate` at `:348` | `fields[*].routing.visible_pixel.{enabled,line_index}` |
| `_TAG_ONLY_KEYWORDS` | `runner.py:48` | `visible_pixel.enabled: false` |
| `SYNTH-` prefix generation | `identity/generator.py:15` | `patient_id.generation.value_template` |
| `ACC-` prefix generation | `identity/generator.py:18` | `accession_number.generation.value_template` |
| Prefix segmentation rules | `planning.build_text_segments()` | generic rule driven by `fields[*].generic_prefix`: if value starts with prefix → `[generic(prefix), pii(rest)]`, else `[pii(value)]` |
| Faker locale | `identity/generator.py:9` | `generator.locale` |
| Faker call recipes + order | `identity/generator.py:13-18` | `fields[]` order + `generation.recipe/arguments` |
| identity_id = patient_id | `runner.py:329`, `:518` | `identity_id_field` |
| Duplicate prefix logic in dead API | `engine/pixel_injection.py:99-138` | deleted, not migrated |
| `_TAG_META` keyword set = tag_map keys | `runner.py:296-303` (`_build_tag_map`) | derived: all fields with a `dicom_tag` route |

Stays code: `_FONT_FAMILY_CHOICES` / `_TEXT_BACKGROUND_CHOICES` /
`_SHOW_LABEL_BOX_CHOICES` (`runner.py:50-52`) are render/CLI options, not
taxonomy — they move to run-config handling in `config/` eventually, but are
out of scope here.

## Determinism constraint (byte-identity)

`generate_identity` seeds one Faker instance and draws in a fixed order
(`identity/generator.py:13-18`): last_name, first_name, numerify, date_of_birth,
random_element, numerify. Faker outputs depend on **call order**, so the
schema-driven generator must draw **in `fields[]` list order with the same
recipe calls** to reproduce identical identities for a given seed. The worked
example's field order intentionally matches — except that today
`last_name` is drawn *before* `first_name` inside one field; the
`dicom_person_name` recipe preserves that internal order. Add a regression
test: seed 42 through the schema-driven path equals today's
`generate_identity(42)` output exactly.

`date_of_birth` must not read the execution day. It uses
`generator.reference_date` and `generator.reference_date_policy` from the
schema; the prototype fixes `2026-07-10` to reproduce Fakers exact
`date_of_birth` path for that day.

## What this does *not* cover

- Run/render configuration (fonts, placement, rotation) — separate config
  concern, later package.
- Multi-identity pools and cross-document identity reuse (PLAN.md "Identity
  Pool") — the schema is compatible (recipes + seeds) but pool semantics are
  future work.
- New PII categories — explicitly out of scope for the pipeline
  (`AGENTS.md`); the schema lets *others* define them.

## Implementation status, 2026-07-12

Implemented:

- `config/identifier_schema.py` validates generator, field, DICOM route,
  visible route, prefix/template, and cross-field constraints.
- `configs/identifier_schemas/dicom-prototype.json` contains the five
  prototype fields and deterministic generator reference date.
- `identity/generator.py` iterates schema fields in file order and delegates to
  `identity/recipes.py`.
- `planning.py` derives tag annotations, visible render plan, and text segments
  from the schema.
- Tests cover malformed schemas, default-schema loading, Faker reference-date
  determinism, legacy seed regressions, and a toy-schema E2E run.

Open:

- `run_metadata` does not yet emit `identifier_schema_id`,
  `identifier_schema_version`, or schema path because ADR-0008 has no emitted
  additive version for those fields.

## Implementation Status

### Implemented 2026-07-12

- `config/identifier_schema.py` and unit tests for validation failures.
- Default schema file under `configs/identifier_schemas/`.
- Recipe registry and schema-driven `generate_identity(seed, schema)`.
- Planning functions read DICOM routing, visible routing, and prefixes from the
  schema.
- Committed coverage: E2E bytehash tests and toy-schema smoke test.

### Remaining

- Emitted schema provenance in `run_metadata`, blocked by ADR-0008.

Definition of done update: the DICOM/JPG path can run with the default schema
or a two-field toy schema without code changes. Provenance emission remains
outside the current `0.2.0-prototype` record.
