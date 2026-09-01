# Thesis-Ergebniswerkzeuge

Dieser Ordner enthält reproduzierbare Werkzeuge für Koordinaten- und
Pixelvalidierung, Platzierungsverteilungen, Skalierbarkeit, PDF-Laufzeitmessung
und qualitative Verifikation. Die Produktionspipeline unter `src/` bleibt
unverändert. Ergebnisdateien werden nicht versioniert.

## PC-Laufzeit- und Skalierungssuite

Die geplanten sequentiellen Dokumentstufen sind 1.000, 5.000, 10.000, 15.000,
20.000 und 25.000. 25.000 ist der geplante Cutoff. Stufen über 25.000,
insbesondere 50.000 bis 1.000.000, werden nicht ausgeführt.

```powershell
uv run python tools/thesis_results/pc_runtime_suite.py
```

Die Suite erzeugt pro Start einen neuen eindeutigen PC-Laufordner mit
Zeitstempel unter `thesis-results/` und überschreibt keine bestehenden
Artefakte oder Benchmarks. Der Parallelvergleich verwendet 10.000 Dokumente
mit 2, 4, 6, 8 und 16 Workern. Die Stufe 6 ergänzt den Vergleich zwischen 4
und 8 Workern; 16 entspricht den verfügbaren CPU-Kernen des PCs.

Optionale Teile können übersprungen werden, sofern die lokale Suite sie
aktiviert werden. `--skip-pdf` und `--skip-visual` bleiben hoechstens
rueckwaertskompatible Redundanzen:

```powershell
uv run python tools/thesis_results/pc_runtime_suite.py --run-pdf
uv run python tools/thesis_results/pc_runtime_suite.py --skip-parallel
uv run python tools/thesis_results/pc_runtime_suite.py --run-visual
```

Verfügbare Optionen, insbesondere für Checkpoint-Fortsetzung und
`continue-on-error`, zuerst prüfen:

```powershell
uv run python tools/thesis_results/pc_runtime_suite.py --help
```

Falls angeboten, setzt die Checkpoint-Option einen kontrolliert abgebrochenen
Lauf fort. `continue-on-error` protokolliert einen fehlgeschlagenen Versuch und
führt die übrigen geplanten Versuche aus.

## PDF-Laufzeitmessung

Die PDF-Reihe umfasst 1, 2, 4, 8 und 16 Bilder pro PDF, mit einem Warm-up und
fünf ausgewerteten Wiederholungen je Konfiguration. Sie ist Bestandteil der
PC-Suite und kann optional übersprungen werden. `pdftoppm` aus Poppler wird für
PDF-Rendering und Parsability-Prüfungen benötigt; fehlt es, wird `unavailable`
dokumentiert.

## Qualitative Verifikation

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

Für einen neuen Lauf ist ein neuer Workspace zu verwenden. `--resume` ist nur
für einen kontrolliert abgebrochenen Lauf im selben Workspace vorgesehen.
Details zu V-001 bis V-011 stehen in `docs/thesis-results-evaluation.md`.

## Qualitätsprüfungen

```powershells
uv run pytest tests/unit/test_thesis_performance.py tests/unit/test_thesis_coordinate_validation.py -q
uv run pytest tests/unit/test_thesis_verification.py tests/unit/test_thesis_verification_extended.py -q
uv run ruff check src/ tests/ tools/thesis_results
uv run mypy src/
uv run mypy --strict --explicit-package-bases tools/thesis_results/verification
```

Diese Korrektheits- und Qualitätstests können nach den PC-Laufzeitmessungen
auf dem Mac nachgeholt werden. PC-Laufzeitwerte und Mac-Laufzeitwerte werden
nicht in einer gemeinsamen Laufzeitreihe vermischt.

Es liegen hier nur Befehle und ein Messplan vor; daraus folgt kein Nachweis
bereits ausgeführter Messungen. Wiederverwendete Fixtures sind bei einem
10.000- oder 25.000-Dokumente-Lauf als Endurance-/Stabilitätsmessung und nicht
als allgemeine Robustheitsprüfung heterogener Eingaben zu klassifizieren.
