# Befehle für Thesis-Ergebnisse

Die zeitintensiven Laufzeit- und Skalierungsmessungen werden vor dem Wechsel
auf den Mac auf demselben PC ausgeführt. Korrektheitsgates können später auf
dem Mac nachgeholt werden.

## Priorisierte PC-Versuche

1. Sequentielle Stufen: 1.000, 5.000, 10.000, 15.000, 20.000 und 25.000.
2. Parallelvergleich bei 10.000 mit 2, 4, 6, 8 und 16 Workern.
3. PDF-Reihe mit 1, 2, 4, 8 und 16 Bildern, Warm-up und fünf Wiederholungen.
4. Optional Visual Checks ohne Handschrift.
5. Anschließend qualitative Verifikation und Korrektheitsgates.

25.000 ist der geplante Cutoff. Stufen über 25.000 und ein 1.000.000-
Dokumente-Lauf werden nicht ausgeführt.

## Sichere Gesamtsuite

```powershell
uv run python tools/thesis_results/pc_runtime_suite.py
```

Pro Start wird ein neuer timestamp-/eindeutiger PC-Laufordner unter
`thesis-results/` erzeugt. Vorhandene Artefakte, Benchmarks und Reports werden
nicht überschrieben. Optionen zuerst prüfen:

```powershell
uv run python tools/thesis_results/pc_runtime_suite.py --help
```

PDF und Visual sind standardmäßig deaktiviert und werden ausschließlich mit
`--run-pdf` beziehungsweise `--run-visual` aktiviert. `--skip-pdf` und
`--skip-visual` bleiben höchstens rückwärtskompatible Redundanzen:

```powershell
uv run python tools/thesis_results/pc_runtime_suite.py --run-pdf
uv run python tools/thesis_results/pc_runtime_suite.py --skip-parallel
uv run python tools/thesis_results/pc_runtime_suite.py --run-visual
```

Falls angeboten, setzt eine Checkpoint-/Continue-Option kontrolliert
abgebrochene Läufe fort. `--continue-on-error` protokolliert einen einzelnen
Fehler und führt die übrigen Versuche fort.

## Korrektheitsgates

```powershell
uv run pytest tests/unit/test_thesis_coordinate_validation.py -q
uv run pytest tests/unit/test_thesis_performance.py -q
uv run pytest tests/unit/test_thesis_verification.py tests/unit/test_thesis_verification_extended.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/ tools/thesis_results
uv run mypy src/
uv run mypy --strict --explicit-package-bases tools/thesis_results/verification
git diff --check
```

Diese Befehle sind keine PC/Mac-Laufzeitmessungen und können auf dem Mac
nachgeholt werden.

## Visual Checks

```powershell
uv run python tools/visual_checks/pipeline_functionality.py --skip-handwriting
```

## Qualitative Verifikation

```powershell
uv run python -m tools.thesis_results.verification.evaluation_cli `
  --manifest configs/evaluation-manifest.json `
  --workspace thesis-results/validation/qualitative-run-<timestamp> `
  --callback tools.thesis_results.verification.evaluation_callback:run_case `
  --seed 42 `
  --block-size 100 `
  --workers 1 `
  --mode sequential
```

Der Workspace muss für jeden neuen Lauf neu gewählt werden, damit bestehende
Ergebnisse und Benchmarks nicht überschrieben werden. Für `--resume` wird
derselbe Workspace eines kontrolliert abgebrochenen Laufs verwendet.

Das Manifest liegt unter `configs/evaluation-manifest.json`; der Callback
`tools.thesis_results.verification.evaluation_callback:run_case` verwendet die
lokale DICOM-/JPG-Auswahl aus `DicomData`, führt nur die ausgewiesenen
Runtime-Defaults aus, schreibt nur in die Fallordner des Runners und validiert
jedes erfolgreiche Bundle mit `validate_run_bundle`. Ein lokaler PDF-Fall wird
als begründete Scope-Ablehnung mit `has_valid_rejection_evidence` erfasst.

V-004 verwendet eine formatbewusste Toleranzpolitik. Die erwartete DICOM-
Farbkonvertierung `YBR_FULL_422 -> RGB` sowie JPG-/JPEG-Rekodierungs-
abweichungen innerhalb der vollständigen Qualitätsregel werden als Erfolg mit
Warnung (`same_with_warnings`) ausgewiesen. Außerhalb der Injektions-ROI
gelten eine Basisgrenze von `8`, ein Mittelwert von höchstens `8`, ein p99 von
höchstens `32` und maximal `0,5 %` Pixel über `32`. JSON und CSV enthalten
Status, Warnungen, alle Grenzwerte, maximale und mittlere Abweichung, p99,
verglichene Pixel sowie die Anzahl der Überschreitungen. Nicht tolerierbare Abweichungen bleiben
`unexpected_failed` und werden als `input_output_differences` bilanziert.

Die auditierbare Rekodierungsregel lautet: per-channel 8, Mittelwert maximal 8,
99%-Quantil maximal 32 und hoechstens 0,5 Prozent Pixel ueber 32. Diese
Grenzwerte und die zugehoerigen Messwerte werden in JSON und CSV ausgegeben.
Der Callback erzwingt außerdem `--mode sequential --workers 1`; der globale
API-Staging-Pfad wird damit nicht als echte parallele Pipelineausführung
missverstanden.

Die manifestbasierte Verifikation weist V-001 bis V-011 nach. Wiederverwendete
Fixtures bei 10.000 oder 25.000 Fällen sind als Endurance-/Stabilitätsmessung
und nicht als allgemeine Robustheitsprüfung heterogener Eingaben zu werten.
Aus den Befehlen folgt kein Nachweis bereits ausgeführter Messungen.
