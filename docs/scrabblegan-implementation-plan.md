# ScrabbleGAN Handwriting Generation — Implementation Plan

Status: **open — real-model work not started**. The fake renderer, manifest,
hashing, and validation scaffold already exist. WP0 through WP7 below remain
open for real ScrabbleGAN generation.

Created 2026-07-10. Based on the findings in
`tools/handwriting/scrabblegan/UPSTREAM_REVIEW.md` (upstream comparison
against `https://github.com/amzn/convolutional-handwriting-gan`). The existing
batch scaffold (manifest contract, hashing, validation, fake renderer,
container isolation) is kept; this plan closes the gap between the scaffold
and a working real-model pipeline, then documents and tests the result.

Goal: generate real ScrabbleGAN handwriting assets (image + ink mask +
manifest) inside the isolated legacy container and consume them in
`uv run injection-pipeline` via `--handwriting-manifest` and
`--handwriting-asset`, end to end, reproducibly.

## Scope

- In:
  - A runnable legacy container with the upstream environment (Python 3.6.8,
    PyTorch 1.2.0) and the batch tool installed.
  - A custom single-text inference wrapper around the upstream generator
    (upstream has no such script — Review finding 1).
  - A trained (or otherwise procured) generator checkpoint, pinned by SHA-256.
  - Fixes to the batch tool: transparent-background mask bug (finding 4),
    alphabet validation (finding 5), invisible white-on-white combination
    (finding 6).
  - One verified end-to-end run: batch manifest → container render →
    validated output manifest → DICOM injection with visual check.
  - Tests (host-side unit tests, container smoke test, determinism check,
    integration test) and documentation updates, including closing out this
    plan and the review file.
- Out:
  - HTTP API around the batch core (explicitly deferred by the v1 README).
  - New identity fields beyond `patient_name`, `patient_id`,
    `accession_number`.
  - Style conditioning / handwriting-style selection (upstream noise-vector
    styles stay implicit via the seed).
  - Committing datasets, checkpoints, or generated assets (stay under
    `DycomData/`, gitignored).

## Decisions

Confirmed by the review; to be re-validated in WP0 where marked *(open)*:

- **Inference runs on CPU inside the container.** Word-image generation with
  the trained generator is cheap; CPU inference removes the CUDA 9/10 base
  image problem, the Docker-Hub tag-pruning risk, and WSL2 GPU passthrough
  uncertainty on the Windows dev machine, and it is more deterministic than
  CUDA. GPU is only needed for *training*, which runs outside this repo's
  container (university GPU machine or Colab). *(open — confirm no
  requirement for in-container GPU rendering)*
- **The wrapper loads a raw `net_G` state dict from a single mounted file.**
  This keeps the existing `--checkpoint` + `--checkpoint-sha256` contract.
  The training run must export `latest_net_G.pth`; the wrapper reconstructs
  the generator architecture from pinned upstream code plus a small JSON
  sidecar with the architecture options (alphabet, image height, channels).
- **Upstream source stays a runtime mount** (pinned commit via `.git_commit`),
  never vendored or committed — unchanged from the current design.
- **Dataset/alphabet: IAM, `IAMcharH32rmPunct`.** English words, no
  punctuation. Digits/hyphens in `patient_id`/`accession_number` and umlauts
  in names must therefore be validated against the actual checkpoint alphabet
  and rejected (v1: reject, do not transliterate). *(open — confirm IAM access
  registration and whether digits are in the trained alphabet)*
- **Multi-word `patient_name` values are rendered per word and composited
  horizontally** by the batch tool with a fixed, seeded gap; the manifest
  `text` keeps the full string. Rejecting spaces outright would make
  `patient_name` useless.
- Record the checkpoint/inference contract as **ADR-0010** once WP0 decisions
  are confirmed (fits the existing `docs/decisions/` series).

## Work Packages

Each WP lists acceptance criteria as checkboxes. Tick them as they complete
and update the Status line at the top; do not delete failed approaches —
strike through and note what replaced them.

### WP0: Decisions And Prerequisites

Confirm the *(open)* decisions above and secure external prerequisites.

- [ ] Pin the exact upstream commit (record in this plan and in
      `.git_commit` convention docs).
- [ ] Confirm CPU-only inference is acceptable for v1.
- [ ] IAM dataset access obtained (registration) and stored under
      `DycomData/` (gitignored); lexicon files downloaded.
