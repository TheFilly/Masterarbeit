# DICOM Injection Prototype

Quick-and-dirty Machbarkeitsnachweis fuer synthetische PII-Injektion in DICOM. Der aktuelle
Stand kombiniert DICOM-Tag-Injektion mit sichtbarer Pixel-Injektion fuer das Echo-/US-Beispiel.
Diese Dokumentation beschreibt bewusst den Prototype-Stand und keinen finalen Entwurf fuer `src/`.

## Zweck

- Verifizieren, dass `pydicom` relevante PII-Tags sicher lesen und schreiben kann
- Ein Ground-Truth-Artefakt im Kleinen erproben
- Seed-gesteuerte Reproduzierbarkeit demonstrieren
- Wiederverwendbare Ideen fuer die spaetere Pipeline vorbereiten

## Ist-Stand

- Der Prototyp injiziert reproduzierbar fuenf DICOM-Tags in eine Echo-DICOM-Datei
- Sichtbare Pixel-Injektion ist fuer `PatientName`, `PatientID` und `AccessionNumber` umgesetzt
- `PatientBirthDate` und `PatientSex` bleiben tag-only
- Schriftgroesse ist per `--font-size-pct` parametrierbar und wirkt sich jetzt sichtbar auf
  Rendering und Geometrie aus (Prozentsatz; 100 = Standard, >= 1)
- Platzierungsmodus ist per `--placement-mode` waehlbar: `corners` (seed-gesteuert zufaellige
  Ecke) oder `free` (unabhaengige Zufallsposition je Annotation)
- Neue CLI-Parameter: `--font-family` mit festen Choices `arial`, `calibri`, `tahoma`,
  `consolas`; optional `--text-background white`
- Pro Run entstehen fuenf Artefakte: injiziertes DICOM, `preview.png`, `preview_annotated.png`
  (rote Bounding Boxes mit duennerer Linie), `ground_truth.json` und `run_manifest.json`
- Das `ground_truth.json` enthaelt Run-Metadaten, `dicom_tag_annotations`, `box_annotations`
  (mit PII-only-`text`, zusaetzlichem `rendered_text`, `corners`, `frame_index`,
  `font_size_pct`), `render_metadata` und `run_metadata`
- Bei praefixierten Tokens wie `SYNTH-433218` oder `ACC-0013389` markieren Bounding Boxes nur den
  PII-Teil; der sichtbare Render-Text bleibt unveraendert
- Validierte Artefakte wurden erfolgreich unter `prototypes/dicom/output_validation_small`,
  `prototypes/dicom/output_validation_large` und `prototypes/dicom/output_validation_main`
  erzeugt
- `inject.py` ist Quick-and-Dirty-Orchestrierung fuer den Prototype und kein Vorgriff auf die
  spaetere Pipeline-Struktur in `src/`

## Beschlossener MVP

- Sichtbare Pixel-Injektion fuer `PatientName`, `PatientID` und `AccessionNumber`
- `PatientBirthDate` und `PatientSex` bleiben im MVP reine DICOM-Tags
- Standardmodus: DICOM-Tag-Injektion und sichtbarer Overlay-Text gemeinsam
- Scope zunaechst nur fuer das bestehende Echo-/US-Beispiel, spaeter ausweitbar
- Rotation nur als kleine diskrete Menge, nicht frei
- `corners` als Standardgeometrie fuer sichtbare Annotationen
- Proto-stabiles Annotationsschema als Ziel fuer den naechsten Schritt
- Run-Ordner enthalten Seed, Winkel, Platzierungsmodus, Beispielart und kurze ID
- Zwei Previews pro Run: `preview.png` (ohne Markierungen) und `preview_annotated.png` (rote Bounding Boxes)

## Ausfuehrung

```bash
uv run python prototypes/dicom/inject.py
uv run python prototypes/dicom/inject.py --seed 99
uv run python prototypes/dicom/inject.py --seed 42 --output-dir prototypes/dicom/output/
uv run python prototypes/dicom/inject.py --seed 42 --font-family tahoma --font-size-pct 120 --text-background white
```

## Schnelltest

Zum Ausfuehren einer Beispiel-Injektion (Standardmodus: `corners`, Standardschriftgroesse):

```bash
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 20
```

Mit expliziten Parametern:

```bash
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 20 --placement-mode corners --font-size-pct 100 --font-family arial
```

Freie Platzierung, halbe Schriftgroesse:

```bash
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 20 --placement-mode free --font-size-pct 50 --font-family calibri
```

Mit weissem Text-Hintergrund:

```bash
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 20 --placement-mode corners --font-size-pct 120 --font-family tahoma --text-background white
```

