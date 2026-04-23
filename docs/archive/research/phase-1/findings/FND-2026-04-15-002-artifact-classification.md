---
id: FND-2026-04-15-002
kind: observation
status: draft
phase: 1
topic: artifact-classification
confidence: high
sources:
  - DycomData/Anonymization/
  - DycomData/MIMIC-IV/
  - DycomData/MIMIC-IV-ECG-subset/
  - DycomData/MIMIC-IV-ED/
  - DycomData/MIMIC-IV-Note/
  - DycomData/MIMIC-IV-Waveform-subset/
related_decisions: []
related_risks:
  - folder-name-based-misclassification
---

## Observation

Artifacts under `DycomData/` fall into three distinct operational classes: true pipeline inputs, derived or annotated reference artifacts, and auxiliary comparison files.

## Evidence

- Raw MIMIC source tables appear under `MIMIC-IV/`, `MIMIC-IV-ED/`, and `MIMIC-IV-Note/`
- Raw WFDB pairs appear under `MIMIC-IV-ECG-subset/files/` and `MIMIC-IV-Waveform-subset/files/`
- Raw case bundles appear under `Anonymization/original_data/`
- Annotated artifacts appear under `Anonymization/deanonymized_with_labels/`
- Comparison artifacts appear under `Anonymization/deanonymized_without_labels/`
- Auxiliary listing and manifest files include `index.html`, `RECORDS`, checksums, and `.DS_Store`
- Some derived files such as `*_deanonymized_2.csv` exist inside `Anonymization/original_data/`

## Interpretation

Folder membership alone is not a sufficient classifier. The pipeline must classify artifacts by role and file semantics, not just by parent directory name.

## Impact

Input discovery logic should use explicit inclusion and exclusion rules, especially inside `Anonymization/`.

## Next Step

Define per-format evidence and addressability rules for the primary input classes.
