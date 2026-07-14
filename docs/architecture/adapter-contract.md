# Format Adapter Contract (WP-F)

Status: implemented for DICOM/JPG and the dedicated PDF workflow, updated
2026-07-14. ADR-0006 defines one loader/writer seam per injected modality.

## Contract

```python
class DocumentLoader(Protocol):
    format_id: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    def load(self, path: Path) -> SourceDocument: ...

class DocumentWriter(Protocol):
    format_id: ClassVar[str]
    output_suffix: ClassVar[str]
    def write(self, document: InjectedDocument, output_path: Path) -> None: ...
```

`SourceDocument` and `InjectedDocument` are the typed seam models in
`models/adapters.py`. DICOM and JPG use the contract directly. Their registry
entries are resolved by source extension and the runner does not contain
format-specific load/save branches.

## PDF modality

PDF is a first-class input modality, not a post-run composer. The PDF operation
accepts an input PDF template, an already injected DICOM, and that DICOM run's
JSON annotation. The PDF loader validates the input PDF and page geometry. The
existing DICOM loader reads the injected frame, and the canonical run-record
loader validates the annotation. The PDF writer places the preview associated
with that frame on the
selected page, maps image-space quads to PDF-space quads, merges a new layer
onto a copy of the input PDF, and writes the PDF sidecar.

PDF-specific request/response models live in `injection_pipeline/pdf/`. They
own page, slot, placement, and sidecar fields; shared `ImagePoint`, `PdfPoint`,
and `Quad` remain in `models/geometry.py`. The PDF implementation must not add
PDF branches to the DICOM/JPG injection engine.

Concrete entry points are `PdfLoader.load(path)` and
`PdfWriterAdapter.write(template, dicom_path, annotation_path, output_root,
slot, page_index)`. The writer returns typed PDF output artifacts.

| Concern | DICOM | JPG | PDF |
|---|---|---|---|
| Loader | pydicom dataset and frame | Pillow RGB image | PDF pages and page geometry |
| Metadata injection | DICOM tag plan | none | none |
| Write | DICOM pixel array and tags | JPEG pixels | reportlab overlay merged with input via pypdf |
| Output | `.dcm` | `.jpg` | `.pdf` plus JSON sidecar |

The PDF source files are never modified. Output is written under
`output/pdf/<run_id>/<template-stem>-<slot>/` so the source DICOM run remains
byte-identical for the DICOM/JPG reproducibility harness.

## PDF implementation handoff

The approved scope and tests are maintained in
`docs/pdf-template-injection-plan.md`. The implementation adds `reportlab` and
`pypdf`, exposes a PDF loader/writer pair, and exposes a CLI operation that
requires `--input-pdf`, `--input-dicom`, and `--dicom-annotation` (plus optional
`--output-dir`, `--slot`, and `--page-index`). It must
preserve all input PDF pages and source annotation/corner order.

## Implementation status

Implemented for DICOM/JPG:

- adapter models, protocols, and extension registry;
- DICOM loader/writer with tag mutation and pixel persistence;
- JPG loader/writer with RGB conversion and JPEG persistence; and
- runner lookup and unit/integration coverage.

PDF loader/writer, sidecar models, and CLI are implemented. Broader
operational fixture coverage remains open. Their schema version is
`0.3.0-pdf-prototype` under ADR-0008.
