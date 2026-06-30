# Migration Plan: prototypes/dicom -> src/injection_pipeline

Status: ready for implementation
Created: 2026-06-10
Scope: move the DICOM/JPG injection prototype out of `prototypes/dicom/` into the
`src/injection_pipeline/` package so the project leaves prototype mode.

## Decisions (already made - do not re-litigate)

1. **Depth:** Map code onto the existing package layout (`identity/`, `loaders/`,
   `engine/`, `writers/`, plus new `cli.py`/`runner.py`). Keep the dict-based data
   structures, the hardcoded five DICOM tags, and the `0.2.0-prototype` schema exactly
   as they are. The pydantic/taxonomy-agnostic redesign is Phase 2 work and explicitly
   **not** part of this migration.
2. **Prototype directory:** delete the `.py` files from `prototypes/dicom/` at the end
   (git history preserves them). Keep the local `output_validation_*` artifacts
   (gitignored, untouched). Update the READMEs to point at `src/`.
3. **Quality gate:** migrated code must pass `ruff check` and `ruff format`. mypy:
   fix only trivial annotation errors that cannot change behavior; for anything that
   would require logic changes, add a per-module `[[tool.mypy.overrides]]` entry with a
   `# TODO(phase-2): tighten typing` note instead.
4. **Dev deps:** running `uv sync --extra dev` is approved (pytest/ruff/mypy are
   declared but missing from `.venv`). No other dependency changes are allowed.

## Hard constraints

- **Behavior must stay identical.** Same CLI flags, same defaults, same interactive
  mode, same output files, same `ground_truth.json` content (modulo the
  timestamp-derived `run_id`). The only approved intentional change is the default
  output directory (see WP4).
- Pure code motion wherever possible. Do not "improve" logic, rename public functions,
  reorder operations, or change RNG usage while moving. Refactors that are not required
  for the move are out of scope.
- One work package = one atomic conventional commit (`refactor:`, `test:`, `docs:`).
  The test suite must be green after every commit.
- `tools/handwriting/scrabblegan/` and `tests/unit/test_scrabblegan_generator.py` are
  **out of scope** - they stay where they are.

## Target module mapping

| Source (prototypes/dicom/) | Target (src/injection_pipeline/) | Contents |
|---|---|---|
| `identity.py` | `identity/generator.py` | `generate_identity` unchanged |
| `dicom_writer.py` | `loaders/dicom.py` | `load_dicom`, `summarize_dicom` |
| `dicom_writer.py` | `engine/dicom_tags.py` | `inject_tags` |
| `dicom_writer.py` | `writers/dicom.py` | `save_dicom` |
| `pixel_injection.py` | `engine/pixel_injection.py` | whole module, unsplit (see note) |
| `view.py` | `writers/preview.py` | preview + annotated-preview rendering |
| `inject.py` | `runner.py` | orchestration: input resolution, run-id/output paths, tag map, render plans, `_run_pixel_injection`, `_run_jpg_pixel_injection`, `_build_record`, `_make_json_safe`, `_attach_dicom_contexts`, handwriting manifest/asset handling |
| `inject.py` | `cli.py` | argparse setup, `_parse_int`, `_validate_*`, all `_prompt_*`, `_collect_interactive_args`, `_validate_args`, `main()` |

Notes:
- `pixel_injection.py` (~1100 lines) moves **as one module**. Do not split it in this
  migration; splitting is a candidate follow-up once equivalence is proven. Minimizing
  diff size beats file-size aesthetics here.
- Re-export the public names in each subpackage `__init__.py` (e.g.
  `from injection_pipeline.identity import generate_identity`) so imports stay short.
- Where exactly the `inject.py` private helpers land (cli vs runner) may be adjusted if
  the seam above turns out wrong in detail - the rule is: everything argparse/prompt/
  validation-of-CLI-strings goes to `cli.py`, everything that does work goes to
  `runner.py`, and `main()` stays a thin wrapper.

## Work packages

### WP0 - Environment and baseline capture (no code changes)

1. `uv sync --extra dev`; confirm `uv run pytest tests/ -x` passes. Record any tests
   that already fail **before** the migration (they are not regressions).
