# Prototype Plan: DICOM/JPG Injection

## Purpose

Track the active DICOM/JPG prototype in `prototypes/dicom/`. The prototype
proves feasibility for DICOM tag injection, visible pixel injection, reproducible
placement, and a prototype ground-truth artifact. It does not define the final
`src/` architecture.

`PLAN.md` remains the project roadmap. `MIGRATION_PLAN.md` covers the planned
move from prototype code into `src/injection_pipeline/`.

## Status

- Scope: `prototypes/dicom/`
- Status: active prototype, not yet migrated
- Last reviewed: 2026-06-12
- Main goal: preserve prototype evidence and prepare Phase-2 handover.

## Current Capabilities

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
  validation, and prototype-side asset rendering.

Validation artifacts remain in gitignored `prototypes/dicom/output_validation_*`
folders.

## Open Work

1. Design the unified annotation schema for Phase 2.
2. Prepare the Phase-2 handover from prototype behavior to production models.
3. Decide how ScrabbleGAN should become productive. `tools/handwriting/scrabblegan/UPSTREAM_REVIEW.md`
   lists current blockers for real generation.

## Phase-2 Handover Notes

- Separate `span_annotations`, `box_annotations`, and
  `dicom_tag_annotations`.
- Define shared metadata and format-specific fields.
- Keep the prototype schema `0.2.0-prototype` separate from the later
  production API.
- Mark prototype heuristics explicitly before reusing them in `src/`.

## Acceptance Criteria

- This file names the active prototype state and open handover work.
- Completed prototype tasks no longer appear as open tasks.
- Annotation-schema work covers spans, boxes, and DICOM tags.
- Prototype behavior stays separate from production design.
