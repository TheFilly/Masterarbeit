---
id: ADR-0005
status: accepted
based_on:
  - docs/architecture/target-architecture.md
  - docs/architecture/domain-model-spec.md
---

# ADR-0005: One canonical pydantic model hierarchy replaces the dict core

## Context

Before WP-B, the ground-truth record was hand-assembled as `dict[str, Any]`,
serialized through a `_make_json_safe` shim, and never validated. Shared stage
boundaries did not have runtime models. `AGENTS.md` mandates pydantic models at
shared boundaries.

## Decision

Define a single model hierarchy in `src/injection_pipeline/models/` as
specified in `docs/architecture/domain-model-spec.md`:

- geometry primitives (`ImagePoint`, `PdfPoint`, `MaskBounds`),
- `TextSegment`, `Identity`, annotation variants (`BoxAnnotation`,
  `DicomTagAnnotation`, `SpanAnnotation`), render/run metadata models, and a
  root `RunRecord` carrying `schema_version`.

All cross-module payloads use these models. JSON artifacts are produced via
`model_dump(mode="json")` with `Path` fields typed as `Path` (pydantic
serializes them to strings), designing `_make_json_safe` out. The PDF plan's
`ImagePoint`/`PdfPoint` fold into this hierarchy rather than living in
`pdf/models.py`.

## Alternatives Considered

- **Keep dicts + add JSON Schema validation**: validates output but leaves every
  internal seam untyped; does not retire the mypy override; two sources of truth
  (builder code and schema file).
- **dataclasses + manual validation**: lighter, but re-implements what pydantic
  gives (validation, JSON-mode serialization, versionable schemas) and
  contradicts the AGENTS.md stack choice.
- **TypedDicts**: typing without runtime validation; ground truth for a thesis
  needs runtime guarantees at the artifact boundary.

## Consequences

- The record becomes a contract: field typos fail loudly; the golden
  round-trip test pins the emitted JSON byte-for-byte against the current
  prototype output.
- Model fields give `engine/` the concrete types needed to delete the mypy
  override's dict-related debt (WP-E confirms most debt is PIL/numpy, not
  dicts — the override can be retired even earlier).
- Migration constraint: `model_dump` must reproduce the current key order and
  value formats exactly (see domain-model-spec, "Byte-compat notes").

## Implementation Status

Implemented 2026-07-12 for the DICOM/JPG core chain:

- `models/geometry.py`, `segments.py`, `identity.py`, `annotations.py`,
  `dicom.py`, `rendering.py`, `record.py`, and `adapters.py` define the
  pydantic boundary models.
- `ground_truth.build_record()` emits a validated `RunRecord`; `_make_json_safe`
  is gone.
- `load_run_record()` parses `0.2.0-prototype` artifacts and the E2E tests
  assert JSON round-trip byte compatibility for `ground_truth.json` and
  `run_manifest.json`.

Still open: ADR-0008 has not opened an emitted version for additive
provenance/reproducibility fields, and PDF sidecar models remain unimplemented.

## Review Notes

Accepted with the WP-B implementation on 2026-07-12. Future schema-emission
changes still need the PLAN.md blocker gate.
