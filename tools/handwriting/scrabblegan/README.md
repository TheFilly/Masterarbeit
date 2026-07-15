# ScrabbleGAN Handwriting Batch Scaffold

This directory contains isolated v1 batch tooling for handwriting assets used
by the migrated injection pipeline. The batch interface remains the low-level
generation contract; the runtime asset provider now calls the same contract
after Faker identity generation when `--font-family handwriting` is selected.

The tooling is useful for manifest validation, hashing, fake-renderer tests,
PNG/mask postprocessing, and downstream injection contracts. The host-side
provider/cache path, single-text wrapper command contract, option-sidecar
contract, and hard prerequisite checks are implemented. The Docker/upstream
path was verified locally on 2026-07-15 with the official source checkout and
checkpoint under `DycomData/HandwritingAssets/`.

## Scope

Version 1 supports a batch CLI workflow:

1. Read an input JSONL manifest.
2. Render or fake-render assets.
3. Write images, masks, hashes, bounding boxes, and an output manifest under
   `DycomData/HandwritingAssets/`.
4. Validate generated artifacts before injection.

No HTTP API exists in v1. The integration adds a local cache lookup and
generation-on-miss path to `uv run injection-pipeline`; it does not move the
legacy ScrabbleGAN dependencies into the Python 3.13 environment.

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
- `generator_options_sha256` for the resolved options sidecar
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
|   |   |-- latest_net_G.pth
|   |   `-- test_opt.txt / train_opt.txt / options.json
|   |-- source/
|   |   `-- .git_commit
|   `-- runs/
`-- logs/
```

`source/.git_commit` must contain the pinned upstream commit when the mounted
source directory is not a full Git checkout. If `.git_commit` is absent, the
tool requires a real Git checkout and reads `git rev-parse HEAD`. Pass the
checkpoint hash to each render and validate command.

The options sidecar is required for real rendering. Pass it explicitly with
`--options-json`/`--handwriting-options-json`, or place one of `options.json`,
`test_opt.json`, `train_opt.json`, `test_opt.txt`, or `train_opt.txt` next to
the checkpoint. The upstream `test_opt.txt`/`train_opt.txt` format is accepted;
its hash is written as `generator_options_sha256` and participates in cache
identity.

## Commands

Build the image:

```powershell
docker build -t injection-scrabblegan tools/handwriting/scrabblegan
```

The image uses Micromamba to solve the historical Python 3.6/PyTorch 1.2
environment. This keeps the upstream runtime contract while avoiding the
memory-heavy legacy Conda solver. On Windows with the WSL2 backend, configure
about 12 GB of WSL memory and 8 GB of swap for the initial build. Do not
upgrade the pinned legacy Python/PyTorch stack inside the image.

The tested CPU image is approximately 1.9 GB. Keep at least 5 GB free for the
image, BuildKit layers/cache, local checkpoints, and generated assets. This is
a practical planning value rather than a hard Docker limit; exact usage depends
on the local Docker cache. IAM datasets and model training are outside the
container and require additional storage.

Run the fake renderer for local contract checks:

```powershell
$env:PYTHONPATH = "tools/handwriting/scrabblegan"
uv run python -m scrabblegan_tool.cli render `
  --input tools/handwriting/scrabblegan/examples/batch_manifest.example.jsonl `
  --output-root DycomData/HandwritingAssets/scrabblegan/runs `
  --run-id fake-smoke `
  --source-dir DycomData/HandwritingAssets/scrabblegan/source `
  --checkpoint DycomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth `
  --checkpoint-sha256 PIN_CHECKPOINT_SHA256 `
  --options-json DycomData/HandwritingAssets/scrabblegan/checkpoints/test_opt.txt `
  --fake-renderer
```

Validate a run:

```powershell
docker run --rm `
  -v ${PWD}:/workspace `
  injection-scrabblegan `
  scrabblegan-validate `
    --manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl `
    --checkpoint DycomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth `
    --checkpoint-sha256 PIN_CHECKPOINT_SHA256
```

Use a generated manifest through the explicit compatibility path:

```powershell
uv run injection-pipeline `
  --handwriting-manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl `
  --handwriting-asset patient_name=patient-name-001
```

Integrated commands are:

```powershell
uv run injection-pipeline --seed 42 --font-family handwriting
uv run injection-pipeline generate-handwriting --seed 42
```

The integrated command generates the Faker identity before resolving the asset
bundle for the visible fields `patient_name`, `patient_id`, and
`accession_number`. A cache hit reuses compatible images and masks; a cache miss
starts the configured Docker image, invokes the isolated renderer, and writes the bundle below
`DycomData/HandwritingAssets/`, and continues with injection. The exact cache
identity includes the seed, schema, field, generated text, checkpoint SHA-256,
upstream commit, generator manifest hash, and `options_sha256`. The runtime
starts automatically on cache miss; if the checkpoint, options sidecar,
source metadata, Docker image, or runtime is unavailable, the command fails
without a font fallback. `--handwriting-runtime-command` remains available as
an explicit host-side override for tests or another isolated runtime.

The real render path uses the IAM English checkpoint options. The wrapper
creates a minimal temporary lexicon for single-word inference, passes the
matching IAM alphabet and OCR options, and copies companion `latest_net_D.pth`
and `latest_net_OCR.pth` files when they are present beside the generator
checkpoint. The output validator accepts both the low-level JSONL format and
the pipeline's JSON object with an `assets` list. Grayscale ScrabbleGAN output
is normalized from the model's `[-1, 1]` range and converted to a soft alpha
mask, preserving anti-aliased handwriting edges. The provider records a
renderer version in the cache identity, so assets from older rasterization
logic are not silently reused.

## Providing the official upstream source locally

Do not copy IAM, checkpoints, generated images, or other external data into
tracked repository paths. Keep the official source under the ignored asset
root:

```powershell
git clone https://github.com/amzn/convolutional-handwriting-gan `
  DycomData/HandwritingAssets/scrabblegan/source
$commit = git -C DycomData/HandwritingAssets/scrabblegan/source rev-parse HEAD
[System.IO.File]::WriteAllText(
  "DycomData/HandwritingAssets/scrabblegan/source/.git_commit",
  $commit.Trim(),
  [System.Text.UTF8Encoding]::new($false)
)
```

If you cannot keep the `.git` directory, copy only the source tree into
`DycomData/HandwritingAssets/scrabblegan/source` and keep the `.git_commit`
file with the exact commit hash. Place the trained generator checkpoint and
its `test_opt`/`train_opt` sidecar under
`DycomData/HandwritingAssets/scrabblegan/checkpoints/`; keep both untracked.

## Failure Modes

The tool rejects missing manifests, source, checkpoint, options sidecar, source
commit metadata, unknown fields, invalid colors or backgrounds, empty text,
duplicate `asset_id`s, checkpoint hash mismatches, empty masks, image/mask size
mismatch, invalid hashes, absolute paths, parent-directory traversal, text
outside the checkpoint alphabet, and white ink on a white background.

Individual render failures go to `failures.jsonl`; successful assets go to
`manifest.jsonl`.
