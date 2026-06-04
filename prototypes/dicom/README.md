# DICOM Injection Prototype

Quick-and-dirty Machbarkeitsnachweis fuer synthetische PII-Injektion in medizinische Bildartefakte.
Der aktuelle Stand kombiniert einen DICOM-Pfad mit Tag- und Pixel-Injektion und einen JPG-Pfad
mit sichtbarer Pixel-Injektion. Diese Dokumentation beschreibt bewusst den Prototype-Stand und
keinen finalen Entwurf fuer `src/`.

## Zweck

- Verifizieren, dass relevante DICOM-PII-Tags sicher gelesen und geschrieben werden koennen
- Ein proto-stabiles Ground-Truth-Artefakt fuer sichtbare und tag-basierte Injektionen erproben
- Seed-gesteuerte Reproduzierbarkeit fuer Placement und Identitaeten demonstrieren
- Wiederverwendbare Ideen fuer spaetere Pipeline-Modelle vorbereiten, ohne `src/` festzulegen

## Ist-Stand

- Der Prototyp injiziert reproduzierbar fuenf DICOM-Tags in eine Echo-DICOM-Datei
- Sichtbare Pixel-Injektion ist fuer `PatientName`, `PatientID` und `AccessionNumber` umgesetzt
- `PatientBirthDate` und `PatientSex` bleiben tag-only
- Neben `.dcm` unterstuetzt `inject.py` jetzt auch `.jpg` und `.jpeg`
- `--font-size-pct`, `--placement-mode`, `--font-family` und optional `--text-background white`
  steuern das sichtbare Rendering
- Manifest-gesteuerte Handschrift-Assets koennen einzelne sichtbare Werte ersetzen; die
  Bounding Boxes stammen dann aus der final transformierten Ink-Maske
- `--show-label-boxes y|n` steuert, ob in `preview_annotated.png` neben roten PII-Boxes auch
  blaue Label-Boxes fuer generische Praefixe (`SYNTH-`, `ACC-`) gezeichnet werden
- `ground_truth.json` enthaelt bei praefixierten sichtbaren Tokens jetzt zusaetzlich
  `label_corners`; fuer Identifier ohne Praefix bleibt das Feld `null`
- Sichtbare `corners` und `label_corners` werden maskenbasiert aus final rotierten Render-Masken
  gewonnen; Platzierung und Annotation greifen auf dieselbe vorbereitete Overlay-Geometrie zu
- `render_metadata` dokumentiert die Geometrie explizit ueber
  `geometry_source = "mask_bbox_after_final_rotation"` und `mask_alpha_threshold`
- Neue Run-Ordner folgen dem Schema
  `{filetype}-{ddmmyyyy}-{hhmm}-seed{seed:04d}-angle{angle:03d}-{mode}-fs{fontsize}-{fontfamily}-{textbg}`
- Bestehende alte Output-Ordner bleiben unveraendert

## Beschlossener MVP

- Sichtbare Pixel-Injektion fuer `PatientName`, `PatientID` und `AccessionNumber`
- `PatientBirthDate` und `PatientSex` bleiben im MVP reine DICOM-Tags
- Standardmodus fuer DCM: sichtbarer Overlay-Text und DICOM-Tag-Injektion gemeinsam
- JPG-Input nutzt dieselbe sichtbare Renderlogik, aber keine DICOM-Tag-Injektion
- Rotation nur als kleine diskrete Menge, nicht frei
- `corners` bleibt die Standardgeometrie fuer sichtbare Annotationen

## Ausfuehrung

```bash
uv run python prototypes/dicom/inject.py
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 20
uv run python prototypes/dicom/inject.py --seed 42 --font-family tahoma --font-size-pct 120 --text-background white
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 20 --show-label-boxes y
uv run python prototypes/dicom/inject.py --input DycomData/images/faces-00a0d634ad200ced.jpg --seed 42 --rotation-angle 20 --show-label-boxes y
uv run python prototypes/dicom/inject.py --handwriting-manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl --handwriting-asset patient_name=patient-name-001
```

## Parameter von `inject.py`

