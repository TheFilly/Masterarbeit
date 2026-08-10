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
- Existing CLI scope: PDF-native free-text/table injection remains out of
  scope for `inject-pdf`; the `make_pdf` API below covers PDF-native text
  composition. De-identification remains out of scope.

## Run

```bash
uv run injection-pipeline
uv run injection-pipeline --seed 42 --rotation-angle 20
uv run injection-pipeline --seed 42 --rotation-angle 20 --run-timestamp 2026-07-10T12:00:00
uv run injection-pipeline --seed 42 --identifier-schema configs/identifier_schemas/dicom-prototype.json
uv run injection-pipeline --seed 42 --font-family tahoma --font-size-pct 120 --text-background white
uv run injection-pipeline --seed 42 --font-family handwriting
uv run injection-pipeline --seed 42 --rotation-angle 20 --show-label-boxes y
uv run injection-pipeline --input DicomData/images/faces-00a0d634ad200ced.jpg --seed 42 --rotation-angle 20
uv run injection-pipeline --handwriting-manifest DicomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl --handwriting-asset patient_name=patient-name-001
uv run injection-pipeline generate-handwriting --seed 42
uv run injection-pipeline inject-pdf --input-pdf DicomData/pdf/Briefmarken.1Stk.17.03.2026_1345.pdf --input-dicom DicomData/InjectedDicom/<run-id>/<source-stem>_injected.dcm --dicom-annotation DicomData/InjectedDicom/<run-id>/ground_truth.json
```

`uv run python -m injection_pipeline ...` is equivalent. With no CLI arguments,
the command starts interactive mode. If at least one CLI argument is set and
`--input` is missing, the command chooses a local default file from sorted
`DicomData/Dicom-Files` and `DicomData/images` candidates using the seeded
`input_selection` stream. Pass `--input` to replay the resolved file directly.
Pass `--run-timestamp` to make the run directory name deterministic. The
`--font-family handwriting` mode generates the Faker identity first,
looks up the corresponding asset bundle, generates missing assets through the
isolated ScrabbleGAN tooling, and then injects the assets. The standalone
`generate-handwriting --seed` command performs the same asset generation and
persistence without requiring an input document. Exact option names and the
cache identity are defined in `docs/scrabblegan-implementation-plan.md`.

## Public Python API

The DICOM/JPG pipeline also exposes a narrow Python API for callers that want
to perform exactly one controlled injection while letting the pipeline choose
the source file and layout details:

```python
from injection_pipeline import inject_function

injected_path, ground_truth_path = inject_function(
    category="Age",
    value="95",
    prefix="Patient is ",
    suffix=" years old",
    handwritten=False,
    documentType="jpg",
    output_dir="api-export",
)
```

Exact signature:

```python
from os import PathLike
from datetime import datetime
from pathlib import Path


def inject_function(
    category: str,
    value: str,
    prefix: str,
    suffix: str,
    handwritten: bool,
    documentType: str,
    output_dir: str | PathLike[str] | None = None,
    handwriting_ink_color: str = "auto",
    handwriting_contrast_mode: str = "none",
    *,
    seed: int | None = None,
    input_path: str | PathLike[str] | None = None,
    rotation_degrees: int | None = None,
    run_timestamp: datetime | None = None,
) -> tuple[Path, Path]: ...
```

Parameters:

| Parameter | Description |
|---|---|
| `category` | Freier Kategoriename als String. Der Wert erscheint in `ground_truth.json`. Native DICOM-Routen werden nur verwendet, wenn der Name case-insensitive eindeutig zu einem Identifier-Schema-Feldnamen oder einem DICOM-Keyword passt, zum Beispiel `patient_id` oder `PatientID`. Ambigue Kategorie-Labels wie `identifier` bleiben sichtbar/pixelbasiert. JPG schreibt nie DICOM-Tags. |
| `value` | PII-Wert als String, zum Beispiel `"95"`. |
| `prefix` | Nicht-PII-Text vor dem Wert. Leerzeichen muessen explizit im String stehen. |
| `suffix` | Nicht-PII-Text nach dem Wert. Leerzeichen muessen explizit im String stehen. |
| `handwritten` | `True` nutzt die Handwriting-Pipeline fuer den kompletten sichtbaren Text `prefix + value + suffix`; `False` nutzt den normalen Renderer. |
| `documentType` | Dokumenttyp, case-insensitive. Erlaubt sind `dcm` und `jpg`; `dcm` waehlt aus `DicomData/Dicom-Files`, `jpg` aus `DicomData/images` mit `.jpg` oder `.jpeg`. |
| `output_dir` | Optionales Exportverzeichnis. Wenn gesetzt, werden das injizierte Dokument und `ground_truth.json` dorthin kopiert. Andere vorhandene Dateien in diesem Ordner werden nicht bereinigt. |
| `handwriting_ink_color` | `auto`, `black`, `gray` oder `white`; gilt für Handschrift. |
| `handwriting_contrast_mode` | `none` oder `halo`; gilt für Handschrift. |
| `seed` | Optionaler Seed für deterministische Identität und Layout-Entscheidungen. Ohne Seed bleibt das Legacy-Verhalten nondeterministisch. |
| `input_path` | Optionaler expliziter DICOM-/JPG-Quellpfad. Ohne Pfad wird die Legacy-Zufallsauswahl verwendet. |
| `rotation_degrees` | Optionaler expliziter Winkel aus `0`, `20`, `90`, `180`, `270`. |
| `run_timestamp` | Optionaler Timestamp für reproduzierbare Run-IDs. |

