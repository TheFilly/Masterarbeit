# InjectionPipeline

Python pipeline for injecting fully synthetic PII into already anonymized
medical documents. The project supports a master's thesis and evaluates how
de-identification systems behave when controlled PII is reintroduced.

The pipeline is an injection tool. It modifies documents and writes a separate
ground-truth artifact for every injected value.

## Current Status

- `src/injection_pipeline/` contains the DICOM/JPG core chain with pydantic
  run models, an external identifier schema, split runner/engine stages, and
  DCM/JPG adapters.
- Run the migrated DICOM/JPG path with `uv run injection-pipeline ...` or
  `uv run python -m injection_pipeline ...`.
- DICOM/JPG operational details live in `docs/dicom-injection.md`.
- Architecture status and open implementation gates live in
  `docs/architecture/` and `docs/fable-work-packages.md`.

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
|   |-- artifacts/
|   |-- config/
|   |-- engine/
|   |-- identity/
|   |-- loaders/
|   |-- models/
|   |-- runtime/
|   |-- validators/
|   `-- writers/
|-- tools/handwriting/            # Isolated handwriting tooling
|-- configs/
|-- docs/
|   |-- architecture/
|   |-- archive/
|   `-- decisions/
|-- tests/
|   |-- fixtures/
|   |-- integration/
|   `-- unit/
|-- DycomData/                    # Local input data, not committed
|-- output/                       # Local generated outputs, not committed
|-- .github/
|-- pyproject.toml
|-- uv.lock
|-- AGENTS.md
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

With no CLI arguments, the command starts an interactive parameter setup. If at
least one CLI argument is set and `--input` is missing, the pipeline chooses a
seeded default from `DycomData/Dicom-Files` and `DycomData/images`.

| Option | Default | Possible values | Description |
|--------|---------|-----------------|-------------|
| `--seed` | `42` | Any integer | Seed for identity generation, default input selection, and layout choices |
| `--input` | Seeded auto-selection | Path ending in `.dcm`, `.jpg`, or `.jpeg` | Source document path |
| `--output-dir` | `output` | Path | Root output directory; each run creates a subdirectory |
| `--identifier-schema` | `configs/identifier_schemas/dicom-prototype.json` | Existing JSON schema path | External identifier schema for identity fields and routes |
| `--rotation-angle` | `0` | `0`, `20`, `90`, `180`, `270` | Rotation angle for visible injected text |
| `--font-size-pct` | `100` | Integer `>= 1` | Visible text size as a percentage of the prototype default |
| `--placement-mode` | `corners` | `corners`, `free` | Placement strategy for visible injected text |
| `--font-family` | `arial` | `arial`, `calibri`, `tahoma`, `consolas` | Font family used for visible rendering |
| `--text-background` | none | `white` | Optional white background behind visible text |
| `--show-label-boxes` | `n` | `y`, `n` | Draw generic prefix boxes in `preview_annotated.png` |
| `--run-timestamp` | Current time | ISO-8601 datetime | Fixed timestamp for deterministic run IDs |
| `--handwriting-manifest` | none | JSONL manifest or JSON manifest with `assets` | Manifest for generated handwriting assets |
| `--handwriting-asset` | none | Repeatable `identity_field=asset_id` mapping | Map schema fields to handwriting assets; requires `--handwriting-manifest` |

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


