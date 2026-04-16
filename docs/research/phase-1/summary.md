# Phase 1 Summary

## Scope

This summary consolidates the initial format inventory of `DycomData/` and distinguishes primary pipeline inputs from reference and auxiliary artifacts.

## Current Findings

- `DycomData/` contains 1,776 files across `Anonymization`, `MIMIC-IV`, `MIMIC-IV-ECG-subset`, `MIMIC-IV-ED`, `MIMIC-IV-Note`, and `MIMIC-IV-Waveform-subset`.
- Dominant file types are `.dat`, `.hea`, `.csv`, `.dcm`, `.csv.gz`, `.txt`, `.html`, and `.pdf`.
- Primary pipeline inputs are the raw MIMIC source tables, raw WFDB ECG/waveform pairs, and raw case bundles under `Anonymization/original_data/`.
- Derived and annotated reference artifacts are concentrated in `Anonymization/deanonymized_with_labels/` and related sidecar files.
- Auxiliary or comparison artifacts include `deanonymized_without_labels/`, `index.html`, `RECORDS`, checksums, and `.DS_Store`.

## Family-Level Classification

- `MIMIC-IV/`, `MIMIC-IV-ED/`, and `MIMIC-IV-Note/` should be treated as primary tabular input families.
- `MIMIC-IV-ECG-subset/files/` and `MIMIC-IV-Waveform-subset/files/.../waves/` should be treated as primary WFDB input families for `.hea` and `.dat`.
- Companion files in the ECG and waveform subsets such as `waveform_note_links.csv`, `record_list.csv`, `machine_measurements.csv`, `RECORDS`, `index.html`, and `*n.csv.gz` should be treated as auxiliary or comparison artifacts.
- `Anonymization/deanonymized_with_labels/` should be treated as a derived and annotated reference family.
- `Anonymization/deanonymized_without_labels/` should be treated as a derived comparison family.
- `Anonymization/original_data/` should be treated as a mixed family that requires exception handling for derived files such as `*_deanonymized_2.csv`.

## Format Outlook

- High-priority MVP formats: `csv`, `csv.gz`, `txt`
- Medium-priority later format: `dcm`
- Lower-priority later formats: `hea`, `dat`
- No MVP priority: `pdf`, `html`, `RECORDS`, `.DS_Store`

## PII-Relevant Observations

- CSV-based annotation bundles explicitly contain fields such as `first_name`, `street_address`, `phone_number`, `email`, and `ssn`.
- Note artifacts contain inline markup such as `<PER>`, `<DATE>`, and `<AGE>`, indicating span-based addressability for text injection.
- DICOM-related annotation artifacts point to header-level fields such as patient name, date of birth, patient ID, institution, and physician.
- WFDB `.hea` files include metadata such as record IDs, dates, and subject comments, while `.dat` files appear to be binary signal payloads with no obvious direct PII surface in the initial review.

## Immediate Consequences

- Phase 2 should first model row/cell and text-span addressing before tackling DICOM tags and WFDB headers.
- The project should treat annotated artifacts as evidence and reference material, not as primary pipeline input.
- Classification rules must not rely on folder names alone, especially inside `Anonymization/original_data/`.
- Input discovery should combine family-level defaults with explicit exclusion rules for manifests, sidecars, crosswalk tables, and derived filename patterns.

## Linked Findings

- `FND-2026-04-15-001` format coverage and file-type distribution
- `FND-2026-04-15-002` input/reference/auxiliary classification
- `FND-2026-04-15-003` addressable and PII-bearing locations by format
- `FND-2026-04-15-004` duplicate storage forms and canonicalization risk
- `FND-2026-04-15-005` family-level input separation and exception rules
