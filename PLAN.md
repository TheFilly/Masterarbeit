# Implementierungsplan InjectionPipeline

## Ziel

Dieser Plan priorisiert die Arbeit fuer die Masterarbeit entlang der drei Forschungsfragen:

- FF1: Formatunabhaengiges Daten- und Annotationsmodell
- FF2: Reproduzierbare, skalierbare Injektionspipeline
- FF3: Technische Verifikation und Qualitaetskriterien

Die Planung folgt der zentralen Abhaengigkeit des Projekts: Ohne belastbare Datenanalyse ist weder ein stabiles abstraktes Dokumentmodell noch eine sinnvolle Injektionslogik moeglich.

## Aktueller Stand

**Soft-Reset (2026-04-22):** Phase-1-Findings wurden archiviert (`docs/archive/research/phase-1/`). Die Datenanalyse wird neu gestartet. Die Ordnerstruktur und der `src/`-Code bleiben erhalten.

Phase 1 ist **offen** und muss neu durchgefuehrt werden.

**Prototype-Migration (2026-06-10):** Der DICOM-/JPG-Prototyp wird nach `src/injection_pipeline/` ueberfuehrt. Der verbindliche Migrationsplan fuer die Implementer-Agenten liegt in `MIGRATION_PLAN.md`.

**DICOM-Prototyp:** Parallel zur Datenanalyse wird ein Quick-and-Dirty-Prototyp fuer DICOM-Injektion entwickelt (`prototypes/dicom/`). Ziel ist ein fruehzeitiger Machbarkeitsnachweis. Erkenntnisse fliessen in das spaetere DICOM-Finding und Phase-3-Design ein. Details zum aktuellen Arbeitsstrang und operativen Prototype-Backlog werden in `prototypes/prototype_plan.md` gepflegt; `PLAN.md` bleibt die uebergeordnete Roadmap. Technische Details zum bestehenden Stand: `prototypes/dicom/README.md`.

## Priorisierung

1. Phase 1: Datenanalyse (neu starten)
2. Kritische Vorab-Entscheidungen treffen (ENT-A bis ENT-D) -- blockiert Phase 3
3. FF1 aus Phase 1 ableiten: abstraktes Dokument- und Annotationsmodell (Phase 2)
4. FF2 implementieren: Loader, Engine, Writer, Config, Identity Pool, Runner (Phase 3)
5. FF3 absichern: Validierung, Reproduzierbarkeit, Qualitaetskriterien (Phase 4)

## Agentenzuordnung

- `Planner`: Planungsarbeit, Priorisierung, Risiken, Akzeptanzkriterien, Task-Zuschnitt, Scope-Entscheidungen
- `Data-Analyst`: Datensichtung, Formatinventar, Feld-/Schemaanalyse, PII-Traegeranalyse. Auch in Phase 3 als Berater verfuegbar
- `Implementer`: klar abgegrenzte Umsetzungsaufgaben mit kleinen Diffs, Tests, technische Ausfuehrung
- `Reviewer`: kritische Pruefung von Korrektheit, Reproduzierbarkeit, Typing, Architekturtreue, Testluecken

**Reviewer-Gates: Blocker vs. Advisory**

Blocker-Reviews (Arbeit stoppt bis Review abgeschlossen):
- Dokumentmodell und JSONL-Ground-Truth-Format (Phase 2)
- Engine-Kernlogik inkl. Konfliktregeln und Reproduzierbarkeit (Phase 3)
- DICOM-Writer (Phase 3, hohes Korruptionsrisiko)
- Jede Aenderung am JSONL-Schema nach Festlegung

Advisory-Reviews (empfohlen, kein Stopper):
- Loader je Format (nach Implementierung)
- Config-Schema
- Identity Pool
- Validatoren und Reproduzierbarkeitstests

## Phase 1 - Datenanalyse (offen)

### Ziel

Belastbare Faktengrundlage ueber die vorhandenen Daten in `DycomData/` erarbeiten: Welche Formate liegen vor, welche sind Pipeline-Input, welche Felder sind PII-Traeger, welche Adressierungsmodi werden benoetigt?

### Agentenempfehlung

- Primaer: `Data-Analyst`
- Planung und Priorisierung: `Planner`
- Scope-Entscheidungen (MVP-Formatauswahl): `Planner`

### Erwartete Outputs

- Formatinventar mit Klassifikation (Input / Referenz / Hilfsartefakt)
- PII-Traegeranalyse je Format und Feldtyp
- Adressierungsmodi je Format (row/cell, text-span, DICOM-Tag, Header-Token)
- Identifikation von Duplikaten und Kanonisierungsrisiken
- Dokumentierte Findings unter `docs/research/phase-1/findings/`
- Phasen-Zusammenfassung unter `docs/research/phase-1/summary.md`
- Offene Fragen unter `docs/research/phase-1/open-questions.md`

### Definition of Done

- Alle relevanten Formate in `DycomData/` sind klassifiziert und dokumentiert
- MVP-Formate sind begruendet ausgewaehlt
- PII-Traeger und Adressierungsmodi fuer MVP-Formate sind belegt
- Phase-1-Summary ist reviewt und akzeptiert

## Phase 2 - Abstraktes Dokumentmodell (FF1)

### Ziel

