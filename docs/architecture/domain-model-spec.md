# Canonical Domain & Ground-Truth Schema Design (WP-B)

Status: implemented for the DICOM/JPG core chain, updated 2026-07-12. Implements
ADR-0005 for current runs and partially implements ADR-0008 by parsing/emitting
`0.2.0-prototype`. Version-safe additive provenance fields and PDF sidecars
remain open.

Source of truth for current behaviour: `ground_truth.build_record()`, the
planning functions in `planning.py`, annotation construction in
`engine/injector.py`, the models under `models/`, and the documented artifact
surface in `docs/dicom-injection.md`.

## Design constraints

1. **Byte-compat first.** `model_dump(mode="json")` of the new `RunRecord`
   must reproduce today's `ground_truth.json` byte-for-byte for the frozen
   validation runs (key order, `null`s, float formatting). Key order in JSON
   follows pydantic field declaration order — declare fields in exactly the
   current emission order.
2. **`_make_json_safe` is designed out.** `Path`-typed fields serialize to
   strings natively; tuples become `list[...]`-typed fields. No custom shim.
3. **Taxonomy-agnostic.** No model hardcodes field names like `patient_name`;
   identity payloads are keyed dynamically and validated against the WP-C
   identifier schema at load time, not by model structure.
4. **One hierarchy for all formats.** DCM, JPG (and later PDF) reuse the same
   annotation and record models; format-specific data lives in clearly marked
   optional substructures.

## Model tree

```text
models/
├── geometry.py     ImagePoint, PdfPoint, Quad, MaskBounds
├── segments.py     TextSegment
├── identity.py     Identity
├── annotations.py  BoxAnnotation, DicomTagAnnotation, SpanAnnotation
├── rendering.py    RenderPlanItem, HandwritingAssetRef, RenderedAnnotation,
│                   AnnotationRenderDetail, EngineRenderMetadata
├── dicom.py        DicomContext
├── record.py       RunMetadata, RecordRenderMetadata, RunRecord
└── adapters.py     SourceDocument, InjectedDocument, WrittenArtifacts (WP-F)
```

All models: `model_config = ConfigDict(extra="forbid")` unless noted.

## Implementation status, 2026-07-12

Implemented:

- `models/geometry.py`, `segments.py`, `identity.py`, `annotations.py`,
  `dicom.py`, `rendering.py`, `record.py`, and `adapters.py`.
- `ground_truth.build_record()` constructs a validated `RunRecord`; JSON
  artifact writing uses `model_dump(mode="json")`.
- `load_run_record()` accepts `0.2.0-prototype` and rejects unknown versions.
- Unit and E2E tests cover model validators, record round-trip behavior, and
  DCM/JPG artifact byte hashes.

Open:

- ADR-0008 schema changelog and future emitted versions.
- Identifier-schema provenance and reproducibility/environment fields in the
  emitted record.
- PDF sidecar models and composer output.

### Geometry (`models/geometry.py`)

| Model | Fields | Validation |
|---|---|---|
| `ImagePoint` | `x: float`, `y: float` | top-left origin, pixels. Serialized as `{"x": ..., "y": ...}`; matches `engine.geometry._rotated_corners()` output. |
| `PdfPoint` | `x: float`, `y: float` | bottom-left origin, PDF points. Distinct type per the PDF plan ("Sidecar Schema Direction") — never interchangeable with `ImagePoint`. |
| `Quad` | `list[ImagePoint]` (annotated type or RootModel) | exactly 4 points, corner order preserved (top-left, top-right, bottom-right, bottom-left before rotation). |
| `MaskBounds` | `left: int`, `top: int`, `right: int`, `bottom: int`, `width: int`, `height: int` | `width == right - left`, `height == bottom - top` (model validator). |

### Text segments (`models/segments.py`)

`TextSegment`: `kind: Literal["generic", "pii"]`, `text: str`. List-level
validation (used by `RenderPlanItem`): concatenated segment texts equal the
full rendered text, and at least one non-empty `pii` segment exists. The model
owns this normalization and validation.

### Identity (`models/identity.py`)

```python
Identity:
    identity_id: str          # selected by identifier_schema.identity_id_field
    seed: int                 # the seed that produced it
    fields: dict[str, str]    # field name -> value, keys from the identifier schema
```

Rationale: a fixed-attribute `Identity(patient_name=..., ...)` would re-hardcode
the taxonomy that WP-C externalizes. The identifier schema (WP-C) validates
which keys must be present; the model only guarantees shape. `identity_id`
stays a plain string whose *derivation* (today: the `patient_id` field) is a
schema-level rule (`identity_id_field` in the WP-C schema), not a model rule.

