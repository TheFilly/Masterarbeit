# Target Architecture Blueprint (WP-A)

Status: active blueprint, updated 2026-07-13.
Anchor document for the architecture-alignment packages in
`docs/fable-work-packages.md`. WP-B..WP-G landed for the DICOM/JPG core chain;
PDF composition and version-safe provenance emission remain open.

Load-bearing choices are recorded as ADRs:

- ADR-0005 - canonical pydantic domain model: accepted, implemented for
  DICOM/JPG.
- ADR-0006 - format adapter contract: accepted, implemented for DICOM/JPG.
- ADR-0007 - identifier-schema externalization: accepted, implemented for the
  prototype schema.
- ADR-0008 - schema versioning strategy: proposed; `0.2.0-prototype` parsing
  exists, emitted provenance/reproducibility fields and PDF sidecar remain
  open.
- ADR-0009 - determinism contract: accepted; seeds and clocks implemented,
  environment provenance open.

The migration invariant holds throughout: existing DCM/JPG runs stay
byte-identical with an injected run timestamp unless an ADR approves a change
(`docs/dicom-injection.md`, Validation State).

## Implementation snapshot, 2026-07-12

Implemented:

- Pydantic models cover geometry, identity, annotations, rendering metadata,
  DICOM context, adapter payloads, and `RunRecord`.
- `configs/identifier_schemas/dicom-prototype.json` externalizes the five
  prototype fields, generation recipes, DICOM routes, visible routes, prefixes,
  and deterministic `reference_date`.
- `runner.py` sequences stages through input resolution, identifier schema
  loading, identity generation, planning, adapter loading/writing, engine
  rendering, preview generation, and typed record writing.
- `engine/pixel_injection.py` is a compatibility export shim over split engine
  modules; DICOM pixel writeback moved to `writers/dicom.py`.
- `loaders/registry.py` resolves DCM/JPG adapters. JPG no longer loads or saves
  inline in the runner.
- WP-I E2E tests generate synthetic DCM/JPG fixtures, run the pipeline with a
  fixed timestamp, and compare artifact hashes. CI runs ruff, mypy, and pytest.

Open:

- ADR-0008 emitted version for identifier-schema provenance and
  reproducibility/environment fields.
- PDF composer, PDF sidecar schema, and `compose-pdf` CLI.
- Validators/DICOM conformance policy, batch mode, manifest split, and output
  hygiene packages listed in `docs/fable-work-packages.md`.

## Before / after

Original flow before WP-B..WP-G: one module owned almost everything, and every
seam passed `dict[str, Any]`:

```text
cli.py ──argparse.Namespace──> runner.py (~708 lines)
                                 ├─ input resolution (seeded default)
                                 ├─ run-id / output paths (injectable clock)
                                 ├─ identity via identity/generator.py (dicts)
                                 ├─ tag map + render plan (hardcoded taxonomy)
                                 ├─ handwriting manifest load/parse/apply
                                 ├─ if dcm: loaders/dicom → engine/dicom_tags
                                 │          → engine/pixel_injection (1097 ln)
                                 │          → writers/dicom
                                 ├─ if jpg: PIL open/save inline
                                 ├─ writers/preview (annotated preview)
                                 └─ _build_record dict → ground_truth.json
                                                        + run_manifest.json (copy)
models/ validators/ config/ : empty
```

Implemented DICOM/JPG core flow: explicit stages with one orchestrator that
currently receives parsed CLI options:

```text
cli.py ──> argparse.Namespace + options.py defaults
             │
             ▼
        InputResolver (seeded)                     [ADR-0009]
             │  Path + document_type
             ▼
        Loader (per format, loaders/)              [ADR-0006]
             │  SourceDocument (typed: frame(s) + format context)
             ▼
        IdentityProvider (identity/, schema-driven) 
             │  Identity                            [ADR-0007]
             ▼
        InjectionPlanner (planning.py)
             │  InjectionPlan = TagPlan + VisibleRenderPlan (typed)
             ▼
        Engine (engine/: tags, rendering, geometry, handwriting)
             │  InjectedDocument + BoxAnnotation/TagAnnotation lists
             ▼
        Writer (per format, writers/)              [ADR-0006]
             │  output file + previews
             ▼
        GroundTruthBuilder (ground_truth.py + models/) [ADR-0005, ADR-0008]
             │  RunRecord (validated pydantic)
```

`RunConfig` and the validator/report stage are target components, not current
implementation. Their design remains in WP-O and WP-K respectively.