2. Capture equivalence baselines with the *current* prototype. Pick one local `.dcm`
   and one local `.jpg` that exist under `DycomData/` (e.g. the files used in the
   `output_validation_*` runs) and run:

   ```bash
   uv run python prototypes/dicom/inject.py --input <DCM> --seed 42 --rotation-angle 20 --show-label-boxes y --output-dir prototypes/dicom/output_migration_baseline
   uv run python prototypes/dicom/inject.py --input <DCM> --seed 7 --font-family tahoma --font-size-pct 120 --text-background white --output-dir prototypes/dicom/output_migration_baseline
   uv run python prototypes/dicom/inject.py --input <JPG> --seed 42 --rotation-angle 20 --output-dir prototypes/dicom/output_migration_baseline
   ```

   (Directory is covered by the existing `prototypes/dicom/output*/` gitignore rule.)
3. If local handwriting assets exist under `DycomData/HandwritingAssets/`, add one
   handwriting-manifest run to the baseline; otherwise note that the handwriting path
   is covered by `tests/unit/test_handwriting_asset_rendering.py` only.

### WP1 - Move identity + DICOM I/O (`refactor:`)

1. Create `identity/generator.py`, `loaders/dicom.py`, `engine/dicom_tags.py`,
   `writers/dicom.py` per the mapping table (pure copy, plus docstrings/imports).
2. Update `prototypes/dicom/inject.py` to import these from `injection_pipeline.*`
   (the package is installed editable, so this works while the prototype still exists).
3. Delete `prototypes/dicom/identity.py` and `prototypes/dicom/dicom_writer.py`.
4. Preserve the `if __name__ == "__main__"` demo block of `identity.py` in the new
   module.
5. Gate: `uv run pytest tests/ -x` green.

### WP2 - Move pixel_injection (`refactor:`)

1. Move `pixel_injection.py` -> `engine/pixel_injection.py` unchanged (module-level
   constants, font handling, everything).
2. Update imports in `prototypes/dicom/inject.py`, `prototypes/dicom/view.py`, and
   `tests/unit/test_pixel_injection_corners.py` +
   `tests/unit/test_handwriting_asset_rendering.py` (remove the `sys.path.insert`
   hacks; import `injection_pipeline.engine.pixel_injection`).
3. Gate: pytest green; spot-check one baseline command still reproduces (run via the
   prototype `inject.py`, compare `ground_truth.json` per the protocol below).

### WP3 - Move view (`refactor:`)

1. Move `view.py` -> `writers/preview.py`; its `from pixel_injection import
   extract_preview_frame` becomes a package import. Keep its `main()`/argparse so
   `uv run python -m injection_pipeline.writers.preview` works as `view.py` did.
2. Update the import in `prototypes/dicom/inject.py`; delete `prototypes/dicom/view.py`.
3. The module-level `DEFAULT_PREVIEW_PATH` keeps pointing at the prototype output dir
   until WP4 changes the default output root; change both together in WP4, not here.
4. Gate: pytest green.

### WP4 - Split inject.py into cli.py + runner.py, entry point (`refactor:`)

1. Create `runner.py` and `cli.py` per the mapping table. `main()` in `cli.py` must
   reproduce the existing behavior exactly, including: interactive mode when invoked
   with zero CLI args, the nondeterministic default-input selection when `--input` is
   omitted but other args are present, and all validation error messages.
2. Add the console script to `pyproject.toml`:

   ```toml
   [project.scripts]
   injection-pipeline = "injection_pipeline.cli:main"
   ```

   plus a package `__main__.py` so `uv run python -m injection_pipeline` also works.
3. **Single approved behavior change:** default `--output-dir` moves from
   `prototypes/dicom/output` to `output/` (repo root). Update
   `DEFAULT_PREVIEW_PATH` in `writers/preview.py` accordingly and add `output/` to
   `.gitignore`. Everything else (DycomData default input dirs, run-folder naming,
   schema version) stays identical.
4. Update `tests/unit/test_inject_default_input.py` and
   `tests/unit/test_handwriting_asset_rendering.py` to import from
   `injection_pipeline.runner` / `injection_pipeline.cli` (no `sys.path` hacks).
5. Delete `prototypes/dicom/inject.py`.
6. Gate: pytest green; full equivalence check (protocol below) against the WP0
   baseline using `uv run injection-pipeline ...`.

### WP5 - Lint/type gate (`refactor:` or `fix:`)

1. `uv run ruff check src/ tests/` and `uv run ruff format src/ tests/` must pass.
   Allowed mechanical fixes: import sorting, line length, `UP`/`SIM` autofixes -
   nothing that alters behavior (be careful with `SIM` rules; prefer `--fix` only for
   safe rules, review every change).
