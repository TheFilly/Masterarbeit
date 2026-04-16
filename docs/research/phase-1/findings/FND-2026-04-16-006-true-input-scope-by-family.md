---
id: FND-2026-04-16-006
kind: observation
status: draft
phase: 1
topic: true-input-scope-by-family
confidence: high
sources:
  - DycomData/Anonymization/
  - DycomData/MIMIC-IV/
  - DycomData/MIMIC-IV-ECG-subset/
  - DycomData/MIMIC-IV-ED/
  - DycomData/MIMIC-IV-Note/
  - DycomData/MIMIC-IV-Waveform-subset/
  - docs/research/phase-1/summary.md
  - docs/research/phase-1/findings/FND-2026-04-15-002-artifact-classification.md
  - docs/research/phase-1/findings/FND-2026-04-15-004-canonical-storage-risk.md
  - docs/research/phase-1/findings/FND-2026-04-15-005-family-level-input-separation.md
related_decisions: []
related_risks:
  - folder-name-based-misclassification
  - duplicate-storage-forms
  - ambiguous-waveform-companion-files
---

## Observation

For each dataset family under `DycomData/`, the set of true pipeline inputs can be defined with stable family-level rules plus a small number of explicit exceptions.

## Evidence

- `MIMIC-IV/hosp/` and `MIMIC-IV/icu/` contain raw tabular source data in `csv` and `csv.gz` form and should be treated as true inputs.
- `MIMIC-IV-ED/ed/` contains raw ED source tables, but `triage.csv` and `triage.csv.gz` appear to represent the same content in two storage forms and should not both be treated as separate inputs.
- `MIMIC-IV-Note/note/` contains raw note tables such as `discharge.csv` and `radiology.csv`, which should be treated as true inputs.
- `MIMIC-IV-ECG-subset/files/` contains WFDB core artifacts in `.hea` and `.dat` form, while `record_list.csv`, `waveform_note_links.csv`, `machine_measurements.csv`, `machine_measurements_data_dictionary.csv`, `RECORDS`, and checksums behave as manifest, crosswalk, measurement, or auxiliary files.
- `MIMIC-IV-Waveform-subset/files/.../waves/` contains WFDB core artifacts in `.hea` and `.dat` form, while `RECORDS`, `index.html`, checksums, and `*n.csv.gz` sidecars behave as auxiliary or reference artifacts.
- `Anonymization/original_data/` contains mixed-format raw cases in `csv`, `txt`, `dcm`, `hea`, and `dat` form, but also includes derived filenames such as `*_deanonymized_2.csv` that should not be treated as true inputs despite their location.
- `Anonymization/deanonymized_with_labels/` contains annotation-bearing derived bundles, including annotation CSV sidecars and reference copies such as `patient_info.csv`, and should not be treated as primary input.
- `Anonymization/deanonymized_without_labels/` contains derived comparison artifacts and should not be treated as primary input.

## Interpretation

The true input scope can be stated per family as follows:

- `MIMIC-IV/`: all raw source tables in `csv` and `csv.gz` form are true pipeline inputs
- `MIMIC-IV-ED/`: raw source tables are true inputs, but only one canonical storage form should be treated as the input for duplicated triage data
- `MIMIC-IV-Note/`: raw note tables are true inputs
- `MIMIC-IV-ECG-subset/`: only WFDB core files `*.hea` and `*.dat` under `files/` are true inputs
- `MIMIC-IV-Waveform-subset/`: only WFDB core files `*.hea` and `*.dat` under `files/.../waves/` are true inputs
- `Anonymization/original_data/`: raw case files in `*.csv`, `*.txt`, `*.dcm`, `*.hea`, and `*.dat` are true inputs unless excluded by an explicit derived filename rule
- `Anonymization/deanonymized_with_labels/`: no files are true inputs
- `Anonymization/deanonymized_without_labels/`: no files are true inputs

## Impact

This resolves the Phase 1 task of documenting which files should count as genuine pipeline inputs for each dataset family. Future loader and input-discovery logic can start from family defaults and then apply explicit exclusion rules for duplicates, manifests, sidecars, and derived filename patterns.

## Next Step

Promote the remaining unresolved cases into a decision once the project chooses canonical storage forms for duplicated tables and confirms whether any borderline companion files should remain outside MVP processing.
