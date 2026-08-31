Hier sind die Befehle einzeln und ohne Platzhalter.

## 1. Automatisierte Thesis-Tests

Koordinatenvalidierung:

```powershell
uv run pytest tests/unit/test_thesis_coordinate_validation.py -q
```

Performance- und Skalierbarkeitstests:

```powershell
uv run pytest tests/unit/test_thesis_performance.py -q
```

Alle Projekttests:

```powershell
uv run pytest tests/ -x
```

## 2. DICOM-Koordinaten validieren

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --ground-truth "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/ground_truth.json" `
  --width 1016 `
  --height 708 `
  --tolerance 2 `
  --output-csv "thesis-results/validation/coordinates/dicom-bounds.csv"
```

Ergebnis:

```text
thesis-results\validation\coordinates\dicom-bounds.csv
```

## 3. Pixelvergleich für alle fünf Annotationen

Annotation 0:

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --ground-truth "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/ground_truth.json" `
  --rendered-image "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/91180014_0001_injected.dcm" `
  --baseline-image "DicomData/Dicom-Files/91180014_0001.dcm" `
  --annotation-index 0 `
  --width 1016 `
  --height 708 `
  --roi-padding 4 `
  --tolerance 2 `
  --difference-threshold 0 `
  --pixel-output-json "thesis-results/validation/coordinates/dicom-pixel-annotation-0.json"
```

Annotation 1:

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --ground-truth "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/ground_truth.json" `
  --rendered-image "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/91180014_0001_injected.dcm" `
  --baseline-image "DicomData/Dicom-Files/91180014_0001.dcm" `
  --annotation-index 1 `
  --width 1016 `
  --height 708 `
  --roi-padding 4 `
  --tolerance 2 `
  --difference-threshold 0 `
  --pixel-output-json "thesis-results/validation/coordinates/dicom-pixel-annotation-1.json"
```

Annotation 2:

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --ground-truth "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/ground_truth.json" `
  --rendered-image "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/91180014_0001_injected.dcm" `
  --baseline-image "DicomData/Dicom-Files/91180014_0001.dcm" `
  --annotation-index 2 `
  --width 1016 `
  --height 708 `
  --roi-padding 4 `
  --tolerance 2 `
  --difference-threshold 0 `
  --pixel-output-json "thesis-results/validation/coordinates/dicom-pixel-annotation-2.json"
```

Annotation 3:

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --ground-truth "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/ground_truth.json" `
  --rendered-image "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/91180014_0001_injected.dcm" `
  --baseline-image "DicomData/Dicom-Files/91180014_0001.dcm" `
  --annotation-index 3 `
  --width 1016 `
  --height 708 `
  --roi-padding 4 `
  --tolerance 2 `
  --difference-threshold 0 `
  --pixel-output-json "thesis-results/validation/coordinates/dicom-pixel-annotation-3.json"
```

Annotation 4:

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --ground-truth "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/ground_truth.json" `
  --rendered-image "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/91180014_0001_injected.dcm" `
  --baseline-image "DicomData/Dicom-Files/91180014_0001.dcm" `
  --annotation-index 4 `
  --width 1016 `
  --height 708 `
  --roi-padding 4 `
  --tolerance 2 `
  --difference-threshold 0 `
  --pixel-output-json "thesis-results/validation/coordinates/dicom-pixel-annotation-4.json"
```

## 4. Verteilung für `corners`

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --distribution-input "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/ground_truth.json" `
  --placement-mode corners `
  --width 1016 `
  --height 708 `
  --bins 10 `
  --distribution-output-json "thesis-results/validation/coordinates/corners-distribution.json" `
  --heatmap-png "thesis-results/validation/coordinates/corners-heatmap.png"
```

## 5. Neuen Lauf für `free` erzeugen

```powershell
uv run injection-pipeline `
  --input "DicomData/Dicom-Files/91180014_0001.dcm" `
  --output-dir "output/thesis-input/dicom-free" `
  --seed 42 `
  --placement-mode free `
  --run-timestamp 2026-08-27T12:10:00
```

## 6. Verteilung für `free`

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --distribution-input "output/thesis-input/dicom-free/dcm-27082026-1210-seed0042-angle000-free-fs100-arial-none-labelsn-inkauto-contrastnone/ground_truth.json" `
  --placement-mode free `
  --width 1016 `
  --height 708 `
  --bins 10 `
  --distribution-output-json "thesis-results/validation/coordinates/free-distribution.json" `
  --heatmap-png "thesis-results/validation/coordinates/free-heatmap.png"
```

## 7. Skalierbarkeit: 10.000 Dokumente

```powershell
uv run python -m tools.thesis_results.performance.scalability_benchmark `
  --input-dir "DicomData" `
  --count 10000 `
  --block-size 1000 `
  --workers 1 `
  --seed 42 `
  --output-dir "thesis-results/benchmarks/scalability-10000"
```

## 8. Skalierbarkeit: 25.000 Dokumente