The visible text is rendered as `prefix + value + suffix`; the API does not add
spaces or separators. The call creates only this one injection. The source
document is selected randomly from the local default candidates when
`input_path` is omitted. Rotation remains random when neither `seed` nor
`rotation_degrees` is supplied. Passing the optional deterministic parameters
enables replay without changing the legacy defaults.
Invalid parameters, unsupported document types, missing default input folders,
or missing candidate files raise `ValueError`.

`handwritten=True` requires the same runtime setup as the CLI handwriting mode:
the ScrabbleGAN source checkout/copy, generator checkpoint, options sidecar,
and Docker image or compatible runtime override must be available. Missing
handwriting prerequisites fail the run instead of falling back to a normal
font.

Every API call still writes the full run directory below `output/<run-id>/`:

```text
output/<run-id>/
|-- <source-stem>_injected.dcm  # or *_injected.jpg
|-- ground_truth.json
|-- preview.png
|-- preview_annotated.png
`-- run_manifest.json
```

When `output_dir` is provided, the function additionally exports only the
injected document and `ground_truth.json` to that directory. This is copy-only
semantics: existing unrelated files in `output_dir` are left in place. The
return value is the tuple `(injected_path, ground_truth_path)`, so callers can
load the artifacts without scanning either directory.

### `make_pdf` API

`make_pdf` is the public Python API for composing several already injected
images and several PDF text injections into one PDF. It is separate from
`inject_function`: `inject_function` creates one DICOM/JPG injection, while
`make_pdf` receives already injected image artifacts and PDF text specs and
writes a composed PDF plus annotations.

```python
from injection_pipeline import (
    PdfMakeArtifacts,
    PdfMakeImageAnnotationInput,
    PdfMakeImageInput,
    PdfMakeTextInput,
    make_pdf,
)