Zum Anschauen der erzeugten Artefakte (oeffnet interaktives Fenster mit Pixelkoordinaten beim Hovern):

```bash
uv run python prototypes/dicom/view.py --dicom prototypes/dicom/output/seed0042-angle020-corners-echo-91180014/91180014_0001_injected.dcm --output prototypes/dicom/output/seed0042-angle020-corners-echo-91180014/preview_check.png
```

Nur Datei speichern, kein Fenster:

```bash
uv run python prototypes/dicom/view.py --dicom ... --output ... --no-show
```

### Parameter von `inject.py`

| Parameter | Pflicht | Default | Beschreibung |
|---|---|---|---|
| `--seed` | Nein | `42` | Zufalls-Seed fuer reproduzierbare Identitaets- und Layout-Auswahl |
| `--input` | Nein | `DycomData/.../91180014_0001.dcm` | Pfad zur DICOM-Quelldatei |
| `--output-dir` | Nein | `prototypes/dicom/output` | Wurzelverzeichnis; pro Run wird ein Unterordner angelegt |
| `--rotation-angle` | Nein | `0` | Rotationswinkel des Overlay-Texts in Grad; erlaubte Werte: `0, 20, 90, 180, 270` |
| `--font-size-pct` | Nein | `100` | Schriftgroesse als Prozentsatz des Standardwerts (100 = Standard, 50 = halb so gross); wirkt sich auf sichtbare Textgroesse und Box-Geometrie aus; muss >= 1 sein |
| `--placement-mode` | Nein | `corners` | Platzierungsmodus: `corners` waehlt eine zufaellige Ecke, `free` platziert den Text frei im Bild |
| `--font-family` | Nein | `arial` | Prototype-Fontwahl mit festen Choices: `arial`, `calibri`, `tahoma`, `consolas` |
| `--text-background` | Nein | - | Optionaler Text-Hintergrund; aktuell ist nur `white` erlaubt |

### Parameter von `view.py`

| Parameter | Pflicht | Default | Beschreibung |
|---|---|---|---|
| `--dicom` | Nein | `DycomData/.../91180014_0001.dcm` | Pfad zur DICOM-Eingabedatei |
| `--output` | Nein | `prototypes/dicom/output/preview.png` | Zielpfad fuer die gespeicherte PNG-Vorschau |
| `--annotations-json` | Nein | - | Pfad zu einer JSON-Datei mit `corners`-Annotationen; werden als gruene Umrisse eingezeichnet |
| `--title` | Nein | `PatientName` aus DICOM | Titel ueber dem Bild |
| `--no-show` | Nein | - | Unterdrueckt das interaktive Matplotlib-Fenster; nur sinnvoll in Scripts |

Nutzliche Dateien nach dem Lauf:

- `prototypes/dicom/output/<run_id>/91180014_0001_injected.dcm`
- `prototypes/dicom/output/<run_id>/preview.png`
- `prototypes/dicom/output/<run_id>/preview_annotated.png`
- `prototypes/dicom/output/<run_id>/ground_truth.json`
- `prototypes/dicom/output/<run_id>/run_manifest.json`

## Eingabedatei

```
DycomData/Anonymization/original_data/patient_10080695_23273240/echo/91180014_0001.dcm
```

Echo-DICOM aus `original_data/`: enthaelt Placeholder-Werte in PII-Tags, was den Injektionspunkt
explizit macht. Die reichere Metadaten-Struktur des Beispiels eignet sich fuer den ersten
Echo-/US-fokussierten MVP.

## Ausgabe (`output/` - gitignored)

Aktueller Stand:

```
output/
`-- seed0042-angle020-corners-echo-91180014/
    |-- 91180014_0001_injected.dcm
    |-- ground_truth.json
    |-- preview.png
    |-- preview_annotated.png
    `-- run_manifest.json
```

Die aktuelle Implementierung schreibt run-spezifische Unterordner, in denen alle fuenf Artefakte
gemeinsam liegen. Die Benennung traegt Seed, Winkel, Platzierungsmodus, Beispielart und kurze ID.

Benennung: `seed{seed:04d}-angle{angle:03d}-{placement_mode}-{example_type}-{short_id}`

Konvention pro Run:

```
output/
`-- seed{seed:04d}-angle{angle:03d}-{mode}-{type}-{short_id}/
    |-- {source_stem}_injected.dcm
    |-- ground_truth.json
    |-- preview.png
    |-- preview_annotated.png
    `-- run_manifest.json
```

## Injizierte DICOM-Tags

