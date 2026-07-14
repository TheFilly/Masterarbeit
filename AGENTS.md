# InjectionPipeline

Scalable pipeline for injecting synthetic personally identifiable information
(PII) into anonymized medical documents. The project supports a master's thesis
and a larger research effort.

## Stack

- Python 3.13
- `uv` for package and virtual environment management
- pytest + pytest-cov for testing
- ruff for linting and formatting
- mypy in strict mode
- pydantic for models and validation
- pydicom for DICOM handling
- pandas for tabular data

## Project Structure

```text
InjectionPipeline/
|-- src/injection_pipeline/
|   |-- artifacts/
|   |-- config/
|   |-- engine/
|   |-- identity/
|   |-- loaders/
|   |-- models/
|   |-- runtime/
|   |-- validators/
|   `-- writers/
|-- tools/handwriting/       # Isolated handwriting tooling
|-- configs/
|-- docs/
|   |-- architecture/
|   |-- archive/
|   `-- decisions/
|-- tests/
|   |-- fixtures/
|   |-- integration/
|   `-- unit/
|-- DycomData/               # Local input data, not committed
|-- output/                  # Local generated outputs, not committed
|-- .github/
|-- pyproject.toml
|-- uv.lock
|-- PLAN.md
|-- AGENTS.md
`-- README.md
```

## Commands

- `uv run pytest tests/ -x` - run tests, stop on first failure
- `uv run pytest tests/ --cov=src/injection_pipeline` - run tests with coverage
- `uv run ruff check src/ tests/` - lint
- `uv run ruff format src/ tests/` - format
- `uv run mypy src/` - type check
- `uv run injection-pipeline --seed 42` - run the migrated DICOM/JPG pipeline

`uv run injection-pipeline` starts an interactive setup when no CLI arguments
are provided. With CLI arguments but without `--input`, it chooses a seeded
default from `DycomData/Dicom-Files` and `DycomData/images`.

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

## Code Style

- Follow PEP 8.
- Type all public function signatures and return values.
- Use pydantic `BaseModel` for shared data structures.
- Use `pathlib.Path` for paths.
- Use snake_case for functions and variables, PascalCase for classes, and
  UPPER_CASE for constants.
- Use commenting-guidelines skill for function comments
- Keep functions focused. Split functions once they become hard to scan or larger than 100 lines
- Avoid wildcard imports.

## Architecture Principles

- **Adapter pattern:** each document format gets its own loader and writer.
- **Taxonomy-agnostic:** consume an external identifier schema; do not hardcode
  PII categories in production pipeline logic.
- **Separation of concerns:** document models, injection logic, writing, and
  validation communicate through explicit models.
- **Reproducibility:** seed all randomness.
- **Ground truth as artifact:** store annotations separately from output
  documents.

## Architecture Rules

- Add format support through loaders and writers, not by changing engine logic.
- Keep the pipeline taxonomy-agnostic. Identifier types come from an external
  schema.
- Keep document models, injection logic, writers, and validators separate.
- Seed all randomness. Same config plus same seed must produce the same output.
- Write annotations as versioned sidecar artifacts, not into the document.

## Testing

- Add unit tests for public functions.
- Use pytest fixtures for reusable sample data.
- Keep integration tests small and fixture-based.
- Name tests `test_<module_name>.py`.
- Prioritize coverage for `models/`, `engine/`, and `validators/`.

## Git

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- Branches: `feature/<short-description>` or `fix/<short-description>`.
- Keep commits atomic.
- Do not commit real patient data, MIMIC-derived data, generated assets, model
  weights, or secrets.

## Out of Scope

- De-identification
- Defining PII categories
- Clinical use
- Web application work

## Codex Safety Rules

- Use sandboxed workspace access by default.
- Do not access the network unless explicitly approved.
- Do not install, update, or remove dependencies without approval.
- Do not edit files outside the repository.
- Do not delete files, rewrite git history, or run destructive commands without
  approval.
- Do not commit secrets, credentials, real patient data, or MIMIC-derived sample
  data.
- Propose a plan before changing architecture, public APIs, schemas, or config
  formats.
- Prefer small diffs and avoid unrelated refactoring.

## Documentation Rules

- `PLAN.md` is the roadmap and prioritization layer.
- `docs/` is the source for architecture notes, operational documentation,
  decisions, and audit/status material.
- `docs/archive/` contains superseded material. Do not use it as source of
  truth.
- For documentation, docstring, and code-comment tasks, use the
  `commenting-guidelines` skill when available.
- Start substantial documentation work from the newest relevant current file in
  `docs/architecture/`, `docs/decisions/`, or operational docs. The retired
  research/thesis/template layer is not active source material.
- Treat accepted decisions as stable.
- If a finding and summary disagree, update the summary instead of combining
  inconsistent states.
- Read the smallest useful slice of `docs/`.

## Contributing

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- Keep commits atomic.
- Do not commit real patient data, MIMIC-derived sample data, checkpoints, or
  generated local artifacts.

## Current Project State

As of 2026-07-13:

- `src/injection_pipeline/` contains the DICOM/JPG core chain: pydantic domain
  models, artifact writers, runtime CLI/runner modules, external identifier
  schema loading, split engine stages, and registered DCM/JPG loader/writer
  adapters.
- The DICOM/JPG entry point is `uv run injection-pipeline ...` or
  `uv run python -m injection_pipeline ...`.
- `docs/dicom-injection.md` documents CLI usage, output artifacts, and the
  `0.2.0-prototype` ground-truth schema.
- The retired `prototypes/` tree is no longer the active source of truth; use
  `docs/dicom-injection.md`, `docs/architecture/`, and `docs/decisions/`.
- WP-I and the implemented WP-B..WP-G slices are tracked in
  `docs/fable-work-packages.md` and `docs/architecture/`. The PDF
  loader/writer, annotation sidecar, and CLI are implemented; broader PDF
  operational fixture coverage, ADR-0008 provenance/reproducibility
  emission, and the WP-G environment block remain open.
