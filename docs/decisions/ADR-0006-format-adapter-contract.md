---
id: ADR-0006
status: accepted
based_on:
  - docs/architecture/target-architecture.md
  - docs/architecture/adapter-contract.md
---

# ADR-0006: Loader/Writer protocols make every document format a peer

## Context

Before WP-F, DICOM had adapter helpers while JPG load/save lived in the
orchestrator. Each new injected source format required another branch in
`runner.run`. PDF remains a downstream composer candidate, not an engine input.

## Decision

Define `DocumentLoader` and `DocumentWriter` as `typing.Protocol`s (structural,
no forced inheritance) in `models/adapters.py`, per
`docs/architecture/adapter-contract.md`:

- `DocumentLoader.load(path) -> SourceDocument` where `SourceDocument` carries
  the render frame(s) plus an optional format context (e.g. the pydicom
  dataset).
- `DocumentWriter.write(document: InjectedDocument, output_path: Path) -> None`.
- A small registry maps file extensions / format ids to adapter pairs; the
  orchestrator looks up, never branches on format.

DICOM and JPG conform first; PDF composes on top as a downstream consumer of a
completed run (it is a *composer*, not a loader — see adapter-contract.md §PDF).

## Alternatives Considered

- **ABC base classes**: equivalent power, but Protocols keep adapters free of
  inheritance coupling and are easier to test with fakes; matches "explicit
  models at seams" without a class hierarchy.
- **Keep per-format branches in the runner**: cheapest now; third format makes
  the orchestrator the permanent integration bottleneck and contradicts the
  AGENTS.md adapter principle.
- **Plugin entry points (importlib.metadata)**: overkill for an in-repo format
  set; the registry can grow into this later without contract changes.

## Consequences

- Adding a format = one loader, one writer, one registry entry, zero runner
  edits.
- JPG handling leaves the orchestrator (behaviour-preserving move; bytes
  unchanged).
- The DICOM pixel writeback (`_write_pixel_array`) moves behind the DICOM
  writer boundary, where its transfer-syntax rewrite is a documented format
  concern instead of engine incidental behaviour.

## Implementation Status

Implemented 2026-07-12 for DICOM and JPG:

- `models/adapters.py` defines `SourceDocument`, `InjectedDocument`,
  `DocumentLoader`, `DocumentWriter`, and the concrete
  `write(InjectedDocument, output_path) -> None` contract.
- `loaders/registry.py` resolves DICOM/JPG adapters by extension; `runner.py`
  uses the registry instead of a format branch.
- `loaders/dicom.py`, `writers/dicom.py`, `loaders/jpg.py`, and
  `writers/jpg.py` implement the contract. DICOM pixel writeback lives in the
  DICOM writer.

Still open: PDF composition remains outside the injected-source adapter path.

## Review Notes

Accepted with the WP-F DICOM/JPG implementation on 2026-07-12. PDF work needs
its own composer implementation and schema gate.