2. `uv run mypy src/`: fix trivial, behavior-neutral annotation gaps. For modules that
   would need real changes to satisfy strict mode, add per-module overrides in
   `pyproject.toml`, e.g.:

   ```toml
   [[tool.mypy.overrides]]
   module = "injection_pipeline.engine.pixel_injection"
   # TODO(phase-2): tighten typing when the document model replaces dict payloads
   disallow_any_explicit = false
   warn_return_any = false
   ```

   (Pick the minimal set of relaxations that makes mypy pass; `ignore_errors = true`
   only as last resort.)
3. Gate: pytest, ruff, mypy all green; re-run one baseline equivalence check (lint
   autofixes are the classic source of silent behavior change).

### WP6 - Docs and cleanup (`docs:`)

1. Move the operational content of `prototypes/dicom/README.md` (parameters table,
   handwriting-asset contract, output schema, annotation format) to
   `docs/dicom-injection.md`, with all commands rewritten to
   `uv run injection-pipeline ...`. Keep the validation-state section.
2. Replace `prototypes/dicom/README.md` with a short stub: code moved to
   `src/injection_pipeline/` (commit reference), local `output_validation_*` folders
   remain as frozen reference artifacts.
3. Update `prototypes/README.md` and `prototypes/prototype_plan.md`: prototype
   concluded and migrated; open work packages 1+2 (annotation schema, Phase-2
   handover) carry over to PLAN.md/Phase 2 - do not silently drop them.
4. Update `PLAN.md` ("Aktueller Stand") and the AGENTS.md "Current project state"
   section: prototype code now lives in `src/injection_pipeline/`, entry point
   `injection-pipeline`.
5. Delete this `MIGRATION_PLAN.md` in the final commit or move it to
   `docs/archive/` once the migration is verified.

### WP7 - Final verification (reviewer gate)

1. `uv run pytest tests/ --cov=src/injection_pipeline` - green.
2. `uv run ruff check src/ tests/`, `uv run mypy src/` - green.
3. Full equivalence protocol against the WP0 baseline (all baseline commands).
4. One manual interactive-mode smoke test (`uv run injection-pipeline` with no args,
   answer the prompts) - DCM and JPG each once.
5. Reviewer agent reviews the branch against main with focus on: unintended logic
   diffs (the diff should be almost pure code motion), import correctness, test
   coverage parity, and the equivalence evidence.

## Equivalence protocol (used in WP2, WP4, WP5, WP7)

For each baseline command, re-run with identical `--seed`/`--input`/flags via the new
entry point, then compare new run folder vs. baseline run folder:

1. `ground_truth.json`: must be identical after normalizing the timestamp-derived
   parts - the `{ddmmyyyy}-{hhmm}` segment inside `run_id` (and anywhere `run_id`
   is embedded, e.g. `run_metadata`). Everything else - `box_annotations`,
   `label_corners`, `dicom_tag_annotations`, `render_metadata`, seeds - must match
   exactly, including float values.
2. `run_manifest.json`: identical after the same run-id/timestamp normalization.
3. `preview.png`, `preview_annotated.png`, `*_injected.dcm` / `*_injected.jpg`:
   byte-identical (timestamps live only in folder/run-id names, not in the artifacts;
   if a DICOM turns out to embed a generation timestamp, normalize that one tag and
   document it).
4. Write a tiny comparison script for this in a scratch location (not committed) or
   do it with python one-liners; record the result in the final commit message or PR
   description.

## Risk notes for the implementer

- `inject.py`'s interactive mode triggers on `len(sys.argv) == 1` semantics - preserve
  exactly, including prompt wording and defaults.
- All default paths (`DycomData/...`, output dirs) are CWD-relative and assume the
  repo root as working directory. Keep them CWD-relative; do not "fix" them to be
  module-relative.
- Seeding is explicit (`generate_identity(seed)`, seeded placement). Pure code motion
  must not touch any `random`/Faker call order. If you find yourself reordering calls,
  stop - that changes outputs.
- The five-tag map, `SYNTH-`/`ACC-` prefixes, and schema version `0.2.0-prototype`
  are frozen prototype contracts. Do not rename, generalize, or version-bump them.
- Tests currently green-light the prototype via `sys.path` hacks; after each WP the
  affected test file must import the new package path - never both.
