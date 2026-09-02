# Deskriptive Platzierungsanalyse

Die Analyse wertet `ground_truth.json` auf Run- und Boxebene aus. Ein Run ist
die primäre Auswertungseinheit; mehrere Boxen desselben Runs werden innerhalb
des Runs zusammengefasst. Rohdateien werden nur gelesen.

## Quellen und Regionen

Bildmaße werden in dieser Reihenfolge gesucht: `preview_file`/`preview.png`,
`output_file`, `source_file`, anschließend der gemeinsame CLI-Fallback
`--width`/`--height`. JPG/JPEG/PNG werden mit Pillow und DICOM mit pydicom
(`Columns`/`Rows`) gelesen. Die verwendete Quelle steht je Box in
`dimension_source`. Nicht auflösbare Maße erzeugen einen Eintrag in
`skipped_runs` mit Pfad, Grund und fehlender Information.

`declared_region` ist ausschließlich der Wert aus `annotation["region"]`.
`center_region` wird aus dem normalisierten Mittelpunkt und der 25-%-Eckschwelle
berechnet. Für `corners` ist `declared_region` der Nachweis der Engine-Auswahl;
`center_region` ist nur eine zusätzliche Lagebeschreibung.

## Deduplizierung und Audit

Der Run-Fingerprint umfasst Seed, Placement-Modus, Input-Fingerprint, Rotation,
Dokumenttyp, Bildgröße, Font, Fontgröße und Box-Geometrie. Identische
Fingerprints zählen in CSV, JSON und Plots nur einmal. Die Rohdateien bleiben
erhalten und werden gemeinsam in `duplicate_runs` aufgeführt. Das Manifest
unterscheidet gefundene, als Kandidat erkannte, ausgewertete, eindeutige,
duplizierte und übersprungene Runs sowie Boxzahlen.

## Metriken und Grenzen

`descriptive_summary.json` enthält je Modus und vollständiger Konfiguration
`n`, Mittelwert, Median, Standardabweichung, IQR, Minimum, Maximum sowie das
5.- und 95.-Perzentil für die sieben geometrischen Kennzahlen. Clipping wird
geometrisch aus der Bounding-Box bestimmt. Ein optionaler Pixelvergleich wird
separat gezählt; fehlende Pixelvergleichsdaten gelten nicht als Fehler.

Overlap zählt positive Flächenüberschneidungen achsenparalleler Bounding-Box-
Paare. Diese Metrik ist ausdrücklich nicht gleichbedeutend mit Masken- oder
Polygon-Overlap.

Heatmaps nutzen für vergleichbare Konfigurationen dieselben Achsen, Bins und
eine gemeinsame Farbskala. Vergleichbare Konfigurationen benötigen beide Modi,
gleiche Bildgröße, gleichen Dokumenttyp, Rotation, Font und Fontgröße sowie
gleiche Run-Anzahlen. Unbalancierte Gruppen erhalten nur getrennte
deskriptive Modusdarstellungen; globale Histogramme/Boxplots/Scatterplots
werden dann unterdrückt.

```powershell
uv run python -m tools.thesis_results.placement_analysis `
  --input output `
  --output-dir thesis-results/validation `
  --analysis-name placement-analysis `
  --bins 10
```

Die Auswertung führt keine Hypothesentests, Chi-Quadrat-Tests, p-Werte oder
kausalen Vergleiche durch.