| Parameter | Pflicht | Default | Beschreibung |
|---|---|---|---|
| `--seed` | Nein | `42` | Zufalls-Seed fuer reproduzierbare Identitaets- und Layout-Auswahl |
| `--input` | Nein | zufaellig aus `DycomData/Dicom-Files` oder `DycomData/images` | Pfad zur DICOM- oder JPG-Quelldatei |
| `--output-dir` | Nein | `prototypes/dicom/output` | Wurzelverzeichnis; pro Run wird ein Unterordner angelegt |
| `--rotation-angle` | Nein | `0` | Erlaubte Werte: `0, 20, 90, 180, 270` |
| `--font-size-pct` | Nein | `100` | Schriftgroesse als Prozentsatz des Standardwerts; muss >= 1 sein |
| `--placement-mode` | Nein | `corners` | `corners` waehlt eine seed-gesteuerte Ecke, `free` platziert frei im Bild |
| `--font-family` | Nein | `arial` | Prototype-Fontwahl: `arial`, `calibri`, `tahoma`, `consolas` |
| `--text-background` | Nein | - | Optionaler Text-Hintergrund; aktuell nur `white` |
| `--show-label-boxes` | Nein | `n` | Zeichnet generische Praefix-Boxes in `preview_annotated.png` blau ein |
| `--handwriting-manifest` | Nein | - | JSON- oder JSONL-Manifest mit generierten Handschrift-Assets |
| `--handwriting-asset` | Nein | - | Wiederholbares Mapping `identity_field=asset_id`, z. B. `patient_name=patient-name-001` |

Ohne CLI-Argumente startet der interaktive Modus und fragt zuerst, ob eine zufaellige lokale
DICOM-/JPG-Datei verwendet werden soll. Bei `n` kann ein konkreter Pfad angegeben werden.
Wenn mindestens ein CLI-Argument gesetzt ist und `--input` fehlt, waehlt der Prototyp weiterhin
nicht-deterministisch eine Datei aus den lokalen Default-Ordnern. Wenn derselbe Input mehrfach
verwendet werden soll, gib den Pfad explizit mit `--input` an.

## Handschrift-Assets

ScrabbleGAN laeuft nicht im Python-3.13-Projekt, sondern als isolierter vorgelagerter Generator
unter `tools/handwriting/scrabblegan/`. Generierte Artefakte liegen lokal unter
`DycomData/HandwritingAssets/` und bleiben aus Git heraus.

Der Generator wird als Batch-Tool im Docker-GPU-Container ausgefuehrt. Source und Checkpoint
werden lokal bereitgestellt; das Tool laedt keine Gewichte und klont keine Repositories:

```powershell
docker build -t injection-scrabblegan tools/handwriting/scrabblegan
docker run --gpus all --rm `
  -v ${PWD}:/workspace `
  injection-scrabblegan `
  scrabblegan-render `
    --input DycomData/HandwritingAssets/inputs/batch.jsonl `
    --output-root DycomData/HandwritingAssets/scrabblegan/runs `
    --run-id demo `
    --source-dir DycomData/HandwritingAssets/scrabblegan/source `
    --checkpoint DycomData/HandwritingAssets/scrabblegan/checkpoints/model.pth `
    --checkpoint-sha256 PIN_CHECKPOINT_SHA256 `
    --generator-command "python3.6 {source_dir}/generate.py --text {text} --seed {seed} --checkpoint {checkpoint} --output {output}"
docker run --rm `
  -v ${PWD}:/workspace `
  injection-scrabblegan `
  scrabblegan-validate `
    --manifest DycomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl `
    --checkpoint DycomData/HandwritingAssets/scrabblegan/checkpoints/model.pth `
    --checkpoint-sha256 PIN_CHECKPOINT_SHA256
```

Der Injection-Prototyp erwartet pro Asset:

- PNG-Bild (`image_path`)
- separate Ink-Maske (`mask_path`)
- stabile `asset_id`
- `text`
- `identity_field` oder `field`
- `ink_color` als `black`, `gray` oder `white`
- `background_mode` oder `background` als `transparent` oder `white`

Unterstuetzt werden JSON-Manifeste mit einer `assets`-Liste und JSONL-Manifeste mit einem Asset
pro Zeile. Bild- und Maskenpfade werden relativ zum Manifest aufgeloest.

Bei `renderer_type = "handwriting_asset"` wird eine Box pro vollstaendigem PII-Wert erzeugt.
Zeichen-, Wortteil- oder Praefix-Boxes werden in v1 nicht erzeugt. Die Box in
`box_annotations[].corners` umfasst die sichtbare Tinte aus der final transformierten Maske; der
Hintergrund vergroessert die PII-Box nicht.

## Ausgabe (`output/` - gitignored)

Neue Runs verwenden folgendes Schema:

```text
output/
`-- dcm-27052026-1435-seed0042-angle020-corners-fs100-arial-none/
    |-- 91180014_0001_injected.dcm
    |-- ground_truth.json
    |-- preview.png
    |-- preview_annotated.png
    `-- run_manifest.json
```

JPG-Runs sehen analog aus:

```text
output/
`-- jpg-27052026-1435-seed0042-angle020-corners-fs100-arial-none/
    |-- faces-00a0d634ad200ced_injected.jpg
    |-- ground_truth.json
    |-- preview.png
    |-- preview_annotated.png
    `-- run_manifest.json
```

Bestehende alte Ordner wie `seed0042-angle020-corners-echo-91180014` werden nicht umbenannt.

## Annotationsformat (`ground_truth.json`)

Schema-Version bleibt `0.2.0-prototype`.

```json
{
  "schema_version": "0.2.0-prototype",
  "record_type": "dcm_injection_run",
  "run_id": "dcm-27052026-1435-seed0042-angle020-corners-fs100-arial-none",
  "seed": 42,
  "rotation_degrees": 20,
  "document_type": "dcm",
  "box_annotations": [...],
  "dicom_tag_annotations": [...],
  "run_metadata": {...},
  "render_metadata": {...}
}
```

Fuer JPG-Runs gilt:

- `record_type = "jpg_injection_run"`
- `document_type = "jpg"`
- `dicom_tag_annotations = []`
- `run_metadata` enthaelt keine `source_dicom_context`- oder `output_dicom_context`-Felder

Beispiel fuer einen `box_annotations`-Eintrag mit Praefix:

```json
{
  "label": "PatientID",
  "text": "433218",
  "rendered_text": "SYNTH-433218",
  "region": "top_left",
  "corners": [
    {"x": 107.14, "y": 139.8},
    {"x": 174.8, "y": 115.17},
    {"x": 180.27, "y": 130.21},
    {"x": 112.62, "y": 154.83}
  ],
  "label_corners": [
    {"x": 52.31, "y": 159.84},
    {"x": 104.56, "y": 140.82},
    {"x": 110.03, "y": 155.85},
    {"x": 57.78, "y": 174.87}
  ],
  "rotation_degrees": 20,
  "frame_index": 0,
  "font_size_pct": 120
}
```

Zusaetzlich enthaelt `render_metadata` jetzt unter anderem:

- `geometry_source = "mask_bbox_after_final_rotation"`
- `mask_alpha_threshold`
- `visible_annotations[*].render_metadata.text_mask_bounds`
- `visible_annotations[*].render_metadata.pii_mask_bounds`
- `visible_annotations[*].render_metadata.label_mask_bounds`
- `visible_annotations[*].render_metadata.rendered_text_corners`
- Fuer Handschrift-Assets: `renderer_type = "handwriting_asset"`, `asset_id`, `asset_path`,
  `mask_path`, `ink_color`, `background_mode` und `geometry_source = "transformed_ink_mask"`

Damit bleibt nachvollziehbar, dass die sichtbaren Boxen aus den final rotierten Masken und nicht
mehr aus rekonstruierten Font-Metriken stammen.

## Validierungsstand

- Erfolgreicher DCM-Run mit sichtbaren Label-Boxes unter `prototypes/dicom/output_validation_dcm_label_y`
- Erfolgreicher DCM-Run ohne sichtbare Label-Boxes unter `prototypes/dicom/output_validation_dcm_label_n`
- Erfolgreicher JPG-Run unter `prototypes/dicom/output_validation_jpg`
- Reproduzierbarkeits-Check fuer AP6 unter `prototypes/dicom/output_validation_ap6_dcm_a` und
  `prototypes/dicom/output_validation_ap6_dcm_b`: identische `box_annotations` und identische
  sichtbare Render-Metadaten bei gleichem Seed und identischen CLI-Parametern
- Separater JPG-Spot-Check fuer AP6 unter `prototypes/dicom/output_validation_ap6_jpg`
- `uv run python -m py_compile prototypes/dicom/pixel_injection.py tests/unit/test_pixel_injection_corners.py`
  erfolgreich; regulere `pytest`-/`ruff`-Laeufe waren im aktuellen Environment nicht moeglich,
  weil `pytest` und `ruff` in der vorhandenen `.venv` fehlen
- Bestehende alte Validierungsordner unter `output_validation_small`, `output_validation_large`
  und `output_validation_main` bleiben als Referenz erhalten