```powershell
uv run python -m tools.thesis_results.performance.scalability_benchmark `
  --input-dir "DicomData" `
  --count 25000 `
  --block-size 1000 `
  --workers 1 `
  --seed 42 `
  --output-dir "thesis-results/benchmarks/scalability-25000"
```

## 9. Skalierbarkeit: 50.000 Dokumente

```powershell
uv run python -m tools.thesis_results.performance.scalability_benchmark `
  --input-dir "DicomData" `
  --count 50000 `
  --block-size 1000 `
  --workers 1 `
  --seed 42 `
  --output-dir "thesis-results/benchmarks/scalability-50000"
```

## 10. Skalierbarkeit: 100.000 Dokumente

```powershell
uv run python -m tools.thesis_results.performance.scalability_benchmark `
  --input-dir "DicomData" `
  --count 100000 `
  --block-size 1000 `
  --workers 1 `
  --seed 42 `
  --output-dir "thesis-results/benchmarks/scalability-100000"
```

## 11. Skalierbarkeit: 250.000 Dokumente

```powershell
uv run python -m tools.thesis_results.performance.scalability_benchmark `
  --input-dir "DicomData" `
  --count 250000 `
  --block-size 1000 `
  --workers 1 `
  --seed 42 `
  --output-dir "thesis-results/benchmarks/scalability-250000"
```

## 12. Skalierbarkeit: 500.000 Dokumente

```powershell
uv run python -m tools.thesis_results.performance.scalability_benchmark `
  --input-dir "DicomData" `
  --count 500000 `
  --block-size 1000 `
  --workers 1 `
  --seed 42 `
  --output-dir "thesis-results/benchmarks/scalability-500000"
```

## 13. Skalierbarkeit: 1.000.000 Dokumente

```powershell
uv run python -m tools.thesis_results.performance.scalability_benchmark `
  --input-dir "DicomData" `
  --count 1000000 `
  --block-size 1000 `
  --workers 1 `
  --seed 42 `
  --output-dir "thesis-results/benchmarks/scalability-1000000"
```

In jedem Skalierbarkeitsordner werden geschrieben:

```text
measurements.csv
checkpoint.json
```

## 14. Optionaler Parallelvergleich

```powershell
uv run python -m tools.thesis_results.performance.scalability_benchmark `
  --input-dir "DicomData" `
  --count 10000 `
  --block-size 1000 `
  --workers 2 `
  --seed 42 `
  --output-dir "thesis-results/benchmarks/scalability-10000-parallel"
```

## 15. PDF-Laufzeitmessung mit 1, 2, 4, 8 und 16 Bildern

```powershell
uv run python -m tools.thesis_results.performance.pdf_scaling_benchmark `
  --template "DicomData/PDF/Briefmarken.1Stk.17.03.2026_1345.pdf" `
  --image "DicomData/images/faces-0a3fed781e431408.jpg" `
  --max-images 16 `
  --repetitions 2 `
  --seed 42 `
  --output-dir "thesis-results/benchmarks/pdf-scaling"
```

Ergebnis:

```text
thesis-results\benchmarks\pdf-scaling\measurements.csv
```

## 16. PDF-Adapter ausführen

```powershell
uv run injection-pipeline inject-pdf `
  --input-pdf "DicomData/PDF/Briefmarken.1Stk.17.03.2026_1345.pdf" `
  --input-dicom "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/91180014_0001_injected.dcm" `
  --dicom-annotation "output/thesis-input/dicom/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/ground_truth.json" `
  --output-dir "thesis-results/validation/pdf-input"
```

Die Ergebnisse liegen anschließend unter:

```text
thesis-results\validation\pdf-input\pdf\dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone\Briefmarken.1Stk.17.03.2026_1345-top_left\
```

## 17. PDF-Seite rendern: saubere PDF

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --pdf "thesis-results/validation/pdf-input/pdf/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/Briefmarken.1Stk.17.03.2026_1345-top_left/pdf_injected.pdf" `
  --pdf-page-index 0 `
  --pdf-dpi 150 `
  --pdf-output-png "thesis-results/validation/pdf-validation/pdf-clean-page.png" `
  --pdf-metadata-json "thesis-results/validation/pdf-validation/pdf-clean-page.json"
```

## 18. PDF-Seite rendern: annotierte PDF

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --pdf "thesis-results/validation/pdf-input/pdf/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/Briefmarken.1Stk.17.03.2026_1345-top_left/pdf_injected_annotated.pdf" `
  --pdf-page-index 0 `
  --pdf-dpi 150 `
  --pdf-output-png "thesis-results/validation/pdf-validation/pdf-annotated-page.png" `
  --pdf-metadata-json "thesis-results/validation/pdf-validation/pdf-annotated-page.json"
```

## 19. PDF-Pixelvergleich

Für das verwendete PDF-Template beträgt die gerenderte Seitengröße bei 150 DPI `1240 × 1754` Pixel.

