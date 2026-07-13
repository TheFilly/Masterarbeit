# PDF Template Injection Implementation Plan

Status: **open, implementation not started**. The DICOM/JPG prerequisites
(models, runner stages, adapters, determinism harness) are complete. PDF WP1
through WP6, the PDF sidecar version, fixtures, dependency, composer, CLI, and
tests remain open; no PDF production code exists under `src/`.

Revised 2026-07-06 after design review (decisions confirmed by project owner;
original plan of 2026-06 superseded in place). Aligned with
`docs/architecture/adapter-contract.md` (PDF is a *composer*, not a loader),
`docs/architecture/domain-model-spec.md` (shared geometry models), and
ADR-0008 (one schema lineage) / ADR-0009 (determinism contract).

Build a PDF composition path that takes an existing DICOM/JPG injection run,
embeds the already PII-injected preview image into a synthetic report PDF, and
maps the existing image-space PII boxes into PDF page-space annotations.

**Key revisions vs. the original plan:**

1. **No input PDF, reportlab-only.** The original flow ("copy the input PDF
   and place the image") is not implementable with reportlab, which can only
   create PDFs, not modify them. Decision: the synthetic report template is
   *drawn by committed code* (template config JSON + a reportlab drawing
   module) and the composer produces each output PDF in a single pass —
   template content and embedded image together. No template PDF binary is
   committed, no second PDF library is added, and the template is synthetic by
   construction.
2. **Annotated PDF embeds the clean preview.** `preview_annotated.png` is a
   matplotlib figure whose pixel space does not match the ground-truth
   coordinate space (title, margins, dpi-dependent size), so polygons drawn
   over it can never align. Decision: `pdf_injected_annotated.pdf` embeds
   `preview.png` (which matches the annotation space exactly) and draws the
   transformed polygons on top — alignment is then a true visual check of the
   mapping. `preview_annotated.png` remains a pipeline artifact but is not
   used in PDFs.
3. **Purpose confirmed:** the PDF path exists for format breadth — inject into
   PDF as a third modality alongside DICOM and JPG. Embedded-image PII is the
   right v1; PDF-native text/table injection remains a later, separate stage.

## Scope

- In:
  - Use `ground_truth.json` from an existing DICOM/JPG run (loaded via the
    WP-B `load_run_record`, not raw JSON) as the source of the injected
    preview path and image-space box annotations.
  - Use `configs/pdf_templates/example_report.json` as the default template
    config; template *content* (title, boilerplate blocks, slot frames) is
    drawn by `pdf/template.py` from that config.
  - Generate `pdf_injected.pdf`, `pdf_injected_annotated.pdf`, and
    `pdf_annotations.json` per composition (see Output Artifacts for layout).
  - Transform image-space corners into PDF page-space corners for every
    embedded image annotation.
  - Support one target page initially while preserving `page_index` in the
    schema.
  - Support `top_left` and `top_right` template slots first, with later
    placement modes left open.
- Out:
  - Injecting PII into PDF-native free text (later stage, separate design).
  - Injecting PII into PDF table cells.
  - Inferring target locations through PDF text or table recognition.
  - Modifying externally supplied PDF files (requires a merge library; can be
    revisited if arbitrary real-world templates become a requirement).
  - Committing real patient data, MIMIC-derived content, or non-synthetic
    template text.

## Decisions

- The PDF path is a `RunComposer` (`adapter-contract.md`): it consumes a
  validated `RunRecord` from a finished run and produces derived artifacts. It
  is not a loader/writer format branch.
- `reportlab` is the only new dependency (accepted). No PDF-reading library.
- Primary command:
  `uv run injection-pipeline compose-pdf --ground-truth output/<run>/ground_truth.json`.
  Integrated PDF output from the normal injection run may follow once the
  composer is stable, hooked after the run record is built (never as a format
  branch in the runner).
- Both output PDFs embed `preview.png`. The annotated variant additionally
  draws PDF-space polygons (PII boxes red, optional prefix boxes blue,
  matching the preview-writer color convention).
- The sidecar records clean-PDF coordinates and references both PDF files.
- Template config is JSON (matches the identifier-schema config convention;
  no new config dependency). Slots are named entries, CLI-overridable.
- **Slot coordinates in the template config are PDF-native: bottom-left
  origin, units in PDF points.** The config schema states this explicitly;
  the `ImagePoint`/`PdfPoint` type split guards the boundary in code.
- Preview images are aspect-fit into the selected slot: scaled down when
  larger, **centered at native size when smaller (never upscaled)**.
- The coordinate mapping uses the **post-aspect-fit placement rectangle**,
  never the raw slot rectangle (see Coordinate Mapping).
- A slot outside the target page is a configuration error with a clear
  message.
- **Determinism:** the composer creates canvases with `invariant=1` and fixed
  producer metadata, so identical inputs produce byte-identical PDFs
  (ADR-0009). This upgrades testing: PDF hashes *may* be asserted.
- Composition parameters (template id, slot) are encoded in the output
  location so recompositions coexist instead of overwriting.

## Output Artifacts

Each composition writes into a parameter-scoped subfolder of the source run:

```text
<run_dir>/
`-- pdf/
    `-- <template_id>-<slot>/
        |-- pdf_injected.pdf
        |-- pdf_injected_annotated.pdf
        `-- pdf_annotations.json
```

`pdf_injected.pdf` is the realistic artifact (template content + embedded
clean preview). `pdf_injected_annotated.pdf` is the validation artifact (same
composition + PDF-space annotation polygons). `pdf_annotations.json` is the
machine-readable PDF ground-truth sidecar. Source-run artifacts are never
modified.

## Sidecar Schema Direction

Schema version `0.3.0-pdf-prototype`, registered in the single schema lineage
and changelog of ADR-0008 (shared numbering, own `record_type`). Do not
replace the existing run-record schema.

The sidecar (`PdfAnnotationRecord` in `pdf/models.py`) includes:

- `schema_version`, `record_type = "pdf_composition"`
- source linkage: `source_ground_truth_file`, **`source_run_id`,
  `source_seed`, `source_schema_version`** (paths move; identity fields make
  the link robust)
- `template_config_file`, `template_id`, `selected_slot`
- `pdf_files.clean`, `pdf_files.annotated`
- `page_annotations`, `layout_metadata` (includes the aspect-fit placement
  rectangle and scale factor)

Each embedded image annotation includes:

- annotation type, initially `embedded_image_box`
- original source annotation index, source label and text
- source image path and size in pixels
- original image corners as `ImagePoint`, transformed corners as `PdfPoint`
- page index
- image placement rectangle in PDF points
- coordinate-space metadata

`ImagePoint` and `PdfPoint` come from `models/geometry.py` (WP-B) — top-left
pixel origin vs. bottom-left point origin; the types are never
interchangeable. `pdf/models.py` defines only PDF-specific models (template
config, slots, placement, sidecar record).

## Coordinate Mapping

Image annotations use top-left image pixel coordinates. PDF annotations use
bottom-left page coordinates in PDF points. `rect_*` below is the
**placement rectangle after aspect-fit** (the area the image actually
occupies), not the configured slot. For each corner:

```text
pdf_x = rect_x + (image_x / image_width_px) * rect_width_pt
pdf_y = rect_y + rect_height_pt - (image_y / image_height_px) * rect_height_pt
```

The mapping preserves polygon corner order and is applied corner by corner,
including rotated polygons. Required test: an image whose aspect ratio
differs from the slot's must produce corners inside the drawn image area, not
merely inside the slot.

## Work Packages

### WP0: Predecessor Cleanup And Repository State

No PDF code has ever existed in this repository (`git log --all -- '*pdf*'` is
empty), so there is nothing to delete under `src/` or `tests/`. The cleanup
debt is entirely in the documentation and prototype layers, and it must be
settled *before* WP1 so the PDF work starts from a committed baseline.

**C0.1 - Doc-layer deletions are intentional.** The project owner retired the
prototype-doc and thesis-traceability layer on 2026-07-06. Do not recreate the
removed Research, Thesis, Template, or prototype README files for PDF work.
Current status belongs in `docs/architecture/`, `docs/decisions/`, and
operational docs.

**C0.2 — The frozen prototype artifacts are gone.** `prototypes/` is empty on
disk. The `prototypes/dicom/output_validation_*` runs that `AGENTS.md` and
`PLAN.md` describe as "frozen validation artifacts" no longer exist and were
never committable (`.gitignore`: `prototypes/dicom/output*/`). Record this
explicitly: the WP-I byte-identity harness has **no inherited reference set**
and must generate its own goldens from a committed synthetic fixture. Do not
plan any PDF validation against `prototypes/`.

**C0.3 - Stale active references are resolved.** `AGENTS.md`, `PLAN.md`, and
`docs/README.md` now point at the active architecture, decision, and
operational documentation layer instead of the removed Research/Thesis/Template
directories.

**C0.4 — Commit the untracked design round.** `docs/architecture/` (8 specs),
`docs/decisions/ADR-0001..0009`, `docs/fable-work-packages.md`, and this plan
are all untracked. Commit them before WP1; this plan cites them as normative.
ADR-0006, ADR-0008, and ADR-0009 are load-bearing here and are still
`status: proposed` — either move them to `accepted` in that commit, or state
in the WP1 PR that the PDF work proceeds on proposed ADRs and will be revised
if review changes them.

**C0.5 — The superseded 2026-06 plan.** It was revised in place and never
committed, so no archival copy is recoverable from history. If a local copy
survives, place it at `docs/archive/pdf-template-injection-plan-2026-06.md`;
otherwise the supersession note in this document's header is the only record,
which is acceptable. Do not reconstruct it.

**C0.6 — Establish a committable run fixture.** The only `ground_truth.json`
in existence is in the single local run directory
`output/dcm-01072026-1350-seed0045-angle020-corners-fs100-arial-none/`, which
sits under a gitignored `output/` and carries a 125 MB DICOM. PDF tests must
not depend on it. Create `tests/fixtures/runs/example/` containing a
synthetic, hand-built `ground_truth.json` (three box annotations, one of them
rotated) and a small synthetic `preview.png` (≤ 100 KB, non-square, aspect
ratio deliberately different from the default slot). No real or MIMIC-derived
content. This fixture is the input for every WP2–WP5 test.

**C0.7 — Do not write PDFs into the source run directory.** The Output
Artifacts layout above nests `pdf/<template_id>-<slot>/` inside `<run_dir>/`.
The WP-I byte-identity harness compares *all* artifacts in a run directory; a
composer that adds files there will make the harness fail or force it to grow
an exclusion rule. Decide before WP4: either (a) the harness ignores
`<run_dir>/pdf/**` by rule, or (b) compositions write to
`output/pdf/<run_id>/<template_id>-<slot>/`. Option (b) keeps the invariant
"source-run artifacts are never modified" literally true, at the cost of
splitting a run's outputs across two trees. Record the choice in this plan.

### WP1: Dependency, Package, And Models

Files:

- Modify `pyproject.toml`
- Create `src/injection_pipeline/pdf/__init__.py`
- Create `src/injection_pipeline/pdf/models.py`
- Create `tests/unit/test_pdf_models.py`

Tasks:

- Add `reportlab>=4.0`.
- Define strict pydantic models for PDF file sets, template slots, template
  configs, placement metadata, embedded image annotations, and the sidecar
  record. Point/quad types are imported from `models/geometry.py` (implement
  that WP-B slice first if not yet present).
- Keep models independent from DICOM-specific concepts.
- Validate that four-corner polygons contain exactly four points (via the
  shared `Quad`).
- Ensure path fields serialize as strings.

### WP2: Geometry And Slot Placement

Files:

- Create `src/injection_pipeline/pdf/geometry.py`
- Create `tests/unit/test_pdf_geometry.py`

Tasks:

- Implement aspect-fit placement inside a slot rectangle (down-scale only;
  center at native size when smaller), returning the placement rectangle and
  scale factor.
- Implement image-corner to PDF-corner mapping against the placement
  rectangle.
- Preserve polygon corner order; validate y-axis inversion at top-left and
  bottom-right; validate non-square images, rotated polygons, and the
  aspect-mismatch case.
- Reject slot rectangles outside the target page with a clear error.

### WP3: Ground Truth And Template Resolution

Files:

- Create `src/injection_pipeline/pdf/ground_truth.py`
- Create `src/injection_pipeline/pdf/template.py`
- Create `configs/pdf_templates/example_report.json`
- Create `tests/unit/test_pdf_ground_truth.py`
- Create `tests/unit/test_pdf_template.py`

Tasks:

- Load the source run via `load_run_record` (WP-B); the model already
  validates `box_annotations` and corner arity — no manual JSON checks.
- Resolve `preview_file` relative to the ground-truth file when needed; a
  missing preview fails clearly.
- Define and load the template config: `template_id`, page size in points,
  named slots (bottom-left origin, points), and synthetic content blocks
  (title, boilerplate paragraphs, frame styling) that `template.py` draws with
  reportlab. All content text must be synthetic placeholder material.
- Resolve the selected slot from config, with CLI override support.

### WP4: PDF Composer

Files:

- Create `src/injection_pipeline/pdf/composer.py`
- Create `tests/unit/test_pdf_composer.py`

Tasks:

- Single-pass composition: draw template content, place `preview.png` into
  the placement rectangle, and (for the annotated variant) draw transformed
  PDF-space polygons — one reportlab canvas per output file, `invariant=1`,
  fixed metadata.
- Write `pdf_annotations.json` with clean-PDF coordinates and references to
  both PDF outputs.
- Structural assertions (file existence, annotation counts, bounds, sidecar
  model validity) plus **byte-reproducibility assertions**: composing twice
  from the same inputs yields identical PDF bytes.

### WP5: CLI Integration

Files:

- Modify `src/injection_pipeline/runtime/cli.py`
- Add CLI tests under `tests/unit/`

Tasks:

- Add a `compose-pdf` subcommand: `--ground-truth` (required), `--template`
  (config path, default `configs/pdf_templates/example_report.json`),
  `--slot` (default from config). No `--input-pdf` (removed with the input-PDF
  concept).
- Existing pipeline behavior unchanged when PDF output is not requested;
  integrated run support only after the standalone path is stable and the
  WP-D runner decomposition has landed (hook after record building).
- Print generated PDF and sidecar paths.

### WP6: Documentation

Files:

- Modify `docs/dicom-injection.md`
- Optionally add `docs/pdf-template-injection.md`

Tasks:

- Document the composer flow, template config fields (origin/units
  convention explicitly), default paths, and the output subfolder layout.
- Document coordinate spaces and the image-to-PDF transformation, including
  the placement-rectangle rule.
- Document `0.3.0-pdf-prototype` sidecar fields and its place in the shared
  schema lineage.
- State that PDF-native text and table injection is out of scope for v1, and
  that all template content is synthetic by construction (generated from
  committed code and config, never from external documents).

## Test Scenarios

- Existing DICOM/JPG runs still pass without PDF generation.
- A ground-truth file with three image boxes creates three PDF annotations.
- Top-left image coordinates map to the top-left of the placement rectangle;
  bottom-right maps to the bottom-right.
- Aspect mismatch: corners land inside the drawn image, not just the slot.
- Small image: centered at native size, no upscaling; annotations correct.
- Rotated image polygons remain polygons and preserve point order.
- Slot override selects `top_left` or `top_right`.
- Missing preview file fails clearly.
- Malformed ground truth fails at `load_run_record` validation.
- Slot outside the page fails with a configuration error.
- All three artifacts are created, non-empty, in the parameter-scoped
  subfolder; a second composition with a different slot coexists with the
  first.
- Sidecar validates against the pydantic model and contains the source
  run-identity fields.
- Byte-reproducibility: same inputs → identical PDF bytes (invariant mode).

## Validation Commands

```bash
uv run pytest tests/unit/test_pdf_models.py -v
uv run pytest tests/unit/test_pdf_geometry.py -v
uv run pytest tests/unit/test_pdf_ground_truth.py tests/unit/test_pdf_template.py -v
uv run pytest tests/unit/test_pdf_composer.py -v
uv run pytest tests/ -x
uv run ruff check src/ tests/
uv run mypy src/
```

## Risks And Notes

- Adding `reportlab` requires dependency sync approval if the environment
  needs to download packages.
- WP1 has a real dependency on the WP-B geometry models
  (`models/geometry.py`); implement at least that slice of WP-B first rather
  than duplicating point types in `pdf/`.
- For JPG runs the composer embeds `preview.png` (a PNG re-encode of the
  injected frame) rather than the injected `.jpg` itself — deliberate for v1:
  one embedding path for both formats, identical coordinate guarantees.
- If arbitrary externally-authored PDF templates ever become a requirement,
  that reopens the merge-library decision (`pypdf`) — record it as a new ADR
  rather than bending this design.
- The current scope embeds the already-injected preview image only. PDF-native
  free-text and table-cell injection are later, separately designed stages
  (they will need `SpanAnnotation`-style ground truth, not `Quad` boxes
  alone).
