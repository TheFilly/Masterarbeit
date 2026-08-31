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
  --callback mein_modul:mein_callback `
  --seed 42 `
  --block-size 100 `
  --workers 1 `
  --mode sequential
```

Für `--resume` wird derselbe Workspace eines kontrolliert abgebrochenen
Laufs verwendet. Ein neuer Lauf erhält einen neuen Workspace.

Die manifestbasierte Verifikation weist V-001 bis V-011 nach. Wiederverwendete
Fixtures bei 10.000 oder 25.000 Fällen sind als Endurance-/Stabilitätsmessung
und nicht als allgemeine Robustheitsprüfung heterogener Eingaben zu werten.
Aus den Befehlen folgt kein Nachweis bereits ausgeführter Messungen.
