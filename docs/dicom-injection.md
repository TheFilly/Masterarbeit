# DICOM/JPG/PDF-Injection-Pipeline

Betriebsdokumentation für die migrierten DICOM/JPG-Injektionspfade und den
PDF-Adapter in `src/injection_pipeline/`. Die Implementierung erhält den
Prototype-Vertrag: schema-gesteuerte DICOM-Tag-Injektion, sichtbare
Pixel-Injektion und das Schema `0.2.0-prototype` von `ground_truth.json`.

## Umfang

- DICOM-Pfad: schema-definierte Tag-Injektion plus sichtbare Pixel-Injektion.
- JPG-Pfad: ausschließlich sichtbare Pixel-Injektion.
- Ground Truth: Prototype-JSON-Datei mit dem Schema `0.2.0-prototype`.
- Aktuelle Architektur: pydantic-Run-Modelle, ein externes Identifier-Schema,
  getrennte Runner-/Engine-Stufen sowie registrierte DCM/JPG-Loader-/Writer-
  Adapter.
- PDF-Pfad: Der PDF-Adapter lädt ein PDF-Template sowie ein bereits injiziertes
  DICOM und dessen JSON-Annotation; eine neue PDF-Datei und ein PDF-Annotation-
  Sidecar werden geschrieben. Die Eingabedateien bleiben unverändert.
- Umfang der bestehenden CLI: PDF-nativer Freitext-/Tabellen-Text bleibt für
  `inject-pdf` außerhalb des Umfangs; die folgende `make_pdf`-API deckt
  PDF-native Textkomposition ab. De-Identifikation bleibt außerhalb des
  Umfangs.

## Ausführung

```bash
uv run injection-pipeline
uv run injection-pipeline --seed 42 --rotation-angle 20
uv run injection-pipeline --seed 42 --rotation-angle 20 --run-timestamp 2026-07-10T12:00:00
uv run injection-pipeline --seed 42 --identifier-schema configs/identifier_schemas/dicom-prototype.json
uv run injection-pipeline --seed 42 --font-family tahoma --font-size-pct 120 --text-background white
uv run injection-pipeline --seed 42 --font-family handwriting
uv run injection-pipeline --seed 42 --rotation-angle 20 --show-label-boxes y
uv run injection-pipeline --input DicomData/images/faces-00a0d634ad200ced.jpg --seed 42 --rotation-angle 20
uv run injection-pipeline --handwriting-manifest DicomData/HandwritingAssets/scrabblegan/runs/demo/manifest.jsonl --handwriting-asset patient_name=patient-name-001
uv run injection-pipeline generate-handwriting --seed 42
uv run injection-pipeline inject-pdf --input-pdf DicomData/pdf/Briefmarken.1Stk.17.03.2026_1345.pdf --input-dicom DicomData/InjectedDicom/<run-id>/<source-stem>_injected.dcm --dicom-annotation DicomData/InjectedDicom/<run-id>/ground_truth.json
```

`uv run python -m injection_pipeline ...` ist gleichbedeutend. Ohne CLI-
Argumente startet der Befehl den interaktiven Modus. Wenn mindestens ein CLI-
Argument gesetzt ist und `--input` fehlt, wählt der Befehl mithilfe des
seed-basierten Streams `input_selection` eine lokale Standarddatei aus den
sortierten Kandidaten in `DicomData/Dicom-Files` und `DicomData/images`.
Mit `--input` kann die aufgelöste Datei direkt erneut verwendet werden.
`--run-timestamp` macht den Namen des Run-Verzeichnisses deterministisch. Die
Run-ID enthält außerdem die ausgaberelevanten Optionen für Label-Boxen,
Handschrift-Farbe und Handschrift-Kontrastmodus, aber keine Quell- oder
Ausgabepfade. Der Modus `--font-family handwriting` erzeugt zunächst die
Faker-Identität,
sucht das zugehörige Asset-Bundle, erzeugt fehlende Assets über die isolierten
ScrabbleGAN-Tools und injiziert anschließend die Assets. Der eigenständige
Befehl `generate-handwriting --seed` führt dieselbe Asset-Erzeugung und
Persistierung ohne Eingabedokument aus. Die exakten Optionsnamen und die
Cache-Identität sind in `docs/scrabblegan-implementation-plan.md` definiert.

