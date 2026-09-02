# Evaluation für den Ergebnisteil der Thesis

Status: aktiv. Diese Dokumentation beschreibt die geplanten Evaluationen und
führt den unten ausgewiesenen kontrollierten Platzierungsnachweis als lokalen
Validierungsstand.

## Zielsetzung

Die Evaluation verifiziert Koordinaten, Platzierungsverteilungen, Artefakte
und qualitative Verarbeitung. Zusätzlich werden Laufzeit, Durchsatz, Speicher
und Ausgabevolumen der DICOM-/JPG-Verarbeitung sowie eine eigene PDF-Reihe
untersucht.

## Platzierungsanalyse

Die vorhandenen `ground_truth.json`-Artefakte werden mit dem CLI unter
`tools/thesis_results/placement_analysis/` rekursiv ausgewertet. Die Ausgabe
liegt unter `thesis-results/validation/<analysis-name>/` und umfasst
Boxmetriken, eine Run-Zusammenfassung, ein Manifest sowie Plotdateien. Ein Run
ist die primäre Auswertungseinheit; Boxen werden nur innerhalb eines Runs
aggregiert. Bildgrößen stammen in dieser Reihenfolge aus Preview, `output_file`
oder `source_file`; JPG/JPEG werden mit Pillow und DICOM mit pydicom gelesen.
`--width`/`--height` sind der gemeinsame Fallback. Die Quelle steht in
`dimension_source`; fehlende Dimensionen werden mit Pfad, Grund und fehlender
Information in `skipped_runs` protokolliert.

Run-Fingerprints umfassen Seed, Modus, Input-Fingerprint, Rotation, Dokumenttyp,
Bildgröße, Font, Fontgröße und Box-Geometrie. Gleiche Fingerprints werden nur
einmal ausgewertet, während alle zugehörigen Rohdateien in `duplicate_runs`
erhalten bleiben. `found_run_count`, `evaluated_run_count`,
`unique_run_count`, `duplicate_run_count` und Boxzahlen sind getrennt
ausgewiesen.

`declared_region` stammt direkt aus `annotation["region"]` und ist für
`corners` die maßgebliche Engine-Region. `center_region` ist die aus dem
normalisierten Boxmittelpunkt berechnete 25-%-Eckregion. Beide werden getrennt
in `box_metrics.csv` und `run_summary.csv` geführt.

Die Zusammenfassung enthält je Modus und vollständiger Konfiguration für
`center_x`, `center_y`, `edge_distance`, `normalized_width`,
`normalized_height`, `normalized_area` und `aspect_ratio` mindestens n,
Mittelwert, Median, Standardabweichung, IQR, Minimum, Maximum sowie 5.- und
95.-Perzentil. Clipping trennt geometrisch außerhalb liegende Boxen von
optionalen Pixelvergleichsfehlern. Overlap zählt achsenparallele
Bounding-Box-Paare; dies ist nicht gleich Masken- oder Polygon-Overlap.

Die Modi `corners` und `free` erhalten bei einem vollständigen und balancierten
Konfigurationssatz gemeinsame Achsen, Bins und Heatmap-Farbskala. Eine
Konfiguration ist nur dann vergleichbar, wenn beide Modi mit gleicher
Bildgröße, gleichem Dokumenttyp, gleicher Rotation, gleichem Font und gleicher
Fontgröße sowie gleicher Run-Anzahl vorhanden sind. Unbalancierte Gruppen
erhalten getrennte Modusplots; globale Vergleichsplots werden unterdrückt und
die freigegebenen Konfigurationen im Manifest genannt. Diese Schicht führt
ausdrücklich keine Chi-Quadrat- oder sonstigen Hypothesentests durch und leitet
keine kausalen Aussagen ab.

Für eine kontrollierte Erhebung werden ein separater Output- und Analyseordner,
dieselben Seeds und dieselbe Konfiguration für beide Modi verwendet. Jeder
Versuch muss Seed, Kommando, Input-Fingerprint, Konfiguration und Outputpfad
protokollieren; fehlerhafte oder abgelehnte Versuche werden nicht still
entfernt. Bestehende Visual-Check-Sitzungen gelten nicht als unabhängige
statistische Wiederholungen. Die Auswertung bleibt deskriptiv.

