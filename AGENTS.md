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
|   |-- models/
|   |-- loaders/
|   |-- engine/
|   |-- writers/
|   |-- validators/
|   |-- config/
|   `-- identity/
|-- prototypes/dicom/        # Active DICOM/JPG prototype
|-- tools/handwriting/       # Isolated handwriting tooling
|-- tests/
|-- configs/
|-- docs/
|-- DycomData/               # Local input data, not committed
|-- pyproject.toml
|-- AGENTS.md
`-- README.md
```

## Commands

- `uv run pytest tests/ -x` - run tests, stop on first failure
- `uv run pytest tests/ --cov=src/injection_pipeline` - run tests with coverage
- `uv run ruff check src/ tests/` - lint
- `uv run ruff format src/ tests/` - format
- `uv run mypy src/` - type check
- `uv run python prototypes/dicom/inject.py --seed 42` - run the current prototype

## Code Style

- Follow PEP 8.
- Type all public function signatures and return values.
- Use pydantic `BaseModel` for shared data structures.
- Use `pathlib.Path` for paths.
- Use snake_case for functions and variables, PascalCase for classes, and
  UPPER_CASE for constants.
- Add Google-style docstrings for public functions and classes.
- Keep functions focused. Split functions once they become hard to scan.
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
- `docs/` is the source for findings, summaries, decisions, and thesis
  traceability.
- `docs/archive/` contains superseded material. Do not use it as source of
  truth.
- For documentation, docstring, and code-comment tasks, use the
  `commenting-guidelines` skill when available.
- Start substantial work from the newest relevant `summary.md` and
  `open-questions.md`. If they do not exist, note the gap and use only directly
  relevant current files.
- Treat accepted decisions as stable.
- If a finding and summary disagree, update the summary instead of combining
  inconsistent states.
- Read the smallest useful slice of `docs/`.

## Current Project State

As of 2026-06-12:

- `src/injection_pipeline/` contains the production package structure.
- The active DICOM/JPG prototype still runs from `prototypes/dicom/`.
- `MIGRATION_PLAN.md` defines the planned migration into `src/injection_pipeline/`.
- New findings belong in `docs/research/phase-1/findings/` using
  `docs/templates/finding.md`.