### Annotations (`models/annotations.py`)

`BoxAnnotation` — one visibly rendered PII box, built by
`engine.injector._build_box_annotation()`:

| Field | Type | Today's key |
|---|---|---|
| `label` | `str` | `label` |
| `text` | `str` | `text` (the PII part only) |
| `rendered_text` | `str` | `rendered_text` (prefix + PII) |
| `region` | `str` | `region` (`top_left` \| `top_right` \| `bottom_left` \| `bottom_right` \| `free`; keep `str`, values come from placement) |
| `corners` | `Quad` | `corners` |
| `label_corners` | `Quad \| None` | `label_corners` (`null` without prefix) |
| `rotation_degrees` | `int` | `rotation_degrees` |
| `frame_index` | `int` | `frame_index` (always 0 today) |
| `font_size_pct` | `int` | `font_size_pct` |

`DicomTagAnnotation` — one injected DICOM tag, built by
`planning.build_tag_annotations()`:

| Field | Type | Today's key |
|---|---|---|
| `label` | `str` | `label` |
| `tag_address` | `str` | `tag_address` (`"0010,0010"` form; regex-validate `^[0-9A-F]{4},[0-9A-F]{4}$`) |
| `tag_keyword` | `str` | `tag_keyword` |
| `dicom_vr` | `str` | `dicom_vr` (2 uppercase letters) |
| `value` | `str` | `value` |
| `identity_field` | `str` | `identity_field` |
| `identity_id` | `str` | `identity_id` |
| `source_file` | `Path` | `source_file` (serializes to string) |
| `output_file` | `Path` | `output_file` |

`SpanAnnotation` — reserved for text-span formats (currently emitted as `[]`
by `ground_truth.build_record()`). Minimal now: `label: str`, `text: str`, `start: int`,
`end: int`, `identity_field: str`. Marked provisional; PLAN.md Phase 2 owns
its real design.

### Rendering (`models/rendering.py`)

`RenderPlanItem` — planner output and engine input, built by
`planning.build_visible_render_plan()` and optionally extended by
`engine.handwriting_manifest.apply_handwriting_assets()`:

- `label: str`, `text: str`, `text_segments: list[TextSegment]`,
  `identity_field: str`, `region: str`, `rotation_degrees: int`,
  `line_index: int`
- `renderer_type: Literal["font_text", "handwriting_asset"] = "font_text"`
- `asset_id: str | None = None`, `asset: HandwritingAssetRef | None = None`
- Engine-added placement fields (`position`, `padding`, `stroke_width`) belong to a
  derived `PlacedRenderItem`, not to the plan item: planning and placement are
  different stages with different data.

`HandwritingAssetRef` (normalized manifest entry from
`engine.handwriting_manifest.load_handwriting_manifest()`): `asset_id: str`,
`text: str`, `identity_field: str`, `ink_color: str | None`,
`background_mode: str | None`, `image_path: Path`, `mask_path: Path`.
`extra="allow"` — manifests carry generator-specific keys that must survive
into `render_metadata`.

`AnnotationRenderDetail` — per-annotation `render_metadata` built by the engine:
`position: {x, y}` (model
`PixelPosition(x: int, y: int)`), font fields (`font_family`, `font_name`,
`font_size`, `padding`, `fill_rgb: list[int]`, `stroke_fill_rgb`,
`stroke_width`, `background_enabled`, `background_color: list[int] | None`),
`text_segments: list[TextSegment]`, `geometry_source: str`,
`mask_coordinate_space: str`, `mask_alpha_threshold: int`,
`text_mask_bounds / pii_mask_bounds / label_mask_bounds: MaskBounds | None`,
`text_box_size / rotated_box_size: {width, height}`,
`rendered_text_corners: Quad`, and for handwriting: `renderer_type`,
`asset_id`, `asset_path: Path`, `mask_path: Path`, `ink_color`,
`background_mode`. Font-text and handwriting emit different key subsets —
model as one class with optional fields (simplest byte-compat) and revisit a
discriminated union after byte-compat is relaxed.

`RenderedAnnotation` — the `visible_annotations` entries produced by
`engine/injector.py`: `label`, `text`, `rendered_text`,
`generic_text`, `pii_text`, `region`, `rotation_degrees`, `corners: Quad`,
`label_corners: Quad | None`, `render_metadata: AnnotationRenderDetail`.

`EngineRenderMetadata` — the engine-level metadata block returned by
`engine/injector.py`: `seed: int`, `rotation_degrees: int`,
`allowed_rotations_degrees: list[int]`, `frame_count: int`,
`applied_frame_indices: list[int]`, `effective_font_family: str`,
`effective_font_size_px: int`, `background_enabled: bool`,
`background_color: list[int] | None`, `geometry_source: str`,
`renderer_types: list[str]`, `handwriting_assets: list[...]` (id/paths/ink
subset), `geometry_notes: str`,
`mask_alpha_threshold: int`, `visible_annotations: list[RenderedAnnotation]`.

