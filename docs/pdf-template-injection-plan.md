# PDF Template Injection Implementation Plan

Status: **implemented** (2026-07-14). PDF is a first-class injection modality.
It has its own loader and writer, like DICOM and JPG; it is not a post-run
composer.

## Purpose and input contract

The PDF path combines three inputs:

1. an existing PDF template (`--input-pdf`),
2. an already injected DICOM (`--input-dicom`), and
3. the DICOM run's JSON ground-truth annotation (`--dicom-annotation`).

The PDF loader validates the template and exposes its page geometry. The DICOM
loader reads the injected pixel frame and the annotation loader validates the
corresponding `RunRecord`. The PDF writer places the preview associated with
the injected DICOM on
the selected template page, transforms image-space annotations to PDF-space,
and writes a new PDF plus a PDF annotation sidecar. Neither source file is
modified. PDF-native text/table injection is out of scope for this first
modality slice.

The adapter boundary remains explicit: PDF-specific models describe template
pages, placement, and output artifacts; shared `ImagePoint`, `PdfPoint`, and
`Quad` models describe annotation geometry. The PDF CLI selects the dedicated
pair and does not add PDF business rules to the DICOM/JPG runner.

## Decisions

- PDF uses a dedicated loader/writer pair for the `inject-pdf` workflow. It is
  intentionally not registered in the DICOM/JPG single-input registry because
  PDF injection requires a PDF, an injected DICOM, and a ground-truth file.
- `reportlab` creates the injected layer and `pypdf` merges it with the input
  template. Both are approved runtime dependencies.
- The default placement is `top_left`; `top_right` and an explicit supported
  slot override can be selected for the target template.
- Template coordinates use PDF points and a bottom-left origin. Image
  coordinates use pixels and a top-left origin. The coordinate types are not
  interchangeable.
- Aspect-fit scales the DICOM image down when necessary and centers a smaller
  image at native size; it never upscales. Annotations map against the actual
  placement rectangle, not the configured slot.
- The output root is `output/pdf/<run_id>/<template-stem>-<slot>/`. Source PDF,
  DICOM, and DICOM ground truth remain untouched.
- PDF output is deterministic for identical inputs, configuration, and seed;
  fixed metadata is used where the PDF backend permits it.
- ADR-0008 is accepted. The PDF sidecar uses the shared schema lineage and
  version `0.3.0-pdf-prototype`.

## Output artifacts

Each invocation writes:

```text
output/pdf/<run_id>/<template-stem>-<slot>/
|-- pdf_injected.pdf
|-- pdf_injected_annotated.pdf
|-- pdf_annotations.json
```

`pdf_injected.pdf` is the template with the preview from the injected DICOM.
`pdf_injected_annotated.pdf` adds visible transformed annotation outlines.
`pdf_annotations.json` contains the transformed PDF ground truth and source
linkage. The sidecar records all input paths and selected layout.

## Sidecar schema (`0.3.0-pdf-prototype`)

The sidecar uses `record_type = "pdf_injection_run"` in the single ADR-0008
lineage. It
contains:

- source PDF, DICOM, and DICOM ground-truth paths, plus the required source run
  identity fields (`source_run_id`, `source_seed`, and
  `source_schema_version`),
- template identifier, selected slot, page index, page size, and placement
  rectangle,
- source image dimensions and the image-to-PDF coordinate-space metadata,
- one transformed four-corner annotation for every source DICOM box, and
- references to the generated PDF and sidecar files.

The sidecar must preserve source annotation order and corner order. Loading a
malformed DICOM annotation fails through the canonical `RunRecord` validator;
the PDF writer does not duplicate JSON validation logic.

## Coordinate mapping

For an image point `(x, y)` in pixels and its post-aspect-fit placement
rectangle `(left, bottom, width, height)` in PDF points:

```text
pdf_x = left + (x / image_width_px) * width
pdf_y = bottom + height - (y / image_height_px) * height
```

The mapping is applied corner by corner, including rotated polygons. A slot
outside the target page, a missing source image, or an annotation outside the
source image bounds is a clear configuration/validation error.

## Work packages

### WP-PDF-1 — dependencies and models

Add `reportlab` and `pypdf`; update the lock file. Add PDF-specific pydantic
models for source inputs, page/slot geometry, placement, output artifacts, and
the `0.3.0-pdf-prototype` sidecar. Reuse shared geometry models.

### WP-PDF-2 — PDF and DICOM loading

Implement the PDF loader as the dedicated PDF workflow adapter. It must reject
unreadable or empty PDFs and expose page size/count. Reuse the existing DICOM
loader for the injected DICOM and load its `ground_truth.json` through
`load_run_record`.

### WP-PDF-3 — placement and coordinate transformation

Implement slot resolution, page-bound checks, aspect-fit placement, and the
image-to-PDF mapping. Cover non-square images, aspect mismatch, native-size
centering, and rotated quads with unit tests.

### WP-PDF-4 — PDF writing

Create the reportlab overlay, merge it onto the selected input-PDF page with
`pypdf`, and emit the PDF sidecar. Preserve all input pages and PDF metadata
unless the writer must replace volatile producer fields for determinism.

### WP-PDF-5 — CLI and integration

Add `inject-pdf` (with the `compose-pdf` alias) requiring `--input-pdf`,
`--input-dicom`, and `--dicom-annotation`, with optional `--output-dir`,
`--slot`, and `--page-index`. Existing DICOM/JPG CLI behaviour remains
unchanged. Print generated PDF and sidecar paths. The adapter entry points are
`PdfLoader.load` and `PdfWriterAdapter.write`.

### WP-PDF-6 — tests, fixture, and local validation

Use synthetic committed fixtures for unit/integration tests. Additionally run
one local smoke test with a DICOM from `DycomData/Dicom-Files`, write its
injected result and annotation under `DycomData/InjectedDicom`, and use the
existing PDF under `DycomData/pdf`. Local generated data is ignored and is not
committed.

### WP-PDF-7 — documentation and provenance

Update the adapter contract, target architecture, DICOM operational guide,
and schema/domain documentation. Add the ADR-0008 schema changelog and mark
the decision accepted.

## Required tests and gates

- PDF loader rejects missing, unreadable, and empty inputs.
- DICOM and annotation linkage is validated before writing.
- All source PDF pages are preserved in the output.
- Aspect mismatch maps corners inside the drawn image, not merely inside the
  configured slot.
- Top-left and bottom-right image points map to the corresponding placement
  corners; y-axis inversion is covered.
- Rotated polygons preserve point order.
- Slot/page bounds and missing-preview failures are clear.
- Output PDF and sidecar are non-empty and sidecar validation succeeds.
- Repeating a run with identical inputs produces identical sidecar content and
  deterministic PDF bytes where supported.
- Existing DICOM/JPG unit, integration, ruff, and mypy gates remain green.
