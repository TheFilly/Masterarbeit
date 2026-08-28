# InjectionPipeline

Skalierbare Pipeline zum Injizieren synthetischer personenbezogener
Informationen (PII) in anonymisierte medizinische Dokumente. Das Projekt
unterstützt eine Masterarbeit und ein größeres Forschungsvorhaben.

## Stack

- Python 3.13
- `uv` für Paket- und Virtual-Environment-Verwaltung
- pytest + pytest-cov für Tests
- ruff für Linting und Formatierung
- mypy in strict mode
- pydantic für Modelle und Validierung
- pydicom für DICOM-Verarbeitung
- pandas für tabellarische Daten

## Projektstruktur

```text
InjectionPipeline/
|-- src/injection_pipeline/
|   |-- artifacts/
|   |-- config/
|   |-- engine/
|   |-- identity/
|   |-- loaders/
|   |-- models/
|   |-- runtime/
|   |-- validators/
|   `-- writers/
|-- tools/handwriting/       # Isolated handwriting tooling
|-- configs/
|-- thesis-results/          # Lokale Benchmark-/Evaluationsdaten, nicht einchecken
|-- docs/
|   |-- architecture/
|   |-- archive/
|   `-- decisions/
|-- tests/
|   |-- fixtures/
|   |-- integration/
|   `-- unit/
|-- DicomData/               # Lokale Eingabedaten, nicht einchecken
|-- output/                  # Normale lokale Pipeline-Ausgaben, nicht einchecken
|-- .github/
|-- .codex/
|   `-- agents/             # Rollenprofile und Review-Gate
|-- pyproject.toml
|-- uv.lock
|-- AGENTS.md
`-- README.md
```

## Befehle

- `uv run pytest tests/ -x` - Tests ausführen, beim ersten Fehler stoppen
- `uv run pytest tests/ --cov=src/injection_pipeline` - Tests mit Coverage ausführen
- `uv run ruff check src/ tests/` - Linting
- `uv run ruff format src/ tests/` - Formatierung
- `uv run mypy src/` - Typprüfung
- `uv run injection-pipeline --seed 42` - migrierte DICOM/JPG-Pipeline ausführen

`uv run injection-pipeline` startet ohne CLI-Argumente eine interaktive
Einrichtung. Mit CLI-Argumenten, aber ohne `--input`, wählt der Befehl einen
geseedeten Standard aus `DicomData/Dicom-Files` und `DicomData/images`.

| Option | Default | Possible values | Description |
|--------|---------|-----------------|-------------|
| `--seed` | `42` | Jede Ganzzahl | Seed für Identitätsgenerierung, Default-Input-Auswahl und Layoutentscheidungen |
| `--input` | Seed-basierte Autoauswahl | Pfad mit Endung `.dcm`, `.jpg` oder `.jpeg` | Pfad des Quelldokuments |
| `--output-dir` | `output` | Pfad | Ausgabe-Stammverzeichnis; jeder Run erzeugt ein Unterverzeichnis |
| `--identifier-schema` | `configs/identifier_schemas/dicom-prototype.json` | Vorhandener JSON-Schema-Pfad | Externes Identifier-Schema für Identitätsfelder und Routen |
| `--rotation-angle` | `0` | `0`, `20`, `90`, `180`, `270` | Rotation angle for visible injected text |
| `--font-size-pct` | `100` | Ganzzahl `>= 1` | Sichtbare Textgröße als Prozentsatz des Prototype-Standards |
| `--placement-mode` | `corners` | `corners`, `free` | Placement strategy for visible injected text |
| `--font-family` | `arial` | `arial`, `calibri`, `tahoma`, `consolas` | Für sichtbares Rendering verwendete Font-Familie |
| `--text-background` | none | `white` | Optional white background behind visible text |
| `--handwriting-ink-color` | `auto` | `auto`, `black`, `gray`, `white` | Handwriting ink color; `auto` selects by local luminance |
| `--handwriting-contrast-mode` | `none` | `none`, `halo` | Optionaler Handschrift-Halo; `auto` aktiviert ihn bei unsicherem Kontrast |
| `--show-label-boxes` | `n` | `y`, `n` | Draw generic prefix boxes in `preview_annotated.png` |
| `--run-timestamp` | Aktuelle Zeit | ISO-8601-Datetime | Fester Zeitstempel für deterministische Run-IDs |
| `--handwriting-manifest` | none | JSONL-Manifest oder JSON-Manifest mit `assets` | Manifest für erzeugte Handschrift-Assets |
| `--handwriting-asset` | none | Wiederholbare Zuordnung `identity_field=asset_id` | Schemafelder Handschrift-Assets zuordnen; benötigt `--handwriting-manifest` |

## Code-Stil

- Follow PEP 8.
- Öffentliche Funktionssignaturen und Rückgabewerte typisieren.
- Für gemeinsame Datenstrukturen pydantic `BaseModel` verwenden.
- Für Pfade `pathlib.Path` verwenden.
- Für Funktionen und Variablen snake_case, für Klassen PascalCase und
  UPPER_CASE for constants.
- Für Funktionskommentare das commenting-guidelines-Skill verwenden.
- Funktionen fokussiert halten. Funktionen aufteilen, sobald sie schwer zu
  überblicken oder länger als 100 Zeilen werden.
- Avoid wildcard imports.

## Architekturprinzipien

- **Adaptermuster:** Jedes Dokumentformat erhält einen eigenen Loader und Writer.
- **Taxonomieagnostisch:** Ein externes Identifier-Schema verwenden; nicht hardcodieren
  PII categories in production pipeline logic.
- **Trennung der Zuständigkeiten:** Dokumentmodelle, Injektionslogik, Schreiben
  und Validierung kommunizieren über explizite Modelle.
- **Reproduzierbarkeit:** Alle Zufallsquellen seeden.
- **Ground Truth als Artefakt:** Annotationen getrennt von Ausgabedokumenten
  speichern.

## Architekturregeln

- Formatunterstützung über Loader und Writer ergänzen, nicht durch Änderung der
  Engine-Logik.
- Die Pipeline taxonomieagnostisch halten. Identifier-Typen kommen aus einem externen
  schema.
- Dokumentmodelle, Injektionslogik, Writer und Validatoren getrennt halten.
- Alle Zufallsquellen seeden. Dieselbe Konfiguration plus derselbe Seed muss
  dieselbe Ausgabe erzeugen.
- Annotationen als versionierte Sidecar-Artefakte schreiben, nicht in das Dokument.

## Tests

- Unit-Tests für öffentliche Funktionen ergänzen.
- pytest-Fixtures für wiederverwendbare Beispieldaten verwenden.
- Integrationstests klein und fixture-basiert halten.
- Tests `test_<module_name>.py` nennen.
- Abdeckung für `models/`, `engine/` und `validators/` priorisieren.

## Git

- Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- Branches: `feature/<short-description>` or `fix/<short-description>`.
- Commits atomar halten.
- Keine echten Patientendaten, aus MIMIC abgeleiteten Daten, erzeugten Assets,
  Modellgewichte oder Secrets einchecken.

## Lokale Artefakte und Naming Convention

- `output/` enthält normale Pipeline-Run-Artefakte wie injizierte Dokumente,
  Vorschauen und Ground-Truth-Dateien.
- `thesis-results/` enthält lokal erzeugte Benchmark-, Validierungs- und
  Plot-Ergebnisse für die Thesis. Die empfohlene Struktur lautet
  `thesis-results/benchmarks/<benchmark-name>/`,
  `thesis-results/validation/<validation-name>/` und
  `thesis-results/plots/`.
- Beide Verzeichnisse sind Arbeitsdaten und werden nicht versioniert. Relevante
  Ergebnisse für die Thesis werden in `docs/` zusammengefasst; Rohdaten bleiben
  lokal oder werden außerhalb des Repositories archiviert.
- Kurzlebige, tool-erzeugte Root-Ordner beginnen mit einem Punkt und einer
  Zweckgruppe: `.cache-<tool>/`, `.tmp-<purpose>-<date>/`,
  `.review-<purpose>/` oder `.qa-<purpose>-<date>/`. Neue lokale Agenten- und
  Review-Daten müssen in diese Namensgruppen fallen, damit die Root-Regeln in
  `.gitignore` sie erfassen.
- Tool-standardisierte Ordner wie `.pytest_cache/`, `.mypy_cache/`,
  `.ruff_cache/`, `.venv/`, `.worktrees/`, `.codex/skills/` und `__pycache__/`
  bleiben entsprechend ihrer Tool-Namen ignoriert.
- `.codex/agents/` ist eine Ausnahme: Die Rollenprofile und das Review-Gate
  sind projektbezogene Konfiguration und werden versioniert.
- Lokale Caches und leere temporäre Ordner dürfen nach abgeschlossenen Läufen
  gelöscht werden; sie werden bei Bedarf neu erzeugt. `DicomData/`,
  `output/` und `thesis-results/` dürfen nur nach Sicherung noch benötigter
  Eingaben bzw. Ergebnisse gelöscht werden.

## Außerhalb des Umfangs

- De-identification
- Defining PII categories
- Klinische Nutzung
- Web application work

## Codex-Sicherheitsregeln

- Standardmäßig Sandbox-Zugriff auf den Workspace verwenden.
- Netzwerkzugriff nur nach ausdrücklicher Genehmigung.
- Abhängigkeiten nicht ohne Genehmigung installieren, aktualisieren oder entfernen.
- Keine Dateien außerhalb des Repositorys bearbeiten.
- Keine Dateien löschen, Git-Historie umschreiben oder destruktive Befehle ohne
  Genehmigung ausführen.
- Keine Secrets, Zugangsdaten, echten Patientendaten oder aus MIMIC abgeleiteten
  Beispieldaten einchecken.
- Vor Änderungen an Architektur, öffentlichen APIs, Schemas oder
  Konfigurationsformaten einen Plan vorlegen.
- Kleine Diffs bevorzugen und unabhängige Refactorings vermeiden.

## Subagent-Workflow

- Für alle geeigneten Arbeiten einen Subagenten mit `luna` und mittlerem Aufwand
  erstellen.
- Coding-Aufgaben laufen durch das verbindliche Review-Gate in
  `docs/agent-workflow.md`: `implementer` → `reviewer` → bei Befunden derselbe
  `implementer` → erneuter `reviewer`.
- Der `reviewer` ist read-only und koordiniert die Rückgabe konkreter Befunde
  an den ursprünglichen Coding-Agenten. Wenn die Laufzeit keine direkte
  Weiterleitung erlaubt, liefert er einen unveränderten Fix-Handoff an den
  übergeordneten Orchestrator.
- Eine Aufgabe darf erst als fertig markiert werden, wenn der `reviewer`
  `APPROVED` meldet. `CHANGES_REQUESTED` bedeutet, dass die Befunde zu beheben
  und die betroffenen Gates erneut auszuführen sind; nach höchstens drei
  Korrekturrunden wird ein ungelöster Zustand als `BLOCKED / NOT READY`
  zurückgegeben.

## Definition of Done für Coding-Aufgaben

- Die Akzeptanzkriterien sind erfüllt und der Diff bleibt auf den beauftragten
  Umfang begrenzt.
- Die für die Aufgabe relevanten Tests sowie `ruff` und `mypy` wurden ausgeführt
  oder eine ausdrückliche Abweichung ist dokumentiert.
- Der read-only `reviewer` hat den aktuellen Diff geprüft und `APPROVED`
  zurückgegeben.
- Offene Befunde, fehlende Validierung oder eine nicht belegte Ausnahme verhindern
  den Abschluss.

## Dokumentationsregeln

- **Dokumentationssprache:** Deutsch. Freitext, Überschriften und erklärende
  Beschreibungen werden auf Deutsch verfasst. Fachbegriffe, API-Bezeichner,
  CLI-Optionen, Code, Dateinamen, Pfade, Ordnernamen und externe Eigennamen
  bleiben unverändert, sofern ihre Übersetzung nicht ausdrücklich Teil der
  Aufgabe ist.
- Die aktuellen Architektur-, Entscheidungs- und Betriebsdokumente in `docs/`
  als Quelle der Wahrheit für die Projektplanung verwenden.
- `docs/` ist die Quelle für Architekturhinweise, Betriebsdokumentation,
  Entscheidungen und Audit-/Statusmaterial.
- `docs/archive/` enthält überholtes Material. Nicht als Quelle der Wahrheit
  verwenden.
- Für Dokumentations-, Docstring- und Code-Kommentaraufgaben das
  `commenting-guidelines`-Skill verwenden, sofern verfügbar.
- Substanzielle Dokumentationsarbeit mit der neuesten relevanten aktuellen Datei
  in `docs/architecture/`, `docs/decisions/` oder Betriebsdokumenten beginnen.
  Die ausgemusterte Research-/Thesis-/Template-Schicht ist kein aktives
  Quellenmaterial.
- Angenommene Entscheidungen als stabil behandeln.
- Wenn ein Befund und eine Zusammenfassung widersprechen, die Zusammenfassung
  aktualisieren, statt widersprüchliche Zustände zu kombinieren.
- Den kleinsten nützlichen Ausschnitt aus `docs/` lesen.

## Mitarbeit

- Conventional Commits verwenden: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- Commits atomar halten.
- Keine echten Patientendaten, aus MIMIC abgeleiteten Beispieldaten,
  Checkpoints oder lokal erzeugten Artefakte einchecken.

## Aktueller Projektstand

Stand 2026-08-27:

- `src/injection_pipeline/` enthält die DICOM/JPG-Kernkette: pydantic-Domain-
  Modelle, Artefakt-Writer, Runtime-CLI-/Runner-Module, Laden des externen
  Identifier-Schemas, aufgeteilte Engine-Stufen und registrierte DCM/JPG-
  Loader-/Writer-Adapter.
- Der DICOM/JPG-Einstiegspunkt ist `uv run injection-pipeline ...` oder
  `uv run python -m injection_pipeline ...`.
- `docs/dicom-injection.md` dokumentiert CLI-Nutzung, Ausgabe-Artefakte und das
  Ground-Truth-Schema `0.2.0-prototype`.
- Der ausgemusterte `prototypes/`-Baum ist keine aktive Quelle der Wahrheit
  mehr; `docs/dicom-injection.md`, `docs/architecture/` und
  `docs/decisions/` verwenden.
- WP-I und die implementierten WP-B..WP-G-Scheiben sind in
  `docs/fable-work-packages.md` und `docs/architecture/` nachverfolgt. PDF-
  Loader/Writer, Annotation-Sidecar und CLI sind implementiert; breitere
  operative PDF-Fixture-Abdeckung, ADR-0008-Provenienz/
  Reproduzierbarkeitsausgabe und der WP-G-Umgebungsblock bleiben offen.
