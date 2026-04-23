---
id: FND-2026-04-15-001
kind: observation
status: draft
phase: 1
topic: format-inventory
confidence: high
sources:
  - DycomData/
related_decisions: []
related_risks: []
---

## Observation

`DycomData/` contains a heterogeneous but finite set of file families that can be grouped into a small number of relevant technical formats.

## Evidence

- Total file count observed: 1,776
- Dataset-family split observed:
  - `Anonymization`: 410
  - `MIMIC-IV`: 37
  - `MIMIC-IV-ECG-subset`: 32
  - `MIMIC-IV-ED`: 12
  - `MIMIC-IV-Note`: 8
  - `MIMIC-IV-Waveform-subset`: 1,276
- Dominant file-type counts observed:
  - `.dat`: 925
  - `.hea`: 354
  - `.csv`: 239
  - `.dcm`: 147
  - `.csv.gz`: 26
  - `.txt`: 19
  - `.html`: 14
  - `.pdf`: 10
  - extensionless: 42, consisting of `RECORDS` and `.DS_Store`

## Interpretation

The format space is broad at the file-system level, but manageable at the modeling level. A small number of technical storage types covers the vast majority of relevant artifacts.

## Impact

Phase 2 can focus on a constrained set of abstract representations rather than treating every folder or dataset as a unique format.

## Next Step

Link each major technical format to its role in the project and classify which artifacts are true inputs versus reference material.
