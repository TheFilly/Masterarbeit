# Koordinatenvalidierung

Dieses Verzeichnis enthält reproduzierbare Thesis-Auswertungen für
`box_annotations`. Es verändert keine Pipeline-Ausgaben und verwendet keine
neuen Dependencies.

## Ausführen

Aus dem Repository-Stamm:

```text
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation --ground-truth output/<run>/ground_truth.json --width 512 --height 512 --output-csv output/coordinate_validation.csv
```

Die CSV enthält die aus `corners` abgeleitete Bounding Box, Mittelpunkt,
normalisierte Koordinaten (`x / width`, `y / height`) sowie Grenz- und
Clippingbefunde. UTF-8-Dateien mit BOM werden unterstützt.

Bei DICOM wird `YBR_FULL_422` über pydicom im Default-`pixel_array`-Pfad gelesen;
dieser liefert bereits RGB. Das Werkzeug konvertiert diesen Frame nicht ein
zweites Mal und unterstützt auch Multiframe-DICOM.
Für die Helligkeitsmatrix werden die drei RGB-Kanäle anschließend per einfachem
arithmetischem Mittel projiziert. Bei Multiframe-DICOM wird der mit
`frame_index` gewählte Frame vor dieser Projektion verwendet.

## Pixelvergleich

Der Vergleich arbeitet pixelbasiert auf einem gerenderten Rasterbild. JPG/PNG
werden direkt gelesen, DICOM über `pydicom`. Für belastbare Messungen wird eine
Baseline ohne Injektion über `--baseline-image` verwendet; die Differenzmaske
wird dann auf die jeweilige Ground-Truth-ROI begrenzt. Ohne Baseline steht der
Schwellwert-Fallback `--threshold` für kontrollierte Fixtures zur Verfügung.

PDF-Seiten werden reproduzierbar mit dem externen Renderer `pdftoppm` in PNG
umgewandelt. Poppler muss installiert sein oder über `--renderer` ein konkreter
`pdftoppm`-Pfad angegeben werden. Die PDF-Koordinaten werden mit
`pdf_point_to_pixel` in den Pixelraum der gerenderten Seite transformiert.

```text
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation --ground-truth output/<run>/ground_truth.json --rendered-image output/<run>/page.png --baseline-image output/<run>/baseline.png --annotation-index 0 --width 512 --height 512 --difference-threshold 0 --roi-padding 4 --tolerance 2 --pixel-output-json output/pixel-comparison.json
```

Die JSON-Ausgabe enthält Ground-Truth- und tatsächliche Pixel-Bounding-Box,
`clipping_detected`, `mask_clipped`, `center_error_px`, `iou` und
`within_tolerance`.

Eine PDF-Seite kann separat gerendert und mit Metadaten gespeichert werden:

```text
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation --pdf input.pdf --pdf-page-index 0 --pdf-dpi 150 --pdf-output-png output/pdf-page.png --pdf-metadata-json output/pdf-page.json
```

Für den anschließenden PDF-Pixelvergleich wird derselbe Sidecar als
`--ground-truth` übergeben und mit `--pdf-ground-truth` aktiviert. `--width`
und `--height` müssen den Pixelabmessungen des gerenderten PNG entsprechen:

```text
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation --ground-truth output/pdf_annotations.json --pdf-ground-truth --pdf-page-index 0 --pdf-dpi 150 --rendered-image output/pdf-page-annotated.png --baseline-image output/pdf-page-clean.png --width 1275 --height 1650 --roi-padding 4 --pixel-output-json output/pdf-pixel-comparison.json
```

## Verteilungsauswertung

Eine Eingabedatei für die Verteilung enthält eine Liste mit `corners`-Arrays:

```json
[{"corners": [{"x": 10, "y": 10}, {"x": 30, "y": 10}, {"x": 30, "y": 30}, {"x": 10, "y": 30}]}]
```

Ausführung für `corners` oder `free`:

```text
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation --distribution-input output/coordinates.json --placement-mode free --width 512 --height 512 --bins 10 --distribution-output-json output/distribution.json
```

Die JSON-Ausgabe enthält normalisierte Mittelpunkte und Bounding Boxes,
Eckhäufigkeiten, eine 2D-Heatmap, erwartete Häufigkeiten sowie
Chi-Quadrat-Wert, Freiheitsgrade und p-Wert. Für `corners` wird die erwartete
Gleichverteilung über vier Eckbereiche geprüft; zusätzlich wird
`outside_corner_count` ausgewiesen. Für `free` wird die Gleichverteilung über
den gültigen Mittelpunktbereich der vollständigen Bounding Box in den
2D-Histogramm-Bins geprüft; ungültige beziehungsweise außerhalb liegende
Boxen werden separat ausgewiesen.

Das Skript akzeptiert neben der kurzen Sample-Liste auch ein Ground-Truth-JSON
mit `box_annotations` sowie eine Liste solcher Ground-Truth-Records. Dadurch
kann dieselbe Auswertung direkt auf die Pipeline-Artefakte angewendet werden.
