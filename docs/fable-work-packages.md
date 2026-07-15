# Fable Work Packages — Second Generation

Backlog of work packages following the completed architecture-alignment round.
The first generation (WP-A through WP-H) was executed on 2026-07-06 and is
removed from this file; its deliverables live in `docs/architecture/` and
`docs/decisions/` (ADR-0001..0009). The DICOM/JPG implementation pass on
2026-07-12 completed WP-I and the core WP-B..WP-G handoff slices. WP-P and two
of three WP-R items followed on 2026-07-13. Remaining work stays explicit below.

| Package | Deliverable status |
|---|---|
| WP-A | Blueprint and ADR review recorded in `docs/architecture/target-architecture.md`. |
| WP-B | Implemented for DICOM/JPG: pydantic models, `RunRecord`, and round-trip tests. Shared geometry and PDF sidecar models are implemented; broader PDF fixture coverage remains. |
| WP-C | Implemented for DICOM/JPG: identifier schema loader, default schema, schema-driven identity generation, and planning. Remaining: emitted schema provenance after ADR-0008. |
| WP-D | Implemented for DICOM/JPG: runner split, `RunRecord` wiring, and adapter lookup. PDF adapter CLI integration is implemented under the approved PDF plan; broader operational fixture coverage remains. |
| WP-E | Implemented for DICOM/JPG: mypy override removed, engine split, dead API removed, DICOM pixel writeback moved. Remaining: none for DICOM/JPG core typing after WP-P. |
| WP-F | Implemented for DICOM/JPG: adapter models, registry, DICOM/JPG loaders and writers. The PDF loader/writer pair is implemented under the approved PDF plan; broader operational fixture coverage remains. |
| WP-G | Partially implemented: seeded default input, injectable clock, stable seed derivation, deterministic `reference_date`. Remaining: environment/provenance emission after ADR-0008. |
| WP-H | Completed: active documentation no longer depends on the retired Research/Thesis/Templates layer. |

Ground rules for the packages below:

