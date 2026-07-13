---
id: ADR-0003
status: accepted
based_on:
  - docs/architecture/identifier-schema-spec.md
---

# ADR-0003: `SYNTH-` / `ACC-` prefixes mark synthetic identifiers and split PII from generic text

Backfilled 2026-07-06. Records a choice already implemented in code.

## Context

Injected identifiers must be recognizably synthetic (safety: nobody should
mistake an injected patient ID for a real one), and downstream evaluation needs
to distinguish the PII payload from generic scaffolding inside one rendered
string, so detector metrics do not reward finding the constant prefix.

## Decision

- The default identifier schema generates `patient_id = "SYNTH-" + 6 digits`
  and `accession_number = "ACC-" + 7 digits`.
- `planning.build_text_segments()` splits rendered text into generic and PII
  segments from each field's configured prefix.
- The renderer tracks separate masks per segment kind and emits `corners` for
  the PII part and `label_corners` for the prefix part
  through the annotation models built in `engine/injector.py`.

## Alternatives Considered

- **No prefix**: rejected — synthetic values would be indistinguishable from
  plausible real ones.
- **Watermark/metadata-only marking**: rejected — the marking must survive in
  the visible pixels, which is where the injected PII lives.

## Consequences

- Ground truth can separate PII boxes from prefix boxes (`label_corners`),
  which the annotated preview visualizes (`--show-label-boxes`).
- The prefix rules originally existed as duplicated string literals. ADR-0007
  moved them into the external identifier schema, and
  `planning.build_text_segments()` now consumes that configuration.
- The convention remains stable while the concrete prefix taxonomy lives in
  data rather than pipeline logic.

## Review Notes

Backfilled by WP-H. Keep the convention; relocate the data.
