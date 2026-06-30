# DICOM/JPG Injection Pipeline

Operational documentation for the migrated DICOM/JPG injection path in
`src/injection_pipeline/`. The implementation preserves the prototype contract:
fixed DICOM tag injection, visible pixel injection, and
`ground_truth.json` schema `0.2.0-prototype`.

## Scope

- DICOM path: fixed tag injection plus visible pixel injection.
- JPG path: visible pixel injection only.
- Ground truth: prototype JSON file, schema `0.2.0-prototype`.
- Not in scope: final production schemas, taxonomy-agnostic model design, or
  de-identification.

## Run

```bash
uv run injection-pipeline
uv run injection-pipeline --seed 42 --rotation-angle 20
uv run injection-pipeline --seed 42 --font-family tahoma --font-size-pct 120 --text-background white
uv run injection-pipeline --seed 42 --rotation-angle 20 --show-label-boxes y
uv run injection-pipeline --input DycomData/images/faces-00a0d634ad200ced.jpg --seed 42 --rotation-angle 20
uv run injection-pipeline --handwriting-manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl --handwriting-asset patient_name=patient-name-001
```

`uv run python -m injection_pipeline ...` is equivalent. With no CLI arguments,
the command starts interactive mode. If at least one CLI argument is set and
`--input` is missing, the command chooses a local default file
non-deterministically from `DycomData/Dicom-Files` or `DycomData/images`. Pass
`--input` for repeatable input selection.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `--seed` | `42` | Seed for identity and layout choices |
| `--input` | random local default | DICOM or JPG source path |
| `--output-dir` | `output` | Root output directory |
| `--rotation-angle` | `0` | One of `0`, `20`, `90`, `180`, `270` |
| `--font-size-pct` | `100` | Font size percentage, minimum `1` |
| `--placement-mode` | `corners` | `corners` or `free` |
| `--font-family` | `arial` | `arial`, `calibri`, `tahoma`, `consolas` |
| `--text-background` | none | Optional `white` background |
| `--show-label-boxes` | `n` | Draw generic prefix boxes in blue |
| `--handwriting-manifest` | none | JSON or JSONL handwriting manifest |
| `--handwriting-asset` | none | Repeatable `identity_field=asset_id` mapping |

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

## Ground Truth

`ground_truth.json` uses schema `0.2.0-prototype`:

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

## Handwriting Assets

Generated handwriting assets live under `DycomData/HandwritingAssets/` and stay
out of git. The pipeline accepts JSON manifests with an `assets` list and JSONL
manifests with one asset per line.

Each asset needs:

- PNG image path
- ink mask path
- stable `asset_id`
- `text`
- `identity_field` or `field`
- `ink_color`: `black`, `gray`, or `white`
- `background_mode` or `background`: `transparent` or `white`

When `renderer_type = "handwriting_asset"`, the pipeline creates one box for
the full visible PII value. It does not create character, word-part, or prefix
boxes in v1.

The ScrabbleGAN tooling is a scaffold with a fake renderer and validation. Real
generation is currently blocked; see
`tools/handwriting/scrabblegan/UPSTREAM_REVIEW.md`.

## Validation State

Known frozen validation artifacts remain in gitignored
`prototypes/dicom/output_validation_*` folders:

- `output_validation_dcm_label_y`
- `output_validation_dcm_label_n`
- `output_validation_jpg`
- `output_validation_ap6_dcm_a`
- `output_validation_ap6_dcm_b`
- `output_validation_ap6_jpg`
- legacy `output_validation_small`, `output_validation_large`,
  `output_validation_main`

During migration, the DCM and JPG baseline runs matched the package entry point
after normalizing timestamp-derived `run_id` values and output-root folder
names. Pixel previews and injected DICOM/JPG artifacts were byte-identical.
