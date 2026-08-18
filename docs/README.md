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
- `archive/`: überholtes Material. Dieses Verzeichnis darf nicht als aktuelle
  Evidenz zitiert werden.

## Lesereihenfolge

1. Die relevante Architektur- oder Betriebsdokumentation lesen.
2. Verknüpfte ADRs in `docs/decisions/` lesen.
3. Nur direkt verknüpften Code, Tests oder archivierten Kontext öffnen.
4. `docs/archive/` als historischen Kontext behandeln, sofern eine aktuelle
   Dokumentationsdatei nicht darauf verweist.

Angenommene Entscheidungen haben Vorrang vor Designnotizen. Wenn eine
Architekturnotiz und ein ADR widersprechen, wird die Notiz aktualisiert oder
ein ersetzendes ADR geschrieben; die beiden Zustände werden nicht vermischt.