Der kontrollierte Validierungsstand `placement-controlled-20260902-01` wurde
mit `DicomData/images/faces-00a0d634ad200ced.jpg`, den Seeds `0` bis `99` je
Modus und der identischen festen Konfiguration `rotation=0`, `font=arial` und
`font_size=100` erzeugt. Das Erhebungsmanifest weist 200 erfolgreiche Versuche,
keine Fehler oder kontrollierten Ablehnungen und denselben Input-Fingerprint
für beide Modi aus. Die Analyse weist 200 gefundene, 200 eindeutige und 200
ausgewertete Runs mit 600 Boxen aus; es gab keine Duplikate oder begründeten
Skips. Ein gemeinsamer Konfigurationssatz (`1024x681`, `jpg`, Rotation `0`,
`arial`, `100`) ist mit 100 Runs je Modus vorhanden. Die Heatmap-Prüfung
verwendete 10 Bins, den Bereich `[0,1]²` und `vmax=50` für beide Modi.
Die Rohdaten und Artefakte liegen lokal unter
`thesis-results/validation/placement-controlled-20260902-01/` und werden
nicht versioniert. Dieser Lauf ist ein deskriptiver Validierungsnachweis und
kein Hypothesentest.

## PC-Laufzeit- und Skalierungsplan

Die zeitintensiven Messungen werden auf demselben PC ausgeführt. Die
sequentiellen Dokumentstufen lauten:

```text
1.000 → 5.000 → 10.000 → 15.000 → 20.000 → 25.000
```

25.000 ist der geplante Cutoff. Die früher vorgesehenen Stufen 50.000,
100.000, 250.000, 500.000 und 1.000.000 werden nicht ausgeführt und sind
nicht Bestandteil der Auswertung.

```powershell
uv run python tools/thesis_results/pc_runtime_suite.py
```

Der Parallelvergleich umfasst 10.000 Dokumente mit 2, 4, 6, 8 und 16
Workern. Die Stufe 6 ergänzt den Vergleich zwischen 4 und 8; 16 entspricht
der verfügbaren CPU-Kernzahl. Die PDF-Reihe umfasst 1, 2, 4, 8 und 16 Bilder
je PDF, mit einem Warm-up und fünf Messwiederholungen je Konfiguration.

Die Suite erzeugt pro Start einen neuen timestamp-/eindeutigen PC-Laufordner
unter `thesis-results/` und überschreibt keine Artefakte oder Benchmarks.
PDF- und Visual-Teile sind standardmäßig deaktiviert und werden mit
`--run-pdf` beziehungsweise `--run-visual` explizit aktiviert; Paralleltests
können mit `--skip-parallel` entfallen. Ohne `--allow-custom` ist die
Default-Matrix verbindlich; abweichende Reihen bleiben auf maximal 25.000
Dokumente begrenzt. Falls angeboten, ermöglichen
Checkpoint-/Continue-Optionen die Fortsetzung kontrolliert abgebrochener
Läufe; `--continue-on-error` setzt die Versuchsreihe nach einem protokollierten
Einzelfehler fort.

Erfasst werden Laufzeit, Laufzeit pro Dokument, Durchsatz, Blockfortschritt,
Peak-Memory, Ausgabevolumen, Seed, Blockgröße und Workerparameter.
Wiederverwendete Fixtures werden ausgewiesen. Ein Lauf mit 10.000 oder 25.000
wiederverwendeten Fixtures ist als Endurance-/Stabilitätsmessung und nicht als
allgemeine Robustheitsprüfung heterogener Eingaben zu klassifizieren.

## Qualitative Verifikation V-001 bis V-011

Die manifestbasierte Verifikationsschicht liegt unter
`tools/thesis_results/verification/`. Der ausführliche Aufruf und die
Manifestbeschreibung stehen in `tools/thesis_results/testing-commands.md`.

Der direkt ausführbare Referenzlauf verwendet
`configs/evaluation-manifest.json` und den Callback
`tools.thesis_results.verification.evaluation_callback:run_case`:

```powershell
uv run python -m tools.thesis_results.verification.evaluation_cli `
  --manifest configs/evaluation-manifest.json `
  --workspace thesis-results/validation/qualitative-run-20260902-01 `
  --callback tools.thesis_results.verification.evaluation_callback:run_case `
  --seed 42 `
  --block-size 100 `
  --workers 1 `
  --mode sequential
