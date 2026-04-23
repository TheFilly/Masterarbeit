---
id: FND-2026-04-15-005
kind: observation
status: draft
phase: 1
topic: family-level-input-separation
confidence: high
sources:
  - DycomData/MIMIC-IV/
  - DycomData/MIMIC-IV-ED/
  - DycomData/MIMIC-IV-Note/
  - DycomData/MIMIC-IV-ECG-subset/
  - DycomData/MIMIC-IV-Waveform-subset/
  - DycomData/Anonymization/
  - docs/research/phase-1/summary.md
related_decisions: []
related_risks:
  - folder-name-based-misclassification
  - duplicate-storage-forms
  - ambiguous-waveform-companion-files
---

## Observation

The separation between true inputs, derived or annotated reference artifacts, and auxiliary comparison artifacts is stable at the dataset-family level, but only if a few explicit exception rules are applied.

## Evidence

- `MIMIC-IV/`, `MIMIC-IV-ED/`, and `MIMIC-IV-Note/` primarily contain tabular source data in `csv` or `csv.gz` form and behave as true pipeline inputs.
- `MIMIC-IV-ECG-subset/files/` and `MIMIC-IV-Waveform-subset/files/.../waves/` contain WFDB core artifacts in `.hea` and `.dat` form and behave as true pipeline inputs.
- `MIMIC-IV-ECG-subset/` also contains companion tables such as `waveform_note_links.csv`, `record_list.csv`, and `machine_measurements.csv`, which act as crosswalk, manifest, or measurement metadata rather than core document inputs.
- `MIMIC-IV-Waveform-subset/` contains auxiliary artifacts such as `index.html`, `RECORDS`, checksums, and `*n.csv.gz` sidecars in addition to the WFDB core files.
- `Anonymization/deanonymized_with_labels/` contains annotation-bearing bundles and should be treated as derived reference material.
- `Anonymization/deanonymized_without_labels/` contains derived but unlabeled comparison artifacts and should not be treated as primary input.
- `Anonymization/original_data/` behaves as a mixed bundle: most `csv`, `dcm`, `hea`, and `dat` files are primary inputs, but files matching `*_deanonymized_2.csv` are derived artifacts despite their location.

## Interpretation

The repository can be classified with a small set of family-aware rules:

- treat source MIMIC tables as primary inputs
- treat WFDB `.hea` and `.dat` files as primary inputs
- treat annotation-bearing bundles as derived reference artifacts
- treat manifests, crosswalks, listings, checksums, and OS metadata as auxiliary artifacts
- override folder-level assumptions with filename-based exception rules inside `Anonymization/original_data/`

## Impact

Any future loader or input-discovery logic should use family-level defaults plus explicit filename and suffix exceptions, rather than relying on folder names alone.

## Next Step

Promote the classification rules into a stable decision once MVP input scope and canonical storage forms are chosen.
