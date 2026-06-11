# Upstream Review: ScrabbleGAN Batch Tooling vs. amzn/convolutional-handwriting-gan

Date: 2026-06-11. Compared the local v1 batch tooling against the official
Amazon repository (`https://github.com/amzn/convolutional-handwriting-gan`,
README and `environmentPytorch12.yml` on `master`).

## Verdict

The local code is a clean batch *scaffold* (manifest contract, hashing,
validation, fake renderer), but the actual ScrabbleGAN integration does not
match upstream reality. As written, neither the Docker image nor the default
generator command can produce a single handwriting image with the real model.

## Findings

### 1. The assumed inference interface does not exist upstream (blocker)

`render.py` defaults to calling
`generate.py --text {text} --seed {seed} --checkpoint {checkpoint} --output {output}`
inside the mounted source. The official repo has **no `generate.py`** and no
script that renders one text string to one PNG. Generation upstream is
`generate_wordsLMDB.py`, which:

- samples words from a **lexicon** (no `--text`),
- writes **LMDB databases of TIFF images** (no `--output <png>`),
- has **no `--seed`** parameter,
- loads the model via the pix2pix-style `TestOptions`/`create_model()`
  machinery (`--name <experiment>`), not via a `--checkpoint <file>` flag.

**Change needed:** write a small custom inference wrapper (e.g.
`generate_single.py`) that lives in this repo and is copied into the image or
mounted next to the source. It must: build the options object, load `netG`
weights, encode the requested text with the dataset alphabet, set
`torch.manual_seed`/`numpy.random.seed`/`random.seed` from the manifest seed,
run the generator, and save a PNG to `--output`. Then make this wrapper the
documented `--generator-command` (or the built-in default) instead of the
fictional `generate.py`.

### 2. The Docker image cannot run ScrabbleGAN (blocker)

- **PyTorch is never installed.** The only Python dependency installed is
  `Pillow<8`; the `PYTORCH_VERSION` ARG/ENV is dead code. Upstream needs
  PyTorch 1.2.0, torchvision 0.2.1, numpy, lmdb, opencv, etc. (see
  `environmentPytorch12.yml`).
- **Wrong CUDA base.** The base image is `nvidia/cuda:9.0-...`. The upstream
  README text says "CUDA 9.0", but the pinned conda environment uses
  `cudatoolkit 10.0.130`, and PyTorch 1.2.0 binaries only exist for CUDA
  9.2/10.0. Use a CUDA 10.0 + cuDNN 7 base.
- **`apt-get install python3.6` fails on Ubuntu 16.04.** Xenial ships Python
  3.5; 3.6 requires the deadsnakes PPA or (better) Miniconda. The cleanest fix
  is to install Miniconda and create the env from upstream's
  `environmentPytorch12.yml` (Python 3.6.8, PyTorch 1.2.0, cudatoolkit 10.0).
- **Tag availability risk.** Old `nvidia/cuda` tags for CUDA 9/10 on
  ubuntu16.04 have been pruned from Docker Hub over time; verify the chosen
  tag still exists (or pull from `nvcr.io`) before relying on it.

### 3. Checkpoint contract does not match upstream (blocker)

The tooling expects a single mounted `model.pth`. Upstream saves weights as
`<checkpoints_dir>/<experiment_name>/<epoch>_net_G.pth` and loads them through
`model.setup(opt)`. Additionally, **no pretrained weights are published** —
the model must be trained locally on IAM/RIMES/CVL (datasets must be obtained
manually). Decide and document:

- whether the custom wrapper loads a raw `net_G.pth` state dict directly
  (then a single mounted file is fine — keep the SHA-256 pinning), and
- that training a checkpoint is a prerequisite step (README currently implies
  a checkpoint simply exists).

### 4. `transparent` background mode only works with the fake renderer (bug)

Real ScrabbleGAN output is grayscale with a white-ish background and **no
alpha channel**. `masks._build_mask` uses the alpha channel when
`background == "transparent"`; after `convert("RGBA")` every pixel has alpha
255, so the mask becomes the full image and the normalized output is a solid
ink rectangle.

**Change needed:** always derive the ink mask from the white-distance
threshold (or use alpha only when the raw image actually has a non-trivial
alpha channel), and use `background` solely for compositing the normalized
output.

### 5. Text constraints are not validated against the model alphabet (gap)

ScrabbleGAN generates with a fixed per-dataset alphabet (e.g.
`IAMcharH32rmPunct` strips punctuation) at 32 px height and ~16 px width per
character. Consequences for the v1 fields:

- `patient_id` / `accession_number` values with digits, hyphens, or other
  symbols may be outside the trained alphabet → garbage glyphs.
- `patient_name` with spaces/umlauts: spaces are not part of word-level
  generation; multi-word names likely need per-word generation plus
  compositing.

**Change needed:** validate manifest `text` against the checkpoint's alphabet
in `manifest.py` (reject or transliterate), and decide a strategy for
multi-word names.

### 6. Minor

- `ink_color: "white"` with `background: "white"` passes validation but yields
  an invisible asset (the mask still carries the shape; flag or reject the
  combination).
- The per-pixel Python loop in `masks._build_mask` is slow for large batches;
  a numpy/`Image.point` formulation would be cheap to adopt inside the
  container env (numpy is available once the upstream env is installed).

## What is already sound

Container isolation from the Python 3.13 project, the JSONL manifest contract,
checkpoint/image/mask SHA-256 pinning, relative-path enforcement, failure
logging, the fake renderer for CI, and the post-run manifest validation all
match the intended design and can stay as-is.
