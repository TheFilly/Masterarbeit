# ScrabbleGAN Handwriting Scaffold

This directory documents the isolated ScrabbleGAN path for generating
handwriting assets. It is intentionally separate from the Python 3.13 project:
ScrabbleGAN is legacy research code and should run in its own container.

Reference basis: the official Amazon ScrabbleGAN repository,
`https://github.com/amzn/convolutional-handwriting-gan`. Pin the exact upstream
commit and model checkpoint before any productive generation run.

## Scope

Version 1 is a batch CLI workflow:

1. Prepare an input manifest with the field values to render.
2. Run ScrabbleGAN inside the legacy container.
3. Write images, ink masks, bounding boxes, and an output manifest under
   `DycomData/HandwritingAssets/`.
4. Validate hashes before using the assets in downstream injection work.

No productive HTTP API exists in this scaffold. A future API can wrap the same
batch core with separate modules for request validation, job creation, worker
execution, and artifact serving, but those pieces should not be implemented
until the batch contract is stable.

## Legacy Runtime Constraints

ScrabbleGAN depends on an old stack:

- Python 3.6
- PyTorch 1.2
- CUDA 9
- matching cuDNN/NVIDIA driver support

Keep these dependencies inside the container. Do not add them to the main
project environment.

## Container Placeholders

The Dockerfile exposes placeholders for reproducible setup:

- `SCRABBLEGAN_REPO_URL`: upstream repository URL
- `SCRABBLEGAN_COMMIT`: exact upstream commit to use
- `SCRABBLEGAN_CHECKPOINT_PATH`: local or mounted checkpoint path
- `SCRABBLEGAN_CHECKPOINT_SHA256`: expected checkpoint hash

The scaffold does not clone repositories or download checkpoints. Provide source
and weights through a local mount when turning this into a productive tool.

## Supported Fields

Only these field names are in scope for v1:

- `patient_name`
- `patient_id`
- `accession_number`

The pipeline remains taxonomy-agnostic elsewhere; these names describe the
handwriting asset generator contract only.

## Rendering Options

Supported ink colors:

- `black`
- `gray`
- `white`

Supported background modes:

- `transparent`
- `white`

Every rendered asset must include an ink mask. The output manifest must record
the tight bounding box of non-background ink pixels for both the full image and
the mask. Bounding boxes use pixel coordinates with `x`, `y`, `width`, and
`height`.

## Manifest Requirements

Input manifests should be JSONL so large batches can stream safely. Each record
must include:

- stable `asset_id`
- `field`
- `text`
- `ink_color`
- `background`
- deterministic `seed`

Output manifests must include, for each rendered asset:

- source `asset_id`
- generated image path
- ink mask path
- image SHA-256
- mask SHA-256
- checkpoint SHA-256
- ScrabbleGAN repository URL and commit
- rendering options
- ink bounding box

Use paths relative to the output manifest file. For a manifest at
`DycomData/HandwritingAssets/scrabblegan/runs/<run-id>/manifest.jsonl`, use paths
such as `images/<asset-id>.png` and `masks/<asset-id>-mask.png`. Absolute local
paths should not appear in committed documentation or fixtures.

## Directory Layout

Suggested local artifact layout:

```text
DycomData/HandwritingAssets/
+-- inputs/
|   +-- batch.jsonl
+-- scrabblegan/
|   +-- checkpoints/
|   +-- source/
|   +-- runs/
|       +-- <run-id>/
|           +-- images/
|           +-- masks/
|           +-- manifest.jsonl
+-- logs/
```

`DycomData/` is ignored project data. Keep it out of git.
