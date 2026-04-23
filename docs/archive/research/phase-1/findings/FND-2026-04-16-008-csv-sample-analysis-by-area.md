---
id: FND-2026-04-16-008
kind: observation
status: draft
phase: 1
topic: csv-sample-analysis-by-area
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
  - docs/research/phase-1/findings/FND-2026-04-16-007-csv-grouping-by-area.md
related_decisions: []
related_risks:
  - duplicate-storage-forms
  - ambiguous-waveform-companion-files
---

## Observation

The relevant CSV families show clearly different structural profiles across areas: highly structured event tables in `hosp` and `icu`, mixed structured-plus-short-text tables in `ed`, full-text note tables in `note`, and companion or sidecar CSVs in the ECG and waveform subsets.

## Evidence

- `MIMIC-IV/hosp/` sample tables repeatedly use encounter and event identifiers such as `subject_id`, `hadm_id`, `labevent_id`, `microevent_id`, `emar_id`, `poe_id`, `pharmacy_id`, `transfer_id`, and `itemid`.
- `MIMIC-IV/hosp/` also contains many temporal and contextual fields such as `admittime`, `dischtime`, `charttime`, `chartdate`, `storetime`, `admission_location`, `discharge_location`, `language`, `marital_status`, `insurance`, and provider-related fields.
- Longer or text-like payloads in `MIMIC-IV/hosp/` appear in fields such as `long_title`, `description`, `comments`, `event_txt`, `medication`, `result_name`, and `result_value`.
- `MIMIC-IV/icu/` sample tables center on `subject_id`, `hadm_id`, `stay_id`, `caregiver_id`, `itemid`, `orderid`, `linkorderid`, and multiple charting timestamps such as `charttime`, `storetime`, `starttime`, and `endtime`.
- `MIMIC-IV/icu/` is predominantly structured, with text-like content appearing mainly in labels or categorical descriptors such as `label`, `abbreviation`, `category`, `ordercategoryname`, `ordercategorydescription`, `statusdescription`, and `location`.
- `MIMIC-IV-ED/ed/` combines stable identifiers such as `subject_id`, `hadm_id`, `stay_id`, `seq_num`, and `charttime` with short textual or coded clinical context such as `chiefcomplaint`, `name`, `etcdescription`, and `icd_title`.
- Sample rows from `triage.csv` show short complaint phrases such as `Hypotension`, `Abd pain, Abdominal distention`, and `n/v/d, Abd pain`, indicating field-level short-text injection surfaces rather than long free text.
- Sample rows from `medrecon.csv.gz` show medication names and therapeutic class descriptions, making the table structured but semantically rich.
- `MIMIC-IV-Note/note/` uses `note_id`, `subject_id`, `hadm_id`, `note_type`, `note_seq`, `charttime`, and `storetime` as stable note-level anchors, with the main content stored in `text`.
- Sample rows from `discharge.csv` and `radiology.csv` confirm that `text` contains long multi-line note bodies with masked placeholders such as `Name: ___`, `Admission Date: ___`, and radiology narrative sections such as `INDICATION` and `TECHNIQUE`.
- `MIMIC-IV-Note/note/*_detail.csv.gz` uses compact key-value style fields `field_name`, `field_value`, and `field_ordinal`, with sample values such as `author -> ___`, which behave more like note metadata sidecars than primary full-text inputs.
- `MIMIC-IV-ECG-subset/` CSVs are companion tables built around `subject_id`, `study_id`, `cart_id`, `ecg_time`, `file_name`, `path`, `waveform_path`, `note_id`, and `note_seq`.
- `machine_measurements.csv` includes text-bearing interpretation fields `report_0` through `report_17`, with sample content such as `Sinus rhythm`, `Possible right atrial abnormality`, and `Borderline ECG`.
- `MIMIC-IV-Waveform-subset/` `*n.csv.gz` files are time-indexed numeric sidecars with columns such as `time`, `HR [bpm]`, `NBPd [mmHg]`, and other physiological measurements, and show no meaningful free-text payload in the sampled rows.

## Interpretation

The CSV-family sample analysis supports the following per-area characterization:

- `MIMIC-IV/hosp`: structured event and reference tables with many identifier and timestamp fields plus occasional descriptive or comment-bearing columns
- `MIMIC-IV/icu`: strongly structured event logs with dense operational identifiers and times, but little natural-language text
- `MIMIC-IV-ED/ed`: mixed structured tables where short textual complaint or medication-description fields are likely the most relevant CSV-level text targets
- `MIMIC-IV-Note/note`: note tables with genuine long-form free text in `text`, while `*_detail.csv.gz` behaves more like key-value metadata than primary narrative content
- `MIMIC-IV-ECG-subset`: CSVs are crosswalk, measurement, and report companion artifacts; they are analytically useful but not primary CSV inputs
- `MIMIC-IV-Waveform-subset`: CSV sidecars are mostly numeric time series and should be treated separately from primary WFDB inputs

Likely key-column patterns across the CSV families are stable enough to guide Phase 2 addressing:

- row-level anchors in tabular clinical data: `subject_id`, `hadm_id`, `stay_id`, `seq_num`, `itemid`
- note-level anchors: `note_id`, `note_seq`
- study and waveform anchors: `study_id`, `cart_id`, `file_name`, `path`, `waveform_path`

Likely indirect identifiers are concentrated in:

- timestamps and date fields
- provider, caregiver, and location-related fields
- demographic or encounter-context fields such as language, race, insurance, and care-unit context

## Impact

This resolves the Phase 1 requirement to perform an initial CSV sample analysis for the relevant areas. The results indicate that the pipeline should not treat all CSVs uniformly: some are row-and-field structured tables, some expose short text phrases, some carry full note text, and some behave mainly as companion artifacts.

## Next Step

Use these sample findings to define the first addressability model for CSV-based documents, especially the distinction between row/cell replacement, short field-text replacement, and long note-text span addressing.