## Öffentliche Python-API

Die DICOM/JPG-Pipeline stellt außerdem eine schlanke Python-API für Aufrufer
bereit, die genau eine kontrollierte Injektion ausführen und dabei die Auswahl
von Quelldatei und Layoutdetails der Pipeline überlassen möchten:

```python
from injection_pipeline import inject_function

injected_path, ground_truth_path = inject_function(
    category="Age",
    value="95",
    prefix="Patient is ",
    suffix=" years old",
    handwritten=False,
    documentType="jpg",
    output_dir="api-export",
)
```

Exakte Signatur:

```python
from os import PathLike
from datetime import datetime
from pathlib import Path


def inject_function(
    category: str,
    value: str,
    prefix: str,
    suffix: str,
    handwritten: bool,
    documentType: str,
    output_dir: str | PathLike[str] | None = None,
    handwriting_ink_color: str = "auto",
    handwriting_contrast_mode: str = "none",
    *,
    seed: int | None = None,
    input_path: str | PathLike[str] | None = None,
    rotation_degrees: int | None = None,
    run_timestamp: datetime | None = None,
) -> tuple[Path, Path]: ...
```

Parameter:

| Parameter | Beschreibung |
|---|---|
| `category` | Freier Kategoriename als String. Der Wert erscheint in `ground_truth.json`. Native DICOM-Routen werden nur verwendet, wenn der Name case-insensitive eindeutig zu einem Identifier-Schema-Feldnamen oder einem DICOM-Keyword passt, zum Beispiel `patient_id` oder `PatientID`. Ambigue Kategorie-Labels wie `identifier` bleiben sichtbar/pixelbasiert. JPG schreibt nie DICOM-Tags. |
| `value` | PII-Wert als String, zum Beispiel `"95"`. |
| `prefix` | Nicht-PII-Text vor dem Wert. Leerzeichen müssen explizit im String stehen. |
| `suffix` | Nicht-PII-Text nach dem Wert. Leerzeichen müssen explizit im String stehen. |
| `handwritten` | `True` nutzt die Handwriting-Pipeline für den kompletten sichtbaren Text `prefix + value + suffix`; `False` nutzt den normalen Renderer. |
| `documentType` | Dokumenttyp, case-insensitive. Erlaubt sind `dcm` und `jpg`; `dcm` wählt aus `DicomData/Dicom-Files`, `jpg` aus `DicomData/images` mit `.jpg` oder `.jpeg`. |
| `output_dir` | Optionales Exportverzeichnis. Wenn gesetzt, werden das injizierte Dokument und `ground_truth.json` dorthin kopiert. Andere vorhandene Dateien in diesem Ordner werden nicht bereinigt. |
| `handwriting_ink_color` | `auto`, `black`, `gray` oder `white`; gilt für Handschrift. |
| `handwriting_contrast_mode` | `none` oder `halo`; gilt für Handschrift. |
| `seed` | Optionaler Seed für deterministische Identität und Layout-Entscheidungen. Ohne Seed bleibt das Legacy-Verhalten nondeterministisch. |
| `input_path` | Optionaler expliziter DICOM-/JPG-Quellpfad. Ohne Pfad wird die Legacy-Zufallsauswahl verwendet. |
| `rotation_degrees` | Optionaler expliziter Winkel aus `0`, `20`, `90`, `180`, `270`. |
| `run_timestamp` | Optionaler Timestamp für reproduzierbare Run-IDs. |

Der sichtbare Text wird als `prefix + value + suffix` gerendert; die API fügt
keine Leerzeichen oder Trennzeichen hinzu. Der Aufruf erzeugt genau diese eine
Injektion. Wenn `input_path` fehlt, wird das Quelldokument zufällig aus den
lokalen Standardkandidaten gewählt. Die Rotation bleibt zufällig, wenn weder
`seed` noch `rotation_degrees` angegeben ist. Die optionalen deterministischen
Parameter ermöglichen eine Wiederholung, ohne die Legacy-Standards zu ändern.
Ungültige Parameter, nicht unterstützte Dokumenttypen, fehlende
Standard-Eingabeordner oder fehlende Kandidatendateien lösen `ValueError` aus.

