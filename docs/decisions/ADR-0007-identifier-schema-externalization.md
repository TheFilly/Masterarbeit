---
id: ADR-0007
status: accepted
based_on:
  - docs/decisions/ADR-0003-synthetic-prefix-conventions.md
  - docs/architecture/identifier-schema-spec.md
---

# ADR-0007: PII taxonomy moves to an external identifier schema under `configs/`

## Context

Before WP-C, identity fields, generation recipes, DICOM routes, visible-pixel
routes, and synthetic prefixes were literals spread across runner and identity
code. `AGENTS.md` forbids hardcoding PII categories in production pipeline
logic and declares "Defining PII categories" out of scope for the pipeline.

## Decision

Introduce a versioned JSON identifier schema (format specified in
`docs/architecture/identifier-schema-spec.md`) at
`configs/identifier_schemas/dicom-prototype.json`, loaded by
`config/identifier_schema.py` into pydantic models. Each field entry declares:
name, generator recipe (Faker provider + arguments + value template), synthetic
prefix (if any), and routing (DICOM tag address/VR/keyword, visible rendering
with line index, or tag-only). `identity/` and the injection planner consume
the schema; the five current fields become the schema's first worked instance,
reproducing today's behaviour exactly.

JSON (not YAML/TOML) to match the PDF plan's config choice and avoid a new
dependency.

## Alternatives Considered

- **Python config module** (fields as constants in `config/`): centralizes but
  does not externalize — swapping taxonomies still means editing code, and the
  thesis claim "taxonomy-agnostic" stays unsupported.
- **YAML schema**: friendlier to hand-edit, adds a dependency; deferred, the
  loader boundary makes a later format swap cheap.
- **Database/registry of identifier types**: out of scale for this project.

## Consequences

- The headline AGENTS.md principle becomes demonstrable: a different taxonomy
  is a different JSON file, not a code change (thesis FF1 evidence).
- Identity generation output order and Faker call sequence must be preserved
  exactly while seeding stays instance-based, or identities change for a given
  seed (byte-identity hazard; spec pins the call order).
- Validation moves to load time: a malformed schema fails before any file is
  touched.

## Implementation Status

Implemented 2026-07-12 for the prototype taxonomy:

- `configs/identifier_schemas/dicom-prototype.json` carries the five current
  fields, generation recipes, DICOM routes, visible routes, prefixes, and
  `generator.reference_date = "2026-07-10"`.
- `config/identifier_schema.py` validates the schema with pydantic models.
- `identity/generator.py` and `identity/recipes.py` generate `Identity` from
  the schema and preserve Faker call order.
- `planning.py` derives tag plans, visible render plans, and text segments
  from the schema. The E2E suite includes a toy schema smoke test with
  different fields.

Still open: emitted identifier-schema provenance in `run_metadata` waits for
ADR-0008.

## Review Notes

Accepted with the WP-C implementation on 2026-07-12. Identity-pool semantics
remain future work.
