# DICOM/JPG/PDF Injection Pipeline

Operational documentation for the migrated DICOM/JPG injection paths and the
PDF adapter in
`src/injection_pipeline/`. The implementation preserves the prototype contract:
schema-driven DICOM tag injection, visible pixel injection, and
`ground_truth.json` schema `0.2.0-prototype`.

## Scope

- DICOM path: schema-defined tag injection plus visible pixel injection.
- JPG path: visible pixel injection only.
- Ground truth: prototype JSON file, schema `0.2.0-prototype`.
- Current architecture: pydantic run models, an external identifier schema,
  split runner/engine stages, and registered DCM/JPG loader/writer adapters.
- PDF path: a PDF template plus an already injected DICOM and its JSON
  annotation are loaded by the PDF adapter; a new PDF and PDF annotation
  sidecar are written. The input files remain unchanged.
- Not in scope: PDF-native free-text/table injection or de-identification.

## Run

```bash
uv run injection-pipeline
uv run injection-pipeline --seed 42 --rotation-angle 20
uv run injection-pipeline --seed 42 --rotation-angle 20 --run-timestamp 2026-07-10T12:00:00
uv run injection-pipeline --seed 42 --identifier-schema configs/identifier_schemas/dicom-prototype.json
uv run injection-pipeline --seed 42 --font-family tahoma --font-size-pct 120 --text-background white
uv run injection-pipeline --seed 42 --font-family handwriting
uv run injection-pipeline --seed 42 --rotation-angle 20 --show-label-boxes y
uv run injection-pipeline --input DycomData/images/faces-00a0d634ad200ced.jpg --seed 42 --rotation-angle 20
uv run injection-pipeline --handwriting-manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl --handwriting-asset patient_name=patient-name-001
uv run injection-pipeline generate-handwriting --seed 42
uv run injection-pipeline inject-pdf --input-pdf DycomData/pdf/Briefmarken.1Stk.17.03.2026_1345.pdf --input-dicom DycomData/InjectedDicom/<run-id>/<source-stem>_injected.dcm --dicom-annotation DycomData/InjectedDicom/<run-id>/ground_truth.json
```

`uv run python -m injection_pipeline ...` is equivalent. With no CLI arguments,
the command starts interactive mode. If at least one CLI argument is set and
`--input` is missing, the command chooses a local default file from sorted
`DycomData/Dicom-Files` and `DycomData/images` candidates using the seeded
`input_selection` stream. Pass `--input` to replay the resolved file directly.
Pass `--run-timestamp` to make the run directory name deterministic. The
`--font-family handwriting` mode generates the Faker identity first,
looks up the corresponding asset bundle, generates missing assets through the
isolated ScrabbleGAN tooling, and then injects the assets. The standalone
`generate-handwriting --seed` command performs the same asset generation and
persistence without requiring an input document. Exact option names and the
cache identity are defined in `docs/scrabblegan-implementation-plan.md`.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `--seed` | `42` | Seed for identity and layout choices |
| `--input` | random local default | DICOM or JPG source path |
| `--output-dir` | `output` | Root output directory |
| `--identifier-schema` | `configs/identifier_schemas/dicom-prototype.json` | External identifier schema JSON |
| `--rotation-angle` | `0` | One of `0`, `20`, `90`, `180`, `270` |
| `--font-size-pct` | `100` | Font size percentage, minimum `1` |
| `--placement-mode` | `corners` | `corners` or `free` |
| `--font-family` | `arial` | `arial`, `calibri`, `tahoma`, `consolas`, `handwriting` |
| `--text-background` | none | Optional `white` background |
| `--show-label-boxes` | `n` | Draw generic prefix boxes in blue |
| `--run-timestamp` | current time | Optional ISO-8601 timestamp used in `run_id` |
| `--handwriting-manifest` | none | Explicit JSON or JSONL handwriting manifest (compatibility path) |
| `--handwriting-asset` | none | Repeatable explicit `identity_field=asset_id` mapping (compatibility path) |
| `--handwriting-asset-root` | `DycomData/HandwritingAssets` | Persistent cache root for generated assets |
| `--handwriting-checkpoint` | `DycomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth` | ScrabbleGAN generator checkpoint |
| `--handwriting-checkpoint-sha256` | auto-hash local file | Expected checkpoint SHA-256 |
| `--handwriting-options-json` | checkpoint-adjacent sidecar | Optional options sidecar; otherwise `options.json`, `test_opt.json`, `train_opt.json`, `test_opt.txt`, or `train_opt.txt` next to the checkpoint |
| `--handwriting-source-dir` | `DycomData/HandwritingAssets/scrabblegan/source` | Official Amazon source checkout or source copy |
| `--handwriting-upstream-commit` | source `.git_commit` or Git HEAD | Pinned upstream commit recorded in manifests |
| `--handwriting-runtime-command` | automatic Docker runtime | Optional host-side runtime override; default starts the configured Docker image |
| `--handwriting-container-image` | `injection-scrabblegan` | Docker image used on cache misses |
| `--handwriting-generator-command` | built-in `generate_single.py` wrapper | Optional single-text generator command template |

