---
id: ADR-0005
status: accepted
based_on:
  - docs/architecture/target-architecture.md
  - docs/architecture/domain-model-spec.md
---

# ADR-0005: Eine kanonische pydantic-Modellhierarchie ersetzt den Dict-Kern

## Kontext

Vor WP-B wurde der Ground-Truth-Datensatz als `dict[str, Any]` manuell
zusammengesetzt, über einen `_make_json_safe`-Shim serialisiert und nie
validiert. Gemeinsame Stufengrenzen besaßen keine Runtime-Modelle.
`AGENTS.md` schreibt pydantic-Modelle an gemeinsamen Grenzen vor.

## Entscheidung

Eine einzelne Modellhierarchie in `src/injection_pipeline/models/` definieren,
wie in `docs/architecture/domain-model-spec.md` spezifiziert:

- Geometrieprimitive (`ImagePoint`, `PdfPoint`, `MaskBounds`),
- `TextSegment`, `Identity`, annotation variants (`BoxAnnotation`,
  `DicomTagAnnotation`, `SpanAnnotation`), Render-/Run-Metadatenmodelle und ein
  Root-`RunRecord` mit `schema_version`.

Alle modulübergreifenden Payloads verwenden diese Modelle. JSON-Artefakte
werden über
`model_dump(mode="json")` erzeugt; `Path`-Felder sind als `Path` typisiert
(pydantic serialisiert sie als Strings), wodurch `_make_json_safe` entfällt.
`ImagePoint`/`PdfPoint` aus dem PDF-Plan werden in diese Hierarchie integriert,
statt in `pdf/models.py` zu liegen.

## Betrachtete Alternativen

- **Dicts beibehalten + JSON-Schema-Validierung ergänzen**: validiert die
  Ausgabe, lässt aber jede interne Grenze untypisiert, beseitigt den mypy-
  Override nicht und erzeugt zwei Wahrheitsquellen (Builder-Code und
  Schema-Datei).
- **dataclasses + manuelle Validierung**: leichter, implementiert aber erneut,
  was pydantic bietet (Validierung, JSON-Mode-Serialisierung, versionierbare
  Schemas) und widerspricht der Stack-Entscheidung in `AGENTS.md`.
- **TypedDicts**: Typisierung ohne Runtime-Validierung; Ground Truth für eine
  Masterarbeit benötigt Runtime-Garantien an der Artefaktgrenze.

## Konsequenzen

- Der Datensatz wird zu einem Vertrag: Tippfehler in Feldern schlagen sichtbar
  fehl; der Golden-Roundtrip-Test fixiert die ausgegebene JSON-Datei Byte für
  Byte gegen die aktuelle Prototype-Ausgabe.
- Modellfelder geben `engine/` die konkreten Typen, um den Dict-bezogenen mypy-
  Schuldenanteil zu entfernen (WP-E bestätigt, dass die meisten Schulden PIL/
  numpy und nicht Dicts betreffen – der Override kann sogar früher entfallen).
- Migrations-Constraint: `model_dump` muss aktuelle Schlüsselreihenfolge und
  Werteformate exakt reproduzieren (siehe Domain-Model-Spezifikation,
  „Hinweise zur Byte-Kompatibilität“).

## Implementierungsstatus

Am 2026-07-12 für die DICOM/JPG-Kernkette implementiert:

- `models/geometry.py`, `segments.py`, `identity.py`, `annotations.py`,
  `dicom.py`, `rendering.py`, `record.py` und `adapters.py` definieren die
  pydantic-Grenzmodelle.
- `ground_truth.build_record()` gibt ein validiertes `RunRecord` aus;
  `_make_json_safe` ist entfernt.
- `load_run_record()` parst `0.2.0-prototype`-Artefakte, und die E2E-Tests
  bestätigen JSON-Roundtrip-Byte-Kompatibilität für `ground_truth.json` und
  `run_manifest.json`.

Noch offen: ADR-0008 hat noch keine ausgegebene DICOM/JPG-Version für additive
Provenienz-/Reproduzierbarkeitsfelder geöffnet. PDF-Sidecar-Modelle sind unter
der Linie `0.3.0-pdf-prototype` implementiert; eine breitere operative PDF-
Fixture-Abdeckung bleibt im PDF-Implementierungsplan erfasst.

## Review-Hinweise

Mit der WP-B-Implementierung am 2026-07-12 angenommen. Künftige Änderungen an
der Schemaausgabe benötigen weiterhin das Blocker-Gate aus `PLAN.md`.