- [ ] Training venue decided (which GPU machine; upstream env reproducible
      there via `environmentPytorch12.yml`).
- [ ] ADR-0010 drafted with the checkpoint/inference contract.

### WP1: Container Rebuild

Replace the broken Dockerfile (Review finding 2) with one that actually runs
the upstream code.

- Base: a plain `ubuntu:16.04`-compatible image is *not* required for CPU
  inference; use a slim Linux base + **Miniconda**, create the env from
  upstream's `environmentPytorch12.yml` (PyTorch 1.2.0 CPU build variant if
  the yml's CUDA pin fails on CPU — adjust and document the delta).
- Keep the `scrabblegan-render` / `scrabblegan-validate` entrypoints, now
  executing inside the conda env.
- Remove dead `PYTORCH_VERSION`/CUDA ARGs or make them real.

- [ ] `docker build` succeeds from a clean checkout.
- [ ] In-container smoke test passes: `python -c "import torch, torchvision;
      print(torch.__version__)"` prints 1.2.0 and upstream
      `models/` imports succeed against a mounted source checkout.
- [ ] `scrabblegan-render --help` / `scrabblegan-validate --help` work
      (current CMD contract preserved).

### WP2: Checkpoint Procurement

Upstream publishes no weights (Review finding 3); train once, outside the
container.

- Follow upstream README: `data/create_text_data.py` → LMDB → `train.py`
  with `IAMcharH32rmPunct`.
- Export `latest_net_G.pth` plus the architecture-options JSON sidecar;
  compute SHA-256; place under
  `DycomData/HandwritingAssets/scrabblegan/checkpoints/`.

- [ ] Training run completed; sample grid images visually plausible.
- [ ] `model.pth` (= exported `net_G`) + options sidecar + SHA-256 recorded
      (hash goes into run commands, not into git-committed docs as a fake
      `PIN_...` placeholder).
- [ ] Trained alphabet string extracted and recorded (input to WP4
      validation).

### WP3: Single-Text Inference Wrapper

The core missing piece (Review finding 1): a script that renders one text
string to one PNG, deterministically.

- Location: `tools/handwriting/scrabblegan/wrapper/generate_single.py`,
  copied into the image next to `scrabblegan_tool` (it is ours, unlike the
  mounted upstream source). Python 3.6-compatible.
- Contract: `--text --seed --checkpoint --options-json --output` — matching
  the existing `--generator-command` placeholders.
- Behavior: seed `random`/`numpy`/`torch` (+
  `torch.backends.cudnn.deterministic` if GPU ever used), build `netG` from
  pinned upstream `models/` code, load the state dict, encode text via the
  alphabet, generate, save grayscale PNG.
- Make this wrapper the built-in default command in `render.py` (replacing
  the fictional `generate.py` default).

- [ ] Wrapper renders a known word to a PNG in the container.
- [ ] Same seed + text + checkpoint → byte-identical PNG on repeated runs
      (determinism contract, AGENTS.md).
- [ ] Different seeds → visibly different handwriting.
- [ ] Out-of-alphabet input fails with a clear error (not garbage output).
- [ ] `render.py` default command updated; README command examples updated
      in WP7.

### WP4: Batch-Tool Fixes

Close the tool-level findings so real (grayscale, no-alpha) generator output
is processed correctly.

- `masks.py`: derive the ink mask from the white-distance threshold whenever
  the raw image has no meaningful alpha channel; use `background` only for
  compositing (Review finding 4). Replace the per-pixel loop with
  `Image.point`/numpy while touching it (finding 6b).
- `manifest.py`: validate `text` against the checkpoint alphabet (passed as
  file/option); reject `ink_color: white` + `background: white`
  (finding 6a).
- Multi-word support: split on spaces, render per word via the wrapper,
  composite with fixed gap in the batch tool.

- [ ] Transparent-background assets from a real grayscale raw image produce a
      correct mask (not a solid rectangle) — covered by a unit test with a
      synthetic grayscale raw.
- [ ] Alphabet validation rejects bad records at manifest load with line
      numbers; white-on-white rejected.
- [ ] Multi-word rendering produces one image + one mask + one bbox per
      asset; word gap deterministic.
- [ ] Existing fake-renderer tests still pass unchanged (contract stability).