### DICOM context (`models/dicom.py`)

`DicomContext` (from `summarize_dicom`, `loaders/dicom.py:20`): `modality`,
`sop_instance_uid`, `study_instance_uid`, `series_instance_uid` (all
`str | None`), `rows`, `columns`, `samples_per_pixel` (`int | None`),
`photometric_interpretation: str | None`, `number_of_frames: int | None`,
`has_pixel_data: bool`. Note: pydicom returns non-str element types
(`PersonName`, `UID`); the loader must coerce to `str` explicitly — today
`json.dump` handles `UID` because it subclasses `str`, so coercion is
behaviour-preserving.

### Run record (`models/record.py`)

`RunMetadata` (keys in emission order, defined in `models/record.py`):
`rotation_degrees: int`, `placement_mode: str`,
`pixel_injection_status: str`, `pixel_renderer: str`,
`visible_identity_fields: list[str]`, `tag_only_identity_fields: list[str]`,
`source_dicom_context: DicomContext | None = None`,
`output_dicom_context: DicomContext | None = None`.
Serialization rule: the two context fields are **omitted when None** (JPG runs
have no such keys; see `ground_truth.attach_dicom_contexts()`); everything
else serializes `None` as `null`. Implement with per-field
`model_serializer`/`exclude_none` handling limited to these two fields.

