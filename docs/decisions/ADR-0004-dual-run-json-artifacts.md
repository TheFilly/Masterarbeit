---
id: ADR-0004
status: accepted
based_on:
  - docs/fable-work-packages.md (WP-Q)
---

# ADR-0004: `ground_truth.json` und `run_manifest.json` sind zwei Kopien eines Datensatzes

Nachgetragen am 2026-07-06. Hält eine bereits im Code umgesetzte Entscheidung
fest.

## Kontext

Die Dokumentation beschreibt zwei Run-Artefakte mit unterschiedlichen Zwecken:
Ground Truth (Annotationen für die Auswertung) und ein Run-Manifest
(Provenienz/Parameter). Der Prototype implementierte beide Namen, bevor sich
die Inhalte unterschieden.

## Entscheidung

`runner.py:689-694` serialisiert dasselbe `record`-Dict zweimal: einmal nach
`ground_truth.json` (mit abschließendem Zeilenumbruch), einmal nach
`run_manifest.json` (ohne). Es gibt keinen Inhaltsunterschied; die Trennung
existiert nur als reservierte Benennung für eine zukünftige Aufteilung.

## Betrachtete Alternativen

- **Eine Datei**: damals abgelehnt, damit das dokumentierte Artefaktlayout für
  nachgelagerte Verbraucher stabil bleibt, solange die Aufteilung noch erwartet
  wurde.
- **Tatsächliche Aufteilung des Datensatzes**: zurückgestellt – der Datensatz
  mischt Annotationsdaten und Run-Provenienz in einer Struktur; eine sinnvolle
  Aufteilung benötigt daher das typisierte Modell (WP-B).

## Konsequenzen

- Verbraucher können sich heute auf beide Namen verlassen; das verdoppelt die
  Kompatibilitätsfläche, solange beide Dateien denselben Datensatz enthalten.
- Jede Umstrukturierung muss beide Dateien Byte für Byte (einschließlich der
  Zeilenumbruch-Asymmetrie) erhalten, bis eine Entscheidung sie ausdrücklich
  ändert.
- Ersetzender Pfad: Das `RunRecord` von WP-B trennt Annotationsnutzlast und
  Run-Provenienz. Ein zukünftiges ADR sollte `run_manifest.json` dann entweder
  einen eigenständigen, nur Provenienz enthaltenden Inhalt geben oder die Datei
  entfernen. Bis dahin dokumentiert dieses ADR die absichtlich vorläufige
  Duplizierung.

## Review-Hinweise

Durch WP-H nachgetragen. Die Zeilenumbruch-Asymmetrie ist zufällig und nicht
entworfen; als eingefrorene Bytes behandeln, nicht als nachzuahmende Konvention.
