# Format Adapter Contract (WP-F)

Status: implemented for DICOM/JPG, updated 2026-07-12. Implements ADR-0006 for
injected source documents. PDF remains a planned downstream composer, not an
implemented loader/writer path.

## The seam before WP-F

- DICOM: `loaders/dicom.py` (load + summarize) and `writers/dicom.py` (save),
  called from a `document_type == "dcm"` branch (`runner.py:612-636`).
- JPG: `Image.open(...).convert("RGB")` and `image.save(...)` inline in the
  orchestrator (`runner.py:638`, `:651`).
- The engine already converges: both paths call the same frame-level renderer
  (`_inject_visible_text_into_frame`, `engine/pixel_injection.py:280`). The
  only genuinely format-specific work is: producing a frame, applying
  format-native metadata injection (DICOM tags), and persisting pixels back.

That convergence is the contract's foundation: **an adapter's job is to get a
frame out and pixels (plus format metadata) back in.**

## Implementation status, 2026-07-12

Implemented:

- `models/adapters.py` defines `SourceDocument`, `InjectedDocument`,
  `DocumentLoader`, `DocumentWriter`, and `TagPlan`.
- `loaders/registry.py` resolves DCM/JPG adapter pairs by extension.
- `loaders/dicom.py` and `writers/dicom.py` implement the DICOM adapter pair.
- `loaders/jpg.py` and `writers/jpg.py` implement the JPG adapter pair.
- `runner.py` uses the registry and no longer contains DCM/JPG load/save
  branches.
- `DocumentWriter.write(document: InjectedDocument, output_path: Path) -> None`
  is the implemented write contract.

Remaining:

- PDF composer package, sidecar model, and CLI are not implemented.

## Contract (models in `models/adapters.py`, protocols in `loaders/`/`writers/`)

```python
class SourceDocument(BaseModel):            # arbitrary types allowed
    format_id: str                          # "dcm", "jpg", ...
    path: Path
    frame: Any                              # np.ndarray, the render target frame
    frame_count: int                        # 1 for single-frame formats
    native: Any | None                      # format handle (pydicom Dataset, PIL Image)
    context: DicomContext | None            # summarized source metadata, format-optional

class InjectedDocument(BaseModel):
    source: SourceDocument
    rendered_frame: Any                     # np.ndarray after pixel injection
    native: Any | None                      # mutated format handle, if any
    tag_annotations: list[DicomTagAnnotation]
    box_annotations: list[BoxAnnotation]
    output_context: DicomContext | None

class DocumentLoader(Protocol):
    format_id: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    def load(self, path: Path) -> SourceDocument: ...

class DocumentWriter(Protocol):
    format_id: ClassVar[str]
    output_suffix: ClassVar[str]
    def inject_native_metadata(
        self, document: SourceDocument, tag_plan: TagPlan
    ) -> list[DicomTagAnnotation]: ...      # no-op ([]) for raster formats
    def write(self, document: InjectedDocument, output_path: Path) -> None: ...
```

Registry (`loaders/registry.py`): `register(loader, writer)` at import time;
`resolve(path) -> tuple[DocumentLoader, DocumentWriter]` by extension. The
orchestrator's format branch (`runner.py:612`) becomes a lookup;
`_detect_input_type`'s unsupported-format `ValueError` (`runner.py:244`)
becomes the registry's miss error with the same message contract.

Notes on shape choices:

- `native: Any` is deliberate: forcing pydicom/PIL types into pydantic fields
  buys nothing; the *seam* payloads (annotations, contexts) are the typed
  part. `SourceDocument` uses `model_config = ConfigDict(arbitrary_types_allowed=True)`.
- `inject_native_metadata` sits on the Writer, not the Loader, because tag
  injection mutates the object that will be persisted (today:
  `inject_tags(ds, tag_map)` then later `save_dicom`, `runner.py:615/:630`).
  For JPG it returns `[]` — exactly today's `tag_annotations = []`
  (`runner.py:652`).
- `output_context` mirrors `summarize_dicom(ds)` *after* injection
  (`runner.py:629`); raster formats leave it `None`, preserving the
  both-or-neither context rule (`runner.py:556`).

## The three formats under the contract

| Concern | DICOM | JPG | PDF |
|---|---|---|---|
| `load` | `pydicom.dcmread`; frame via `extract_preview_frame`; context via `summarize_dicom` | `Image.open(...).convert("RGB")`; frame = `np.asarray(image)` | n/a — see below |
| native metadata | `inject_tags` (`engine/dicom_tags.py:9`) + tag annotations | none | none |
| pixel writeback | `_write_pixel_array` (moves here per WP-E step 5) + `dcmwrite` | `Image.fromarray(...).save(..., format="JPEG")` | n/a |
| output suffix | `.dcm` | `.jpg` | `.pdf` |