`handwritten=True` benötigt dieselbe Runtime-Einrichtung wie der CLI-
Handschriftmodus: ScrabbleGAN-Source-Checkout/-Kopie, Generator-Checkpoint,
Options-Sidecar und Docker-Image oder ein kompatibler Runtime-Override müssen
verfügbar sein. Fehlende Handschriftvoraussetzungen lassen den Run
fehlschlagen, statt auf eine normale Font zurückzufallen.

Jeder API-Aufruf schreibt weiterhin das vollständige Run-Verzeichnis unter
`output/<run-id>`:

```text
output/<run-id>/
|-- <source-stem>_injected.dcm  # oder *_injected.jpg
|-- ground_truth.json
|-- preview.png
|-- preview_annotated.png
`-- run_manifest.json
```

Wenn `output_dir` angegeben ist, exportiert die Funktion zusätzlich nur das
injizierte Dokument und `ground_truth.json` in dieses Verzeichnis. Das ist eine
reine Kopieroperation: Vorhandene, nicht zugehörige Dateien in `output_dir`
bleiben erhalten. Der Rückgabewert ist das Tupel
`(injected_path, ground_truth_path)`, sodass Aufrufer die Artefakte ohne eine
Verzeichnissuche laden können.

### `make_pdf` API

`make_pdf` ist die öffentliche Python-API, die mehrere bereits injizierte
Bilder und mehrere PDF-Textinjektionen zu einer PDF-Datei zusammensetzt. Sie
ist von `inject_function` getrennt: `inject_function` erzeugt eine einzelne
DICOM/JPG-Injektion, während `make_pdf` bereits injizierte Bildartefakte und
PDF-Textspezifikationen erhält und eine kompositions-PDF samt Annotationen
schreibt.

```python
from injection_pipeline import (
    PdfMakeArtifacts,
    PdfMakeImageAnnotationInput,
    PdfMakeImageInput,
    PdfMakeTextInput,
    make_pdf,
)

