# Evaluation für den Ergebnisteil der Thesis

Status: aktiv. Diese Dokumentation beschreibt geplante Evaluationen und
behauptet keine bereits ausgeführten Messungen.

## Zielsetzung

Die Evaluation verifiziert Koordinaten, Platzierungsverteilungen, Artefakte
und qualitative Verarbeitung. Zusätzlich werden Laufzeit, Durchsatz, Speicher
und Ausgabevolumen der DICOM-/JPG-Verarbeitung sowie eine eigene PDF-Reihe
untersucht.

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
