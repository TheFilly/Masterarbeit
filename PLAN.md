# Implementierungsplan InjectionPipeline

## Ziel

Dieser Plan priorisiert die Arbeit entlang der drei Forschungsfragen:

- FF1: formatunabhaengiges Daten- und Annotationsmodell
- FF2: reproduzierbare, skalierbare Injektionspipeline
- FF3: technische Verifikation und Qualitaetskriterien

Die Datenanalyse bleibt die Grundlage. Ohne belastbare Fakten zu Formaten,
PII-Traegern und Adressierungsmodi kann das Dokumentmodell nicht stabil werden.

## Aktueller Stand

**Phase 1 / Forschungsdoku:** Die aktive Research-, Thesis- und Template-
Dokumentationsschicht wurde entfernt. Material unter
`docs/archive/research/phase-1/` ist historischer Kontext und keine aktuelle
Quelle.

**DICOM/JPG-Kernkette:** Der fruehere Prototyp ist nach
`src/injection_pipeline/` migriert und in die Kernmodule aufgeteilt. Der
aktuelle Stand umfasst pydantic-Modelle fuer RunRecord/Annotationen, ein
externes Identifier-Schema, einen schlanken Runner, DCM/JPG-Adapter, E2E-
Bytehash-Tests und CI. Er injiziert schema-definierte DICOM-Tags, rendert
sichtbare PII fuer DCM/JPG und schreibt `ground_truth.json` im
`0.2.0-prototype` Schema.

**Package Entry Point:** Die migrierte Pipeline laeuft ueber
`uv run injection-pipeline ...` oder `uv run python -m injection_pipeline ...`.
Operational Details stehen in `docs/dicom-injection.md`.

`docs/fable-work-packages.md` und `docs/architecture/` enthalten den aktuellen
Status der WP-I- und WP-B..WP-G-Umsetzung. Lokale
`prototypes/dicom/output_validation_*` Artefakte bleiben eingefrorene
Referenzen.

## Priorisierung

1. Phase 1 neu durchfuehren.
2. Kritische Entscheidungen ENT-A bis ENT-D treffen.
3. FF1 ableiten: Dokument- und Annotationsmodell.
4. FF2 implementieren: Loader, Engine, Writer, Config, Identity Pool, Runner.
5. FF3 absichern: Validierung, Reproduzierbarkeit, Qualitaetskriterien.

## Agentenzuordnung

- `Planner`: Priorisierung, Risiken, Akzeptanzkriterien, Scope.
- `Data-Analyst`: Datensichtung, Formatinventar, Feldanalyse,
  PII-Traegeranalyse.
- `Implementer`: kleine, abgegrenzte Umsetzungsaufgaben mit Tests.
- `Reviewer`: Pruefung von Korrektheit, Reproduzierbarkeit, Typing,
  Architekturtreue und Testluecken.

### Reviewer-Gates

Blocker-Reviews:

- Dokumentmodell und JSONL-Ground-Truth-Format.
- Engine-Kernlogik inklusive Konfliktregeln und Reproduzierbarkeit.
- DICOM-Writer.
- Jede Aenderung am festgelegten JSONL-Schema.

Advisory-Reviews:

- Loader je Format.
- Config-Schema.
- Identity Pool.
- Validatoren und Reproduzierbarkeitstests.

## Phase 1: Datenanalyse

Status: ausserhalb der aktiven Dokumentationsschicht. Neue Analysearbeit
braucht vorab eine neue Ablageentscheidung; die entfernten Ordner werden nicht
wiederhergestellt.

### Ziel

Die Daten in `DycomData/` klassifizieren: Formate, Pipeline-Inputs,
PII-Traeger, Adressierungsmodi und Kanonisierungsrisiken.

### Agenten

- Primaer: `Data-Analyst`
- Planung und MVP-Scope: `Planner`

### Outputs

- Formatinventar mit Klassifikation: Input, Referenz, Hilfsartefakt.
- PII-Traegeranalyse je Format und Feldtyp.
- Adressierungsmodi: row/cell, text-span, DICOM-Tag, Header-Token.
- Duplikat- und Kanonisierungsrisiken.
- Ablageort fuer neue Analyseartefakte ist vor Beginn festzulegen.

### Definition of Done

- Relevante Formate in `DycomData/` sind klassifiziert.
- MVP-Formate sind begruendet ausgewaehlt.
- PII-Traeger und Adressierungsmodi fuer MVP-Formate sind belegt.
- Phase-1-Summary ist reviewt und akzeptiert.

