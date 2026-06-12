# Implementierungsplan InjectionPipeline

## Ziel

Dieser Plan priorisiert die Arbeit entlang der drei Forschungsfragen:

- FF1: formatunabhaengiges Daten- und Annotationsmodell
- FF2: reproduzierbare, skalierbare Injektionspipeline
- FF3: technische Verifikation und Qualitaetskriterien

Die Datenanalyse bleibt die Grundlage. Ohne belastbare Fakten zu Formaten,
PII-Traegern und Adressierungsmodi kann das Dokumentmodell nicht stabil werden.

## Aktueller Stand

**Phase 1:** Am 2026-04-22 neu gestartet. Fruehere Findings liegen unter
`docs/archive/research/phase-1/` und sind nicht mehr gueltig.

**DICOM/JPG-Prototyp:** Der aktive Prototyp liegt weiter in `prototypes/dicom/`.
Er injiziert fuenf DICOM-Tags, rendert sichtbare PII fuer DCM/JPG und schreibt
`ground_truth.json`.

**Prototype-Migration:** `MIGRATION_PLAN.md` beschreibt die geplante Migration
des Prototyps nach `src/injection_pipeline/`. Der Code ist noch nicht migriert;
`src/injection_pipeline/` enthaelt derzeit die Produktionsstruktur.

`prototypes/prototype_plan.md` enthaelt den operativen Prototyp-Backlog.
`prototypes/dicom/README.md` beschreibt CLI, Output und Ground Truth des
aktuellen Prototyps.

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

Status: offen.

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
- Findings unter `docs/research/phase-1/findings/`.
- `docs/research/phase-1/summary.md`.
- `docs/research/phase-1/open-questions.md`.

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
- Aktualisiertes `docs/thesis/claim-register.md`.

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
