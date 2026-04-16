# InjectionPipeline

Scalable pipeline for injecting synthetic personally identifiable information (PII) into anonymized medical documents. Developed as part of a master's thesis and a larger research project on medical NLP and de-identification evaluation.

The pipeline does the **inverse** of de-identification: it takes already-anonymized documents and re-introduces realistic, fully synthetic PII at controlled positions, producing both the modified document and a ground-truth annotation artifact (JSONL) that records every injection site.

---

## Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.13 | Runtime |
| [uv](https://github.com/astral-sh/uv) | Package management and virtual environments |
| [Pydantic v2](https://docs.pydantic.dev/) | Data models and validation |
| [pydicom](https://pydicom.github.io/) | DICOM file handling |
| [pandas](https://pandas.pydata.org/) | Tabular data (MIMIC-IV CSVs) |
| [pytest](https://pytest.org/) + pytest-cov | Testing and coverage |
| [ruff](https://docs.astral.sh/ruff/) | Linting and formatting |
| [mypy](https://mypy.readthedocs.io/) (strict) | Static type checking |

---

## Project Structure

```
InjectionPipeline/
├── src/
│   └── injection_pipeline/
│       ├── __init__.py
│       ├── models/          # Pydantic models: document, annotation schema, identifier schema
│       ├── loaders/         # Format-specific document loaders (adapter pattern)
│       ├── engine/          # Injection engine: insert / replace operations
│       ├── writers/         # Output writers: serialize back to native formats
│       ├── validators/      # Post-injection validators
│       ├── config/          # Configuration loading and defaults
│       └── identity/        # Identity pool and synthetic value generation
├── tests/
│   ├── unit/                # Unit tests (one file per module)
│   ├── integration/         # Integration tests using sample files
│   └── fixtures/            # Small sample files for tests (no real patient data)
├── configs/                 # YAML / JSON pipeline configuration files
├── pyproject.toml
└── README.md
```

### Key architectural decisions

- **Adapter pattern** — each document format (DICOM, CSV, plain text) has its own loader and writer. Adding a new format means implementing a new adapter, not touching the engine.
- **Taxonomy-agnostic** — the pipeline never hardcodes PII categories. It consumes an externally provided `IdentifierSchema` (Pydantic model) at runtime.
- **Separation of concerns** — document model, injection logic, and validation are fully independent and communicate only through well-defined Pydantic models.
- **Reproducibility** — all randomness is seeded. Identical config + seed always produces identical output.
- **Ground truth as artifact** — injection annotations are written to a versioned JSONL sidecar, never embedded in the output document.

---

## Setup

### Prerequisites

- Python 3.13
- [uv](https://github.com/astral-sh/uv) — install via `pip install uv` or see the [uv docs](https://github.com/astral-sh/uv#installation)

### Install

```bash
# Clone the repository
git clone <repo-url>
cd InjectionPipeline

# Create virtual environment and install all dependencies (including dev tools)
uv sync --extra dev
```

---

## Commands

### Tests

```bash
# Run all tests, stop on first failure
uv run pytest tests/ -x

# Run all tests with coverage report
uv run pytest tests/ --cov=src/injection_pipeline

# Run only unit tests
uv run pytest tests/unit/

# Run only integration tests
uv run pytest tests/integration/
```

### Linting & Formatting

```bash
# Check for lint errors
uv run ruff check src/ tests/

# Auto-fix lint errors
uv run ruff check src/ tests/ --fix

# Format code
uv run ruff format src/ tests/

# Check formatting without applying changes
uv run ruff format src/ tests/ --check
```

### Type Checking

```bash
uv run mypy src/
```

### Run everything (lint + types + tests)

```bash
uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest tests/ -x
```

---

## Configuration

Pipeline runs are configured via YAML files in `configs/`. Pass the config path as an argument when invoking the pipeline:

```bash
uv run python -m injection_pipeline --config configs/default.yaml
```

> Configuration format is not yet finalized; this section will be updated as the config schema stabilizes.

---

## Output

Each pipeline run produces two artifacts:

| Artifact | Description |
|----------|-------------|
| Modified document | The input document with synthetic PII injected, written back to its original format |
| Annotation JSONL | Ground-truth record of every injection: position, identifier type, injected value, source identity |

---

## What This Project Is Not

- **Not a de-identification tool** - it does the inverse (injection, not removal)
- **Not responsible for defining PII categories** - those come from an external `IdentifierSchema`
- **Not a clinical system** - no real patient data is processed or generated
- **Not a web application** - this is a CLI / library pipeline

---

## Contributing

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- Branch naming: `feature/<short-description>`, `fix/<short-description>`
- Keep commits atomic — one logical change per commit
- Do not commit test data containing real patient information (MIMIC data stays in `.gitignore`)