| Tag-Adresse | Keyword | VR | Beschreibung |
|---|---|---|---|
| `(0010,0010)` | `PatientName` | `PN` | Primaerer Name-Traeger |
| `(0010,0020)` | `PatientID` | `LO` | Patienten-ID |
| `(0010,0030)` | `PatientBirthDate` | `DA` | Geburtsdatum `YYYYMMDD` |
| `(0010,0040)` | `PatientSex` | `CS` | `M` oder `F` |
| `(0008,0050)` | `AccessionNumber` | `SH` | Accession-Nummer |

Nicht angefasst: `PixelData`, UIDs (`StudyInstanceUID`, `SeriesInstanceUID`), File Meta
Information.

## Injektionsarten im aktuellen Prototype-MVP

| Identifier | DICOM-Tag | Sichtbarer Overlay-Text |
|---|---|---|
| `PatientName` | Ja | Ja |
| `PatientID` | Ja | Ja |
| `AccessionNumber` | Ja | Ja |
| `PatientBirthDate` | Ja | Nein |
| `PatientSex` | Ja | Nein |

## Annotationsformat (`ground_truth.json`)

Aktueller Stand: ein Run-Record pro Lauf. Schema-Version `0.2.0-prototype`.

**Top-Level-Felder:**

```json
{
  "schema_version": "0.2.0-prototype",
  "record_type": "dicom_injection_run",
  "run_id": "seed0042-angle020-corners-echo-91180014",
  "seed": 42,
  "rotation_degrees": 20,
  "source_file": "...",
  "output_file": "...",
  "preview_file": "...",
  "annotated_preview_file": "...",
  "document_type": "dicom",
  "example_type": "echo",
  "modality": "US",
  "identity_id": "SYNTH-123456",
  "span_annotations": [],
  "box_annotations": [...],
  "dicom_tag_annotations": [...],
  "run_metadata": {...},
  "render_metadata": {...}
}
```

**`box_annotations`-Eintraege** (ein Eintrag pro sichtbar injizierten Identifier):

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
  "rotation_degrees": 20,
  "frame_index": 0,
  "font_size_pct": 120
}
```

- `region`: konkrete Platzierung - `"top_left"`, `"top_right"`, `"bottom_left"`, `"bottom_right"` oder `"free"`
- `corners`: vier `{x, y}`-Punkte als rotiertes Quadrilateral (Koordinaten in Pixeln, Frame 0)
- `font_size_pct`: verwendeter Schriftgroessen-Prozentsatz
- `text`: annotierter PII-Teil; bei praefixierten Tokens also z. B. nur `433218` oder `0013389`
- `rendered_text`: voll sichtbar gerenderter Token, z. B. `SYNTH-433218` oder `ACC-0013389`

**`dicom_tag_annotations`-Eintraege** (alle fuenf Tags, auch tag-only):

```json
{
  "label": "PatientName",
  "tag_address": "0010,0010",
  "tag_keyword": "PatientName",
  "dicom_vr": "PN",
  "value": "Smith^John",
  "identity_field": "patient_name",
  "identity_id": "SYNTH-123456",
  "source_file": "...",
  "output_file": "..."
}
```

**`run_metadata`** enthaelt: `rotation_degrees`, `placement_mode`, `pixel_injection_status`,
`pixel_renderer`, `visible_identity_fields`, `tag_only_identity_fields`,
`source_dicom_context` und `output_dicom_context` (je mit `modality`, `rows`, `columns`,
`samples_per_pixel`, `photometric_interpretation`, `number_of_frames`, `has_pixel_data` sowie
den im Prototype mitgefuehrten UIDs).

**`render_metadata`** enthaelt: `rotation_degrees`, `placement_mode`, `font_size_pct`,
`font_family`, `text_background`, `visible_render_plan`, `seed`,
`allowed_rotations_degrees`, `frame_count`, `applied_frame_indices`,
`effective_font_family`, `effective_font_size_px`, `background_enabled`,
`background_color` und `visible_annotations`.

In `visible_render_plan` und pro sichtbarer Annotation werden ausserdem `text_segments`
dokumentiert, damit generische Praefixe und PII-Segmente getrennt nachvollziehbar bleiben.

Die per-Annotation-`render_metadata` enthalten im aktuellen Prototype u. a.:
`position`, `font_family`, `font_name`, `font_size`, `padding`, `fill_rgb`,
`stroke_fill_rgb`, `stroke_width`, `background_enabled`, `background_color`,
`text_segments`, `pii_bounds`, `pii_text_box_size`, `text_box_size`,
`rotated_box_size` und `rendered_text_corners`.

Beispiel fuer eine praefixierte sichtbare Annotation:

```json
{
  "label": "AccessionNumber",
  "text": "0013389",
  "rendered_text": "ACC-0013389",
  "generic_text": "ACC-",
  "pii_text": "0013389",
  "region": "top_left",
  "rotation_degrees": 20,
  "corners": [
    {"x": 80.35, "y": 230.64},
    {"x": 159.28, "y": 201.91},
    {"x": 164.76, "y": 216.94},
    {"x": 85.82, "y": 245.67}
  ],
  "render_metadata": {
    "font_family": "tahoma",
    "font_size": 22,
    "background_enabled": true,
    "background_color": [255, 255, 255],
    "text_segments": [
      {"kind": "generic", "text": "ACC-"},
      {"kind": "pii", "text": "0013389"}
    ],
    "pii_bounds": {"left": 52.0, "top": 4.0, "right": 136.0, "bottom": 20.0},
    "pii_text_box_size": {"width": 84.0, "height": 16.0},
    "rendered_text_corners": [
      {"x": 30.12, "y": 244.67},
      {"x": 161.67, "y": 196.78},
      {"x": 169.88, "y": 219.33},
      {"x": 38.33, "y": 267.22}
    ]
  }
}
```

**Hinweis zum Photometric Interpretation-Wechsel:** Die Quelldatei verwendet `YBR_FULL_422`,
das injizierte DICOM wird als `RGB` geschrieben. Dieser Wechsel ist im `output_dicom_context`
dokumentiert und ist ein bekanntes Prototype-Verhalten.

## Dateistruktur

```
prototypes/dicom/
|-- README.md
|-- inject.py
|-- identity.py
|-- dicom_writer.py
|-- pixel_injection.py
|-- view.py
`-- output/
```