## Phase 2: Dokumentmodell (FF1)

### Ziel

Ein formatunabhaengiges Pydantic-Modell fuer Dokumente, Zielstellen und
Annotationen definieren. Row/cell und text-span bilden den MVP. DICOM-Tag und
Header-Token bleiben Erweiterungspunkte, solange Phase 1 sie nicht als MVP
begruendet.

### Agenten

- Optional: `Planner` fuer Scope und Modellentscheidungen.
- Primaer: `Implementer`.
- Blocker-Review: `Reviewer`.

### Outputs

- Pydantic-Schemas fuer Dokumente, Zielstellen und Annotationen.
- Adressierungsmodell in `docs/decisions/`.
- JSONL-Spezifikation fuer Ground Truth.
- Beispielinstanzen fuer MVP-Formate.

### Definition of Done

- Eine Dokumentabstraktion deckt alle MVP-Formate ab.
- Jede Injektionsstelle ist eindeutig referenzierbar.
- Ground Truth ist formatunabhaengig speicherbar.
- Das JSONL-Schema enthaelt alle Felder fuer Phase-4-Validierung.

## Phase 3: Pipeline-Kern (FF2)

### Ziel

Native Formate einlesen, ins Dokumentmodell ueberfuehren, synthetische Werte
injizieren und formatkonform ausschreiben. Ein Runner verbindet die Komponenten.

Empfehlung: Erst ein vertikaler Durchstich fuer einen Dokumenttyp, dann weitere
Loader.

### Agenten

- `Planner` fuer Scope.
- Primaer: `Implementer`.
- Blocker-Reviews nach Engine und DICOM-Writer.
- Advisory-Reviews nach Loader, Config und Identity Pool.

### Outputs

- MVP-Pipeline fuer priorisierte Formate.
- Konfigurierbarer Run mit Seed.
- Ground-Truth-Ausgabe als JSONL.
- CLI Entry Point.
- Strukturiertes Logging oder Reporting pro Run.
- Tests fuer Kernkomponenten.

### Definition of Done

- Mindestens ein End-to-End-Run funktioniert fuer ein MVP-Format.
- Gleiche Konfiguration plus gleicher Seed erzeugen denselben Output.
- Output-Dokumente und Ground Truth werden gemeinsam reproduzierbar erzeugt.
- CLI ist lauffaehig.

## Phase 4: Validierung (FF3)

### Ziel

Automatisch nachweisen, dass Injektionen korrekt, formatgueltig und
reproduzierbar sind. Die Ergebnisse muessen als Thesis-Belege nutzbar sein.

### Agenten

- Optional: `Planner` fuer Qualitaetskriterien.
- Primaer: `Implementer`.
- Blocker-Review: `Reviewer`.

### Outputs

- Validierungsmodul fuer Positionskonsistenz und Formatgueltigkeit.
- Reproduzierbarkeitstests.
- Skalierbarkeitsmessungen oder begruendete qualitative Bewertung.
- Qualitaetskriterien fuer FF3.
- Entscheidungs- oder Statusnotiz in `docs/architecture/` oder
  `docs/decisions/`, falls Validierung neue Architekturfolgen hat.

### Definition of Done

- Annotationen sind automatisch pruefbar.
- Formatgueltigkeit ist fuer MVP-Formate abgesichert.
- Reproduzierbarkeit ist nachgewiesen.
- Skalierbarkeit ist belegt.
- FF3-Claims sind vollstaendig belegbar.

## Zeitplanung

| Phase | Status | Aufwand |
|---|---|---|
| Phase 1 Datenanalyse | offen, Neustart | 1-2 Wochen |
| ENT-A bis ENT-D | offen | 1-2 Tage |
| Phase 2 Dokumentmodell | offen | 1-2 Wochen |
| Phase 3 MVP CSV/TXT | offen | 3-4 Wochen |
| Phase 3 DICOM-Integration | offen | 1-2 Wochen |
| Phase 3 HEA/DAT-Integration | offen | 1 Woche |
| Phase 4 Validierung | offen | 2 Wochen |

Groesstes Risiko: ein spaetes Redesign des Dokumentmodells oder JSONL-Schemas
nach Start von Phase 3. Das Blocker-Review am Ende von Phase 2 bleibt Pflicht.
