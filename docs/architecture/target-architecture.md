# Zielarchitektur-Blueprint (WP-A)

Status: aktiver Blueprint, aktualisiert am 2026-07-14.
Referenzdokument für die Architekturabgleich-Pakete in
`docs/fable-work-packages.md`. WP-B..WP-G wurden für die DICOM/JPG-Kernkette
umgesetzt; die PDF-Adapterintegration ist implementiert, die versionssichere
Provenienz-Ausgabe bleibt offen.

Architekturentscheidungen mit tragender Bedeutung sind in ADRs festgehalten:

- ADR-0005 - kanonisches pydantic-Domainmodell: angenommen, für DICOM/JPG
  implementiert; gemeinsame Geometrie wird für PDF wiederverwendet.
- ADR-0006 - Format-Adapter-Vertrag: angenommen, für DICOM/JPG und den
  dedizierten PDF-Loader/Writer-Workflow implementiert.
- ADR-0007 - Externalisierung des Identifier-Schemas: angenommen, für das
  Prototype-Schema implementiert.
- ADR-0008 - Strategie zur Schema-Versionierung: angenommen;
  `0.2.0-prototype` bleibt das DICOM/JPG-Record und
  `0.3.0-pdf-prototype` die PDF-Sidecar-Version.
- ADR-0009 - Determinismusvertrag: angenommen; Seeds und Uhren implementiert,
  Umgebungsprovenienz offen.

Die Migrationsinvariante gilt durchgehend: Bestehende DCM/JPG-Runs bleiben bei
injiziertem Zeitstempel byteidentisch, sofern nicht ein ADR eine Änderung
genehmigt (`docs/dicom-injection.md`, Validierungsstatus).

## Implementierungsstand, 2026-07-14

Implementiert:

- Pydantic-Modelle decken Geometrie, Identität, Annotationen, Render-Metadaten,
  DICOM-Kontext, Adapter-Payloads und `RunRecord` ab.
- `configs/identifier_schemas/dicom-prototype.json` externalisiert die fünf
  Prototype-Felder, Generierungsrezepte, DICOM-Routen, sichtbaren Routen,
  Präfixe und das deterministische `reference_date`.
- `runner.py` reiht Stufen für Input-Auflösung, Laden des Identifier-Schemas,
  Identitätsgenerierung, Planung, Adapter-Laden/Schreiben, Engine-Rendering,
  Preview-Erzeugung und typisiertes Record-Schreiben aneinander.
- `engine/pixel_injection.py` ist ein Kompatibilitäts-Export-Shim über die
  aufgeteilten Engine-Module; DICOM-Pixel-Schreiben wurde nach
  `writers/dicom.py` verschoben.
- `loaders/registry.py` löst DCM/JPG-Adapter auf. JPG wird nicht mehr inline im
  Runner geladen oder gespeichert.
- WP-I-E2E-Tests erzeugen synthetische DCM/JPG-Fixtures, führen die Pipeline mit
  festem Zeitstempel aus und vergleichen Artefakt-Hashes. Die CI führt ruff,
  mypy und pytest aus.

Offen:

- Ausgabe von Identifier-Schema-Provenienz und Reproduzierbarkeits-/Umgebungs-
  feldern für künftige DICOM/JPG-Schema-Versionen.
- Breitere operative PDF-Fixture-Validierung. Der implementierte Pfad akzeptiert
  ein PDF-Template samt injiziertem DICOM und dessen JSON-Annotation; er ist
  kein Post-Run-Composer.
- Validatoren-/DICOM-Konformitätsrichtlinie, Batch-Modus, Manifestaufteilung und
  Output-Hygiene-Pakete aus `docs/fable-work-packages.md`.
- ScrabbleGAN-Echtmodellgenerierung und integrierter Handschrift-Asset-
  Provider/Cache sind implementiert. ADR-0010 und vollständige
  Umgebungs-/Provenienz-Gates bleiben offen.

## Vorher / nachher

Ursprünglicher Ablauf vor WP-B..WP-G: Ein Modul besaß fast die gesamte Logik,
und jede Grenze übergab `dict[str, Any]`:

```text
cli.py ──argparse.Namespace──> runner.py (~708 lines)
                                 ├─ Input-Auflösung (geseedeter Standard)
                                 ├─ Run-ID / Ausgabepfade (injizierbare Uhr)
                                 ├─ Identität über identity/generator.py (dicts)
                                 ├─ Tag-Map + Render-Plan (hartcodierte Taxonomie)
                                 ├─ Handschrift-Manifest laden/parsen/anwenden
                                 ├─ if dcm: loaders/dicom → engine/dicom_tags
                                 │          → engine/pixel_injection (1097 ln)
                                 │          → writers/dicom
                                 ├─ bei JPG: PIL direkt öffnen/speichern
                                 ├─ writers/preview (annotated preview)
                                 └─ _build_record dict → ground_truth.json
                                                        + run_manifest.json (copy)
models/ validators/ config/ : leer
```

