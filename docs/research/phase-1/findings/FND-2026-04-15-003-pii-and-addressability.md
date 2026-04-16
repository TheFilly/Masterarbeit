---
id: FND-2026-04-15-003
kind: observation
status: draft
phase: 1
topic: pii-and-addressability
confidence: medium
sources:
  - DycomData/Anonymization/deanonymized_with_labels/patient_10005749_20010003/annotations_csv/hosp_patients.csv
  - DycomData/Anonymization/deanonymized_with_labels/patient_10005749_20010003/discharge_note_20010003.txt
  - DycomData/MIMIC-IV-Note/note/discharge.csv
  - DycomData/MIMIC-IV-ECG-subset/files/p1001/p10010066/s46643223/46643223.hea
related_decisions: []
related_risks:
  - incomplete-dicom-tag-verification
---

## Observation

The relevant input formats expose addressable PII-bearing locations at different abstraction levels: cells in tables, character spans in notes, metadata tags in DICOM, and header tokens in WFDB files.

## Evidence

- Annotation CSVs contain explicit fields such as `first_name`, `street_address`, `phone_number`, `email`, and `ssn`
- Annotated notes contain inline tags such as `<PER>`, `<DATE>`, and `<AGE>`
- DICOM annotation artifacts reference patient-facing header fields such as name, DOB, patient ID, institution, and physician
- ECG `.hea` files include subject comments and acquisition metadata
- Waveform `.hea` files include record and timing metadata

## Interpretation

The abstract document model must support at least four addressability modes:

- row or cell addressing
- text-span addressing
- tag-based metadata addressing
- header token or line addressing

## Impact

Phase 2 should first model CSV and text abstractions, then extend the same framework to DICOM and WFDB headers.

## Next Step

Use these addressability modes as the starting point for the Phase 2 document-location model.