artifacts = make_pdf(
    images=[
        PdfMakeImageInput(
            path="patient-card.png",
            annotations=[
                PdfMakeImageAnnotationInput(
                    category="patient_name",
                    value="Jane Doe",
                    prefix="Name: ",
                    suffix="",
                    rendered_text="Name: Jane Doe",
                    image_corners=[
                        {"x": 20, "y": 30},
                        {"x": 180, "y": 30},
                        {"x": 180, "y": 55},
                        {"x": 20, "y": 55},
                    ],
                )
            ],
        )
    ],
    texts=[
        PdfMakeTextInput(
            category="patient_id",
            value="PID-123",
            prefix="ID: ",
            suffix="",
            handwritten=False,
        )
    ],
    pdf="template.pdf",
    output_dir="api-pdf-export",
    seed=42,
)
```

Die exportierte Signatur lautet:

```python
def make_pdf(
    images: Sequence[PdfMakeImageInput | Mapping[str, object]],
    texts: Sequence[PdfMakeTextInput | Mapping[str, object]],
    pdf: str | PathLike[str],
    output_dir: str | PathLike[str],
    *,
    seed: int | None = None,
) -> PdfMakeArtifacts: ...
```

Parameter:

| Parameter | Beschreibung |
|---|---|
| `images` | Erforderliche Liste bereits injizierter Bilder mit Bildraum-Annotationen. Der Composer bindet die Bilder ein und bildet jede Annotation auf finale PDF-Seitenkoordinaten ab. Dictionaries im Stil von `BoxAnnotation` werden akzeptiert: `label` -> `category`, `text` -> `value` und `corners` -> `image_corners`; Legacy-Präfix- und -Suffix-Ecken bleiben erhalten, sofern vorhanden. |
| `texts` | Erforderliche Liste von PDF-Textinjektionen. Jeder Eintrag hat dieselbe Bedeutung wie `category`, `value`, `prefix`, `suffix` und `handwritten` von `inject_function`, jedoch keinen Ausgabepfad. |
| `pdf` | Erforderliches PDF-Eingabe-Template. Quellseiten bleiben erhalten; bei Bedarf können zusätzliche Seiten angehängt werden. |
| `output_dir` | Erforderliches Verzeichnis für erzeugte PDF, annotierte PDF und Annotation-Sidecar. |
| `seed` | Optionaler Reproduzierbarkeits-Seed für automatische Platzierung, Seitenumbrüche und Bildrotation. Er erzeugt oder verändert keine Textinhalte. |

Normale Texteinträge werden als PDF-nativer Text gerendert. `handwritten=True`
für direkten PDF-Text bricht mit einem eindeutigen Fehler ab, weil die API für
diesen Fall keine sichere Handschrift-Asset- oder Manifestquelle besitzt.
Bereits gerenderte Handschrift wird als Bild mit Annotation übergeben. Die
Layout-Engine vermeidet Überlappungen zwischen Bild- und Textplatzierungen,
kombiniert nebeneinanderliegende und gestapelte Anordnungen und rotiert Bilder
um einen seedbaren kleinen Winkel, sofern das Layout dies auswählt. Wenn die
aktuelle Seite die verbleibenden Elemente nicht aufnehmen kann, hängt der
Composer eine weitere Seite an. Ungültige Eingaben, fehlerhafte Annotationen,
unmögliche Platzierungen oder nicht unterstützte Handschriftanfragen brechen
mit einem eindeutigen Fehler ab.

Das Rückgabeobjekt ist `PdfMakeArtifacts`. Es stellt die erzeugte unveränderte
PDF, die sichtbar annotierte PDF, den JSON-Sidecar und die finalen
Platzierungsmetadaten bereit. Die Dateien werden als `pdf_make.pdf`,
`pdf_make_annotated.pdf` und `pdf_make_annotations.json` unter `output_dir`
geschrieben. Der Sidecar speichert Quellbild-Annotationen nach der
Transformation in PDF-Koordinaten, PDF-native Textannotation, Seitenindizes,
Rotationen sowie die für die Reproduktion benötigten Seed-/Layout-Metadaten.
Bildannotation enthalten Haupt-Quads und optionale Präfix-/Suffix-Quads,
sofern die Quellannotation diese liefert.
Vor dem Anlegen des Ausgabeverzeichnisses weist der Composer Aliase zwischen
jeder PDF-/Bildquelle und allen drei Ausgabepfaden zurück, einschließlich
relativer/absoluter, Hardlink- und Symlink-Aliase. Bei einer Kollision wird
kein Ausgabe-Artefakt geschrieben.

## Parameter

| Parameter | Default | Description |
|---|---|---|
| `--seed` | `42` | Seed für Identitäts- und Layoutentscheidungen |
| `--input` | zufälliger lokaler Standard | DICOM- oder JPG-Quellpfad |
| `--output-dir` | `output` | Ausgabe-Stammverzeichnis |
| `--identifier-schema` | `configs/identifier_schemas/dicom-prototype.json` | Externes Identifier-Schema als JSON |
| `--rotation-angle` | `0` | Einer aus `0`, `20`, `90`, `180`, `270` |
| `--font-size-pct` | `100` | Font-Größe in Prozent, mindestens `1` |
| `--placement-mode` | `corners` | `corners` oder `free` |
| `--font-family` | `arial` | `arial`, `calibri`, `tahoma`, `consolas`, `handwriting` |
| `--text-background` | none | Optionaler `white`-Hintergrund |
| `--handwriting-ink-color` | `auto` | `auto`, `black`, `gray`, `white`; Handschriftfarbe beim Rendern |
| `--handwriting-contrast-mode` | `none` | `none` oder `halo`; `auto` kann bei Bedarf einen Halo aktivieren |
| `--show-label-boxes` | `n` | Generische Präfix-Boxen blau zeichnen |
| `--run-timestamp` | aktuelle Zeit | Optionaler ISO-8601-Zeitstempel für `run_id` |
| `--handwriting-manifest` | none | Explizites JSON- oder JSONL-Handschrift-Manifest (Kompatibilitätspfad) |
| `--handwriting-asset` | none | Wiederholbare explizite Zuordnung `identity_field=asset_id` (Kompatibilitätspfad) |
| `--handwriting-asset-root` | `DicomData/HandwritingAssets` | Persistenter Cache-Stamm für erzeugte Assets |
| `--handwriting-checkpoint` | `DicomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth` | ScrabbleGAN-Generator-Checkpoint |
| `--handwriting-checkpoint-sha256` | Hash der lokalen Datei | Erwarteter Checkpoint-SHA-256 |
| `--handwriting-options-json` | Sidecar neben dem Checkpoint | Optionaler Options-Sidecar; andernfalls `options.json`, `test_opt.json`, `train_opt.json`, `test_opt.txt` oder `train_opt.txt` neben dem Checkpoint |
| `--handwriting-source-dir` | `DicomData/HandwritingAssets/scrabblegan/source` | Offizieller Amazon-Source-Checkout oder eine Source-Kopie |
| `--handwriting-upstream-commit` | Source `.git_commit` oder Git HEAD | Festgelegter Upstream-Commit in Manifesten |
| `--handwriting-runtime-command` | automatische Docker-Runtime | Optionaler Runtime-Override auf dem Host; standardmäßig wird das konfigurierte Docker-Image gestartet |
| `--handwriting-container-image` | `injection-scrabblegan` | Docker-Image bei Cache-Misses |
| `--handwriting-generator-command` | eingebauter `generate_single.py`-Wrapper | Optionales Befehls-Template für den Single-Text-Generator |

Im interaktiven Modus folgt auf die Seed-Abfrage unmittelbar eine gemeinsame
Font-/Renderer-Auswahl. Danach werden Eingabe/Schema sowie die übrigen
Parameter für Rotation, Größe, Platzierung, Hintergrund, Label-Box und
Zeitstempel abgefragt. Normale Font-Auswahlen behalten den bestehenden
Pillow-Pfad; `handwriting` wählt automatische Asset-Suche/-Generierung für die
sichtbaren Felder `patient_name`, `patient_id` und `accession_number`.

## Identifier-Schema und Determinismus

Das Standardschema liegt unter `configs/identifier_schemas/dicom-prototype.json`.
Es definiert die fünf Prototype-Identitätsfelder, Faker-Rezepte, DICOM-Routen,
Routen für sichtbare Pixel, synthetische Präfixe und die Reihenfolge sichtbarer
Zeilen. `--identifier-schema` kann auf eine andere Schemadatei zeigen; die
E2E-Suite enthält einen Lauf mit einem Zwei-Felder-Spielzeugschema, um zu
belegen, dass dieser Pfad keine Codeänderungen erfordert.

Das Schema fixiert `generator.reference_date = "2026-07-10"` mit
`reference_date_policy = "faker-date_of_birth-reference-v1"`. Datumsabhängige
Faker-Rezepte verwenden dieses Datum statt des Ausführungstags, sodass
`PatientBirthDate` bei einem festen Seed stabil bleibt.

Zufallsentscheidungen verwenden den Run-Seed und benannte Streams, soweit der
Prototype-Vertrag dies zulässt:

- `identity_a`: direktes Faker-Seeding mit `--seed`
- Default-Input-Auswahl: abgeleiteter `input_selection`-Stream über sortierte Kandidaten
- Platzierung: übernommener Raw-Seed für Bytekompatibilität
- Run-Uhr: aktuelle Zeit, sofern `--run-timestamp` nicht gesetzt ist

## Ausgaben

Runs werden unter dem konfigurierten Ausgabe-Stammverzeichnis geschrieben:

```text
output/
`-- dcm-27052026-1435-seed0042-angle020-corners-fs100-arial-none/
    |-- 91180014_0001_injected.dcm
    |-- ground_truth.json
    |-- preview.png
    |-- preview_annotated.png
    `-- run_manifest.json
