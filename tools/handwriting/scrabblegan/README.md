# ScrabbleGAN Handwriting Batch Scaffold

This directory contains isolated v1 batch tooling for handwriting assets used by
`prototypes/dicom/inject.py`.

The scaffold is useful for manifest validation, hashing, fake-renderer tests,
PNG/mask postprocessing, and downstream injection contracts. Real ScrabbleGAN
generation is not ready. `UPSTREAM_REVIEW.md` lists the blockers: missing
upstream single-text inference command, incomplete Docker runtime, checkpoint
contract mismatch, mask handling issues, and alphabet constraints.

## Scope

Version 1 supports a batch CLI workflow:

1. Read an input JSONL manifest.
2. Render or fake-render assets.
3. Write images, masks, hashes, bounding boxes, and an output manifest under
   `DycomData/HandwritingAssets/`.
4. Validate generated artifacts before injection.

No HTTP API exists in v1.

## Runtime Boundary

ScrabbleGAN is legacy research code. Keep it outside the Python 3.13 project.
The real upstream stack needs an old Python/PyTorch/CUDA environment; do not add
those dependencies to the main environment.

Local generated assets, checkpoints, source clones, manifests, and logs belong
under `DycomData/HandwritingAssets/` or another ignored local path.

## Supported Prototype Fields

- `patient_name`
- `patient_id`
- `accession_number`

These names describe the handwriting asset contract only. The production
pipeline remains taxonomy-agnostic.

## Manifest Contract

Input JSONL records must include:

- stable `asset_id`
- `field`
- `text`
- `ink_color`: `black`, `gray`, or `white`
- `background`: `transparent` or `white`
- deterministic `seed`

Output records include:

- source `asset_id`
- generated image path
- ink mask path
- image and mask SHA-256
- checkpoint SHA-256
- ScrabbleGAN repository URL and commit
- rendering options
- ink bounding box
- image size

Use paths relative to the output manifest. Do not write absolute local paths or
parent-directory traversal into committed fixtures.

## Local Layout

```text
DycomData/HandwritingAssets/
|-- inputs/
|   `-- batch.jsonl
|-- scrabblegan/
|   |-- checkpoints/
|   |   `-- model.pth
|   |-- source/
|   |   `-- .git_commit
|   `-- runs/
`-- logs/
```

`source/.git_commit` must contain the pinned upstream commit when the mounted
source directory is not a full Git checkout. Pass the checkpoint hash to each
render and validate command.

## Commands

Build the image:

```powershell
docker build -t injection-scrabblegan tools/handwriting/scrabblegan
```

Run the fake renderer for local contract checks:

```powershell
$env:PYTHONPATH = "tools/handwriting/scrabblegan"
uv run python -m scrabblegan_tool.cli render `
  --input tools/handwriting/scrabblegan/examples/batch_manifest.example.jsonl `
  --output-root DycomData/HandwritingAssets/scrabblegan/runs `
  --run-id fake-smoke `
  --source-dir DycomData/HandwritingAssets/scrabblegan/source `
  --checkpoint DycomData/HandwritingAssets/scrabblegan/checkpoints/model.pth `
  --checkpoint-sha256 PIN_CHECKPOINT_SHA256 `
  --fake-renderer
```

Validate a run:

```powershell
docker run --rm `
  -v ${PWD}:/workspace `
  injection-scrabblegan `
  scrabblegan-validate `
    --manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl `
    --checkpoint DycomData/HandwritingAssets/scrabblegan/checkpoints/model.pth `
    --checkpoint-sha256 PIN_CHECKPOINT_SHA256
```

Use a generated manifest in the prototype:

```powershell
uv run python prototypes/dicom/inject.py `
  --handwriting-manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl `
  --handwriting-asset patient_name=patient-name-001
```

Real GPU rendering needs the blockers in `UPSTREAM_REVIEW.md` fixed before this
repository should document a default production command.

## Failure Modes

The tool rejects missing manifests, source, checkpoint, source commit metadata,
unknown fields, invalid colors or backgrounds, empty text, duplicate
`asset_id`s, checkpoint hash mismatches, empty masks, image/mask size mismatch,
invalid hashes, absolute paths, and parent-directory traversal.

Individual render failures go to `failures.jsonl`; successful assets go to
`manifest.jsonl`.
