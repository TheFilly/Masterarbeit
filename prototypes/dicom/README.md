# DICOM/JPG Injection Prototype

Quick feasibility prototype for synthetic PII injection in medical image
artifacts. The code still lives in `prototypes/dicom/`; `MIGRATION_PLAN.md`
describes the planned move into `src/injection_pipeline/`.

## Scope

- DICOM path: fixed tag injection plus visible pixel injection.
- JPG path: visible pixel injection only.
- Ground truth: prototype JSON file, schema `0.2.0-prototype`.
- Not in scope: final production schemas, taxonomy-agnostic model design, or the
  future package entry point.

## Current Behavior

- Injects five DICOM tags.
- Renders visible values for `PatientName`, `PatientID`, and
  `AccessionNumber`.
- Leaves `PatientBirthDate` and `PatientSex` as tag-only fields.
- Supports `.dcm`, `.jpg`, and `.jpeg`.
- Supports seeded placement, rotation, font family, font size, optional white
  text background, optional label boxes, and handwriting assets.
- Derives `corners` and `label_corners` from final rotated masks.
- Uses `label_corners` for generic prefixes such as `SYNTH-` and `ACC-`; fields
  without prefixes use `null`.

## Run

```bash
uv run python prototypes/dicom/inject.py
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 20
uv run python prototypes/dicom/inject.py --seed 42 --font-family tahoma --font-size-pct 120 --text-background white
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 20 --show-label-boxes y
uv run python prototypes/dicom/inject.py --input DycomData/images/faces-00a0d634ad200ced.jpg --seed 42 --rotation-angle 20
uv run python prototypes/dicom/inject.py --handwriting-manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl --handwriting-asset patient_name=patient-name-001
```

With no CLI arguments, the script starts interactive mode. If at least one CLI
argument is set and `--input` is missing, the script chooses a local default file
non-deterministically from `DycomData/Dicom-Files` or `DycomData/images`. Pass
`--input` for repeatable input selection.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `--seed` | `42` | Seed for identity and layout choices |
| `--input` | random local default | DICOM or JPG source path |
| `--output-dir` | `prototypes/dicom/output` | Root output directory |
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
prototypes/dicom/output/
`-- dcm-27052026-1435-seed0042-angle020-corners-fs100-arial-none/
    |-- 91180014_0001_injected.dcm
    |-- ground_truth.json
    |-- preview.png
    |-- preview_annotated.png
    `-- run_manifest.json
```

JPG runs use the same structure and write `*_injected.jpg`. Existing older
output folders are left unchanged.

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

Typical visible annotation with a generic prefix:

```json
{
  "label": "PatientID",
  "text": "433218",
  "rendered_text": "SYNTH-433218",
  "region": "top_left",
  "corners": [
    {"x": 107.14, "y": 139.8},
    {"x": 174.8, "y": 115.17},
    {"x": 180.27, "y": 130.21},
    {"x": 112.62, "y": 154.83}
  ],
  "label_corners": [
    {"x": 52.31, "y": 159.84},
    {"x": 104.56, "y": 140.82},
    {"x": 110.03, "y": 155.85},
    {"x": 57.78, "y": 174.87}
  ],
  "rotation_degrees": 20,
  "frame_index": 0,
  "font_size_pct": 120
}
```

`render_metadata` records:

- `geometry_source = "mask_bbox_after_final_rotation"`
- `mask_alpha_threshold`
- text, PII, label, and rendered-text mask bounds
- for handwriting assets: `renderer_type = "handwriting_asset"`, `asset_id`,
  `asset_path`, `mask_path`, `ink_color`, `background_mode`, and
  `geometry_source = "transformed_ink_mask"`

## Handwriting Assets

Generated handwriting assets live under `DycomData/HandwritingAssets/` and stay
out of git. The prototype accepts JSON manifests with an `assets` list and JSONL
manifests with one asset per line.

Each asset needs:

- PNG image path
- ink mask path
- stable `asset_id`
- `text`
- `identity_field` or `field`
- `ink_color`: `black`, `gray`, or `white`
- `background_mode` or `background`: `transparent` or `white`

When `renderer_type = "handwriting_asset"`, the prototype creates one box for
the full visible PII value. It does not create character, word-part, or prefix
boxes in v1.

The ScrabbleGAN tooling is a scaffold with a fake renderer and validation. Real
generation is currently blocked; see
`tools/handwriting/scrabblegan/UPSTREAM_REVIEW.md`.

## Validation State

Known validation artifacts:

- `output_validation_dcm_label_y`
- `output_validation_dcm_label_n`
- `output_validation_jpg`
- `output_validation_ap6_dcm_a`
- `output_validation_ap6_dcm_b`
- `output_validation_ap6_jpg`
- legacy `output_validation_small`, `output_validation_large`,
  `output_validation_main`

AP6 DCM runs with identical seed and parameters produced identical
`box_annotations` and visible render metadata. A JPG spot check exercised the
same visible render path without DICOM tag injection.

Last recorded local code check:

```bash
uv run python -m py_compile prototypes/dicom/pixel_injection.py tests/unit/test_pixel_injection_corners.py
```

At that time, regular `pytest` and `ruff` runs could not run because the local
`.venv` lacked those dev tools.
