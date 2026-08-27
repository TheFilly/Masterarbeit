# Dokumentation

`docs/` enthält Architektur- und Entscheidungsnotizen, Betriebsdokumentation
und Statusmaterial. Rohnotizen gehören nicht in `PLAN.md`; stabile
Entscheidungen werden in Entscheidungen überführt.

## Sprache

Die Dokumentationssprache des Repositorys ist Deutsch. Freitext,
Überschriften und erklärende Beschreibungen werden auf Deutsch geschrieben.
Fachbegriffe, API-Bezeichner, CLI-Optionen, Code, Dateinamen, Pfade,
Ordnernamen und externe Eigennamen bleiben unverändert.

## Verzeichnisse

- `decisions/`: angenommene oder vorgeschlagene Architektur- und
  Bereichsentscheidungen.
- `architecture/`: aktuelle Spezifikationen, aktive Audits und
  Implementierungsstatus. Abgeschlossene einmalige Übergabepläne werden
  entfernt, sobald ihre dauerhaften Entscheidungen und Ergebnisse an anderer
  Stelle festgehalten sind.
- `agent-workflow.md`: aktueller Ablauf für Coding-Agenten, Review-Gate und
  Korrekturschleife.
- `archive/`: überholtes Material. Dieses Verzeichnis darf nicht als aktuelle
  Evidenz zitiert werden.

## Lesereihenfolge

Die Evaluation für den Thesis-Ergebnisteil ist in
[`thesis-results-evaluation.md`](thesis-results-evaluation.md) beschrieben.
Die zugehörigen reproduzierbaren Skripte liegen unter
`tools/thesis_results/`.

1. Die relevante Architektur- oder Betriebsdokumentation lesen.
2. Verknüpfte ADRs in `docs/decisions/` lesen.
3. Nur direkt verknüpften Code, Tests oder archivierten Kontext öffnen.
4. `docs/archive/` als historischen Kontext behandeln, sofern eine aktuelle
   Dokumentationsdatei nicht darauf verweist.

Angenommene Entscheidungen haben Vorrang vor Designnotizen. Wenn eine
Architekturnotiz und ein ADR widersprechen, wird die Notiz aktualisiert oder
ein ersetzendes ADR geschrieben; die beiden Zustände werden nicht vermischt.

Für Änderungen am Code gilt zusätzlich der verbindliche Review-Gate-Ablauf in
[`agent-workflow.md`](agent-workflow.md). Dieses Dokument beschreibt die
Zusammenarbeit der Rollen; die fachlichen Projektentscheidungen bleiben in
`architecture/` und `decisions/` maßgeblich.