In interactive mode, the seed prompt is followed immediately by one common
font-family/renderer choice, then input/schema and the remaining rotation,
size, placement, background, label-box, and timestamp parameters follow that
choice. Normal font choices keep the existing Pillow path; `handwriting`
selects automatic asset lookup/generation for the visible fields
`patient_name`, `patient_id`, and `accession_number`.

## Identifier Schema and Determinism

The default schema lives at `configs/identifier_schemas/dicom-prototype.json`.
It defines the five prototype identity fields, Faker recipes, DICOM routes,
visible-pixel routes, synthetic prefixes, and visible line order. `--identifier-schema`
can point at another schema file; the E2E suite includes a two-field toy schema
run to prove this path does not require code changes.

The schema fixes `generator.reference_date = "2026-07-10"` with
`reference_date_policy = "faker-date_of_birth-reference-v1"`. Date-sensitive
Faker recipes use that date instead of the execution day, so `PatientBirthDate`
stays stable for a fixed seed.

Randomness uses the run seed plus named streams where the prototype contract
allows it:

- `identity_a`: direct Faker seeding with `--seed`
- default input choice: derived `input_selection` stream over sorted candidates
- placement: grandfathered raw seed for byte compatibility
- run clock: current time unless `--run-timestamp` is set

## Outputs

Runs are written under the configured output root:

```text
output/
`-- dcm-27052026-1435-seed0042-angle020-corners-fs100-arial-none/
    |-- 91180014_0001_injected.dcm
    |-- ground_truth.json
    |-- preview.png
    |-- preview_annotated.png
    `-- run_manifest.json
```

JPG runs use the same structure and write `*_injected.jpg`. Existing older
prototype output folders remain unchanged as local validation artifacts.

The runner loads the source through `loaders/registry.py`, which resolves DICOM
and JPG adapters by extension. DICOM writes through `writers/dicom.py`; JPG
writes through `writers/jpg.py`. Adding another injected source format should
use a loader/writer pair and registry entry, not a new runner branch.

## PDF injection

The PDF command requires three inputs: `--input-pdf`, `--input-dicom`, and
`--dicom-annotation`. Optional flags are `--output-dir`, `--slot`, and
`--page-index`. `compose-pdf` is retained as an equivalent command alias.
The PDF loader validates template pages; the DICOM annotation is parsed by the
canonical `RunRecord` loader. The PDF writer resolves the `preview_file` named
by that `RunRecord` (relative paths are resolved beside the annotation), embeds
that preview associated with the injected DICOM frame, transforms image-space
annotation corners to PDF points, and writes:

```text
output/pdf/<run_id>/<template-stem>-<slot>/
|-- pdf_injected.pdf
|-- pdf_injected_annotated.pdf
|-- pdf_annotations.json
```

The sidecar uses schema `0.3.0-pdf-prototype` in the ADR-0008 lineage. PDF
points use a bottom-left origin and image points use a top-left pixel origin;
aspect-fit mapping uses the actual placement rectangle. Source PDF, DICOM, and
JSON files are never overwritten.

## Ground Truth

`ground_truth.json` uses schema `0.2.0-prototype`. The pipeline builds it as a
pydantic `RunRecord` and serializes it with `model_dump(mode="json")`:

```json
{
  "schema_version": "0.2.0-prototype",
  "record_type": "dcm_injection_run",
  "run_id": "dcm-27052026-1435-seed0042-angle020-corners-fs100-arial-none",
  "seed": 42,
  "rotation_degrees": 20,
  "document_type": "dcm",
  "box_annotations": [],
  "dicom_tag_annotations": [],
  "run_metadata": {},
  "render_metadata": {}
}
```

For JPG runs:

- `record_type = "jpg_injection_run"`
- `document_type = "jpg"`
- `dicom_tag_annotations = []`
- DICOM context fields are absent from `run_metadata`