```

Für einen neuen Lauf ist stets ein neuer Workspace zu wählen. Das verhindert
das Überschreiben vorhandener Ergebnisartefakte; `--resume` ist ausschließlich
für die Fortsetzung desselben kontrolliert abgebrochenen Workspaces gedacht.
Das Manifest enthält sieben lokal erwartete DICOM-/JPG-Fixtures sowie einen
lokalen PDF-Scope-Negativfall. DICOM/JPG führen die im Manifest ausgewiesenen
Runtime-Defaults (`corners`, `arial`, `100`, `none`) tatsächlich aus; nur die
Rotation wird pro Fall variiert. Der PDF-Fall wird aufgrund des expliziten
DICOM/JPG-Scope-Vertrags kontrolliert abgelehnt und mit gültiger
Rejection-Evidenz ausgewiesen. Ein erfolgreicher Callback-Fall wird vor der
Runner-seitigen ROI-/Input-Output-Prüfung mit `validate_run_bundle` validiert.
Ein nichtleerer Fallordner wird nicht überschrieben; neue Läufe benötigen
einen neuen Workspace, `--resume` ist nur für denselben Abbruch-Workspace.
Der Callback erzwingt `mode=sequential` und `workers=1`, weil der verwendete
API-Staging-Mechanismus einen globalen Runtime-Ausgabepfad benötigt. Der
qualitative Lauf ist daher kein Nachweis paralleler Pipelineausführung.

V-004 verwendet eine formatbewusste Toleranzpolitik. Die bekannte DICOM-
Farbkonvertierung `YBR_FULL_422 -> RGB` wird als erwartete Änderung mit
Warnung und weiterhin als erfolgreicher Fall bewertet. Für DICOM-, JPG- und
JPEG-Pixel wird außerhalb der Injektions-ROI eine Qualitätsregel angewendet:
Basisgrenze `8`, Mittelwert höchstens `8`, 99%-Quantil höchstens `32` und
höchstens `0,5 %` der Pixel über `32`. Diese Regel ist messbar und wird pro
Fall mit Maximum, Mittelwert, 99%-Quantil, verglichenen Pixeln,
Überschreitungen, Ausreißerquote und allen Grenzwerten in JSON und CSV
ausgegeben. Erwartete Abweichungen innerhalb der Regel werden als
`same_with_warnings` und damit als erfolgreicher Fall klassifiziert;
Überschreitungen,
unbekannte Metadatenänderungen oder nicht verfügbare Vergleiche bleiben
`unexpected_failed` beziehungsweise `unavailable`. Die kleine
Fixture-Auswahl ist eine qualitative Stichprobe und kein Nachweis für
Robustheit gegenüber 10.000 unterschiedlichen Dokumenten.

| ID | Nachweis |
| --- | --- |
| V-001 | Vollständige Run-/Blockbilanz mit Fallstatus, Ground Truth, Parsability, Annotationen, Kollisionen, Clipping, Geometrie, Laufzeit, Durchsatz, Speicher und Ausgabevolumen. |
| V-002 | Bundle- und Artefaktintegrität, Referenzen und Fingerprints. |
| V-003 | Strukturelle Koordinaten- und Boundsprüfung. |
| V-004 | Input-/Output-Vergleich für DICOM, JPG und PDF unter Berücksichtigung der Injektions-ROI. |
| V-005 | Format- und Parsabilityprüfung der erzeugten Dokumente. |
| V-006 | Ground-Truth- und Annotationsevidenz. |
| V-007 | Klassifikation von Erfolg, kontrollierter Ablehnung und unerwartetem Fehler. |
| V-008 | Pixel-/Geometriemetriken, Clipping, Mittelpunkt, IoU und Toleranz. |
| V-009 | Eingabeprofil, Eindeutigkeit und Fixture-Wiederverwendung. |
| V-010 | Seed-, Konfigurations-, Eingabefingerprint- und Reproduzierbarkeitsprüfung. |
| V-011 | Block-/Checkpoint-Konsistenz, Resume, Commitpakete und Abbruchnachweis. |

Auditierbare V-004-Qualitaetsregel: Ausserhalb der Injektions-ROI gelten eine
per-channel-Basisgrenze von 8, ein maximaler Mittelwert von 8, ein maximales
99%-Quantil von 32 und hoechstens 0,5 Prozent Pixel mit einer Abweichung ueber
32. JSON und CSV speichern diese Grenzwerte sowie Maximum, Mittelwert,
99%-Quantil, Pixelanzahl und Ausreisserquote.

Für jede Block- und Runbilanz gilt:

```text
geplant = erfolgreich + kontrolliert_abgewiesen + unerwartet_fehlgeschlagen
```

Ungeklärte Differenzen sind Evaluationsfehler. `unknown`, `unsupported` und
`unavailable` bleiben getrennte Zustände. Profile umfassen unter anderem
DICOM-Photometrie, Bildgröße, Single-/Multiframe, Dokumenttyp, Platzierung,
Rotation, Schrift-/Renderingmodus sowie Handschrift- und Kontrastoptionen.

## Grenzen und nachholbare Prüfungen

pytest, Ruff und mypy sind Korrektheits- und Qualitätstests, keine relevanten
PC/Mac-Laufzeitmessungen. Sie können nach der PC-Messreihe auf dem Mac
nachgeholt werden. Visual Checks sind fachliche Renderingprüfungen und können
ebenfalls optional auf dem Mac wiederholt werden.

PDF-Rendering und Parsability benötigen `pdftoppm` aus Poppler; fehlt das Tool,
wird `unavailable` dokumentiert. Die Peak-Memory-Messung basiert auf
`tracemalloc` und erfasst native Speicheranteile nicht vollständig.
