# ScrabbleGAN Handwriting Batch Generator

This directory contains the isolated v1 batch tooling for generating handwriting
assets consumed by `prototypes/dicom/inject.py`. It is intentionally separate
from the Python 3.13 project: ScrabbleGAN is legacy research code and runs in
its own container.

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

No HTTP API exists in v1. A future API can wrap the same batch core with
separate modules for request validation, job creation, worker execution, and
artifact serving, but those pieces should not be implemented until the batch
contract is stable.

## Legacy Runtime Constraints

ScrabbleGAN depends on an old stack:

- Python 3.6
- PyTorch 1.2
- CUDA 9
- matching cuDNN/NVIDIA driver support

Keep these dependencies inside the container. Do not add them to the main
project environment.

## Local Artifacts

The Docker image does not clone ScrabbleGAN and does not download model
weights. Provide both through gitignored local mounts:

```text
DycomData/HandwritingAssets/
+-- inputs/
|   +-- batch.jsonl
+-- scrabblegan/
|   +-- checkpoints/
|   |   +-- model.pth
|   +-- source/
|   |   +-- .git_commit
|   +-- runs/
+-- logs/
```

`source/.git_commit` must contain the pinned upstream commit if the mounted
source directory is not a full Git checkout. The checkpoint hash must be supplied
on every render and validate command.

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

Output manifests include, for each rendered asset:

- source `asset_id`
- generated image path
- ink mask path
- image SHA-256
- mask SHA-256
- checkpoint SHA-256
- ScrabbleGAN repository URL and commit
- rendering options
- ink bounding box
- image size

Use paths relative to the output manifest file. For a manifest at
`DycomData/HandwritingAssets/scrabblegan/runs/<run-id>/manifest.jsonl`, use paths
such as `images/<asset-id>.png` and `masks/<asset-id>-mask.png`. Absolute local
paths should not appear in committed documentation or fixtures.

## Commands

Build the isolated legacy image:

```powershell
docker build -t injection-scrabblegan tools/handwriting/scrabblegan
```

Run a real GPU batch. Replace `PIN_CHECKPOINT_SHA256` and optionally
`--generator-command` with the command required by the mounted upstream checkout.
The command template may use `{text}`, `{seed}`, `{output}`, `{source_dir}`,
`{checkpoint}`, `{asset_id}`, and `{field}` placeholders.

```powershell
docker run --gpus all --rm `
  -v ${PWD}:/workspace `
  injection-scrabblegan `
  scrabblegan-render `
    --input DycomData/HandwritingAssets/inputs/batch.jsonl `
    --output-root DycomData/HandwritingAssets/scrabblegan/runs `
    --run-id demo `
    --source-dir DycomData/HandwritingAssets/scrabblegan/source `
    --checkpoint DycomData/HandwritingAssets/scrabblegan/checkpoints/model.pth `
    --checkpoint-sha256 PIN_CHECKPOINT_SHA256 `
    --generator-command "python3.6 {source_dir}/generate.py --text {text} --seed {seed} --checkpoint {checkpoint} --output {output}"
```

Validate the output before injecting it:

```powershell
docker run --rm `
  -v ${PWD}:/workspace `
  injection-scrabblegan `
  scrabblegan-validate `
    --manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl `
    --checkpoint DycomData/HandwritingAssets/scrabblegan/checkpoints/model.pth `
    --checkpoint-sha256 PIN_CHECKPOINT_SHA256
```

Use the generated manifest in the DICOM prototype:

```powershell
uv run python prototypes/dicom/inject.py `
  --handwriting-manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl `
  --handwriting-asset patient_name=patient-name-001
```

For CI/local contract checks without ScrabbleGAN, use the fake renderer:

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

## Failure Modes

- Missing input manifest, ScrabbleGAN source, checkpoint, or source commit
  metadata fails the run before rendering.
- Unknown fields, invalid colors/backgrounds, empty text, duplicate `asset_id`s,
  and checkpoint hash mismatches are rejected.
- Individual render failures are written to `failures.jsonl`; only successful
  assets appear in `manifest.jsonl`.
- Empty masks, image/mask size mismatches, invalid hashes, absolute paths, and
  parent-directory traversal fail validation.

`DycomData/` is ignored project data. Keep generated images, masks, logs,
checkpoints, and downloaded third-party source out of git.
