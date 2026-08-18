---
id: ADR-0006
status: accepted
based_on:
  - docs/architecture/target-architecture.md
  - docs/architecture/adapter-contract.md
---

# ADR-0006: Loader-/Writer-Protokolle behandeln jedes Dokumentformat gleichrangig

## Kontext

Vor WP-F besaß DICOM Adapter-Hilfsfunktionen, während JPG-Laden/Speichern im
Orchestrator lag. Jedes neue injizierte Quellformat erforderte einen weiteren
Zweig in `runner.run`. PDF folgt nun demselben Prinzip einer gleichrangigen
Modalität.

## Entscheidung

`DocumentLoader` und `DocumentWriter` werden gemäß
`docs/architecture/adapter-contract.md` als strukturelle `typing.Protocol`s
(ohne erzwungene Vererbung) in `models/adapters.py` definiert:

- `DocumentLoader.load(path) -> SourceDocument`, wobei `SourceDocument` die
  Render-Frames plus einen optionalen Formatkontext (z. B. das pydicom-
  Dataset) enthält.
- `DocumentWriter.write(document: InjectedDocument, output_path: Path) -> None`.
- Eine kleine Registry ordnet Dateiendungen bzw. Format-IDs Adapterpaaren zu;
  der Orchestrator löst sie auf und verzweigt nie nach Format.

 DICOM und JPG werden zuerst konform umgesetzt; PDF verwendet eine eigene
Loader/Writer-Operation. Sie lädt ein PDF-Template, verarbeitet ein injiziertes
DICOM samt validierter JSON-Annotation und schreibt ein neues PDF und einen
Sidecar, ohne Quellen zu verändern.

## Betrachtete Alternativen

- **ABC-Basisklassen**: Gleichwertige Möglichkeiten, aber Protocols halten
  Adapter frei von Vererbungskopplung und sind mit Fakes leichter zu testen;
  entspricht „explizite Modelle an Grenzen“ ohne Klassenhierarchie.
- **Formatzweige im Runner beibehalten**: zunächst am günstigsten; ein drittes
  Format macht den Orchestrator zum dauerhaften Integrationsengpass und
  widerspricht dem Adapterprinzip aus `AGENTS.md`.
- **Plugin-Einstiegspunkte (importlib.metadata)**: für die Formatmenge im
  Repository überdimensioniert; die Registry kann später ohne Vertragsänderung
  dorthin wachsen.

## Konsequenzen

- Ein Format hinzufügen = ein Loader, ein Writer, ein Registry-Eintrag, keine
  Änderungen am Runner.
- JPG-Verarbeitung verlässt den Orchestrator (verhaltenswahrende Verschiebung;
  Bytes unverändert).
- Das DICOM-Pixel-Schreiben (`_write_pixel_array`) wird hinter die DICOM-Writer-
  Grenze verschoben, wo die Transfer-Syntax-Umschreibung ein dokumentiertes
  Formatproblem statt zufälligem Engine-Verhalten ist.

## Implementierungsstatus

Am 2026-07-12 für DICOM und JPG implementiert:

- `models/adapters.py` definiert `SourceDocument`, `InjectedDocument`,
  `DocumentLoader`, `DocumentWriter` und den konkreten Vertrag
  `write(InjectedDocument, output_path) -> None`.
- `loaders/registry.py` löst DICOM/JPG-Adapter nach Endung auf; `runner.py`
  verwendet die Registry statt eines Format-Zweigs.
- `loaders/dicom.py`, `writers/dicom.py`, `loaders/jpg.py` und `writers/jpg.py`
  implementieren den Vertrag. DICOM-Pixel-Schreiben liegt im DICOM-Writer.

Die PDF-Implementierung ist als eigenes Workflow-Paar (`PdfLoader` und
`PdfWriterAdapter`) vollständig; breitere operative Fixture-Abdeckung wird in
`docs/pdf-template-injection-plan.md`.

## Review-Hinweise

Mit der WP-F-DICOM/JPG-Implementierung am 2026-07-12 angenommen; die PDF-
Erweiterung wurde am 2026-07-14 vom Projektverantwortlichen unter der
ADR-0008-Schema-Version
`0.3.0-pdf-prototype`.
