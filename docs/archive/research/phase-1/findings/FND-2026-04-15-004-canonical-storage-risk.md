---
id: FND-2026-04-15-004
kind: observation
status: draft
phase: 1
topic: canonical-storage
confidence: medium
sources:
  - DycomData/MIMIC-IV-ED/ed/triage.csv
  - DycomData/MIMIC-IV-ED/ed/triage.csv.gz
  - DycomData/MIMIC-IV-Waveform-subset/
related_decisions: []
related_risks:
  - duplicate-storage-forms
  - ambiguous-waveform-companion-files
---

## Observation

Some datasets are present in more than one storage form or include companion files whose role is ambiguous.

## Evidence

- `triage.csv` and `triage.csv.gz` appear to be content-identical duplicates in two storage forms
- `MIMIC-IV-Waveform-subset/.../n.csv.gz` appears to be a companion artifact rather than a core waveform file

## Interpretation

The pipeline should define a canonical input representation for duplicated tabular data and explicitly classify borderline companion files.

## Impact

Input loaders and config defaults may become inconsistent if the project does not decide which storage form is canonical.

## Next Step

Create a decision record for canonical storage selection once the MVP scope is finalized.
