---
id: ADR-0004
status: accepted
based_on:
  - docs/fable-work-packages.md (WP-Q)
---

# ADR-0004: `ground_truth.json` and `run_manifest.json` are two copies of one record

Backfilled 2026-07-06. Records a choice already implemented in code.

## Context

Docs describe two run artifacts with different purposes: ground truth
(annotations for evaluation) and a run manifest (provenance/parameters). The
prototype implemented both names before the contents diverged.

## Decision

`runner.py:689-694` serializes the *same* `record` dict twice: once to
`ground_truth.json` (with trailing newline), once to `run_manifest.json`
(without). There is no content difference; the split exists only as reserved
naming for a future separation.

## Alternatives Considered

- **Single file**: rejected at the time to keep the documented artifact layout
  stable for downstream consumers while the split was still expected.
- **Actually splitting the record**: deferred — the record mixes annotation
  data and run provenance in one structure, so a meaningful split needs the
  typed model (WP-B).

## Consequences

- Consumers can rely on either name today, which doubles the compatibility
  surface while both files contain the same record.
- Any refactor must preserve both files byte-for-byte (including the
  newline asymmetry) until a decision explicitly changes them.
- Superseding path: WP-B's `RunRecord` separates annotation payload from run
  provenance; a future ADR should then either give `run_manifest.json` distinct
  provenance-only content or drop it. Until then this ADR documents the
  duplication as intentional-but-temporary.

## Review Notes

Backfilled by WP-H. The trailing-newline asymmetry is accidental, not designed;
treat it as frozen bytes, not as a convention to imitate.