`RecordRenderMetadata` (`models/record.py`): `rotation_degrees: int`,
`placement_mode: str`, `font_size_pct: int`, `font_family: str`,
`text_background: str | None`, `visible_render_plan: list[RenderPlanItem]`,
then the flattened `EngineRenderMetadata` fields. To keep byte compatibility,
`ground_truth.build_record()` spreads the validated engine block into this
model *inlines* `EngineRenderMetadata`'s fields after `visible_render_plan`
(composition via flattened serialization, or plain field duplication —
implementer's choice, byte output is the contract).

`RunRecord` (field order = emission order, `models/record.py`):

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `str` | `"0.2.0-prototype"` emitted (ADR-0008) |
| `record_type` | `str` | `f"{document_type}_injection_run"` |
| `run_id` | `str` | |
| `seed` | `int` | |
| `rotation_degrees` | `int` | |
| `source_file` | `Path` | |
| `output_file` | `Path` | |
| `preview_file` | `Path` | accepts the engine preview path and serializes as a string |
| `annotated_preview_file` | `Path` | |
| `document_type` | `str` | `"dcm"` \| `"jpg"` today; open set for new formats |
| `example_type` | `str` | |
| `modality` | `str \| None` | `null` for JPG |
| `identity_id` | `str` | |
| `span_annotations` | `list[SpanAnnotation]` | `[]` today |
| `box_annotations` | `list[BoxAnnotation]` | |
| `dicom_tag_annotations` | `list[DicomTagAnnotation]` | `[]` for JPG |
| `run_metadata` | `RunMetadata` | |
| `render_metadata` | `RecordRenderMetadata` | |

Every key currently written by `ground_truth.build_record()` is accounted for
above. Pydantic serialization handles paths and nested typed metadata.

## Versioning (with ADR-0008)

- One lineage, documented in a `docs/architecture/schema-changelog.md` started
  by the implementer:
  - `0.2.0-prototype` — current run record (this spec's byte-compat target).
  - `0.3.0-pdf-prototype` — PDF sidecar (`PdfAnnotationRecord`, defined by the
    PDF plan WP1 but its point/quad models come from `models/geometry.py`).
  - `0.4.0` — first version emitted *by* the pydantic models once byte-compat
    with `0.2.0-prototype` is deliberately retired (future ADR; not part of
    this package).
- The models parse all published versions: a `schema_version`-dispatching
  `load_run_record(path)` in `models/record.py`, with golden fixture files per
  version under `tests/fixtures/schemas/`. Old `ground_truth.json` files keep
  parsing forever or their version is explicitly dropped by ADR.
- Additive change = MINOR bump + new golden file. Breaking change = MAJOR (or
  pre-1.0: MINOR with migration note) + ADR.

## Byte-compat notes (golden-test checklist)

- `json.dump(record, indent=2)` + trailing `"\n"` for `ground_truth.json`; no
  trailing newline for `run_manifest.json` (`ground_truth.write_run_artifacts()`,
  ADR-0004).
- Corner coordinates are `round(value, 2)` floats — `100.0` must emit as
  `100.0`, not `100`; keep fields `float`, never `int`-coerce.
- `label_corners`/`label_mask_bounds` emit `null` (not omitted) when absent.
- `run_metadata.source_dicom_context`/`output_dicom_context` are *omitted*
  (not `null`) for JPG runs.
- Handwriting-asset entries in `visible_render_plan` carry the full normalized
  asset mapping including absolute paths (today stringified by
  `_make_json_safe`); `HandwritingAssetRef` with `Path` fields reproduces this.
- Font name fallback `"PillowDefaultFont"` (`engine/overlay.py`) is part of the
  surface.

## Annotated example (abbreviated DCM run)

```jsonc
{
  "schema_version": "0.2.0-prototype",        // RunRecord.schema_version
  "record_type": "dcm_injection_run",         // RunRecord.record_type
  "run_id": "dcm-27052026-1435-seed0042-angle020-corners-fs100-arial-none",
  "seed": 42,
  "rotation_degrees": 20,
  "source_file": "DycomData/Dicom-Files/91180014_0001.dcm",   // Path -> str
  "output_file": "output/dcm-.../91180014_0001_injected.dcm",
  "preview_file": "output/dcm-.../preview.png",
  "annotated_preview_file": "output/dcm-.../preview_annotated.png",
  "document_type": "dcm",
  "example_type": "dicom-files",
  "modality": "US",                            // null for JPG runs
  "identity_id": "SYNTH-661414",
  "span_annotations": [],                      // list[SpanAnnotation]
  "box_annotations": [
    {
      "label": "PatientID",
      "text": "661414",                        // PII part only
      "rendered_text": "SYNTH-661414",         // prefix + PII
      "region": "top_left",
      "corners": [ {"x": 74.13, "y": 30.0}, ... ],   // Quad of ImagePoint
      "label_corners": [ ... ],                // null when no prefix
      "rotation_degrees": 20,
      "frame_index": 0,
      "font_size_pct": 100
    }
  ],
  "dicom_tag_annotations": [
    {
      "label": "PatientName",
      "tag_address": "0010,0010",
      "tag_keyword": "PatientName",
      "dicom_vr": "PN",
      "value": "Smith^Anna",
      "identity_field": "patient_name",
      "identity_id": "SYNTH-661414",
      "source_file": "...", "output_file": "..."
    }
  ],
  "run_metadata": {
    "rotation_degrees": 20,
    "placement_mode": "corners",
    "pixel_injection_status": "rendered",
    "pixel_renderer": "pixel_injection.inject_visible_text",
    "visible_identity_fields": ["patient_name", "patient_id", "accession_number"],
    "tag_only_identity_fields": ["patient_birth_date", "patient_sex"],
    "source_dicom_context": { "modality": "US", ... },   // omitted for JPG
    "output_dicom_context": { ... }
  },
  "render_metadata": {
    "rotation_degrees": 20,
    "placement_mode": "corners",
    "font_size_pct": 100,
    "font_family": "arial",
    "text_background": null,
    "visible_render_plan": [ /* RenderPlanItem[] */ ],
    "seed": 42,                                // EngineRenderMetadata, flattened
    "allowed_rotations_degrees": [0, 20, 90, 180, 270],
    "frame_count": 47,
    "applied_frame_indices": [0],
    "effective_font_family": "arial",
    "effective_font_size_px": 18,
    "geometry_source": "mask_bbox_after_final_rotation",
    "mask_alpha_threshold": 8,
    "visible_annotations": [ /* RenderedAnnotation[] */ ]
  }
}
```

The JPG variant differs exactly as `docs/dicom-injection.md` documents:
`record_type = "jpg_injection_run"`, `document_type = "jpg"`,
`modality: null`, `dicom_tag_annotations: []`, no DICOM contexts in
`run_metadata`.

## Implementation Status

### Implemented 2026-07-12

- Model modules created and validators covered by unit tests.
- `models/rendering.py` and `models/record.py` declare the current emission
  order.
- E2E tests parse `ground_truth.json` with `load_run_record()` and assert
  byte-compatible serialization for `ground_truth.json` and `run_manifest.json`.
- Runner/engine outputs are wired into `BoxAnnotation`, `DicomTagAnnotation`,
  `DicomContext`, and `RunRecord`; `_make_json_safe` is deleted.

### Remaining

- `docs/architecture/schema-changelog.md` has not been created.
- ADR-0008 still needs an emitted version for provenance fields and future PDF
  sidecar records.

Definition of done update: the DICOM/JPG `RunRecord` path is implemented and
strict-typechecked. ADR-0008 still owns future emitted versions and PDF sidecar
records.
