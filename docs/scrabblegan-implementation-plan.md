# ScrabbleGAN Handwriting Generation — Implementation Plan

Status: **partially complete — host-side provider/cache integration, automatic
Docker runtime wiring, real checkpoint verification, and soft-alpha raster
processing completed; ADR and full test-gate follow-up remain open**.
The fake renderer, manifest, hashing, validation scaffold, integrated
`--font-family handwriting` path, and standalone `generate-handwriting --seed`
path exist. The real ScrabbleGAN run was verified on 2026-07-15 with the
official source checkout, `.git_commit` metadata, and the local
checkpoint/options sidecar.

Created 2026-07-10. Based on the findings in
`tools/handwriting/scrabblegan/UPSTREAM_REVIEW.md` (upstream comparison
against `https://github.com/amzn/convolutional-handwriting-gan`). The existing
batch scaffold (manifest contract, hashing, validation, fake renderer,
container isolation) is kept; this plan closes the gap between the scaffold
and a working real-model pipeline, then documents and tests the result.

Goal: generate real ScrabbleGAN handwriting assets (image + ink mask +
manifest) inside the isolated legacy environment and consume them in
`uv run injection-pipeline` end to end, reproducibly. In handwriting mode,
the pipeline shall generate the Faker identity first, look up the resulting
seed in the local handwriting-asset store, generate missing assets, attach the
assets to the render plan, and persist them for later runs. A separate console
command shall accept a seed and pre-generate the same asset bundle without
injecting a document.

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
  - An integrated handwriting render mode in the DICOM/JPG injection flow:
    Faker identity generation → asset lookup → generation of missing assets →
    handwriting overlay injection → persistent manifest/artifacts under
    `DycomData/HandwritingAssets/`.
  - A standalone seed-based handwriting-generation command that uses the same
    cache and generator contract as the integrated mode.
  - Interactive CLI ordering in which the seed is selected before the common
    font/renderer choice, followed by the remaining render parameters.
  - Tests (host-side unit tests, container smoke test, determinism check,
    integration test) and documentation updates, including closing out this
    plan and the review file.
- Out:
  - HTTP API around the batch core (explicitly deferred by the v1 README).
  - New identity fields beyond `patient_name`, `patient_id`,
    `accession_number`.
  - Model-level style conditioning beyond the selected renderer and seed;
    ScrabbleGAN noise-vector styles stay implicit via the seed unless a later
    decision adds an explicit style parameter.
  - Committing datasets, checkpoints, or generated assets (stay under
    `DycomData/`, gitignored).

## Decisions

### Confirmed integration contract

- The existing manifest-controlled path remains a supported low-level
  contract for explicit asset injection and testing.
- The new integrated path uses one common `--font-family`/interactive choice.
  It includes the normal font options (`arial`, `calibri`, `tahoma`,
  `consolas`) plus `handwriting`. A handwriting choice invokes an
  asset provider after Faker identity generation; normal choices keep the
  existing Pillow rendering path.
- The asset provider must be shared by the injection CLI and the standalone
  seed command so that a pre-generated seed is reused by injection.
- Handwriting is generated only for the currently visible identity fields:
  `patient_name`, `patient_id`, and `accession_number`.
- The cache is a seed bundle, but an asset is reusable only when its cache
  identity matches the seed, identity-schema ID/version, identity field,
  generated text, ScrabbleGAN checkpoint SHA-256, upstream commit, generator
  manifest hash, and options sidecar SHA-256 (`options_sha256` /
  `generator_options_sha256`). A changed identity or generator contract
  creates a new compatible asset instead of silently reusing stale output.
- Asset lookup and writes are local filesystem operations below
  `DycomData/HandwritingAssets/`; generated images, masks, manifests,
  checkpoints, and third-party source remain untracked.
- Both integrated and standalone modes start the isolated ScrabbleGAN runtime
  automatically on cache miss. If the runtime, checkpoint, required source,
  source `.git_commit`/Git checkout metadata, or options sidecar is
  unreachable, the command fails clearly and does not fall back to a normal
  font.
- The default isolated runtime is the `injection-scrabblegan` Docker image;
  `--handwriting-runtime-command` is an explicit override for host-side tests
  or another isolated runtime.
- The standalone command is `uv run injection-pipeline generate-handwriting
  --seed <seed>` and writes the same reusable bundle as integrated injection.
- Normal asset generation uses CPU-only inference inside the isolated runtime.
  A GPU is not required on the machine running the injection pipeline.
- Because the official Amazon repository provides the training and generation
  code but no ready-to-use generator checkpoint in its repository tree, v1
  uses a checkpoint trained from the official code. Training is a one-time
  prerequisite performed on a university GPU or cloud GPU; the trained
  generator is then mounted for CPU inference.

Confirmed by the review; to be re-validated in WP0 where marked *(open)*:

- **Inference runs on CPU inside the container.** Word-image generation with
  the trained generator is cheap; CPU inference removes the CUDA 9/10 base
  image problem, the Docker-Hub tag-pruning risk, and WSL2 GPU passthrough
  uncertainty on the Windows dev machine, and it is more deterministic than
  CUDA. GPU is only needed for *training*, which runs outside this repo's
  container (university GPU machine or Colab).
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

## One-Time Prerequisite For The User

The user does not need to implement the model integration manually, but one
trained generator checkpoint must exist before `--font-family handwriting` can
produce real assets. The setup follows the official Amazon repository:

1. Clone the pinned commit of
   `https://github.com/amzn/convolutional-handwriting-gan` in a separate
   Linux/WSL2 or cloud-GPU workspace.
2. Register for and download IAM, then arrange the official `Datasets/IAM`
   structure (`wordImages`, `lineImages`, `original`, and
   `original_partition`). Keep the dataset outside Git and outside committed
   project fixtures.
3. Create the official legacy environment from
   `environmentPytorch12.yml`; the repository documents Python 3.6,
   PyTorch 1.2, CUDA 9, and Ubuntu 16.04 as its tested combination.
4. Run the official `data/create_text_data.py` preparation step and audit the
   resulting alphabet before training. The checkpoint must support letters,
   digits, and the hyphen needed by the three visible prototype fields; if it
   does not, training data/configuration must be extended before integration.
5. Train with the official `train.py`/`train_semi_supervised.py` workflow on
   the external GPU, export the generator weights and architecture options,
   and place the resulting checkpoint under the ignored
   `DycomData/HandwritingAssets/scrabblegan/checkpoints/` directory.

The repository implementation will then build the isolated runtime, validate
the checkpoint hash, start CPU inference automatically, and generate/cache
the requested seed assets. No checkpoint, IAM data, or legacy environment is
added to the Python 3.13 project.

### WP0: Decisions And Prerequisites

Confirm the *(open)* decisions above and secure external prerequisites.

- [ ] Pin the exact upstream commit (record in this plan and in
      `.git_commit` convention docs).
- [x] Confirm CPU-only inference is acceptable for v1; GPU is reserved for
      one-time checkpoint training.
- [ ] IAM dataset access obtained (registration) and stored under
      `DycomData/` (gitignored); lexicon files downloaded.
- [x] Training venue decided: external Linux GPU, preferably a university
      machine; a cloud GPU is the fallback. The checkpoint is not trained in
      the Python 3.13 project environment.
- [x] Renderer contract decided: one common font-family/renderer choice,
      including `arial`, `calibri`, `tahoma`, `consolas`, and `handwriting`.
- [x] Handwriting scope limited to the visible fields
      `patient_name`, `patient_id`, and `accession_number`.
- [x] Cache identity includes seed, schema, field, generated text, checkpoint,
      upstream commit, generator manifest hash, and options sidecar hash;
      invalidation is explicit.
- [x] Standalone command is `generate-handwriting --seed <seed>` and shares
      the integrated asset-provider contract.
- [x] Missing or unreachable ScrabbleGAN prerequisites fail the run; there is
      no automatic font fallback.
- [ ] ADR-0010 drafted with the checkpoint/inference contract.

### WP1: Container Rebuild

Replace the broken Dockerfile (Review finding 2) with one that actually runs
the upstream code.

- Base: a plain `ubuntu:16.04`-compatible image is *not* required for CPU
  inference; use a slim Linux base + **Micromamba**, create the env from
  upstream's `environmentPytorch12.yml` (PyTorch 1.2.0 CPU build variant if
  the yml's CUDA pin fails on CPU — adjust and document the delta).
- Keep the `scrabblegan-render` / `scrabblegan-validate` entrypoints, now
  executing inside the Micromamba environment.
- Use the Micromamba solver rather than the legacy Conda solver; the latter
  can exhaust the memory available to Docker Desktop while resolving the
  historical Python 3.6 dependency graph.
- Remove dead `PYTORCH_VERSION`/CUDA ARGs or make them real.

- [x] `docker build` succeeds from a clean checkout.
- [x] In-container smoke test passes: `python -c "import torch, torchvision;
      print(torch.__version__)"` prints 1.2.0 and upstream
      `models/` imports succeed against a mounted source checkout.
- [x] `scrabblegan-render --help` / `scrabblegan-validate --help` work
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
- Contract:
  `--text --seed --checkpoint --options-json --output --source-dir` — matching
  the existing `--generator-command` placeholders and the
  `--handwriting-options-json` provider sidecar path.
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
- [x] Out-of-alphabet input fails with a clear error (not garbage output).
- [x] `render.py` default command updated; README command examples updated
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

- [x] Transparent-background assets from a real grayscale raw image produce a
      correct mask (not a solid rectangle) — covered by a unit test with a
      synthetic grayscale raw.