## Wiederverwendbarkeit

| Datei | Prototype-Einschaetzung | Spaeteres Ziel |
|---|---|---|
| `identity.py` | Voraussichtlich uebernehmbar | `src/injection_pipeline/identity/synthetic.py` |
| `dicom_writer.py` | Voraussichtlich mit Anpassungen uebernehmbar | `src/injection_pipeline/writers/dicom_writer.py` |
| `pixel_injection.py` | Kernlogik teilweise uebernehmbar; Placement-Heuristik prototype-spezifisch | `src/injection_pipeline/writers/` (Rendering-Primitives) |
| `inject.py` | Prototype-Orchestrierung, nicht uebernehmen | Ersetzt durch PipelineRunner + CLI |
| `view.py` | Preview-Helfer; `create_annotated_preview` als Muster fuer QA-Artefakte | Noch offen |

Wichtig: Diese Tabelle ist eine Prototype-Einschaetzung, keine Implementierungszusage fuer `src/`.
Echo-/US-spezifische Platzierungslogik, konkrete Overlay-Szenarien und aktuelle Dateiorchestrierung
gelten weiterhin als prototype-spezifisch.

## Seed-Strategie

- `--seed`-Argument, Default `42`
- Zwei Identitaeten: `seed` und `seed + 1`
- `fake.seed_instance(seed)` pro Identitaet; kein globales `random.seed()`
- Platzierungsentscheidungen nutzen `random.Random(seed)` - lokale Instanz, kein globales `random.seed()`
- Gleicher Seed + gleiche Argumente -> bit-identische Ausgabe (DICOM-Bytes, Corners, Previews)

## Validierungsstand

- Die aktuell dokumentierte Prototype-Variante wurde erfolgreich mit Artefakten unter
  `prototypes/dicom/output_validation_small`,
  `prototypes/dicom/output_validation_large` und
  `prototypes/dicom/output_validation_main` validiert.
- Diese Validierung bezieht sich auf den Prototype in `prototypes/dicom/` und stellt keine
  automatische Zusage fuer eine Uebernahme in `src/` dar.

## Nicht im Scope dieses Prototypen

- Kein produktionsreifes Pydantic-Modell im Prototype-Code
- Keine finale Fehlerbehandlung oder Retry-Logik
- Kein finales Logging-Konzept
- Keine generische Modalitaetsabdeckung ueber das Echo-/US-Beispiel hinaus
- Keine automatische Uebernahme von Prototype-Heuristiken in `src/`

## Abgrenzung zu `src/`

- Dieser Prototype dient zum Erproben von Injektionsarten, Geometrie und Artefakten
- Das proto-stabile Schema ist ein Design-Artefakt fuer die naechsten Schritte, aber noch kein
  finaler Vertrag fuer `src/injection_pipeline/models/`
- Echo-/US-spezifische Entscheidungen werden nicht automatisch in die spaetere generische Pipeline
  uebernommen