**PDF is a composer, not a loader.** The PDF plan consumes a *finished run's*
`ground_truth.json` and preview images and produces new artifacts in the same
run folder. It never loads a source document into the injection engine, so
forcing it through `DocumentLoader` would violate the adapter boundary. The
target shape:

```python
class RunComposer(Protocol):                 # pdf/composer.py implements this
    composer_id: ClassVar[str]               # "pdf_template"
    def compose(self, record: RunRecord, config: Any) -> ComposedArtifacts: ...
```

Composers are a second, downstream extension point (input: validated
`RunRecord`; output: sidecar record under the ADR-0008 lineage). This keeps
"format peers" honest — loaders/writers for injection targets, composers for
derived artifacts — and `compose-pdf` (PDF plan WP5) is just the CLI face of
the first composer.

## Review: PDF plan WP1-WP6 against this contract

> **Resolved 2026-07-06:** `docs/pdf-template-injection-plan.md` was revised
> to incorporate every adjustment below, plus two review findings beyond this
> contract's scope: the original "copy the input PDF" flow was impossible with
> reportlab alone (resolved: reportlab-only single-pass composition from a
> config-driven drawn template — no input PDF, no merge library), and the
> annotated PDF now embeds the clean preview because the matplotlib
> `preview_annotated.png` does not share the annotation coordinate space. The
> table is kept as the review record; the revised plan is authoritative.

| PDF plan item | Verdict | Adjustment |
|---|---|---|
| WP1 models in `pdf/models.py` (`ImagePoint`, `PdfPoint`, quads, sidecar) | adjust | Point/quad models move to `models/geometry.py` (WP-B); `pdf/models.py` keeps only PDF-specific models (template slots, placement, `PdfAnnotationRecord`). Keeps "separate ImagePoint/PdfPoint" decision — it agrees with WP-B. |
| WP1 sidecar `0.3.0-pdf-prototype` | adjust | Version joins the single lineage + changelog of ADR-0008; the string itself stays. |
| WP2 geometry (`pdf/geometry.py`) | aligns | Image→PDF corner mapping is PDF-specific; stays in `pdf/`. Consumes `ImagePoint`/`PdfPoint` from `models/`. |
| WP3 ground-truth loading | adjust | Must load via WP-B's `load_run_record` (validated `RunRecord`), not raw JSON + manual `box_annotations` checks — the model already validates corners/quads. Relative-path resolution stays. |
| WP3 template config JSON under `configs/pdf_templates/` | aligns | Same config conventions as the WP-C identifier schema (JSON + pydantic loader in `config/`). |
| WP4 writer (`pdf/writer.py`) | aligns | It is the composer implementation; structural (non-byte) assertions are the right call for reportlab output. Determinism requirement joins the ADR-0009 contract (reportlab embeds creation timestamps — set `invariant=1` / fixed metadata, see WP-G N9). |
| WP5 CLI `compose-pdf` + runner integration | adjust | `compose-pdf` lands as a subcommand calling the composer; the "integrated output path" in `run` waits until the WP-D decomposition is done, then hooks after the record is built (stage 7) — not another branch inside the format dispatch. |
| WP6 docs | aligns | Add: PDF sidecar is a composer artifact under the shared schema lineage. |

Conflicts found: none fatal. The two structural corrections are (1) models
fold into `models/`, (2) PDF is a composer, not a third loader branch.

## JPG regularization (first implementation step)

`loaders/jpg.py` + `writers/jpg.py` implementing the protocols with today's
exact calls (`convert("RGB")` on load; `format="JPEG"` with default quality on
save — do not add quality parameters, bytes must not change). The
`example_type` derivation (`runner.py:226`) stays in input resolution, not in
the adapter — it is provenance labeling, not format handling.

## Implementation Status

### Implemented 2026-07-12

- Adapter models, protocols, and registry.
- DICOM adapter pair, including DICOM tag mutation and pixel persistence.
- JPG adapter pair with the existing RGB conversion and Pillow JPEG defaults.
- Runner registry lookup for DCM/JPG.
- Unit tests for registry resolution, registry miss errors, fake adapters,
  DICOM writeback, JPG round-trip, and multiframe grayscale preservation.

### Remaining

- PDF path: not implemented. It stays a future `RunComposer` consumer of a
  validated `RunRecord`, with schema versioning gated by ADR-0008.

Definition of done update: DCM/JPG adapters are implemented and covered. PDF is
outside the completed WP-F slice.
