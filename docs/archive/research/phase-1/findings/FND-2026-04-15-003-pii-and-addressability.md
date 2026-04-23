---
id: FND-2026-04-15-003
kind: observation
status: draft
phase: 1
topic: pii-and-addressability
confidence: low
sources:
  - DycomData/Anonymization/deanonymized_with_labels/patient_10005749_20010003/annotations_csv/hosp_patients.csv
  - DycomData/Anonymization/deanonymized_with_labels/patient_10005749_20010003/discharge_note_20010003.txt
  - DycomData/Anonymization/original_data/patient_10005749_20010003/csv/note_discharge_20010003.csv
  - DycomData/MIMIC-IV-Note/note/discharge.csv
  - DycomData/MIMIC-IV-ECG-subset/files/p1001/p10010066/s46643223/46643223.hea
related_decisions: []
related_risks:
  - incomplete-dicom-tag-verification
  - txt-input-misclassification
---

## Observation

The repository exposes several plausible PII-bearing addressability modes, but the current evidence solidly supports only row or cell addressing and text-span addressing for MVP inputs. DICOM tag-level claims remain provisional until raw files are inspected directly.

## Evidence

- Annotation CSVs contain explicit fields such as `first_name`, `street_address`, `phone_number`, `email`, and `ssn`
- Annotated notes contain inline tags such as `<PER>`, `<DATE>`, and `<AGE>`
- Raw note inputs in `MIMIC-IV-Note/` and `Anonymization/original_data/.../csv/` are CSV files whose text payloads imply span-based addressing inside CSV-backed note content rather than a separate standalone `.txt` input class
- DICOM annotation artifacts reference patient-facing header fields such as name, DOB, patient ID, institution, and physician, but no raw DICOM file has yet been validated with `pydicom`
- ECG `.hea` files include subject comments and acquisition metadata
- Waveform `.hea` files include record and timing metadata

## Interpretation

The abstract document model must support at least two confirmed MVP addressability modes:

- row or cell addressing
- text-span addressing

It should reserve extension points for later-confirmed modes:

- tag-based metadata addressing for DICOM
- header token or line addressing for WFDB

## Impact

Phase 2 should first model CSV-backed row/cell and text-span abstractions. Standalone `.txt` should not be treated as a required MVP input format on the current evidence, and DICOM support should not be scoped from annotation artifacts alone.

## Next Step

Validate raw DICOM files with `pydicom`, then refresh this finding and the format matrix before Phase 2 depends on DICOM-specific claims.
