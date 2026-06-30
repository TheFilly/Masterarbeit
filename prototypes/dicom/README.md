# DICOM/JPG Prototype Archive

The DICOM/JPG injection code has moved to `src/injection_pipeline/`.

Use the package entry point instead:

```bash
uv run injection-pipeline --seed 42
uv run python -m injection_pipeline --seed 42
```

Operational documentation now lives in `docs/dicom-injection.md`.

Local `output_validation_*` folders under this directory remain frozen
reference artifacts and stay out of git.
