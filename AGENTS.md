# InjectionPipeline

Scalable pipeline for injecting synthetic personally identifiable information (PII) into anonymized medical documents. Part of a master's thesis and a larger research project.

## Stack

- Python 3.13
- uv for package management and virtual environments
- pytest + pytest-cov for testing
- ruff for linting and formatting
- mypy (strict mode) for type checking
- pydantic for data models and validation
- pydicom for DICOM file handling
- pandas for tabular data (MIMIC-IV CSVs)

## Project structure

```
InjectionPipeline/
├── src/
│   └── injection_pipeline/
│       ├── __init__.py
│       ├── models/          # Pydantic models (document model, annotation schema, identifier schema)
│       ├── loaders/         # Format-specific document loaders (adapters)
│       ├── engine/          # Injection engine (insert/replace operations)
│       ├── writers/         # Output writers (back to native formats)
│       ├── validators/      # Post-injection validation
│       ├── config/          # Configuration loading and defaults
│       └── identity/        # Identity pool and synthetic value generation
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/            # Test data and sample files
├── configs/                 # YAML/JSON config files
├── DycomData/               # Raw DYCOM input data (not committed)
├── pyproject.toml
├── AGENTS.md
└── README.md
```

## Commands

- `uv run pytest tests/ -x` — run tests, stop on first failure
- `uv run pytest tests/ --cov=src/injection_pipeline` — run tests with coverage
- `uv run ruff check src/ tests/` — lint
- `uv run ruff format src/ tests/` — format
- `uv run mypy src/` — type check

## Code style

- Follow PEP 8
- Type hints on all function signatures and return types
- Use pydantic BaseModel for all data structures, not plain dicts
- Use pathlib.Path for file paths, never string concatenation
- Use snake_case for variables and functions, PascalCase for classes, UPPER_CASE for constants
- Docstrings on all public functions and classes (Google style)
- Keep functions short and focused — if a function exceeds ~30 lines, consider splitting
- No wildcard imports
- Prefer explicit over implicit

## Architecture principles

- **Adapter pattern** for format support: each document format (DICOM, CSV, plain text) gets its own loader and writer. New formats are added by implementing a new adapter, not by changing the engine.
- **Taxonomy-agnostic**: the pipeline does not define PII categories. It consumes an externally provided IdentifierSchema (pydantic model). Never hardcode identifier types.
- **Separation of concerns**: document model, injection logic, and validation are independent components. They communicate through well-defined pydantic models.
- **Reproducibility**: all randomness must be seeded. Given the same config and seed, the pipeline must produce identical output.
- **Ground truth as artifact**: annotations are stored as a separate, versioned output (JSONL), never embedded in the output documents.

## Testing

- Every public function needs a unit test
- Use pytest fixtures for reusable test data
- Integration tests use small sample files in tests/fixtures/
- Test file naming: test_<module_name>.py
- Aim for high coverage on models/, engine/, and validators/

## Git

- Conventional commits: feat:, fix:, refactor:, test:, docs:
- Branch naming: feature/<short-description>, fix/<short-description>
- Keep commits atomic — one logical change per commit
- Do not commit test data that contains real patient information (even if anonymized MIMIC data — keep it in .gitignore)

## What this project is NOT

- Not a de-identification tool — it does the inverse (injection, not removal)
- Not responsible for defining which PII categories exist — that comes from an external team
- Not a clinical system — no real patient data is processed or generated
- Not a web application — this is a CLI/library pipeline

## Codex safety rules

- Default mode: use sandboxed workspace access.
- Do not access the network unless explicitly approved.
- Do not install, update, or remove dependencies without approval.
- Do not edit files outside the repository.
- Do not delete files, rewrite git history, or run destructive commands without approval.
- Do not commit secrets, credentials, real patient data, or MIMIC-derived sample data.
- Before changing architecture, public APIs, schemas, or config formats, propose a plan first.
- Prefer small diffs. Avoid unrelated refactoring.

## Documentation usage rules

- `PLAN.md` is the roadmap and task-prioritization layer, not the place for raw findings.
- The `docs/` tree is the canonical place for research findings, summaries, decisions, and thesis traceability.
- `docs/archive/` contains superseded or invalidated findings from earlier iterations — do not use as source of truth.
- Agents should read the latest relevant consolidated documentation before starting substantial work.
- Start with the most recent phase `summary.md` and `open-questions.md`, then open only the findings or decisions that are directly relevant to the task.
- Treat accepted decisions as the stable source of truth once they exist.
- If a finding and a phase summary disagree, treat that as a signal to refresh the summary rather than silently combining inconsistent states.
- Avoid loading the entire `docs/` tree by default; prefer the smallest relevant context.

## Current project state (as of 2026-04-22)

Phase 1 (Datenanalyse) is open and being restarted from scratch. All prior Phase-1 findings have been archived under `docs/archive/research/phase-1/` and are considered invalid. The `src/` code and folder structure are intact. New findings should be written to `docs/research/phase-1/findings/` following the template in `docs/templates/finding.md`.
