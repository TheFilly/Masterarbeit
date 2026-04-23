# Phase 1 Summary

## Scope

This summary consolidates the initial format inventory of `DycomData/` and distinguishes primary pipeline inputs from reference and auxiliary artifacts.

Phase 1 is materially useful, but parts of the result set are still provisional. In particular, the former standalone-`txt` MVP classification and the DICOM addressability claims require rework before Phase 2 should rely on them as settled fact.

## Current Findings

- `DycomData/` contains 1,776 files across `Anonymization`, `MIMIC-IV`, `MIMIC-IV-ECG-subset`, `MIMIC-IV-ED`, `MIMIC-IV-Note`, and `MIMIC-IV-Waveform-subset`.
- Dominant file types are `.dat`, `.hea`, `.csv`, `.dcm`, `.csv.gz`, `.txt`, `.html`, and `.pdf`.
- Primary pipeline inputs are the raw MIMIC source tables, raw WFDB ECG/waveform pairs, and raw case bundles under `Anonymization/original_data/`.
- Within `Anonymization/original_data/`, the currently observed raw case inputs are `csv`, `dcm`, `hea`, and `dat`; the note content is represented as CSV files such as `note_discharge_*.csv` and `note_radiology_*.csv`, not as standalone note `.txt` inputs.
- Derived and annotated reference artifacts are concentrated in `Anonymization/deanonymized_with_labels/` and related sidecar files.
- Auxiliary or comparison artifacts include `deanonymized_without_labels/`, `index.html`, `RECORDS`, checksums, and `.DS_Store`.

## Family-Level Classification

- `MIMIC-IV/`, `MIMIC-IV-ED/`, and `MIMIC-IV-Note/` should be treated as primary tabular input families.
- `MIMIC-IV-ECG-subset/files/` and `MIMIC-IV-Waveform-subset/files/.../waves/` should be treated as primary WFDB input families for `.hea` and `.dat`.
- Companion files in the ECG and waveform subsets such as `waveform_note_links.csv`, `record_list.csv`, `machine_measurements.csv`, `RECORDS`, `index.html`, and `*n.csv.gz` should be treated as auxiliary or comparison artifacts.
- `Anonymization/deanonymized_with_labels/` should be treated as a derived and annotated reference family.
- `Anonymization/deanonymized_without_labels/` should be treated as a derived comparison family.
- `Anonymization/original_data/` should be treated as a mixed family that requires exception handling for derived files such as `*_deanonymized_2.csv`.
- The true input scope is now defined per family: raw MIMIC tables, WFDB core `.hea` and `.dat` files, and raw files under `Anonymization/original_data/` are inputs unless excluded by explicit duplicate or derived-file rules.
- Standalone clinical-note `.txt` files currently appear in derived `deanonymized_*` bundles, not in the primary source families that define MVP input scope.

## Format Outlook

- High-priority MVP formats: `csv`, `csv.gz`
- Text-span support is still part of the MVP, but it should be derived from note text stored inside CSV inputs rather than from a separate primary `.txt` input format.
- Medium-priority later format: `dcm` (provisional until raw-tag inspection is completed)
- Lower-priority later formats: `hea`, `dat`
- No current MVP priority: standalone derived `.txt`, `pdf`, `html`, `RECORDS`, `.DS_Store`

## PII-Relevant Observations

- CSV-based annotation bundles explicitly contain fields such as `first_name`, `street_address`, `phone_number`, `email`, and `ssn`.
- Annotated note artifacts and note CSVs indicate span-based addressability for free text, but the primary raw note inputs in this repository are CSV-backed notes rather than standalone `.txt` files.
- DICOM-related annotation artifacts suggest header-level fields such as patient name, date of birth, patient ID, institution, and physician, but these claims still need confirmation against raw DICOM files with `pydicom`.
- WFDB `.hea` files include metadata such as record IDs, dates, and subject comments, while `.dat` files appear to be binary signal payloads with no obvious direct PII surface in the initial review.

## Immediate Consequences

- Phase 2 should first model row/cell and text-span addressing for CSV-backed inputs before tackling DICOM tags and WFDB headers.
- The project should treat annotated artifacts as evidence and reference material, not as primary pipeline input.
- Classification rules must not rely on folder names alone, especially inside `Anonymization/original_data/`.
- Input discovery should combine family-level defaults with explicit exclusion rules for manifests, sidecars, crosswalk tables, and derived filename patterns.
- Standalone `.txt` should not currently be assumed to be a required MVP input format.
- DICOM statements remain provisional until raw files have been inspected directly with `pydicom`.

## Linked Findings

- `FND-2026-04-15-001` format coverage and file-type distribution
- `FND-2026-04-15-002` input/reference/auxiliary classification
- `FND-2026-04-15-003` addressable and PII-bearing locations by format
- `FND-2026-04-15-004` duplicate storage forms and canonicalization risk
- `FND-2026-04-15-005` family-level input separation and exception rules
- `FND-2026-04-16-006` true pipeline input scope by dataset family
- `FND-2026-04-16-007` CSV grouping by requested dataset areas
- `FND-2026-04-16-008` CSV sample analysis by dataset area
