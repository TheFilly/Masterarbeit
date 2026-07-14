# Ground-truth schema changelog

This changelog is the single version history required by ADR-0008. Run
records and PDF annotation sidecars have distinct `record_type` values but
share the same version namespace.

## 0.3.0-pdf-prototype — 2026-07-14

Added the PDF modality sidecar. It links an input PDF template, an already
injected DICOM, and the validated DICOM `ground_truth.json` to the generated
PDF and transformed PDF-space annotation quads. PDF input/output is handled by
the dedicated PDF loader/writer pair; source files are never modified.

## 0.2.0-prototype — existing

Current DICOM/JPG `RunRecord` schema. Existing parsers and byte-compatibility
fixtures remain valid.

## Change policy

Additive fields require a minor version and a fixture. Breaking reads require a
major (or pre-1.0 minor) bump, migration note, and a superseding ADR. Parsers
must continue accepting every published version unless an explicit decision
retires one.
