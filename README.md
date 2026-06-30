# InjectionPipeline

Python pipeline for injecting fully synthetic PII into already anonymized
medical documents. The project supports a master's thesis and evaluates how
de-identification systems behave when controlled PII is reintroduced.

The pipeline is an injection tool. It modifies documents and writes a separate
ground-truth artifact for every injected value.

## Current Status

- Phase 1 data analysis was restarted on 2026-04-22. Old Phase-1 findings live
  in `docs/archive/research/phase-1/` and are not source of truth.
- `src/injection_pipeline/` contains the package structure and the migrated
  DICOM/JPG injection pipeline.
- Run the migrated DICOM/JPG path with `uv run injection-pipeline ...` or
  `uv run python -m injection_pipeline ...`.
- DICOM/JPG operational details live in `docs/dicom-injection.md`.
- New Phase-1 findings belong in `docs/research/phase-1/findings/`.

## Stack

| Tool | Purpose |
|------|---------|
| Python 3.13 | Runtime |
| `uv` | Package and virtual environment management |
| Pydantic v2 | Data models and validation |
| pydicom | DICOM handling |
| pandas | Tabular data such as MIMIC-IV CSVs |
| pytest + pytest-cov | Tests and coverage |
| ruff | Linting and formatting |
| mypy strict mode | Static type checking |

## Structure

```text
InjectionPipeline/
|-- src/injection_pipeline/       # Package code and migrated DICOM/JPG pipeline
|   |-- models/
|   |-- loaders/
|   |-- engine/
|   |-- writers/
|   |-- validators/
|   |-- config/
|   `-- identity/
|-- prototypes/dicom/             # Frozen DICOM/JPG validation artifacts
|-- tools/handwriting/            # Isolated handwriting tooling
|-- tests/
|-- configs/
|-- docs/
|-- DycomData/                    # Local input data, not committed
|-- pyproject.toml
`-- PLAN.md
```

## Setup

```bash
git clone <repo-url>
cd InjectionPipeline
uv sync --extra dev
```

Run `uv sync --extra dev` after a fresh clone or new virtual environment. The
dev extra installs `pytest`, `ruff`, and `mypy`.

## Commands

```bash
uv run pytest tests/ -x
uv run pytest tests/ --cov=src/injection_pipeline
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

Run all local gates:

```bash
uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest tests/ -x
```

Run the migrated DICOM/JPG pipeline:

```bash
uv run injection-pipeline --seed 42 --rotation-angle 20
```

The same CLI is also available through `uv run python -m injection_pipeline`.

## Architecture Rules

- Add format support through loaders and writers, not by changing engine logic.
- Keep the pipeline taxonomy-agnostic. Identifier types come from an external
  schema.
- Keep document models, injection logic, writers, and validators separate.
- Seed all randomness. Same config plus same seed must produce the same output.
- Write annotations as versioned sidecar artifacts, not into the document.

## Outputs

Each run produces:

| Artifact | Description |
|----------|-------------|
| Modified document | Input document with injected synthetic PII |
| Ground truth | Separate annotation artifact with positions, identifier type, value, and metadata |

The migrated DICOM/JPG path currently writes `ground_truth.json` with schema
`0.2.0-prototype`; the planned production contract remains JSONL.

## Not In Scope

- De-identification
- Defining the PII taxonomy
- Clinical use
- Web application work
- Real patient data

## Contributing

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- Keep commits atomic.
- Do not commit real patient data, MIMIC-derived sample data, checkpoints, or
  generated local artifacts.