### WP5: End-To-End Run And Injection

- Real batch run in the container against the trained checkpoint for all
  three v1 fields (multi-word name included).
- `scrabblegan-validate` on the output manifest.
- `uv run injection-pipeline --handwriting-manifest ... --handwriting-asset
  patient_name=...` consumes the assets.

- [ ] Batch run completes; `failures.jsonl` empty or explained.
- [ ] Output manifest passes validation (hashes, bboxes, relative paths).
- [ ] Injection run produces a DICOM/preview where the handwriting overlay is
      visually correct (position, ink color, transparency) — screenshot or
      preview artifact kept under the run output.
- [ ] Ground truth of the injection run records the handwriting asset
      (`renderer_type: handwriting_asset`) correctly.

### WP6: Testing

Consolidate what WP3–WP5 introduced into the repeatable test suite.

- Host-side (Python 3.13, existing `tests/unit/test_scrabblegan_generator.py`
  pattern): new tests for alphabet validation, white-on-white rejection,
  grayscale-raw mask derivation, multi-word compositing, and the
  `--generator-command` template building.
- Container-side: a smoke-test script (checked in under
  `tools/handwriting/scrabblegan/`) that runs the fake renderer plus a
  1-record real render and asserts manifest validity — runnable manually and
  documented; not wired into CI (CI has no checkpoint).
- Determinism: test that two renders of the same record yield identical
  `image_sha256`/`mask_sha256` (real renderer, manual; fake renderer, CI).

- [ ] `uv run pytest tests/ -x` green, including the new unit tests.
- [ ] `uv run ruff check` / `uv run mypy src/` unaffected (tool code is
      outside `src/`, keep it that way).
- [ ] Container smoke test documented and executed once with the real
      checkpoint; result noted here.

### WP7: Documentation And Plan Closure

- Update `tools/handwriting/scrabblegan/README.md`: real prerequisites
  (training required, no pretrained weights), the wrapper as default
  generator command, real (non-fictional) command examples, CPU-inference
  note, alphabet/multi-word rules.
- Update `UPSTREAM_REVIEW.md`: mark each finding resolved with a pointer to
  the fixing WP/commit; keep the file as a historical record.
- Finalize ADR-0010 (accepted).
- Update the example manifests in `examples/` if the contract gained fields
  (e.g. options sidecar reference).

- [ ] README rewritten and consistent with the implemented behavior.
- [ ] UPSTREAM_REVIEW findings all marked resolved/waived.
- [ ] ADR-0010 accepted and cross-linked.
- [ ] **This plan: all checkboxes ticked, Status line set to `done` with
      date.** Unticked items must carry a written reason (waived/deferred).

## Test Scenarios (summary)

1. Fake renderer round trip (existing) — contract regression guard.
2. Grayscale raw + `transparent` background → correct mask and bbox.
3. Alphabet: record with out-of-alphabet character rejected at load.
4. White ink on white background rejected.
5. Multi-word name → single composited asset, deterministic gap.
6. Determinism: identical record rendered twice → identical hashes.
7. End-to-end: real manifest → render → validate → inject → visual check.

## Validation Commands

```powershell
# Host-side tests
uv run pytest tests/ -x
uv run ruff check src/ tests/

# Container build + smoke
docker build -t injection-scrabblegan tools/handwriting/scrabblegan
docker run --rm injection-scrabblegan

# Real render + validate + inject: see README commands (updated in WP7)
```

## Risks And Notes

- **Training is the long pole.** IAM registration, LMDB preparation, and GPU
  training time are external to this repo; WP1/WP3/WP4 can proceed in
  parallel using the fake renderer and a randomly initialized `net_G` for
  plumbing tests.
- **PyTorch 1.2.0 CPU build availability** in conda/pip for Python 3.6 must
  be verified early in WP1; if unavailable, fall back to the CUDA-10.0 GPU
  image (accepting the Docker-Hub tag risk noted in the review).
- **Handwriting realism** for digit-heavy fields depends on digits being in
  the IAM training alphabet; if they are not, `patient_id`/
  `accession_number` may need a digits-capable retraining or must be waived
  for v1 (decision point in WP0/WP2).
- Old upstream code may need small compatibility patches; keep any patches as
  documented `.patch` files in the tool directory, applied to the mounted
  source — never fork silently.
