# Prototypes

This directory contains prototype code used for thesis-adjacent exploration.

## Active Prototype

- `dicom/`: DICOM/JPG PII injection prototype.
- `prototype_plan.md`: current prototype status and remaining handover work.
- `dicom/README.md`: CLI, parameters, outputs, and annotation contract.

## Current State

As of 2026-06-12, the DICOM/JPG prototype remains in `prototypes/dicom/`.
`MIGRATION_PLAN.md` describes the planned move into `src/injection_pipeline/`;
the migration has not happened yet.

Implemented prototype capabilities:

- DICOM tag injection for five fixed tags.
- Visible pixel injection for `PatientName`, `PatientID`, and
  `AccessionNumber`.
- JPG input through the same visible rendering path.
- `label_corners`, optional label-box rendering, and mask-derived boxes.
- Manifest-driven handwriting assets for selected visible values.

Generated outputs stay in gitignored local folders.