Ein formatunabhaengiges Pydantic-Modell definieren, das die in Phase 1 identifizierten Dokumenttypen und Zielstellen einheitlich abbildet. MVP-Adressierungsmodi sind row/cell und text-span. DICOM-Tag und Header-Token werden als Erweiterungspunkte vorgesehen, aber nicht im MVP implementiert.

### Agentenempfehlung

- Optional vorgelagert: `Planner` fuer Scope und Modellentscheidungen
- Primaer: `Implementer`
- Blocker-Review: `Reviewer` vor Finalisierung von Modellen, JSONL-Schema und Adressierungslogik

### Erwartete Outputs

- Pydantic-Schemas fuer Dokument, Zielstellen und Annotationen
- Schriftlich festgehaltenes Adressierungsmodell (in `docs/decisions/`)
- JSONL-Spezifikation fuer Ground Truth
- Beispielinstanzen fuer MVP-Formate

### Definition of Done

- Fuer alle MVP-Formate kann dieselbe Dokumentabstraktion verwendet werden
- Jede Injektionsstelle ist einheitlich referenzierbar
- Ground Truth ist unabhaengig vom nativen Dateiformat speicherbar
- Das JSONL-Schema enthaelt alle Felder, die fuer Phase-4-Validierung benoetigt werden

## Phase 3 - Pipeline-Kern (FF2)

### Ziel

Die eigentliche Injektionspipeline implementieren: native Formate einlesen, in das abstrakte Modell ueberfuehren, synthetische Werte injizieren und wieder formatkonform ausschreiben. Ein Orchestrator-Runner verbindet alle Komponenten.

**Empfohlene Implementierungsreihenfolge:** Vertikaler Durchstich zuerst -- einen einzelnen Dokumenttyp komplett durchlaufen, bevor mehrere Loader-Typen gebaut werden.

### Agentenempfehlung

- `Planner` fuer Scope-Entscheidungen (Feldauswahl, Injektionstiefe, Ausnahmeregeln)
- Primaer: `Implementer`
- Blocker-Reviews: `Reviewer` nach Engine und DICOM-Writer
- Advisory-Reviews: `Reviewer` nach Loader, Config, Identity Pool

### Erwartete Outputs

- Funktionsfaehige MVP-Pipeline fuer priorisierte Formate
- Konfigurierbarer Pipeline-Run mit Seed
- Ground-Truth-Ausgabe als JSONL
- CLI-Schnittstelle mit Entry Point
- Strukturiertes Logging/Reporting pro Run
- Testabdeckung fuer Kernkomponenten

### Definition of Done

- Mindestens ein kompletter End-to-End-Run funktioniert fuer die priorisierten MVP-Formate
- Dieselbe Konfiguration plus derselbe Seed erzeugen denselben Output
- Output-Dokumente und Ground Truth sind gemeinsam reproduzierbar erzeugbar
- CLI ist lauffaehig

## Phase 4 - Validierung (FF3)

### Ziel

Technisch nachweisen, dass die Injektionen korrekt, formatgueltig und reproduzierbar sind. Die Ergebnisse muessen als Belege fuer FF3 in der Masterarbeit verwertbar sein.

### Agentenempfehlung

- Optional vorgelagert: `Planner` fuer Qualitaetskriterien und Abnahmestrategie
- Primaer: `Implementer`
- Blocker-Review: `Reviewer` fuer die Bewertung, ob die Validierung FF3 abdeckt

### Erwartete Outputs

- Validierungsmodul fuer Positionskonsistenz und Formatgueltigkeit
- Automatisierte Reproduzierbarkeitstests
- Messergebnisse fuer Skalierbarkeit
- Explizite technische Qualitaetskriterien fuer FF3
- Aktualisiertes Claim-Register mit belegten Claims
- Nachvollziehbare Ergebnisbasis fuer die Masterarbeit

### Definition of Done

- Korrektheit der Annotationen ist automatisiert pruefbar
- Formatgueltigkeit ist fuer MVP-Formate automatisiert abgesichert
- Reproduzierbarkeit ist testbar und nachgewiesen
- Skalierbarkeit ist mit konkreten Messwerten oder einem belegten qualitativen Argument verankert
- Claims in `docs/thesis/claim-register.md` sind fuer FF3 vollstaendig und belegbar

## Grobe Zeitplanung (Masterarbeit)

| Phase | Status | Geschaetzter Aufwand |
|---|---|---|
| Phase 1 (Datenanalyse) | Offen (Neustart) | 1-2 Wochen |
| Vorab-Entscheidungen ENT-A bis ENT-D | Offen | 1-2 Tage |
| Phase 2 (Dokumentmodell) | Offen | 1-2 Wochen |
| Phase 3 MVP (CSV + TXT, ohne DICOM) | Offen | 3-4 Wochen |
| Phase 3 DICOM-Integration | Offen | 1-2 Wochen |
| Phase 3 HEA/DAT-Integration | Offen | 1 Woche |
| Phase 4 (Validierung + FF3) | Offen | 2 Wochen |

**Groesstes Zeitrisiko:** Spaetes Redesign des Dokumentmodells oder des JSONL-Schemas nach Phase 3-Beginn. Das JSONL-Schema-Blocker-Review am Ende von Phase 2 ist deshalb nicht optional.