Implementierter DICOM/JPG-Kernablauf: explizite Stufen mit einem Orchestrator,
der derzeit geparste CLI-Optionen erhält:

```text
cli.py ──> argparse.Namespace + options.py defaults
             │
             ▼
        InputResolver (seeded)                     [ADR-0009]
             │  Path + document_type
             ▼
        Loader (per format, loaders/)              [ADR-0006]
             │  SourceDocument (typisiert: frame(s) + Formatkontext)
             ▼
        IdentityProvider (identity/, schema-gesteuert)
             │  Identity                            [ADR-0007]
             ▼
        HandwritingAssetProvider (implementiert, nur Handschriftmodus)
             │  Cache-Hit oder erzeugtes Bild/Mask/Manifest unter
             │  DicomData/HandwritingAssets/
             ▼
        InjectionPlanner (planning.py)
             │  InjectionPlan = TagPlan + VisibleRenderPlan (typisiert)
             ▼
        Engine (engine/: tags, rendering, geometry, handwriting)
             │  InjectedDocument + BoxAnnotation/TagAnnotation lists
             ▼
        Writer (per format, writers/)              [ADR-0006]
             │  Ausgabedatei + Previews
             ▼
        GroundTruthBuilder (ground_truth.py + models/) [ADR-0005, ADR-0008]
             │  RunRecord (validated pydantic)
```

`RunConfig` und die Validator-/Report-Stufe sind Zielkomponenten, nicht Teil der
aktuellen Implementierung. Ihr Design bleibt in WP-O beziehungsweise WP-K.

Typisierte Daten, die jede Grenze überschreiten, sind spezifiziert in
`docs/architecture/domain-model-spec.md` (WP-B). Die Adapter-Grenze ist spezifiziert
in `docs/architecture/adapter-contract.md` (WP-F).

## Komponentenübersicht

Die folgende Tabelle bewahrt die Gap-Analyse vom 2026-07-06. Für den Code-Stand
vom 2026-07-14 ist der obige Implementierungssnapshot maßgeblich.

| Komponente | Heute | Ziel | Weiteres Schicksal |
|---|---|---|---|
| `cli.py` | argparse + interaktive Prompts; importiert Runner-Privates (`cli.py:10-17`) | unveränderte Rolle; baut `RunConfig` und übergibt es an den Orchestrator; importiert nur öffentliche Namen | bleibt, neu ausgerichtet |
| `runner.py` | God-Modul (~708 Zeilen, alle Stufen) | schlanker Orchestrator, der typisierte Stufenmodule reiht | aufgeteilt (WP-D) |
| `models/` | leeres Docstring | kanonisches Domainmodell + `RunRecord` (`domain-model-spec.md`, WP-B) | erstellt |
| `config/` | leeres Docstring | Loader für Run-Konfiguration und externes Identifier-Schema (`identifier-schema-spec.md`, WP-C) | erstellt |
| `configs/` | `.gitkeep` | Identifier-Schema-Datei(en) + PDF-Template-Konfigurationen | erstellt |
| `identity/generator.py` | Faker mit hardcodierten Feldern/Präfixen | schema-gesteuerter `IdentityProvider`, der Feldrezepte aus der Konfiguration liest | neu verdrahtet (WP-C) |
| `engine/pixel_injection.py` | 1097 Zeilen, sechs Zuständigkeiten, mypy-Override | Aufteilung in frames / fonts / geometry / segments / overlay / handwriting / placement / injector (`pixel-injection-decomposition.md`, WP-E) | Aufteilung |
| `engine/dicom_tags.py` | 13-zeiliger Tag-Setter | bleibt; erhält typisierte `TagPlan`-Eingabe | bleibt |
| `loaders/dicom.py`, `writers/dicom.py` | Ad-hoc-Hilfsfunktionen | erste Implementierungen des Loader/Writer-Vertrags (WP-F) | bleibt, konform |
| JPG-Verarbeitung | inline in `runner.py:638,651` | `loaders/jpg.py` + `writers/jpg.py` gemäß Vertrag | erstellt (WP-F) |
| PDF-Pfad | dedizierter Loader/Writer und Sidecar implementiert (`loaders/pdf.py`, `writers/pdf.py`, `pdf/`) | `pdf/`-Loader/Writer-Paar; gemeinsame Geometriemodelle aus WP-B und PDF-spezifische Seiten-/Sidecar-Modelle | im PDF-Implementierungslauf implementiert |
| `writers/preview.py` | matplotlib-Previews + eigene CLI, hardcodierter Standardpfad | Preview-Writer mit erforderlichem Input und opt-in-Anzeige | bleibt, bereinigt |
| `validators/` | leeres Docstring | Schema-Round-Trip-Validierung, Annotation-/Geometrieprüfungen, Formatgültigkeit | erstellt (nach WP-B; PLAN.md Phase 4) |
| Handschrift-Manifestlogik | in `runner.py:59-168` | `engine/handwriting_manifest.py` (Laden/Parsen/Anwenden), typisiertes Asset-Modell | verschoben (WP-D) |
| Handschriftgenerierung/-cache | integrierter Provider/Cache mit isolierter Runtime | isolierter ScrabbleGAN-Asset-Provider, gemeinsam von Injektion und eigenständigem Seed-Befehl verwendet; Cache-Suche nach Identitätsgenerierung | implementiert; ADR-0010 und vollständige Gates bleiben offen |
| Tote Engine-API (`build_visible_text_annotations`, `render_annotations_for_dataset`) | exportiert, unaufgerufen, dupliziert Präfixtaxonomie | gelöscht | entfernt |

