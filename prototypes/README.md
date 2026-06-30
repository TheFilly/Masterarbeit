# Prototypes

This directory contains prototype evidence and frozen local validation outputs
used for thesis-adjacent exploration.

## Current State

As of 2026-06-30, the DICOM/JPG injection prototype has been migrated into
`src/injection_pipeline/`.

- Run the migrated pipeline with `uv run injection-pipeline ...`.
- Read operational DICOM/JPG documentation in `docs/dicom-injection.md`.
- `dicom/output_validation_*` folders remain local reference artifacts and stay
  out of git.
- `prototype_plan.md` records the concluded prototype state and Phase-2 handover
  notes.
