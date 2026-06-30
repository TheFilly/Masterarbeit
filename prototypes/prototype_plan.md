# Prototype Plan: DICOM/JPG Injection

## Purpose

Record the concluded DICOM/JPG prototype and its handover into the package
pipeline. The prototype proved feasibility for DICOM tag injection, visible
pixel injection, reproducible placement, and a prototype ground-truth artifact.

`PLAN.md` remains the project roadmap. Operational usage now lives in
`docs/dicom-injection.md`.

## Status

- Scope: migrated from `prototypes/dicom/` to `src/injection_pipeline/`
- Status: concluded and packaged
- Last reviewed: 2026-06-30
- Entry point: `uv run injection-pipeline ...`

## Migrated Capabilities

- Injects five fixed DICOM tags.
- Renders visible PII for `PatientName`, `PatientID`, and `AccessionNumber`.
- Keeps `PatientBirthDate` and `PatientSex` tag-only.
- Accepts `.dcm`, `.jpg`, and `.jpeg`.
- Supports seeded placement, font family, font size, rotation, optional white
  text background, and optional label boxes.
- Writes `label_corners` for prefixed visible tokens (`SYNTH-`, `ACC-`).
- Derives visible boxes from final rotated masks.
- Supports manifest-driven handwriting assets with ink-mask boxes.
- Writes run folders using
  `{filetype}-{ddmmyyyy}-{hhmm}-seed{seed:04d}-angle{angle:03d}-{mode}-fs{fontsize}-{fontfamily}-{textbg}`.

## Completed Prototype Work

- AP3: `label_corners` in ground truth and optional annotated preview.
- AP4: JPG input through a visible-only render path.
- AP5: expanded run folder and `run_id` schema.
- AP6: mask-derived visible boxes for full text, PII value, and optional label.
- Handwriting MVP: ScrabbleGAN scaffold, manifest contract, fake renderer,
  validation, and package-side asset rendering.
- Prototype migration: code moved into `src/injection_pipeline/` with CLI entry
  point and equivalence checks against frozen baseline runs.

Validation artifacts remain in gitignored `prototypes/dicom/output_validation_*`
folders.

## Phase-2 Handover Notes

Open work carries forward to `PLAN.md` Phase 2:

1. Design the unified annotation schema.
2. Prepare the Phase-2 handover from prototype behavior to production models.
3. Decide how ScrabbleGAN should become productive. `tools/handwriting/scrabblegan/UPSTREAM_REVIEW.md`
   lists current blockers for real generation.

Additional notes:

- Separate `span_annotations`, `box_annotations`, and
  `dicom_tag_annotations`.
- Define shared metadata and format-specific fields.
- Keep the prototype schema `0.2.0-prototype` separate from the later
  production API.
- Mark prototype heuristics explicitly before reusing them in Phase 2 models.