artifacts = make_pdf(
    images=[
        PdfMakeImageInput(
            path="patient-card.png",
            annotations=[
                PdfMakeImageAnnotationInput(
                    category="patient_name",
                    value="Jane Doe",
                    prefix="Name: ",
                    suffix="",
                    rendered_text="Name: Jane Doe",
                    image_corners=[
                        {"x": 20, "y": 30},
                        {"x": 180, "y": 30},
                        {"x": 180, "y": 55},
                        {"x": 20, "y": 55},
                    ],
                )
            ],
        )
    ],
    texts=[
        PdfMakeTextInput(
            category="patient_id",
            value="PID-123",
            prefix="ID: ",
            suffix="",
            handwritten=False,
        )
    ],
    pdf="template.pdf",
    output_dir="api-pdf-export",
    seed=42,
)
```

The exported signature is:

```python
def make_pdf(
    images: Sequence[PdfMakeImageInput | Mapping[str, object]],
    texts: Sequence[PdfMakeTextInput | Mapping[str, object]],
    pdf: str | PathLike[str],
    output_dir: str | PathLike[str],
    *,
    seed: int | None = None,
) -> PdfMakeArtifacts: ...
```

Parameters:

| Parameter | Description |
|---|---|
| `images` | Required list of already injected images plus their image-space annotations. The composer embeds the images and maps each annotation to final PDF page coordinates. `BoxAnnotation`-style dictionaries are accepted: `label` -> `category`, `text` -> `value`, and `corners` -> `image_corners`; legacy prefix and suffix corners are preserved when available. |
| `texts` | Required list of PDF text injections. Each entry uses the same meaning as `inject_function`'s `category`, `value`, `prefix`, `suffix`, and `handwritten`, but has no output path. |
| `pdf` | Required input PDF template. Source pages are preserved and additional pages may be appended when needed. |
| `output_dir` | Required directory for the generated PDF, annotated PDF, and annotation sidecar. |
| `seed` | Optional reproducibility seed for automatic placement, page breaks, and image rotation. It does not generate or change text contents. |

Normal text entries are rendered as PDF-native text. `handwritten=True` for
direct PDF text aborts with a clear error because the API has no safe
handwriting asset or manifest source for that case. Already rendered
handwriting is passed as an image plus annotation. The layout engine avoids
overlap between image and text placements, mixes beside-each-other and stacked
arrangements, and rotates images by a seedable small angle where selected by
the layout. If the current page cannot fit the remaining items, the composer
appends another page. Invalid inputs, malformed annotations, impossible
placements, or unsupported handwriting requests abort with a clear error.

The return object is `PdfMakeArtifacts`. It exposes the generated clean PDF,
the visibly annotated PDF, the JSON sidecar, and the final placement metadata.
The files are written as `pdf_make.pdf`, `pdf_make_annotated.pdf`, and
`pdf_make_annotations.json` under `output_dir`. The sidecar records source
image annotations after transformation into PDF coordinates, PDF-native text
annotations, page indices, rotations, and the seed/layout metadata needed for
reproduction. Image annotations include main quads and optional prefix/suffix
quads when the source annotation provides them.

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
| `--handwriting-ink-color` | `auto` | `auto`, `black`, `gray`, `white`; render-time handwriting color |
| `--handwriting-contrast-mode` | `none` | `none` or `halo`; auto can enable a halo when needed |
| `--show-label-boxes` | `n` | Draw generic prefix boxes in blue |
| `--run-timestamp` | current time | Optional ISO-8601 timestamp used in `run_id` |
| `--handwriting-manifest` | none | Explicit JSON or JSONL handwriting manifest (compatibility path) |
| `--handwriting-asset` | none | Repeatable explicit `identity_field=asset_id` mapping (compatibility path) |
| `--handwriting-asset-root` | `DicomData/HandwritingAssets` | Persistent cache root for generated assets |
| `--handwriting-checkpoint` | `DicomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth` | ScrabbleGAN generator checkpoint |
| `--handwriting-checkpoint-sha256` | auto-hash local file | Expected checkpoint SHA-256 |
| `--handwriting-options-json` | checkpoint-adjacent sidecar | Optional options sidecar; otherwise `options.json`, `test_opt.json`, `train_opt.json`, `test_opt.txt`, or `train_opt.txt` next to the checkpoint |
| `--handwriting-source-dir` | `DicomData/HandwritingAssets/scrabblegan/source` | Official Amazon source checkout or source copy |
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

The current DICOM writer contract accepts only little-endian `uint8` input with
`MONOCHROME2` or `RGB` photometry. Unsupported 16-bit, big-endian, and other
photometric representations fail before an output directory is created. For
Multi-Frame-DICOM, only Frame 0 is currently injected and recorded; injection
of all frames is reserved for a future explicit policy.

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

This existing CLI remains the DICOM-to-PDF adapter. The public `make_pdf` API
extends the PDF composition use case to multiple already injected images plus
direct PDF-native text entries in a single output PDF. Already rendered
handwriting is included through image inputs and their annotations.

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

Visible annotations include final rotated `corners`. `text` is the injected
PII value, while `rendered_text` is the complete visible string. The JSON keeps
the compatible `label` and `label_corners` fields and adds `category`,
`prefix`, `suffix`, `prefix_corners`, and `suffix_corners`. For generic
prefixes such as `SYNTH-` and `ACC-`, `label_corners` and `prefix_corners`
store the prefix box; fields without prefixes use `null`. DICOM tag
annotations include `category` when the tag comes from a schema field.

`render_metadata` records:

- `geometry_source = "mask_bbox_after_final_rotation"`
- `mask_alpha_threshold`
- text, PII, label, and rendered-text mask bounds
- prefix and suffix mask bounds when those segments exist
- for handwriting assets: `renderer_type = "handwriting_asset"`, `asset_id`,
  `asset_path`, `mask_path`, `ink_color`, `background_mode`, and
  `geometry_source = "transformed_ink_mask"`

`run_manifest.json` currently contains the same record as `ground_truth.json`.
`ground_truth.json` keeps the prototype trailing newline; `run_manifest.json`
does not. ADR-0004 records this compatibility detail.

## Handwriting Assets

Generated handwriting assets live under `DicomData/HandwritingAssets/` and stay
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

The generator's image color and background are legacy presentation metadata.
The current renderer treats the separate mask as canonical and reconstructs
the visible ink at render time, so changing the render color does not require
a second generated asset or cache entry. The selected color, actual contrast
mode, luminance statistics, and decision reason are recorded in annotation
metadata.

When `renderer_type = "handwriting_asset"`, the pipeline records the full
visible handwritten text as `rendered_text` and keeps the PII value, prefix,
and suffix as separate annotation fields. Segment boxes are derived from the
asset ink mask so the full handwritten sentence is not silently labelled as
PII.

### Dynamic handwriting appearance

The handwriting PNG and its separate L-mask are treated as shape data. During
the final render pass, the pipeline samples only valid pixels below the final
rotated mask in the display-mapped RGB frame. Median luminance below `128`
selects white ink; luminance at or above `128` selects black ink. A p10-p90
spread above `96`, selected contrast below `64`, or fewer than eight valid
samples activates a two-pixel halo. If no samples are available, the
deterministic fallback is white ink with a black halo.

`--handwriting-ink-color black|gray|white` overrides automatic color choice.
`--handwriting-contrast-mode halo` always requests the halo, while `none`
allows automatic mode to add it only when needed. Halo pixels are not part of
the ground-truth ink mask or segment geometry. Legacy manifests remain
readable; their stored `ink_color` and `background` fields are retained as
provenance rather than controlling the new render-time color.

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
