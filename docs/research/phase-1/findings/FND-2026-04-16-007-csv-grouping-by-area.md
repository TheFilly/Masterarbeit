---
id: FND-2026-04-16-007
kind: observation
status: draft
phase: 1
topic: csv-grouping-by-area
confidence: medium
sources:
  - DycomData/MIMIC-IV/hosp/
  - DycomData/MIMIC-IV/icu/
  - DycomData/MIMIC-IV-ED/ed/
  - DycomData/MIMIC-IV-Note/note/
  - DycomData/MIMIC-IV-ECG-subset/
  - DycomData/MIMIC-IV-Waveform-subset/
  - docs/research/phase-1/summary.md
  - docs/research/phase-1/findings/FND-2026-04-16-006-true-input-scope-by-family.md
related_decisions: []
related_risks:
  - duplicate-storage-forms
  - ambiguous-waveform-companion-files
---

## Observation

The CSV-family artifacts under `DycomData/` can be grouped cleanly by the requested dataset areas, but the operational role of those CSV files differs across areas.

## Evidence

- `MIMIC-IV/hosp/` contains 22 CSV-family files:
  - `admissions.csv`
  - `diagnoses_icd.csv.gz`
  - `drgcodes.csv`
  - `d_hcpcs.csv`
  - `d_icd_diagnoses.csv`
  - `d_icd_procedures.csv`
  - `d_labitems.csv`
  - `emar.csv`
  - `emar_detail.csv`
  - `hcpcsevents.csv`
  - `labevents.csv`
  - `microbiologyevents.csv`
  - `omr.csv`
  - `patients.csv.gz`
  - `pharmacy.csv`
  - `poe.csv`
  - `poe_detail.csv.gz`
  - `prescriptions.csv`
  - `procedures_icd.csv.gz`
  - `provider.csv.gz`
  - `services.csv.gz`
  - `transfers.csv.gz`
- `MIMIC-IV/icu/` contains 9 CSV-family files:
  - `caregiver.csv.gz`
  - `chartevents.csv`
  - `datetimeevents.csv.gz`
  - `d_items.csv.gz`
  - `icustays.csv.gz`
  - `ingredientevents.csv`
  - `inputevents.csv`
  - `outputevents.csv.gz`
  - `procedureevents.csv.gz`
- `MIMIC-IV-ED/ed/` contains 7 CSV-family files:
  - `diagnosis.csv.gz`
  - `edstays.csv.gz`
  - `medrecon.csv.gz`
  - `pyxis.csv.gz`
  - `triage.csv`
  - `triage.csv.gz`
  - `vitalsign.csv.gz`
- `MIMIC-IV-Note/note/` contains 4 CSV-family files:
  - `discharge.csv`
  - `discharge_detail.csv.gz`
  - `radiology.csv`
  - `radiology_detail.csv.gz`
- `MIMIC-IV-ECG-subset/` contains 4 CSV files:
  - `machine_measurements.csv`
  - `machine_measurements_data_dictionary.csv`
  - `record_list.csv`
  - `waveform_note_links.csv`
- `MIMIC-IV-Waveform-subset/` contains 5 CSV-family files:
  - `81739927n.csv.gz`
  - `87033314n.csv.gz`
  - `83268087n.csv.gz`
  - `88501826n.csv.gz`
  - `82924339n.csv.gz`

## Interpretation

The CSV grouping by area should be understood as follows:

- `MIMIC-IV/hosp`: raw tabular source family; all listed CSV-family files belong to the hospital-domain group
- `MIMIC-IV/icu`: raw tabular source family; all listed CSV-family files belong to the ICU-domain group
- `MIMIC-IV-ED/ed`: raw ED source family, but `triage.csv` and `triage.csv.gz` should be treated as duplicate storage forms rather than two separate logical inputs
- `MIMIC-IV-Note/note`: note-domain CSV family; `discharge.csv` and `radiology.csv` behave as primary note tables, while `*_detail.csv.gz` behaves as companion or metadata-style detail artifacts
- `MIMIC-IV-ECG-subset`: CSV files belong to the ECG area but function as companion, manifest, crosswalk, or measurement artifacts rather than primary CSV inputs
- `MIMIC-IV-Waveform-subset`: CSV-family files belong to the waveform area but behave as sidecar artifacts; the primary inputs in this area remain WFDB `.hea` and `.dat`

## Impact

This resolves the Phase 1 task of grouping CSV-family artifacts by area and clarifies that not every CSV-shaped file should be treated as the same kind of pipeline input. The grouping is therefore both structural and operational.

## Next Step

Use this grouping to support the remaining CSV-focused analysis tasks, especially sampling, field-role analysis, and the pending decision on canonical storage for duplicated ED triage data.