```powershell
uv run python -m tools.thesis_results.coordinate_validation.coordinate_validation `
  --ground-truth "thesis-results/validation/pdf-input/pdf/dcm-27082026-1200-seed0042-angle000-corners-fs100-arial-none-labelsn-inkauto-contrastnone/Briefmarken.1Stk.17.03.2026_1345-top_left/pdf_annotations.json" `
  --pdf-ground-truth `
  --pdf-page-index 0 `
  --pdf-dpi 150 `
  --rendered-image "thesis-results/validation/pdf-validation/pdf-annotated-page.png" `
  --baseline-image "thesis-results/validation/pdf-validation/pdf-clean-page.png" `
  --width 1240 `
  --height 1754 `
  --roi-padding 4 `
  --tolerance 2 `
  --difference-threshold 0 `
  --pixel-output-json "thesis-results/validation/pdf-validation/pdf-pixel-comparison.json"
```

## 20. Diagramme erzeugen

Nach den Skalierbarkeits- und PDF-Messungen:

```powershell
uv run python -m tools.thesis_results.performance.plot_results `
  --scalability-csv "thesis-results/benchmarks/scalability-1000000/measurements.csv" `
  --pdf-csv "thesis-results/benchmarks/pdf-scaling/measurements.csv" `
  --output-dir "thesis-results/plots"
```

Die Diagramme liegen dann unter:

```text
thesis-results\plots\
```

## Manifestbasierter Verifikationslauf

```powershell
uv run python -m tools.thesis_results.verification.evaluation_cli `
  --manifest "configs/evaluation-manifest.json" `
  --workspace "thesis-results/validation/qualitative-run" `
  --callback "mein_modul:mein_callback" `
  --seed 42 `
  --block-size 100 `
  --workers 1 `
  --mode sequential
```

Fortsetzung nach kontrolliertem Abbruch:

```powershell
uv run python -m tools.thesis_results.verification.evaluation_cli `
  --manifest "configs/evaluation-manifest.json" `
  --workspace "thesis-results/validation/qualitative-run" `
  --callback "mein_modul:mein_callback" `
  --seed 42 `
  --block-size 100 `
  --workers 1 `
  --mode sequential `
  --resume
```

Das Manifest benötigt mindestens `cases` mit `case_id` und `source`; relative
Pfade beziehen sich auf den Manifestordner. Ein optionales
`identifier_schema` profiliert erwartete strukturierte DICOM-Felder. Weitere
optionale Felder sind `document_type`, `placement_mode`, `rotation_degrees`,
`font_family`, `font_or_renderer`, `handwriting_ink_color`,
`handwriting_contrast_mode`, `expected_schema_fields` und
`used_schema_fields`.

Der Callback muss ein `CaseResult` zurückgeben. `expected_rejection` und ein
freies `error_code`-Feld reichen nicht als Rejection-Evidenz. Die Invariante
für jede Block- und Runbilanz lautet:

```text
planned = successful + rejected + unexpected_failed
```

Ground Truth vorhanden/fehlend, Parsability, ungültige Annotationen,
Pfadkollisionen, Clipping und Geometrie werden separat gezählt. `unknown`
heißt nicht bestimmbar, `unsupported` außerhalb des Vertrags und
`unavailable` bezeichnet eine fehlende Ressource wie `pdftoppm`.

Ein Lauf kann `input-manifest.json`, `checkpoint.json`, `run-summary.json`,
`run-summary-interrupted.json`, `evaluation-results.json`,
`evaluation-results.csv`, `profile-aggregate.json`, `coordinate-metrics.json`,
`case-results/<case_id>.json` und `.commits/block-<nummer>/` enthalten.
Orphan-Commitpakete werden beim Resume nur nach Fingerprint-, Sequenz- und
Inhaltsprüfung übernommen; fremde Pakete werden abgewiesen. Abgebrochene
Läufe nennen den letzten vollständigen Block und offene Fälle.

## Verifikations- und Projektgates

```powershell
uv run pytest tests/unit/test_thesis_verification.py tests/unit/test_thesis_verification_extended.py -q
uv run ruff check tools/thesis_results tests/unit/test_thesis_coordinate_validation.py tests/unit/test_thesis_performance.py
uv run mypy --strict --explicit-package-bases tools/thesis_results/verification
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/ -x
```

Bei `mode parallel` und `workers > 1` führt der Verifikationsharness die Fälle
mit `ThreadPoolExecutor` aus. Der Report verwendet dafür
`worker_execution_status: "thread_pool_measured"`, speichert
`actual_worker_count` und liefert die Ergebnisse in deterministischer
Planungsreihenfolge. Jeder Fall wird über einen getrennten Ausgabepfad
verarbeitet.

`execution_measurement_status: "thread_pool_tracemalloc_measured"` bedeutet,
dass Python-Allokationen des laufenden Prozesses mit `tracemalloc` gemessen
wurden. Native Prozess-/Worker-Speicheranteile werden nicht vollständig
aggregiert; `peak_memory_bytes` ist deshalb keine vollständige native
Peak-Memory-Messung des Workerbetriebs und muss als entsprechend limitierter
Messwert berichtet werden. `single_process_measured` gilt für sequentielle
Läufe beziehungsweise `workers = 1`.

Die Befehle für 10.000 Fälle beschreiben eine geplante Messung und sind kein
Nachweis eines bereits ausgeführten Laufs.
