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

## Manifestbasierte Verifikationsschicht

Die qualitative Verifikation liegt unter `tools/thesis_results/verification/`
und schreibt ausschließlich in den Evaluation-Workspace, standardmäßig unter
`thesis-results/`. Beispiel:

```powershell
uv run python -m tools.thesis_results.verification.evaluation_cli `
  --manifest configs/evaluation-manifest.json `
  --workspace thesis-results/validation/qualitative-run `
  --callback mein_modul:mein_callback `
  --seed 42 `
  --block-size 100 `
  --workers 1 `
  --mode sequential
```

Mit `--resume` wird ein kontrolliert abgebrochener Lauf fortgesetzt. Ein
Manifest enthält `cases` mit `case_id` und `source`; relative Pfade werden
relativ zum Manifest aufgelöst. Optional sind unter anderem `document_type`,
`placement_mode`, `rotation_degrees`, `font_family`, `font_or_renderer`,
`handwriting_ink_color`, `handwriting_contrast_mode`,
`expected_schema_fields` und `used_schema_fields` möglich. Ein
`identifier_schema` liefert erwartete strukturierte Felder.

```json
{
  "identifier_schema": "configs/identifier_schemas/dicom-prototype.json",
  "cases": [
    {
      "case_id": "dicom-0001",
      "source": "../DicomData/Dicom-Files/example.dcm",
      "document_type": "dicom",
      "placement_mode": "corners",
      "rotation_degrees": 0,
      "font_family": "arial",
      "handwriting_ink_color": "auto",
      "handwriting_contrast_mode": "none"
    }
  ]
}
```

Der Callback wird als `modul:funktion` geladen und liefert pro Fall ein
`CaseResult`. `expected_rejection` ist nur eine Planungseigenschaft; freie
`error_code`- oder Flag-Werte beweisen keine kontrollierte Ablehnung.

## V-001 bis V-011

| ID | Nachweis |
| --- | --- |
| V-001 | Vollständige Run-/Blockbilanz einschließlich Fallstatus, Ground Truth, Parsability, Annotationen, Kollisionen, Clipping, Geometrie, Laufzeit, Durchsatz, Speicher und Ausgabevolumen. |
| V-002 | Bundle- und Artefaktintegrität, einschließlich `RunRecord`-Validierung, Referenzen und Fingerprints. |
| V-003 | Strukturelle Koordinaten- und Boundsprüfung. |
| V-004 | Input-/Output-Vergleich für DICOM, JPG und PDF unter Berücksichtigung der Injektions-ROI. |
| V-005 | Format- und Parsabilityprüfung der erzeugten Dokumente. |
| V-006 | Ground-Truth- und Annotationsevidenz. |
| V-007 | Nachweisbare Klassifikation von Erfolg, kontrollierter Ablehnung und unerwartetem Fehler. |
| V-008 | Pixel-/Geometriemetriken, Clipping, Mittelpunkt, IoU und Toleranz. |
| V-009 | Eingabeprofil, Eindeutigkeit und Fixture-Wiederverwendung. |
| V-010 | Seed-, Konfigurations-, Eingabefingerprint- und Reproduzierbarkeitsprüfung. |
| V-011 | Block-/Checkpoint-Konsistenz, Resume, Commitpakete und Abbruchnachweis. |

### Bilanz, Profiling und Resume

Jeder Block und der Gesamtlauf weisen geplante, erfolgreiche, kontrolliert
abgewiesene und unerwartet fehlgeschlagene Fälle aus. Zusätzlich werden
erzeugte/fehlende Ground-Truth-Dateien, nicht parsbare Ausgabeartefakte,
ungültige Annotationen, kollidierende Pfade, Clipping-, Positions- und
Geometriefehler, abgeschlossene Fälle, Blocknummer/-größe, Seed, Workerzahl,
Modus, Laufzeit, Durchsatz, Peak-Speicher und Ausgabevolumen gespeichert.

```text
geplant = erfolgreich + kontrolliert_abgewiesen + unerwartet_fehlgeschlagen
```

Ungeklärte Differenzen sind Evaluationsfehler. Ground Truth wird separat
gezählt und nicht aus der Fallzahl abgeleitet. Das Ausgabevolumen umfasst nur
deklarierte Fallartefakte, nicht Reports, Checkpoints oder temporäre
Renderdateien.

Das V-009-Profil enthält DICOM-Photometrie, Bildgröße/-klasse,
Single-/Multiframe, unterstützte oder abgewiesene Repräsentation,
strukturierte DICOM-Felder, Dokumenttyp, Platzierung, Rotation,
Schrift-/Renderingmodus sowie Handschrift- und Kontrastoptionen.
Fingerprints machen sichtbar, ob 10.000 unterschiedliche Dokumente oder
wiederverwendete Fixtures verarbeitet wurden. Fixture-Wiederverwendung wird
als Endurance-/Stabilitätsmessung, nicht als heterogene Robustheitsprüfung,
klassifiziert. In diesem Stand wurde kein 10.000-Dokumente-Lauf durchgeführt.

Nach jedem vollständigen Block wird unter `.commits/block-<nummer>/` ein Paket
mit `block.json`, `checkpoint.json` und `case-results.json` veröffentlicht.
Der äußere `checkpoint.json` verweist auf das letzte vollständige Paket. Ein
Abbruch schreibt `run-summary-interrupted.json`; Teilresultate werden nicht
als autoritativer Checkpoint veröffentlicht. Beim Resume werden terminale
Fälle anhand stabiler `case_id` nicht erneut verarbeitet.

Orphan-Pakete werden nur bei passender Konfiguration, Eingabefingerprint,
lückenloser Sequenz und konsistenten Resultaten übernommen. Fremde oder
inkonsistente Pakete werden abgewiesen. Der Abbruchreport enthält letzten
vollständigen Block, Grund sowie terminale, in Bearbeitung befindliche und
offene Fälle.

`unknown` bedeutet nicht bestimmbar, `unsupported` außerhalb des
Formatvertrags und `unavailable` bezeichnet eine fehlende Ressource. Ein
`unavailable`-Status ist kein fachlicher Outputfehler. PDF-Vergleiche und
Parsability benötigen `pdftoppm` aus Poppler; ohne das Tool wird
`unavailable` protokolliert.

Bei `mode parallel` und `workers > 1` verwendet der aktuelle
Verifikationsharness einen `ThreadPoolExecutor`. `actual_worker_count` weist
die tatsächlich verwendete Threadzahl aus (begrenzt durch die Fallanzahl).
`worker_execution_status` ist in diesem Fall `thread_pool_measured`;
`execution_measurement_status` lautet `thread_pool_tracemalloc_measured`.
Die Zuordnung der Ergebnisse bleibt durch die geordnete Executor-Auswertung
deterministisch, und jeder Fall erhält einen getrennten Ausgabepfad.

`peak_memory_bytes` ist der mit `tracemalloc` ermittelte Python-Peak des
laufenden Prozesses. Native Speicheranteile und eine separat aggregierte
Peak-Memory der einzelnen Threads werden nicht vollständig erfasst. Der Wert
ist daher als Prozess-/Python-Allokationsmessung mit dieser Limitierung zu
interpretieren, nicht als vollständige native Worker-Speichermessung.

Typische Verifikationsartefakte sind `input-manifest.json`, `checkpoint.json`,
`run-summary.json`, `run-summary-interrupted.json`, `evaluation-metrics.json`,
`evaluation-results.json`, `evaluation-results.csv`, `profile-aggregate.json`,
`coordinate-metrics.json`, `block-000001.json`,
`case-results/<case_id>.json` und die Commitpakete unter `.commits/`.
