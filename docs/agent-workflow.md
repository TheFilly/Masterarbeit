# Agenten-Workflow und Review-Gate

Status: aktiv, eingeführt am 2026-08-27.

Dieses Dokument beschreibt den Entwicklungs-Workflow der Codex-Agenten im
Repository. Es ergänzt die Projektregeln in `AGENTS.md`; Architektur- und
Produktentscheidungen bleiben in `docs/architecture/` und
`docs/decisions/` maßgeblich.

## Rollen

Die Profile liegen unter `.codex/agents/` und sind in
`.codex/agents/config.toml` registriert.

| Rolle | Verantwortung | Schreibrecht im Workflow |
|---|---|---|
| `planner` | Zerlegt Anforderungen und formuliert Plan, Risiken und Akzeptanzkriterien. | kein Code |
| `implementer` | Bearbeitet genau eine abgegrenzte Coding-Aufgabe und aktualisiert Tests. | Produktionscode und Tests im beauftragten Umfang |
| `test` | Ergänzt oder verbessert deterministische pytest-Tests. | Tests, sofern beauftragt |
| `reviewer` | Prüft den aktuellen Diff, koordiniert den Korrekturauftrag und wiederholt die Prüfung bis zur Entscheidung. | read-only |
| `docs` | Aktualisiert README, technische Dokumentation und Release-Hinweise. | Dokumentation, sofern beauftragt |
| `data-analyst` | Analysiert Daten, Formate, Schemas und PII-relevante Stellen evidenzbasiert. | grundsätzlich read-only |

## Verbindlicher Ablauf

```text
Aufgabe
  -> planner (falls Planung erforderlich)
  -> implementer
  -> lokale Tests und Quality Gates
  -> reviewer (Review-Gate)
       -> APPROVED ----------------------> Aufgabe darf abgeschlossen werden
       -> CHANGES_REQUESTED
            -> reviewer beauftragt denselben implementer mit der Korrektur
            -> Tests und Quality Gates erneut
            -> reviewer prüft den neuen Diff
       -> nach drei Fixrunden ohne Freigabe
            -> BLOCKED / NOT READY
```

Der Review-Agent prüft immer den aktuellen Diff. Ein früheres `APPROVED` wird
durch nachfolgende Änderungen ungültig und muss erneut eingeholt werden.

## Review- und Fix-Vertrag

Der `reviewer` beginnt seine Antwort mit genau einem der Statuswerte
`APPROVED`, `CHANGES_REQUESTED` oder `BLOCKED / NOT READY`. Jeder Befund enthält:

- eine eindeutige Kennung und eine Schwere (`critical`, `major`, `minor`),
- eine konkrete Datei- oder Code-Referenz,
- Beleg oder reproduzierbare Begründung,
- eine umsetzbare Korrekturempfehlung.

`CHANGES_REQUESTED` ist erforderlich, wenn ein `critical`- oder `major`-Befund,
ein nicht erfülltes Akzeptanzkriterium oder ein fehlgeschlagenes erforderliches
Gate offen ist. `minor`-Befunde werden ebenfalls behoben, wenn sie die
Wartbarkeit, Sicherheit oder die Projektregeln betreffen; rein optionale
Verbesserungen dürfen die Freigabe nicht künstlich blockieren.

Der `reviewer` übergibt die vollständige Befundliste an den ursprünglichen
`implementer`. Dieser ändert nur den beauftragten Umfang, führt die betroffenen
und die allgemeinen Gates erneut aus und reicht den neuen Diff wieder ein.
Der Review-Agent schreibt selbst keinen Produktionscode und bestätigt keine
Korrektur ohne erneute Prüfung.

## Abschlusskriterien

Eine Coding-Aufgabe ist erst abgeschlossen, wenn alle folgenden Punkte erfüllt
sind:

1. Die Akzeptanzkriterien und der beauftragte Umfang sind erfüllt.
2. Die relevanten Tests und Qualitätsprüfungen sind erfolgreich oder eine
   ausdrücklich genehmigte Abweichung ist dokumentiert.
3. Der aktuelle Diff wurde vom `reviewer` geprüft.
4. Der `reviewer` hat `APPROVED` zurückgegeben.

Nach drei Korrekturrunden ohne Freigabe endet der Prozess mit
`BLOCKED / NOT READY`. Der Status enthält die verbleibenden Befunde, die
fehlenden Nachweise und einen nächsten konkreten Auftrag. Ein solcher Status
darf nicht als Fertigstellung umformuliert werden.

## Grenzen der Automatisierung

Die TOML-Dateien definieren Rollen und verbindliche Instruktionen; sie ersetzen
keinen externen CI- oder Merge-Hook. Die Completion-Regel ist daher als
Workflow-Gate für die Agenten und als dokumentierte Projektregel umgesetzt.
Ein späterer CI-/Merge-Hook kann dieselben Abschlusskriterien maschinell
erzwingen, ohne die Rollenaufteilung zu ändern.