- Packages marked **design** produce Markdown deliverables under `docs/`
  (Fable's job); packages marked **implementation** are executed directly by
  Opus/Codex against an existing spec, with tests.
- Reference concrete code (`file:line`); design deliverables end with an
  implementation handoff and definition of done.
- Preserve the migration invariant: existing DCM/JPG runs stay byte-identical
  unless an ADR approves a change (`docs/dicom-injection.md`, Validation
  State).
- The thesis-traceability layer (claims, findings, templates) was removed on
  2026-07-06 and is out of scope for all packages.

---

## WP-I — End-to-End Test Harness & CI (implementation, done 2026-07-12)

**Implemented.** `tests/fixtures/synthetic_documents.py` generates synthetic
DCM/JPG inputs without real or MIMIC-derived data.
`tests/integration/test_end_to_end.py` runs DICOM and JPG paths with fixed
seed, fixed input, fixed timestamp, default schema, and a deterministic test
font, then compares all artifact hashes. CI in `.github/workflows/ci.yml` runs
uv sync, ruff, mypy, and pytest.

**Remaining.** None for WP-I. The scratch-branch one-pixel proof is not kept as
a repository artifact.

---

## WP-J — ScrabbleGAN Restart and Injection Integration (design, then implementation)

**Goal.** Make real ScrabbleGAN handwriting generation work end-to-end in this
repo: a runnable environment, a working single-text inference path, a pinned
checkpoint, and generated assets flowing through the existing manifest
contract into an injection run. Extend that batch contract so the injection
pipeline can generate missing assets after Faker identity generation, reuse
them from `DycomData/HandwritingAssets/`, and expose the same behavior through
a standalone seed-based console command.

**Why now.** The first attempt produced a sound batch scaffold
(`tools/handwriting/scrabblegan/`: manifest contract, hashing, validation,
fake renderer) but zero real generation. `UPSTREAM_REVIEW.md` (2026-06-11)
found the integration was built against an assumed upstream interface that
does not exist. The scaffold is worth keeping; the generation core must be
rebuilt on verified upstream reality
(`https://github.com/amzn/convolutional-handwriting-gan`).

**Verified blockers to clear (from `UPSTREAM_REVIEW.md`, re-confirm against
upstream `master` before building):**

1. **No single-text inference upstream.** `render.py:89-106` defaults to a
   fictional `generate.py --text ... --seed ... --checkpoint ... --output ...`;
   upstream only has `generate_wordsLMDB.py` (lexicon-sampled, LMDB/TIFF
   output, no seed flag, pix2pix-style `TestOptions`/`create_model()`
   loading). A custom wrapper (`generate_single.py`) must be written in this
   repo: build the options object, load `netG` weights, encode text with the
   dataset alphabet, seed `torch`/`numpy`/`random` from the manifest seed,
   save one PNG to `--output`.
2. **The Docker image cannot run ScrabbleGAN.** `Dockerfile:6` uses a CUDA 9.0
   / Ubuntu 16.04 base, installs only `Pillow<8` (`Dockerfile:33`), never
   installs PyTorch, and `apt-get install python3.6` fails on Xenial. Upstream
   needs Python 3.6.8 + PyTorch 1.2.0 + cudatoolkit 10.0
   (`environmentPytorch12.yml`); old `nvidia/cuda` tags may be pruned from
   Docker Hub.
3. **No pretrained weights exist.** Upstream publishes none; a checkpoint must
   be trained locally on IAM/RIMES/CVL (manual dataset registration) or
   sourced from a community reproduction and hash-pinned. The tooling's
   single-`model.pth` mount also mismatches upstream's
   `<checkpoints_dir>/<experiment>/<epoch>_net_G.pth` layout — decide whether
   the wrapper loads a raw `net_G.pth` state dict directly (then the single
   mounted file + SHA-256 pinning stays).
4. **Mask bug for real output.** `masks._build_mask` trusts the alpha channel
   for `background == "transparent"`, but real ScrabbleGAN output is grayscale
   with no alpha — after `convert("RGBA")` every pixel is opaque and the mask
   becomes a solid rectangle. Always derive ink from the white-distance
   threshold; use alpha only when the raw image has a non-trivial alpha
   channel.
5. **Alphabet constraints unvalidated.** Trained alphabets (e.g.
   `IAMcharH32rmPunct`) may exclude digits/hyphens — `patient_id`
   (`SYNTH-######`) and `accession_number` values can produce garbage glyphs;
   multi-word `patient_name` needs per-word generation plus compositing.
   Validate manifest `text` against the checkpoint's alphabet in
   `manifest.py`; define the multi-word strategy.
6. **Minor:** reject `ink_color: white` + `background: white`; replace the
   per-pixel Python loop in `masks._build_mask` with numpy.

**Phase 0 — feasibility decision (design, one ADR).** Before touching the
Dockerfile, decide the runtime strategy; this was the first attempt's fatal
gap. Options to evaluate against the actual host (Windows 10 + WSL2 + GPU
availability):

- (a) Faithful legacy container: Miniconda + upstream
  `environmentPytorch12.yml` in a CUDA 10.0 base — maximal fidelity, fragile
  base-image availability, GPU passthrough via WSL2 required for training.
- (b) **Modern-PyTorch port (recommended default):** run upstream inference
  code on current PyTorch in a plain container or venv; pix2pix-era code
  typically needs small patches. CPU inference is fine for asset generation;
  only training needs GPU.
- (c) Replace ScrabbleGAN with a maintained handwriting-synthesis model with
  published weights — fallback if (a) and (b) both fail the time budget; the
  manifest/mask/validation contract is generator-agnostic by design, so only
  `render.py`'s command changes.

The ADR must also settle the checkpoint plan (train vs. community weights,
dataset licensing constraints — IAM requires registration and must never be
committed) and pin the upstream commit (`Dockerfile:9` still says
`PIN_UPSTREAM_COMMIT`).

**Implementation sequence (after the ADR).**

1. Pin upstream commit; write `generate_single.py` against it (blocker 1) and
   make it the built-in default command in `render.py`, replacing the
   fictional `generate.py` path.
2. Build the chosen runtime (blocker 2 or its port alternative); smoke-test
   `generate_single.py` with random-init weights (shape/alphabet plumbing
   works without a trained checkpoint).
3. Acquire/train the checkpoint per the ADR; record SHA-256; document the
   training prerequisite in the README (blocker 3).
4. Fix the mask derivation (blocker 4) + minor fixes (blocker 6); extend the
   fake-renderer tests with a no-alpha grayscale fixture that reproduces the
   bug first.
5. Add alphabet validation and the multi-word strategy (blocker 5); update
   `examples/batch_manifest.example.jsonl` accordingly.
6. End-to-end: `batch.jsonl` → real render → `manifest.jsonl` →
   `scrabblegan-validate` → `uv run injection-pipeline --handwriting-manifest
   ... --handwriting-asset patient_name=...` produces a DCM run with correct
   ink-mask geometry in `ground_truth.json`.
7. Rewrite `UPSTREAM_REVIEW.md` findings as resolved/superseded; update both
   READMEs' "blocked" notices.

**Scope / DoD.** One real generated asset for each selected v1 field
(`patient_name`, `patient_id`, `accession_number` unless the field decision
expands the set) is injected into a DCM run; a second run with the same
compatible seed/cache identity reuses the persisted assets; a standalone seed
command produces the same reusable bundle; existing fake-renderer tests still
pass; no legacy dependencies enter the Python 3.13 project
(`tools/handwriting/README.md` runtime boundary holds); no datasets, weights,
or generated assets are committed.

**Depends on.** The real generator core remains isolated, but the integrated
asset-provider seam touches the main pipeline's runtime CLI, runner, render
plan, and ground-truth metadata. **Leverage.** High for datasets that require
realistic handwriting; the existing scaffold reduces the integration work but
not the model/checkpoint or cache-contract risk.

---

## WP-K — DICOM Conformance & Validators (design)

**Goal.** Specify the `validators/` module and the DICOM-conformance policy
for injected outputs.

**Why now.** `writers/dicom.py` does not regenerate `SOPInstanceUID` after
modifying pixel data and rewrites transfer syntax to
ExplicitVRLittleEndian. Downstream consumers may reject or mis-index such
files. `validators/` has no implemented validation policy.

**Deliverables.** `docs/architecture/validators-spec.md`: validation stages
(schema round-trip, annotation-geometry consistency vs. rendered pixels,
format validity per adapter) and an ADR on UID regeneration + transfer-syntax
policy (a deliberate byte-compat break, so it needs its own golden-file
transition plan).

**Depends on.** WP-B models implemented; WP-I harness. **Leverage.** Medium-high.

---

## WP-L — Multi-Frame Injection Policy (design, small)

**Goal.** Decide and record how multi-frame DICOM (cine loops) should be
injected.

**Why now.** Only frame 0 is injected (`applied_frame_indices: [0]` in
`engine/injector.py`); a 47-frame loop is PII-free on 46 frames.
For detector training data this is a dataset property that must be either
fixed or documented as intended.

**Deliverables.** One ADR (inject all frames vs. frame-0-only as recorded
property vs. per-run option), plus the ground-truth implications
(`frame_index` semantics in `BoxAnnotation`, per-frame corners) folded into
the WP-B spec as an addendum.

**Depends on.** WP-B spec (annotation shapes). **Leverage.** Medium.

---

## WP-M — Batch Generation Mode (design)

**Goal.** Design the dataset-scale runner: many documents per invocation with
derived per-item seeds and aggregate reporting.

**Why now.** The CLI does one document per run; producing a training corpus by
hand-looping invocations loses seed discipline (the correlated-seed hazard,
determinism-audit N4) and provenance. Scalability is a core pipeline goal
(PLAN.md FF2/FF3).

**Deliverables.** `docs/architecture/batch-mode-spec.md`: input manifest
format, per-item seed derivation via `derive_seed` (WP-G), output layout (one
run dir per item + batch-level manifest), failure isolation semantics, resume
behaviour, and CLI surface (`injection-pipeline batch ...`).

**Depends on.** WP-G implemented (derive_seed, injectable clock), WP-D done
(stage functions callable without the CLI). **Leverage.** High for the
research goal, later in sequence.

---

## WP-N — Docstring & Comment Migration (implementation, mechanical)

**Goal.** Reconcile the conflicting documentation conventions, then migrate
production functions to the selected format.

**Why now.** `AGENTS.md` asks for Google-style docstrings, while the active
`commenting-guidelines` skill requires `# Input:/# Output:` blocks. The code
currently follows the skill in many modules, so a mechanical migration before
choosing one source of truth would recreate the conflict.

**Tasks.** Decide which convention is authoritative, update `AGENTS.md` and the
skill so they agree, then migrate remaining functions in a standalone pass.

**Scope / DoD.** One documented convention, no mixed requirement, ruff/mypy
green, and no behaviour changes. **Depends on.** Documentation convention
decision. **Leverage.** Low-medium (readability, consistency).

---

## WP-O — Declarative CLI Parameter Spec (design, small)

**Goal.** One parameter table driving both argparse and interactive mode.

**Why now.** Interactive mode re-implements every default and validator by
hand (`cli.py:174-234` vs `cli.py:255-319`); the two require manual sync
today and a run-config file (future) would be a third copy.

**Deliverables.** Short spec in `docs/architecture/` defining the parameter
descriptor (name, type, default, choices, validator, prompt text, help),
how argparse and the prompt loop are generated from it, and where it lives in
`config/`. Include the migration mapping for all 11 current parameters.

**Depends on.** WP-D step 1 (options module). **Leverage.** Medium — removes a
standing sync hazard before the PDF subcommand (`compose-pdf`) adds more
parameters.

---

## WP-P — Engine Render-Pass Reuse (implementation, perf)

**Goal.** Stop rendering every overlay twice.

**Implemented 2026-07-13.** Placement now carries a private typed
`PreparedOverlay` payload from the sizing pass into the final render pass, so
font and handwriting overlays are prepared once per annotation. The cache lives
only on internal positioned annotations and is not serialized into public
records, schemas, annotations, or DCM/JPG artifacts. Focused tests count one
prepare call per annotation for both renderer types; the DCM/JPG E2E harness
keeps artifact hashes unchanged.

**Microbenchmark hint.** Reuse
`tests/unit/test_overlay_reuse.py::test_overlay_reuse_microbenchmark_fixture_is_reproducible`
as the deterministic fixture for manual timing, e.g. run the same fixed
`_inject_visible_text_into_frame` setup with `python -m timeit` and compare
medians outside pytest. Do not add timing thresholds to CI.

**Original issue.** Placement rendered each overlay once for measurement and
the render stage rendered it again. WP-P now reuses the prepared overlay;
avoiding duplicate work matters more once batch mode (WP-M) exists.

**Tasks.** Cache the prepared overlay from the sizing pass (keyed by plan
item) and reuse it in `_render_single_annotation`; byte-identity harness
proves output is unchanged; micro-benchmark before/after in the PR
description.

**Scope / DoD.** Done for DCM/JPG: byte-identical outputs, no public API
change, and focused reuse tests. Measurable speedup should be recorded in the
future PR/release note with the deterministic fixture above. **Depends on.**
WP-E split done, WP-I harness. **Leverage.** Low until WP-M, then medium.

---

## WP-Q — Run-Manifest Provenance Split (design, small)

**Goal.** Give `run_manifest.json` distinct provenance-only content instead of
duplicating `ground_truth.json`.

**Why now.** ADR-0004 documents the duplication as intentional-but-temporary;
WP-B's `RunRecord` plus WP-G's `reproducibility` block provide the natural
split (annotations → ground truth; parameters/environment → manifest).

**Deliverables.** Superseding ADR for ADR-0004 defining both file contents,
the schema-version bump (ADR-0008 lineage), and consumer migration notes.

**Depends on.** WP-B and WP-G implemented. **Leverage.** Low-medium (clarity,
smaller ground-truth files).

---

## WP-R — Output & CLI Hygiene Bundle (implementation, small)

**Goal.** Clear three small warts in reviewable passes.

**Tasks.**
1. **JPEG re-encode transparency.** Open. JPG runs still re-encode with
   Pillow defaults. ADR-0008 has no emission version gate for additive
   `render_metadata` fields, so this pass does not record partial encoder
   settings. Configurable quality stays behind a later byte-compat ADR.
2. **`identity_b` stdout noise.** Done 2026-07-13. The unused second identity
   generation and its stdout output were removed. `derive_seed()` remains
   available for real named random streams.
3. **Preview writer hygiene.** Done 2026-07-13. The internal
   `python -m injection_pipeline.writers.preview` CLI remains unregistered,
   requires `--dicom`, has no patient-style default path, and opens a
   Matplotlib window when the caller passes `--show`.

**Scope / DoD.** This pass covers identity and preview hygiene with tests; no
hardcoded `DycomData` patient paths remain in `src/`. Remaining DoD: decide
the ADR-0008 emission gate before adding JPEG encoder settings to
`render_metadata`. **Depends on.** WP-I harness; the remaining JPEG point also
depends on the ADR-0008 version decision. **Leverage.** Low.

---

## Suggested sequencing

```text
Architecture handoffs (docs/architecture/*, ADR review)   done for DICOM/JPG core
WP-I  E2E harness + CI          done 2026-07-12
WP-J  ScrabbleGAN + injection integration  open, parallel generator track with
     a defined runtime/CLI integration handoff
  after WP-B..WP-G DICOM/JPG handoffs:
WP-K  Validators & DICOM conformance
WP-L  Multi-frame policy        open, pairs with WP-K
WP-O  Declarative param spec    open, after WP-D stage split
WP-N  Docstring migration       open, spotchecks only in current pass
WP-Q  Manifest split            open, after ADR-0008 version decision
WP-M  Batch mode                open, after WP-G seed/clock core
WP-P  Render-pass reuse         done 2026-07-13
WP-R  Hygiene bundle            partially implemented; JPEG point waits for ADR-0008
```

## How to run a package

Design packages: point a fresh Fable session at one package ("Execute WP-K
from `docs/fable-work-packages.md`; read the referenced code, produce the
deliverable docs, end with an implementation handoff; do not modify `src/`").
Implementation packages: hand the package section plus its referenced spec to
Opus/Codex directly. Keep one package per session.
