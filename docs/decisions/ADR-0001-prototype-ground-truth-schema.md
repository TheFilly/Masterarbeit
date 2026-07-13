---
id: ADR-0001
status: accepted
based_on:
  - docs/dicom-injection.md
---

# ADR-0001: Prototype ground-truth schema `0.2.0-prototype` as a hand-built JSON record

Backfilled 2026-07-06. Records a choice already implemented in code.

## Context

The migrated DICOM/JPG pipeline needed a ground-truth artifact before the
format-agnostic document model (PLAN.md Phase 2) existed. `PLAN.md` planned a
JSONL ground-truth format; the prototype shipped earlier than that design work.

## Decision

The prototype established one JSON object per run with
`schema_version = "0.2.0-prototype"`. At adoption it was assembled by hand and
had no validating model; `docs/dicom-injection.md` records the field surface.

## Alternatives Considered

- **JSONL per-annotation records** (the PLAN.md direction): deferred; a single
  per-run JSON object was simpler while the annotation shapes were still
  changing.
- **pydantic models from the start**: deferred to keep the prototype migration
  byte-identical with the pre-package prototype output.

## Consequences

- The original builder was fast to iterate and preserved migration byte
  identity.
- Before ADR-0005, a key typo could silently change the schema and consumers
  had no validated contract beyond the documented example.
- The PDF plan introduces a second, differently-versioned sidecar schema
  (`0.3.0-pdf-prototype`), guaranteeing drift without a unifying strategy.
- Superseding path: WP-B (`docs/architecture/domain-model-spec.md`) designs the
  typed replacement; ADR-0008 defines how versions relate. This ADR stays
  `accepted` as the record of the emitted prototype-format baseline.

## Implementation Status

The hand-built builder was replaced on 2026-07-12 by
`ground_truth.build_record()` and the validated `RunRecord` from ADR-0005.
The pipeline still parses and emits the `0.2.0-prototype` artifact contract, so
this ADR remains the historical baseline for that published version.

## Review Notes

Backfilled by WP-H; the decision was implicit in the prototype migration
(commits `0be8818` and earlier).