- [x] Alphabet validation rejects bad records at manifest load with line
      numbers; white-on-white rejected.
- [x] Multi-word rendering produces one image + one mask + one bbox per
      asset; word gap deterministic.
- [x] Existing fake-renderer tests still pass unchanged (contract stability).

### WP5: End-To-End Run And Injection

Host-side provider/cache wiring is implemented for both integrated injection
and standalone generation. The real Docker/upstream checkpoint run completed
successfully on 2026-07-15.

- Real batch run in the container against the trained checkpoint for all
  three v1 fields (multi-word name included).
- `scrabblegan-validate` on the output manifest.
- `uv run injection-pipeline --handwriting-manifest ... --handwriting-asset
  patient_name=...` consumes the assets.
- Integrated handwriting run: after the seed and common font-family/renderer
  choice are known,
  generate the Faker identity, resolve or create the seed's asset bundle,
  attach matching assets to every selected render item, and persist the
  resulting manifest under `DycomData/HandwritingAssets/`.
- Standalone seed run: invoke the asset provider without a document and write
  the same bundle and manifest that the integrated run would reuse.

- [x] Batch run completes; `failures.jsonl` empty or explained.
- [x] Output manifest passes validation (hashes, bboxes, relative paths).
- [x] Injection run produces a DICOM/preview where the handwriting overlay is
      visually correct (position, ink color, transparency) — screenshot or
      preview artifact kept under the run output.
- [x] Ground truth of the injection run records the handwriting asset
      (`renderer_type: handwriting_asset`) correctly.
- [x] A second injection with the same resolved seed and compatible cache key
      reuses the existing assets and does not invoke ScrabbleGAN again.
- [x] The standalone seed command and the integrated run produce compatible
      asset manifests and deterministic image/mask hashes.

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
- Cache behavior: cache hit avoids generation; cache miss creates all required
  assets; stale/incompatible cache entries follow the documented invalidation
  policy.
- CLI behavior: interactive prompts ask for the common font-family/renderer
  choice immediately after the seed and before the remaining render
  parameters; standalone generation accepts a seed and writes the expected
  asset bundle.

- [x] `uv run pytest tests/unit/test_scrabblegan_generator.py -q` green:
      17 tests passed on 2026-07-15, including JSON/JSONL manifest handling.
- [x] `uv run ruff check src/ tests/` / `uv run mypy src/` green on
      2026-07-15 (tool code remains outside `src/` except the provider seam).
- [ ] Full `uv run pytest tests/ -x` gate is green on Windows. Some broader
      pytest cases are currently blocked by permission errors while pytest
      creates its Windows temporary directories; rerun after that environment
      issue is resolved.
- [x] Container smoke test documented and executed once with the real
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
- Update `docs/dicom-injection.md`, `README.md`, and the architecture/work-
  package documents with the integrated renderer mode, cache behavior,
  interactive prompt order, and standalone command.

- [x] README rewritten and consistent with the implemented host-side behavior.
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
8. Integrated cache: seed → Faker identity → generate-on-miss → inject →
   persisted asset bundle → repeat run cache hit.
9. Standalone seed generation followed by injection reuses the generated
   bundle without regeneration.

## Validation Commands

```powershell
# Host-side tests
uv run pytest tests/ -x
uv run ruff check src/ tests/
uv run mypy src/

# Focused handwriting validation used on 2026-07-15
uv run pytest tests/unit/test_handwriting*.py tests/unit/test_scrabblegan_generator.py

# Container build + smoke
docker build -t injection-scrabblegan tools/handwriting/scrabblegan
docker run --rm injection-scrabblegan

# Real render + validate + inject (verified 2026-07-15):
uv run injection-pipeline generate-handwriting --seed 42
uv run injection-pipeline --seed 42 --font-family handwriting
```

## Risks And Notes

- **Local prerequisites are present and verified.** The official source,
  `.git_commit`, checkpoint, companion checkpoints, and options sidecar are
  already under the ignored `DycomData/HandwritingAssets/` tree. On another
  machine they must be provided in the same layout; do not copy IAM data,
  checkpoints, generated assets, or external source into tracked repo paths.
- **Training remains external only if the checkpoint is replaced.** IAM
  registration, LMDB preparation, and GPU training are not required for the
  current inference setup, but are needed to train a new compatible model.
- **PyTorch 1.2.0 CPU availability is verified.** The Micromamba image builds
  and runs the pinned Python 3.6/PyTorch 1.2 CPU environment; no CUDA image is
  required for handwriting generation.
- **Handwriting realism** for digit-heavy fields depends on digits being in
  the IAM training alphabet; if they are not, `patient_id`/
  `accession_number` may need a digits-capable retraining or must be waived
  for v1 (decision point in WP0/WP2).
- Old upstream code may need small compatibility patches; keep any patches as
  documented `.patch` files in the tool directory, applied to the mounted
  source — never fork silently.
