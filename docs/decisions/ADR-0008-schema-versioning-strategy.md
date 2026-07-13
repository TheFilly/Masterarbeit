---
id: ADR-0008
status: proposed
based_on:
  - docs/decisions/ADR-0001-prototype-ground-truth-schema.md
  - docs/pdf-template-injection-plan.md
  - docs/architecture/domain-model-spec.md
---

# ADR-0008: One versioned schema lineage for all ground-truth artifacts

## Context

`0.2.0-prototype` is a bare string constant (`runner.py:49`) with no validator.
The PDF plan introduces `0.3.0-pdf-prototype` for its sidecar only, explicitly
not replacing the run schema. Two independently evolving version strings with
no shared rules is guaranteed drift.

## Decision

- **One lineage, two document kinds.** `RunRecord` (per-run ground truth) and
  `PdfAnnotationRecord` (PDF sidecar) are distinct document kinds distinguished
  by `record_type`, but share one `schema_version` numbering scheme and one
  changelog (`docs/architecture/domain-model-spec.md`, "Versioning").
- **Semver with pre-release tags.** `MAJOR.MINOR.PATCH[-tag]`: MAJOR = breaking
  reads, MINOR = additive fields, PATCH = documentation/constraint fixes.
  `-prototype` / `-pdf-prototype` tags mark pre-stability versions; the typed
  models start at `0.4.0` (first validated version) while *emitting*
  `0.2.0-prototype` until byte-compat is deliberately broken by a future ADR.
- **Back-compat by parser, not by freeze.** The models must parse
  `0.2.0-prototype` and `0.3.0-pdf-prototype` files (permissive read models or
  explicit migration functions); golden files under `tests/fixtures/schemas/`
  pin every published version.

## Alternatives Considered

- **Independent versions per artifact kind**: what the PDF plan implies; drifts
  immediately, and shared submodels (points, boxes) get two version histories.
- **No versions until stable**: removes drift by removing information; existing
  artifacts already carry version strings, so the field cannot be dropped.
- **JSON Schema files as the source of truth**: duplicate of the pydantic
  models; can be *generated* from the models later if external consumers need
  them.

## Consequences

- A schema change is: bump version in one place, add a golden file, note the
  changelog entry. Old artifacts stay parseable.
- The PDF work (`pdf-template-injection-plan.md` WP1) must take its models from
  `models/` instead of defining its own (adapter-contract.md records this
  adjustment).

## Implementation Status

Partially implemented 2026-07-12:

- `RunRecord` validates and emits the existing `0.2.0-prototype` DICOM/JPG
  record.
- `load_run_record()` accepts only `0.2.0-prototype`; tests pin round-trip
  behavior.

Still open:

- No schema changelog exists yet.
- The emitted DICOM/JPG record has no version-safe slot for identifier-schema
  provenance or the ADR-0009 `reproducibility` block.
- `0.3.0-pdf-prototype` remains planned; no PDF sidecar model or composer
  exists in `src/`.

## Review Notes

Proposed by WP-A/WP-B. Blocker review — PLAN.md marks every schema change as a
blocker gate.