Typed data crossing each seam is specified in
`docs/architecture/domain-model-spec.md` (WP-B). The adapter seam is specified
in `docs/architecture/adapter-contract.md` (WP-F).

## Component map

The table below preserves the 2026-07-06 gap analysis. Use the implementation
snapshot above for the 2026-07-12 code state.

| Component | Today | Target | Fate |
|---|---|---|---|
| `cli.py` | argparse + interactive prompts; imports runner privates (`cli.py:10-17`) | unchanged role; builds a `RunConfig` and passes it to the orchestrator; imports only public names | stays, re-pointed |
| `runner.py` | god-module (~708 lines, all stages) | thin orchestrator that sequences typed stage modules | split completed (WP-D) |
| `models/` | empty docstring | canonical domain model + `RunRecord` (`domain-model-spec.md`, WP-B) | created |
| `config/` | empty docstring | loaders for run config and the external identifier schema (`identifier-schema-spec.md`, WP-C) | created |
| `configs/` | `.gitkeep` | identifier schema file(s) + PDF template configs | created |
| `identity/generator.py` | Faker with hardcoded fields/prefixes | schema-driven `IdentityProvider` reading field recipes from config | rewired (WP-C) |
| `engine/pixel_injection.py` | 1097 lines, six concerns, mypy override | split into frames / fonts / geometry / segments / overlay / handwriting / placement / injector (`pixel-injection-decomposition.md`, WP-E) | splits |
| `engine/dicom_tags.py` | 13-line tag setter | stays; gains typed `TagPlan` input | stays |
| `loaders/dicom.py`, `writers/dicom.py` | ad-hoc helpers | first implementations of the Loader/Writer contract (WP-F) | stays, conforms |
| JPG handling | inline in `runner.py:638,651` | `loaders/jpg.py` + `writers/jpg.py` per contract | created (WP-F) |
| PDF path | plan only (`docs/pdf-template-injection-plan.md`) | `pdf/` composer conforming to the contract; models fold into WP-B hierarchy | created later (WP-F review) |
| `writers/preview.py` | matplotlib previews + own CLI, hardcoded default path | preview writer with required input and opt-in display | stays, cleaned |
| `validators/` | empty docstring | schema round-trip validation, annotation-geometry checks, format validity | created (post-WP-B; PLAN.md Phase 4) |
| handwriting manifest logic | in `runner.py:59-168` | `engine/handwriting_manifest.py` (load/parse/apply), typed asset model | moves (WP-D) |
| dead engine API (`build_visible_text_annotations`, `render_annotations_for_dataset`) | exported, uncalled, duplicates prefix taxonomy | deleted | removed |

## Boundaries and rules

1. **Orchestrator owns sequencing only.** No business rule (which fields exist,
   where they render, how they serialize) lives in `runner.py` after WP-C/WP-D.
2. **Every seam is a pydantic model.** `dict[str, Any]` payloads are legal only
   inside a single module, never across module boundaries (ADR-0005).
3. **Formats are peers.** Adding a format touches `loaders/`, `writers/`, a
   registration entry — not the orchestrator body (ADR-0006).
4. **Taxonomy enters exactly once**, at config load, as an identifier schema
   consumed by identity generation and injection planning (ADR-0007).
5. **One schema lineage.** All ground-truth-style artifacts (run record, PDF
   sidecar) version under a single strategy (ADR-0008).
6. **Determinism is a contract**, not a habit: every random draw comes from a
   named, seeded, recorded stream; clocks are injectable (ADR-0009).

## Implementation Status

WP-A is not implemented directly; it gates the other packages.

### Implemented 2026-07-12

- ADR-0005, ADR-0006, ADR-0007, and ADR-0009 accepted.
- WP-B DICOM/JPG model layer and RunRecord round-trip tests.
- WP-C identifier schema loader, default schema file, schema-driven
  identity generation, and schema-driven planning.
- WP-D runner split and WP-E engine split for the DICOM/JPG core path.
- WP-F DICOM/JPG adapters and registry.
- WP-G seeded input selection, injectable clock, stable seed derivation, and
  deterministic `reference_date`.
- WP-H documentation-reality cleanup and WP-R preview/identity hygiene.

### Remaining

- ADR-0008 emitted schema evolution.
- PDF composer path.
- Recorded environment/provenance fields, blocked by ADR-0008.

Definition of done for the blueprint itself: every module in `src/` appears in
the component map with a fate; all five ADRs exist with options considered;
each downstream package references this document without contradicting it.