Visible annotations include final rotated `corners`. For generic prefixes such
as `SYNTH-` and `ACC-`, `label_corners` stores the prefix box; fields without
prefixes use `null`.

`render_metadata` records:

- `geometry_source = "mask_bbox_after_final_rotation"`
- `mask_alpha_threshold`
- text, PII, label, and rendered-text mask bounds
- for handwriting assets: `renderer_type = "handwriting_asset"`, `asset_id`,
  `asset_path`, `mask_path`, `ink_color`, `background_mode`, and
  `geometry_source = "transformed_ink_mask"`

`run_manifest.json` currently contains the same record as `ground_truth.json`.
`ground_truth.json` keeps the prototype trailing newline; `run_manifest.json`
does not. ADR-0004 records this compatibility detail.

## Handwriting Assets

Generated handwriting assets live under `DycomData/HandwritingAssets/` and stay
out of git. The pipeline accepts JSON manifests with an `assets` list and JSONL
manifests with one asset per line. The integrated handwriting mode uses the
same manifest contract as the explicit compatibility path, but adds a cache
lookup after Faker identity generation. If the cache does not contain a
compatible asset for a selected identity value, the isolated ScrabbleGAN
runtime starts automatically, creates the image and mask, writes the manifest,
and the runner uses that asset immediately. If the runtime, checkpoint, options
sidecar, `.git_commit`/Git checkout metadata, or generator command is missing,
the run fails; it does not fall back to a normal font.

Each asset needs:

- PNG image path
- ink mask path
- stable `asset_id`
- `text`
- `identity_field` or `field`
- `ink_color`: `black`, `gray`, or `white`
- `background_mode` or `background`: `transparent` or `white`
- checkpoint SHA-256, ScrabbleGAN commit, generator manifest hash, and
  `generator_options_sha256`/`options_sha256` metadata for cache identity

When `renderer_type = "handwriting_asset"`, the pipeline creates one box for
the full visible PII value. It does not create character, word-part, or prefix
boxes in v1.

The ScrabbleGAN tooling has the host-side provider/cache path, automatic Docker
runtime wiring, fake renderer validation, option-sidecar hashing, and hard
prerequisite checks. The real Docker/upstream checkpoint path was verified on
2026-07-15 with three generated assets, manifest validation, cache reuse, and a
full DICOM injection; see `tools/handwriting/scrabblegan/UPSTREAM_REVIEW.md`.

## Local Gates

The committed E2E harness generates synthetic DCM/JPG fixtures, runs the
pipeline with seed `42`, rotation `20`, default schema, fixed timestamp
`2026-07-10T12:00:00`, and a deterministic test font, then compares artifact
hashes for:

- injected document
- `ground_truth.json`
- `run_manifest.json`
- `preview.png`
- `preview_annotated.png`

CI installs `fonts-liberation2` (the Linux `arial` fallback font Pillow needs
for tests that do not pin a fixture font), then runs
`uv sync --locked --all-extras`, `uv run ruff check src/ tests/`,
`uv run mypy src/`, and `uv run pytest tests/ -x` on push and pull request.

## Validation State

No local `prototypes/dicom/output_validation_*` reference set is currently
present. Regression validation therefore uses the committed synthetic DCM/JPG
fixtures and full-artifact hashes in `tests/integration/test_end_to_end.py`.

The E2E harness passes a fixed timestamp and compares complete artifact bytes,
including `ground_truth.json` and `run_manifest.json`. The DCM/JPG output
hashes changed once because `PatientBirthDate` used the schema reference date
instead of Faker's execution day, and again on 2026-07-14 because
`date_of_birth` stopped calling Faker's own `date_of_birth()`/`date_time_ad()`
(their internal OS branch made the birth date, and therefore these hashes,
differ between Windows and Linux for the same seed — see
`docs/architecture/determinism-audit.md` N14). `ground_truth.json`,
`run_manifest.json`, and both preview PNGs are pinned to the bytes produced on
CI (ubuntu-latest): their rendered content is byte-identical across platforms,
but the raw file bytes are not (JSON embeds `os.linesep`; PNGs are re-encoded
by a platform-specific Pillow/matplotlib build). See
`docs/architecture/determinism-audit.md` N8/N9.

As of 2026-07-15, 44 focused handwriting tests pass, `uv run ruff check
src/ tests/` passes, and `uv run mypy src/` passes. The complete frozen-hash
test remains locally red only for the known Windows JSON/PNG byte differences;
the DCM/JPG pixel artifacts remain identical.
