# Evaluation für den Ergebnisteil der Thesis

Status: aktiv, Scope am 2026-08-27 mit der Betreuung festgelegt.

Diese Dokumentation beschreibt ausschließlich die drei vorgesehenen
Evaluationen der entwickelten InjectionPipeline. Die aktuelle
Adapterarchitektur sowie die bestehenden Ground-Truth-Schemas bleiben die
fachliche Grundlage. Die ausführbaren Werkzeuge liegen unter
`tools/thesis_results/`.

## Zielsetzung

Die Experimente sollen die Implementierung der Pipeline nachvollziehbar
verifizieren und die Entwicklungsentscheidung zur Skalierbarkeit empirisch
bewerten. Gemessen werden sowohl funktionale Eigenschaften der Platzierung
als auch Laufzeit, Durchsatz und Speicherverbrauch. Die allgemeine
Dokument-Skalierung wird für DICOM und JPG durchgeführt; PDF erhält wegen der
zusätzlichen Bild-/Seitenkomposition eine eigene Laufzeitreihe.

## Koordinaten und Platzierung

Für DICOM, JPG und die transformierten PDF-Koordinaten werden die vier Punkte
der Ground-Truth-Bounding-Box gespeichert. Für übersichtliche Diagramme wird
zusätzlich der Mittelpunkt verwendet. Die Bildkoordinaten werden mit

```text
x_norm = x / Bildbreite
y_norm = y / Bildhöhe
```

auf den Bereich `[0, 1]` normiert. Bei PDF wird die Ground Truth zunächst in
den Pixelraum der gerenderten PDF-Seite übertragen.

Für jede Box werden folgende Eigenschaften geprüft:

- alle Punkte liegen innerhalb des gültigen Bild- oder Seitenraums,
- der injizierte Text wird nicht abgeschnitten,
- die tatsächliche Pixel-Bounding-Box stimmt innerhalb einer vorab
  festgelegten Toleranz mit der Ground Truth überein.

Der Pixelvergleich verwendet gerenderte Ausgabebilder. Für kontrollierte
Fixtures wird eine Pixelmaske des injizierten Bereichs bestimmt und mit der
transformierten Ground Truth verglichen. Abweichungen werden als
Mittelpunktfehler, Boxüberlappung beziehungsweise IoU und Clippingrate
gespeichert.

### Erwartete Verteilungen

Bei `corners` muss der Mittelpunkt in einem der vier äußeren Eckbereiche
liegen. Die Häufigkeit der vier Bereiche wird getrennt ausgewertet.

Bei `free` wird nicht die gesamte Bildfläche als gleichverteilt betrachtet,
sondern der gültige Mittelpunktbereich, in dem die vollständige Bounding Box
liegen kann. Die Ergebnisse werden als 2D-Histogramm beziehungsweise Heatmap
dargestellt und gegen diese erwartete Gleichverteilung geprüft.

## Skalierbarkeit

Die Standardmessung beginnt mit 10.000 Dokumenten und kann stufenweise bis
1.000.000 Dokumente erweitert werden:

```text
10.000 → 25.000 → 50.000 → 100.000 → 250.000 → 500.000 → 1.000.000
```

Die Verarbeitung erfolgt blockweise. Nach jedem Block werden Zwischenstände
geschrieben, sodass lange Läufe nachvollziehbar und nach einem Abbruch
auswertbar bleiben. Erfasst werden:

- Gesamtlaufzeit und Laufzeit pro Dokument,
- Durchsatz in Dokumenten pro Sekunde,
- Peak-Speicherverbrauch,
- abgeschlossene Dokumente und Blocknummer,
- Seed, Workeranzahl und Verarbeitungsmodus.

Zuerst wird die sequentielle Verarbeitung vermessen. Danach kann eine
optionale dokumentweise Parallelisierung mit expliziter Workerzahl unter
identischen Bedingungen verglichen werden. Die Standardausführung der
Pipeline bleibt sequentiell.

Die Skalierbarkeit wird anhand des gemessenen Laufzeitverlaufs, des
Durchsatzes und des Speicherverlaufs diskutiert. Eine lineare Skalierung wird
nicht vorausgesetzt, sondern durch die Daten geprüft.

## PDF-Bildanzahl

Die PDF-Messung untersucht ausschließlich PDF und vergleicht nur PDF-
Konfigurationen miteinander. Die Versuchsreihe enthält 1, 2, 4, 8 und 16
Bilder pro PDF. Zunächst wird dieselbe vorhandene Bildquelle mehrfach
verwendet, damit Bildinhalt und Bildgröße konstant bleiben. Die
Injektionsparameter und das PDF-Template bleiben ebenfalls konstant.

Jede Konfiguration erhält einen Warm-up-Lauf und fünf ausgewertete
Wiederholungen. Pro Wiederholung werden Bildanzahl, Seitenanzahl,
Gesamtlaufzeit, Laufzeit pro Bild, PDF-Dateigröße, Peak-Speicher und Seed
gespeichert.

Zur Prüfung des Zusammenhangs wird ein Modell der Form

```text
Laufzeit = konstanter PDF-Grundaufwand + zusätzlicher Aufwand pro Bild
```

untersucht. Zusätzlich werden Einzelmessungen, Mittelwerte und Streuung
dargestellt. Eine separate Profilierung einzelner PDF-Verarbeitungsschritte
ist nicht Bestandteil dieses Scopes.

## Akzeptanzkriterien

1. Kein geprüfter gültiger Testfall erzeugt eine Bounding Box außerhalb des
   Bild- oder Seitenraums.
2. Kein geprüfter gültiger Testfall zeigt Clipping des injizierten Textes.
3. Ground Truth und pixelbasiert ermittelte Position stimmen innerhalb der
   vorab dokumentierten Toleranz überein.
4. Die Verteilung von `corners` und `free` wird für DICOM, JPG und PDF-
   relevante Koordinatentransformationen getrennt dargestellt.
5. Die DICOM/JPG-Skalierbarkeitsmessung speichert blockweise Zwischenstände
   und alle vereinbarten Laufzeit-, Durchsatz- und Speichermetriken.
6. Die PDF-Reihe enthält die Bildanzahlen 1, 2, 4, 8 und 16 mit einem Warm-up
   und fünf Messwiederholungen je Konfiguration.
7. Alle Rohdaten und Diagramme können ausschließlich mit den Skripten unter
   `tools/thesis_results/` reproduziert werden.

## Reproduzierbarkeit und Grenzen

Jeder Lauf verwendet einen expliziten Seed. Die Benchmarks schreiben ihre
Rohdaten außerhalb des Quellcodes unter `thesis-results/benchmarks/`; abgeleitete
Validierungsdaten liegen unter `thesis-results/validation/` und Diagramme unter
`thesis-results/plots/`. Normale Pipeline-Run-Artefakte bleiben unter `output/`.
Hardware, Betriebssystem, Python-Version, verwendete Testdaten und Laufparameter werden
im jeweiligen Checkpoint festgehalten und bei der Thesis-Auswertung genannt.

Eine nicht durchführbare Millioner-Stufe wird nicht durch eine unbelegte
Behauptung ersetzt. In diesem Fall werden die letzte vollständige Stufe, der
konkrete Abbruchgrund und eine klar gekennzeichnete Extrapolation berichtet.
