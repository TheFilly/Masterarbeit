---
id: ADR-0002
status: accepted
based_on:
  - docs/architecture/determinism-audit.md
---

# ADR-0002: Fixed Windows font paths for prototype text rendering

Backfilled 2026-07-06. Records a choice already implemented in code.

## Context

Visible pixel injection renders synthetic PII with PIL and needs concrete
TrueType fonts. The prototype targets a single Windows development machine, and
rendered glyph geometry (and therefore ground-truth box coordinates and the
frozen byte-identical validation artifacts) depends on the exact font files.

## Decision

Font families are a closed set mapped to absolute Windows paths in
`engine/pixel_injection.py:19-24` (`_FONT_PATHS`: arial, calibri, tahoma,
consolas under `C:/Windows/Fonts/`). A missing font raises at run time
(`load_default_font`, `engine/pixel_injection.py:77`). The CLI exposes the same
closed set (`runner.py:50`, `cli.py:280-289`).

## Alternatives Considered

- **Font discovery via matplotlib/fontconfig**: rejected for the prototype —
  discovery order is environment-dependent, which would break geometry
  reproducibility.
- **Bundling fonts in the repo**: cleanest for portability but has licensing
  implications (Windows system fonts are not redistributable); deferred.

## Consequences

- Deterministic rendering on the primary machine; frozen validation artifacts
  stay comparable.
- The pipeline is not portable: any non-Windows environment (CI included) fails
  at font load. Font *file versions* are an unrecorded reproducibility input
  (see `docs/architecture/determinism-audit.md`, N7).
- Superseding path: externalize font configuration (WP-C identifier/run config)
  and record font file hashes in the run record (WP-G). Bundle or pin a freely
  licensed font (e.g. DejaVu) for CI.

## Review Notes

Backfilled by WP-H. Revisit before any CI or multi-machine work.
