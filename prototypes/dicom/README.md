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

- Der Prototyp injiziert reproduzierbar genau fuenf DICOM-Tags in eine Echo-DICOM-Datei
- Sichtbare Pixel-Injektion ist fuer `PatientName`, `PatientID` und `AccessionNumber` umgesetzt
- `PatientBirthDate` und `PatientSex` bleiben tag-only
- Das aktuelle `ground_truth.jsonl` enthaelt Run-Metadaten, `dicom_tag_annotations` und
  `box_annotations`
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
- Run-Ordner enthalten Seed, Winkel, Beispielart und kurze ID
- Preview wird als standardisiertes Artefakt pro Run behandelt

## Ausfuehrung

```bash
uv run python prototypes/dicom/inject.py
uv run python prototypes/dicom/inject.py --seed 99
uv run python prototypes/dicom/inject.py --seed 42 --output-dir prototypes/dicom/output/
```

## Schnelltest

Zum Ausfuehren einer Beispiel-Injektion:

```bash
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 20
```

Zum Testen einer anderen diskreten Rotation:

```bash
uv run python prototypes/dicom/inject.py --seed 42 --rotation-angle 90
```

Zum Anschauen der erzeugten Artefakte (oeffnet interaktives Fenster mit Pixelkoordinaten beim Hovern):

```bash
uv run python prototypes/dicom/view.py --dicom prototypes/dicom/output/seed0042-angle020-echo-91180014/91180014_0001_injected.dcm --output prototypes/dicom/output/seed0042-angle020-echo-91180014/preview_check.png
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
| `--font-size-pct` | Nein | `100` | Schriftgroesse als Prozentsatz des Standardwerts (100 = Standard, 50 = halb so gross); muss >= 1 sein |
| `--placement-mode` | Nein | `corners` | Platzierungsmodus: `corners` waehlt eine zufaellige Ecke, `free` platziert den Text frei im Bild |

### Parameter von `view.py`

| Parameter | Pflicht | Default | Beschreibung |
|---|---|---|---|
| `--dicom` | Nein | `DycomData/.../91180014_0001.dcm` | Pfad zur DICOM-Eingabedatei |
| `--output` | Nein | `prototypes/dicom/output/preview.png` | Zielpfad fuer die gespeicherte PNG-Vorschau |
| `--annotations-json` | Nein | — | Pfad zu einer JSON-Datei mit `corners`-Annotationen; werden als gruene Umrisse eingezeichnet |
| `--title` | Nein | `PatientName` aus DICOM | Titel ueber dem Bild |
| `--no-show` | Nein | — | Unterdrueckt das interaktive Matplotlib-Fenster; nur sinnvoll in Scripts |

Nutzliche Dateien nach dem Lauf:

- `prototypes/dicom/output/<run_id>/91180014_0001_injected.dcm`
- `prototypes/dicom/output/<run_id>/preview.png`
- `prototypes/dicom/output/<run_id>/ground_truth.jsonl`
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
`-- seed0042-angle020-echo-91180014/
    |-- 91180014_0001_injected.dcm
    |-- ground_truth.jsonl
    |-- preview.png
    `-- run_manifest.json
```

Die aktuelle Implementierung schreibt run-spezifische Unterordner, in denen DICOM-Datei, Ground
Truth, Preview und Manifest gemeinsam liegen. Die Benennung traegt Seed, Winkel, Beispielart und
eine kurze ID.

Konvention pro Run:

```
output/
`-- seed0042-angle020-echo-91180014/
    |-- 91180014_0001_injected.dcm
    |-- ground_truth.jsonl
    |-- preview.png
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

## Annotationsformat (`ground_truth.jsonl`)

Aktueller Stand: ein Run-Record pro Lauf.

```json
{
  "schema_version": "0.2.0-prototype",
  "record_type": "dicom_injection_run",
  "run_id": "seed0042-angle020-echo-91180014",
  "seed": 42,
  "rotation_degrees": 20,
  "source_file": "DycomData/Anonymization/original_data/patient_10080695_23273240/echo/91180014_0001.dcm",
  "output_file": "prototypes/dicom/output/seed0042-angle020-echo-91180014/91180014_0001_injected.dcm",
  "box_annotations": [],
  "dicom_tag_annotations": []
}
```

Das Artefakt ist jetzt proto-stabil auf MVP-Niveau und trennt klar zwischen:

- `dicom_tag_annotations` fuer Tag-Injektionen ohne 2D-Geometrie
- `box_annotations` fuer sichtbare Overlays mit `corners` als Standardgeometrie
- gemeinsamen Run-Metadaten wie `seed`, `run_id`, `rotation_degrees`, `identity_id`,
  `source_file`, `output_file` und `modality`

Fuer sichtbare Overlays gilt aktuell:

- `corners` ist die Standardform der Geometrie
- `rotation_degrees` wird explizit gespeichert
- im aktuellen Echo-/US-Prototyp wird sichtbare PHI nur in Frame `0` geschrieben und entsprechend
  mit `frame_index: 0` annotiert
- die Preview dient als manuell pruefbares Kontrollartefakt pro Run

## Dateistruktur

```
prototypes/dicom/
|-- README.md
|-- inject.py
|-- identity.py
|-- dicom_writer.py
|-- view.py
`-- output/
```

## Wiederverwendbarkeit

| Datei | Prototype-Einschaetzung | Spaeteres Ziel |
|---|---|---|
| `identity.py` | Voraussichtlich uebernehmbar | `src/injection_pipeline/identity/synthetic.py` |
| `dicom_writer.py` | Voraussichtlich mit Anpassungen uebernehmbar | `src/injection_pipeline/writers/dicom_writer.py` |
| `inject.py` | Prototype-Orchestrierung, nicht uebernehmen | Ersetzt durch PipelineRunner + CLI |
| `view.py` | Prototype-Helfer, im MVP als Preview-Pfad zu schaerfen | Noch offen |

Wichtig: Diese Tabelle ist eine Prototype-Einschaetzung, keine Implementierungszusage fuer `src/`.
Echo-/US-spezifische Platzierungslogik, konkrete Overlay-Szenarien und aktuelle Dateiorchestrierung
gelten weiterhin als prototype-spezifisch.

## Seed-Strategie

- `--seed`-Argument, Default `42`
- Zwei Identitaeten: `seed` und `seed + 1`
- `fake.seed_instance(seed)` pro Identitaet; kein globales `random.seed()`

Im MVP wird der Seed zusaetzlich Layout-, Rotations- und Run-Benennungsentscheidungen
reproduzierbar steuern.

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