```

JPG-Runs verwenden dieselbe Struktur und schreiben `*_injected.jpg`. Bestehende
ältere Prototype-Ausgabeordner bleiben als lokale Validierungsartefakte
unverändert.

Der Runner lädt die Quelle über `loaders/registry.py`, das DICOM- und JPG-
Adapter anhand der Dateiendung auflöst. DICOM wird über `writers/dicom.py`, JPG
über `writers/jpg.py` geschrieben. Ein weiteres injiziertes Quellformat soll
ein Loader-/Writer-Paar und einen Registry-Eintrag verwenden, nicht einen
neuen Runner-Zweig.

Der aktuelle DICOM-Writer-Vertrag akzeptiert nur little-endian-`uint8`-Eingaben
mit `MONOCHROME2`- oder `RGB`-Photometrie. Nicht unterstützte 16-Bit-,
Big-Endian- und andere photometrische Repräsentationen schlagen fehl, bevor
ein Ausgabeordner erzeugt wird. Bei Multi-Frame-DICOM wird derzeit nur Frame 0
injiziert und aufgezeichnet; die Injektion aller Frames bleibt einer künftigen
expliziten Richtlinie vorbehalten.

## PDF-Injektion

Der PDF-Befehl benötigt drei Eingaben: `--input-pdf`, `--input-dicom` und
`--dicom-annotation`. Optionale Flags sind `--output-dir`, `--slot` und
`--page-index`. `compose-pdf` bleibt als gleichwertiger Befehlsalias erhalten.
Der PDF-Loader validiert Template-Seiten; die DICOM-Annotation wird vom
kanonischen `RunRecord`-Loader geparst. Der PDF-Writer löst die vom
`RunRecord` benannte `preview_file` auf (relative Pfade werden neben der
Annotation aufgelöst), bindet die zugehörige Preview des injizierten DICOM-
Frames ein, transformiert Bildraum-Annotations-Ecken in PDF-Punkte und
schreibt:

```text
output/pdf/<run_id>/<template-stem>-<slot>/
|-- pdf_injected.pdf
|-- pdf_injected_annotated.pdf
|-- pdf_annotations.json
```

Der Sidecar verwendet das Schema `0.3.0-pdf-prototype` aus der ADR-0008-Linie.
PDF-Punkte verwenden einen Ursprung unten links, Bildpunkte einen Pixelursprung
oben links; das Aspect-Fit-Mapping verwendet das tatsächliche
Platzierungsrechteck. Quell-PDF, DICOM und JSON-Dateien werden nie
überschrieben.

Diese bestehende CLI bleibt der DICOM-zu-PDF-Adapter. Die öffentliche
`make_pdf`-API erweitert den PDF-Kompositionsfall auf mehrere bereits
injizierte Bilder plus direkte PDF-native Texteinträge in einer Ausgabe-PDF.
Bereits gerenderte Handschrift wird über Bildeingaben und deren Annotationen
eingebunden.

## Ground Truth

`ground_truth.json` verwendet das Schema `0.2.0-prototype`. Die Pipeline baut
es als pydantic-`RunRecord` auf und serialisiert es mit
`model_dump(mode="json")`:

```json
{
  "schema_version": "0.2.0-prototype",
  "record_type": "dcm_injection_run",
  "run_id": "dcm-27052026-1435-seed0042-angle020-corners-fs100-arial-none-labelsn-inkauto-contrastnone",
  "seed": 42,
  "rotation_degrees": 20,
  "document_type": "dcm",
  "box_annotations": [],
  "dicom_tag_annotations": [],
  "run_metadata": {},
  "render_metadata": {}
}
```

Für JPG-Runs gilt:

- `record_type = "jpg_injection_run"`
- `document_type = "jpg"`
- `dicom_tag_annotations = []`
- DICOM-Kontextfelder fehlen in `run_metadata`

Sichtbare Annotationen enthalten die final rotierten `corners`. `text` ist der
injizierte PII-Wert, während `rendered_text` die vollständige sichtbare
Zeichenkette ist. Das JSON behält
die kompatiblen Felder `label` und `label_corners` und ergänzt `category`,
`prefix`, `suffix`, `prefix_corners` und `suffix_corners`. Für generische
Präfixe wie `SYNTH-` und `ACC-` speichern `label_corners` und `prefix_corners`
die Präfix-Box; Felder ohne Präfix verwenden `null`. DICOM-Tag-Annotationen
enthalten `category`, wenn das Tag aus einem Schemafeld stammt.

`render_metadata` records:

- `geometry_source = "mask_bbox_after_final_rotation"`
- `mask_alpha_threshold`
- Maskengrenzen für Text, PII, Label und gerenderten Text
- Präfix- und Suffix-Maskengrenzen, wenn diese Segmente vorhanden sind
- für Handschrift-Assets: `renderer_type = "handwriting_asset"`, `asset_id`,
  `asset_path`, `mask_path`, `ink_color`, `background_mode` und
  `geometry_source = "transformed_ink_mask"`

`run_manifest.json` enthält derzeit denselben Record wie `ground_truth.json`.
`ground_truth.json` behält den abschließenden Prototype-Zeilenumbruch;
`run_manifest.json` nicht. ADR-0004 dokumentiert dieses Kompatibilitätsdetail.

## Handschrift-Assets

Erzeugte Handschrift-Assets liegen unter `DicomData/HandwritingAssets/` und
werden nicht in Git aufgenommen. Die Pipeline akzeptiert JSON-Manifeste mit
einer `assets`-Liste und JSONL-Manifeste mit einem Asset pro Zeile. Der
integrierte Handschriftmodus verwendet denselben Manifest-Vertrag wie der
explizite Kompatibilitätspfad und ergänzt nach der Faker-Identitätsgenerierung
eine Cache-Suche. Enthält der Cache kein kompatibles Asset für einen gewählten
Identitätswert, startet die isolierte ScrabbleGAN-Runtime automatisch, erzeugt
Bild und Maske, schreibt das Manifest und der Runner verwendet das Asset sofort.
Fehlen Runtime, Checkpoint, Options-Sidecar, `.git_commit`-/Git-Checkout-
Metadaten oder Generatorbefehl, schlägt der Run fehl; ein Fallback auf eine
normale Font erfolgt nicht.

Jedes Asset benötigt:

- PNG-Bildpfad
- Tintenmaskenpfad
- stable `asset_id`
- `text`
- `identity_field` oder `field`
- `ink_color`: `black`, `gray` oder `white`
- `background_mode` oder `background`: `transparent` oder `white`
- Checkpoint-SHA-256, ScrabbleGAN-Commit, Generator-Manifest-Hash und
  `generator_options_sha256`/`options_sha256` metadata for cache identity

Die Bildfarbe und der Hintergrund des Generators sind Legacy-
Präsentationsmetadaten. Der aktuelle Renderer behandelt die separate Maske als
kanonisch und rekonstruiert die sichtbare Tinte beim Rendern. Eine Änderung der
Renderfarbe benötigt daher weder ein zweites Asset noch einen weiteren
Cache-Eintrag. Gewählte Farbe, tatsächlicher Kontrastmodus,
Luminanzstatistiken und Entscheidungsgrund werden in den
Annotationsmetadaten aufgezeichnet.

Wenn `renderer_type = "handwriting_asset"` gilt, zeichnet die Pipeline den
vollständigen sichtbaren Handschrifttext als `rendered_text` auf und hält
PII-Wert, Präfix und Suffix als getrennte Annotationsfelder. Segment-Boxen
werden aus der Asset-Tintenmaske abgeleitet, damit der vollständige
Handschriftsatz nicht stillschweigend als PII markiert wird.

### Dynamisches Handschrift-Erscheinungsbild

Das Handschrift-PNG und seine separate L-Maske werden als Formdaten behandelt.
Im finalen Render-Pass sampelt die Pipeline nur gültige Pixel unterhalb der
final rotierten Maske im display-gemappten RGB-Frame. Eine mittlere Luminanz
unter `128` wählt weiße Tinte, eine Luminanz ab `128` schwarze Tinte. Eine
p10-p90-Spanne über `96`, ein gewählter Kontrast unter `64` oder weniger als
acht gültige Samples aktivieren einen Zwei-Pixel-Halo. Wenn keine Samples
verfügbar sind, ist weiße Tinte mit schwarzem Halo der deterministische
Fallback.

`--handwriting-ink-color black|gray|white` überschreibt die automatische
Farbwahl. `--handwriting-contrast-mode halo` fordert den Halo immer an, während
`none` dem Automatikmodus erlaubt, ihn nur bei Bedarf hinzuzufügen. Halo-Pixel
sind nicht Teil der Ground-Truth-Tintenmaske oder Segmentgeometrie. Legacy-
Manifeste bleiben lesbar; ihre gespeicherten Felder `ink_color` und `background`
werden als Provenienz beibehalten und steuern nicht mehr die Renderfarbe.

Die ScrabbleGAN-Tools besitzen den Provider-/Cache-Pfad auf dem Host, die
automatische Docker-Runtime-Verdrahtung, Fake-Renderer-Validierung,
Options-Sidecar-Hashing und harte Voraussetzungstests. Der reale
Docker-/Upstream-Checkpoint-Pfad wurde am 2026-07-15 mit drei erzeugten Assets,
Manifest-Validierung, Cache-Wiederverwendung und einer vollständigen DICOM-
Injektion verifiziert; siehe
`tools/handwriting/scrabblegan/UPSTREAM_REVIEW.md`.

## Lokale Gates

Der versionierte E2E-Harness erzeugt synthetische DCM/JPG-Fixtures, führt die
Pipeline mit Seed `42`, Rotation `20`, Standardschema, festem Zeitstempel
`2026-07-10T12:00:00` und einer deterministischen Test-Font aus und vergleicht
anschließend die Artefakt-Hashes für:

- injiziertes Dokument
- `ground_truth.json`
- `run_manifest.json`
- `preview.png`
- `preview_annotated.png`

CI installiert `fonts-liberation2` (die Linux-Fallback-Font für `arial`, die
Pillow für Tests ohne festgelegte Fixture-Font benötigt) und führt anschließend
`uv sync --locked --all-extras`, `uv run ruff check src/ tests/`,
`uv run mypy src/` und `uv run pytest tests/ -x` bei Push und Pull Request.

## Validierungsstand

Derzeit ist kein lokaler Referenzsatz unter
`prototypes/dicom/output_validation_*` vorhanden. Die
Regressionsvalidierung verwendet daher die versionierten synthetischen DCM/JPG-
Fixtures und vollständigen Artefakt-Hashes in
`tests/integration/test_end_to_end.py`.

Der E2E-Harness übergibt einen festen Zeitstempel und vergleicht vollständige
Artefakt-Bytes einschließlich `ground_truth.json` und `run_manifest.json`. Die
DCM/JPG-Ausgabe-Hashes änderten sich zunächst, weil `PatientBirthDate` das
Schema-Referenzdatum statt des Faker-Ausführungstags verwendete, und erneut am
2026-07-14, weil `date_of_birth` nicht mehr die eigenen
Faker-Methoden `date_of_birth()`/`date_time_ad()` aufruft. Deren interner
OS-Zweig erzeugte für denselben Seed unter Windows und Linux unterschiedliche
Geburtsdaten und damit unterschiedliche Hashes (siehe
`docs/architecture/determinism-audit.md` N14). `ground_truth.json`,
`run_manifest.json` und beide Preview-PNGs sind auf die von CI (ubuntu-latest)
erzeugten Bytes festgelegt: Der gerenderte Inhalt ist plattformübergreifend
byte-identisch, die Rohdatei-Bytes sind es jedoch nicht (`os.linesep` im JSON;
PNG-Neukodierung durch plattformspezifische Pillow-/matplotlib-Builds). Siehe
`docs/architecture/determinism-audit.md` N8/N9.

Stand 2026-08-27 besteht die vollständige Testsuite (`215 passed`) zusammen mit
`uv run ruff check src/ tests/` und `uv run mypy src/`. Die bestehenden zwei
pydicom-`DeprecationWarning`s aus dem testseitigen `FileDataset`-Aufbau bleiben
als separates technisches To-do bestehen; sie wurden wegen des Review-Scopes
nicht geändert. Bekannte Windows-Unterschiede bei JSON-/PNG-Rohbytes werden
durch semantische bzw. Pixelprüfungen abgedeckt; DCM-/JPG-Pixelartefakte bleiben
identisch.
