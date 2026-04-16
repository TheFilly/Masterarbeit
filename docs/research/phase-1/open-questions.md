# Open Questions

- Should `Anonymization/original_data/` be treated as a curated evaluation input set, even though it also contains derived files such as `*_deanonymized_2.csv`?
- Should `triage.csv` or `triage.csv.gz` become the canonical storage form for ED triage data?
- Is `MIMIC-IV-Waveform-subset/.../n.csv.gz` a true input artifact or only a companion/reference file?
- Should `record_list.csv` in the ECG subset be treated only as a manifest or as a reusable reference artifact?
- Should `waveform_note_links.csv` and `machine_measurements.csv` be modeled explicitly as reference artifacts, or simply excluded from MVP processing?
- Should `patient_info.csv` inside annotated bundles be treated as a reference copy or as a special case of labeled artifact?
- For DICOM MVP support, should the first version be limited to metadata tags and exclude burned-in pixel text?
- Should PDFs remain out of scope entirely for the MVP, even if they visibly contain patient-facing identifiers?