## Grenzen und Regeln

1. **Der Orchestrator steuert nur die Reihenfolge.** Nach WP-C/WP-D liegt keine
   Geschäftsregel (welche Felder existieren, wo sie gerendert werden, wie sie
   serialisiert werden) in `runner.py`.
2. **Jede Grenze ist ein pydantic-Modell.** `dict[str, Any]`-Payloads sind nur
   innerhalb eines einzelnen Moduls zulässig, nie über Modulgrenzen hinweg
   (ADR-0005).
3. **Formate sind gleichrangig.** Das Hinzufügen eines Formats berührt
   `loaders/`, `writers/` und einen Registrierungseintrag — nicht den Körper
   des Orchestrators (ADR-0006).
4. **Die Taxonomie wird genau einmal eingebracht**, beim Laden der Konfiguration
   als Identifier-Schema, das von Identitätsgenerierung und Injektionsplanung
   verwendet wird (ADR-0007).
5. **Eine Schema-Versionslinie.** Alle Ground-Truth-artigen Artefakte
   (Run-Record, PDF-Sidecar) werden nach einer gemeinsamen Strategie versioniert
   (ADR-0008).
6. **Jede Modalität besitzt ihren Adapter.** PDF lädt ein Template und schreibt
   mit dem injizierten DICOM und der validierten JSON-Annotation ein neues PDF;
   es verändert keine Quell-Run-Ausgabeverzeichnisse und hängt nicht von ihnen
   ab.
7. **Determinismus ist ein Vertrag**, keine Gewohnheit: Jeder Zufallszugriff
   stammt aus einem benannten, geseedeten und aufgezeichneten Stream; Uhren sind
   injizierbar (ADR-0009).
8. **Die Legacy-Handschrift-Runtime bleibt isoliert.** Die Hauptpipeline
   verwendet eine typisierte/lokale Asset-Provider-Grenze und darf den
   isolierten Generator aufrufen, aber die Python-/PyTorch-Umgebung von
   ScrabbleGAN wird nicht zum Python-3.13-Projekt hinzugefügt.
9. **Die Cache-Identität muss explizit sein.** Ein Handschrift-Asset darf nur
   wiederverwendet werden, wenn seine Cache-Identität mit dem ausgewählten Seed,
   dem erzeugten Text, dem Schema, Generator/Checkpoint und allen weiteren vom
   finalen WP-J-Vertrag genehmigten Parametern übereinstimmt.

## Implementierungsstatus

WP-A wird nicht direkt implementiert, sondern bildet das Gate für die anderen
Pakete.

### Implementiert am 2026-07-12

- ADR-0005, ADR-0006, ADR-0007 und ADR-0009 angenommen.
- WP-B-DICOM/JPG-Modellschicht und RunRecord-Round-Trip-Tests.
- WP-C-Identifier-Schema-Loader, Standardschema-Datei, schema-gesteuerte
  Identitätsgenerierung und schema-gesteuerte Planung.
- WP-D-Runner-Aufteilung und WP-E-Engine-Aufteilung für den DICOM/JPG-Kernpfad.
- WP-F-DICOM/JPG-Adapter und Registry.
- PDF-Loader/Writer-Adapter, Sidecar-Modelle und `inject-pdf`-CLI-Operation
  unter `0.3.0-pdf-prototype`.
- WP-G-geseedete Input-Auswahl, injizierbare Uhr, stabile Seed-Ableitung und
  deterministisches `reference_date`.
- WP-H-Bereinigung der Dokumentationsrealität und WP-R-Preview-/Identitäts-
  Hygiene.

### Verbleibend

- Breitere operative PDF-Fixture-Validierung (Unit- und CLI-Abdeckung existiert;
  vollständige Modalitäts-Integrations-Fixtures bleiben offen).
- Aufgezeichnete Umgebungs-/Provenienzfelder für eine künftige DICOM/JPG-
  Schemaerhöhung.

Abschlusskriterium für den Blueprint: Jedes Modul in `src/` erscheint mit einem
Schicksal in der Komponentenkarte; alle fünf ADRs existieren mit betrachteten
Optionen; jedes nachgelagerte Paket referenziert dieses Dokument, ohne ihm zu
widersprechen.
