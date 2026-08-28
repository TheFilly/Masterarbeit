# Thesis-Ergebniswerkzeuge

Dieser Ordner enthält ausschließlich die reproduzierbaren Werkzeuge für den
Ergebnisteil der Thesis. Der Umfang ist auf drei Untersuchungen begrenzt:

1. Validierung der Bounding Boxes und ihrer tatsächlichen Pixelpositionen,
2. Verteilung der Platzierungsmodi `corners` und `free`,
3. Skalierbarkeit sowie PDF-Laufzeit in Abhängigkeit von der Bildanzahl.

Die Produktionspipeline unter `src/` bleibt unverändert, sofern eine
Evaluation nicht ausdrücklich eine kleine, dafür notwendige Schnittstelle
benötigt. Der allgemeine Skalierbarkeitsbenchmark misst DICOM und JPG; PDF
wird im separaten PDF-Benchmark untersucht. Die Benchmarks verwenden feste
Seeds und einen festen Zeitstempel.
Echte Patientendaten, MIMIC-abgeleitete Daten und erzeugte Ergebnisdateien
werden nicht versioniert.

## Struktur

```text
tools/thesis_results/
|-- coordinate_validation/       # Koordinaten, Bounding Boxes, Verteilung
|-- performance/                # Laufzeit-, Speicher- und Durchsatzmessung
|   |-- scalability_benchmark.py
|   |-- pdf_scaling_benchmark.py
|   `-- plot_results.py
`-- README.md
```

Die erzeugten CSV-, JSON- und Bilddateien liegen standardmäßig unter
`thesis-results/`. Benchmarks schreiben nach
`thesis-results/benchmarks/`, Validierungsergebnisse nach
`thesis-results/validation/` und Diagramme nach `thesis-results/plots/`.
Dieser Ausgabeordner enthält Messdaten und Diagramme, nicht die versionierten
Skripte. Normale Pipeline-Run-Artefakte wie injizierte Dokumente bleiben unter
`output/`.

Für die PDF-Koordinatenprüfung wird zusätzlich ein vorhandener `pdftoppm`-
Renderer aus Poppler benötigt. Der Pfad kann mit `--renderer` explizit gesetzt
werden.

## Qualitätsprüfungen

```powershell
uv run pytest tests/unit/test_thesis_performance.py tests/unit/test_thesis_coordinate_validation.py -q
uv run ruff check tools/thesis_results tests/unit/test_thesis_performance.py tests/unit/test_thesis_coordinate_validation.py
```

Die vollständigen Projekt-Gates bleiben:

```powershell
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/ -x
```

## Skalierbarkeitsmessung

Zunächst mit 10.000 Dokumenten starten. Die weiteren Stufen werden separat
ausgeführt: 25.000, 50.000, 100.000, 250.000, 500.000 und 1.000.000.

```powershell
uv run python -m tools.thesis_results.performance.scalability_benchmark `
  --input-dir DicomData `
  --count 10000 `
  --block-size 1000 `
  --workers 1
```

Für den optionalen Vergleich auf Dokumentebene kann `--workers 2` oder eine
andere explizite Workerzahl verwendet werden. Die Standardpipeline wird
dabei nicht parallelisiert. Nach jedem Block werden
`measurements.csv` und `checkpoint.json` aktualisiert. Mit
`--keep-artifacts` können die erzeugten Dokumente behalten werden; ohne diese
Option werden ausschließlich die Benchmark-Messdaten behalten.

Beim Quellen-Scan werden DICOM-Dateien vorab auf den aktuellen
Pipeline-Vertrag (8-Bit, `MONOCHROME2`, `RGB` oder `YBR_FULL_422`) geprüft.
`YBR_FULL_422` wird beim Laden über pydicoms Default-`pixel_array` verwendet;
dieses liefert bereits RGB und darf nicht ein zweites Mal konvertiert werden.
Beim Schreiben gilt `PhotometricInterpretation = RGB` mit
`PlanarConfiguration = 0` und `ExplicitVRLittleEndian`. Bei Multiframe-DICOM
wird nur Frame 0 ersetzt, weitere Frames bleiben unverändert. Nicht unterstützte
DICOMs werden ausgeschlossen und nicht als erfolgreiche Messungen gezählt.

## PDF-Messung

Die PDF-Messung verwendet zunächst dieselbe vorhandene Bildquelle mehrfach,
damit nur die Bildanzahl variiert wird. Es werden 1, 2, 4, 8 und 16 Bilder pro
PDF untersucht. Pro Konfiguration läuft ein Warm-up und anschließend fünf
Messwiederholungen.

```powershell
uv run python -m tools.thesis_results.performance.pdf_scaling_benchmark `
  --template DicomData/PDF/Briefmarken.1Stk.17.03.2026_1345.pdf `
  --image DicomData/images/example.jpg
```

Das Skript schreibt Laufzeit, Laufzeit pro Bild, PDF-Größe, Seitenanzahl,
Peak-Speicher und Seed nach `measurements.csv`.

## Diagramme

```powershell
uv run python -m tools.thesis_results.performance.plot_results `
  --scalability-csv thesis-results/benchmarks/scalability/measurements.csv `
  --pdf-csv thesis-results/benchmarks/pdf-scaling/measurements.csv
```

Die Diagramme werden unter `thesis-results/plots/` erzeugt. Die
Auswertung der CSV-Dateien prüft die Linearität und den konstanten PDF-
Grundaufwand; sie ersetzt nicht die qualitative Diskussion in der Thesis.
