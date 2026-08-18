# InjectionPipeline

Python-Pipeline zum Injizieren vollständig synthetischer PII in bereits
anonymisierte medizinische Dokumente. Das Projekt unterstützt eine
Masterarbeit und untersucht, wie sich De-Identifikationssysteme verhalten,
wenn kontrollierte PII erneut eingebracht wird.

Die Pipeline ist ein Injection-Tool. Sie verändert Dokumente und schreibt für
jeden injizierten Wert ein separates Ground-Truth-Artefakt.

## Aktueller Status

- `src/injection_pipeline/` enthält die DICOM/JPG-Kernkette sowie den PDF-
  Loader/Writer-Pfad mit pydantic-Modellen, einem externen Identifier-Schema
  und getrennten Runner-/Engine-Stufen.
- Der migrierte DICOM/JPG-Pfad wird mit `uv run injection-pipeline ...` oder
  `uv run python -m injection_pipeline ...` ausgeführt.
- Betriebsdetails für DICOM/JPG stehen in `docs/dicom-injection.md`.
- Die ScrabbleGAN-Handschriftgenerierung ist in
  `docs/scrabblegan-implementation-plan.md` spezifiziert; der integrierte
  Cache-/Provider-Pfad und die automatische Docker-Runtime-Verdrahtung sind
  implementiert und mit dem lokalen Amazon-Source-Checkout und Checkpoint
  verifiziert.
- Architekturstatus und offene Implementierungsgates stehen in
  `docs/architecture/` und `docs/fable-work-packages.md`.

## Stack

| Tool | Zweck |
|------|---------|
| Python 3.13 | Runtime |
| `uv` | Paket- und Virtual-Environment-Verwaltung |
| Pydantic v2 | Datenmodelle und Validierung |
| pydicom | DICOM-Verarbeitung |
| reportlab + pypdf | PDF-Overlay-Erzeugung und Template-Zusammenführung |
| pandas | Tabellendaten wie MIMIC-IV-CSV-Dateien |
| pytest + pytest-cov | Tests und Coverage |
| ruff | Linting und Formatierung |
| mypy strict mode | Statische Typprüfung |

## Struktur

```text
InjectionPipeline/
|-- src/injection_pipeline/       # Paketcode und migrierte DICOM/JPG-Pipeline
|   |-- artifacts/
|   |-- config/
|   |-- engine/
|   |-- identity/
|   |-- loaders/
|   |-- pdf/
|   |-- models/
|   |-- runtime/
|   |-- validators/
|   `-- writers/
|-- tools/handwriting/            # Isolierte Handschrift-Tools
|-- configs/
|-- docs/
|   |-- architecture/
|   |-- archive/
|   `-- decisions/
|-- tests/
|   |-- fixtures/
|   |-- integration/
|   `-- unit/
|-- DicomData/                    # Lokale Eingabedaten, nicht versioniert
|-- output/                       # Lokal erzeugte Ausgaben, nicht versioniert
|-- .github/
|-- pyproject.toml
|-- uv.lock
|-- README.md
`-- AGENTS.md
```

## Einrichtung

```bash
git clone <repo-url>
cd InjectionPipeline
uv sync --extra dev
```

Nach einem frischen Clone oder einem neuen Virtual Environment `uv sync --extra
dev` ausführen. Das Dev-Extra installiert `pytest`, `ruff` und `mypy`.

## Befehle

```bash
uv run pytest tests/ -x
uv run pytest tests/ --cov=src/injection_pipeline
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

Alle lokalen Gates ausführen:

```bash
uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest tests/ -x
```

Die migrierte DICOM/JPG-Pipeline ausführen:

```bash
uv run injection-pipeline --seed 42 --rotation-angle 20
uv run injection-pipeline --seed 42 --font-family handwriting
uv run injection-pipeline generate-handwriting --seed 42
```

Die manuell geprüfte, funktionsübergreifende Visual-Check-Suite ausführen:

```bash
uv run python tools/visual_checks/pipeline_functionality.py
```

Sie schreibt eine neue Sitzung mit Zeitstempel unter `output/visual-checks/`
und deckt die normale CLI, Handschrift, PDF-Befehle, `inject_function` und
`make_pdf` ab. Die Suite ist absichtlich nicht Teil von pytest; siehe
`tools/visual_checks/README.md` für Skip-Optionen und die abgedeckten
Szenarien.

Die öffentliche Python-API für eine kontrollierte DICOM/JPG-Injektion:

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

Die Funktion hat diese Signatur:

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

`category` ist ein freier String für die PII-Kategorie, die in
`ground_truth.json` erscheint. Native DICOM-Tags werden nur verwendet, wenn
`category` case-insensitive eindeutig zu einem Schema-Feldnamen wie
`patient_id` oder einem DICOM-Keyword wie `PatientID` passt; freie Labels wie
`identifier` bleiben sichtbar/pixelbasiert. `value` ist der zu injizierende
PII-Wert als String.
`prefix` und `suffix` sind nicht-PII-Text vor und nach dem Wert. Leerzeichen
werden nicht automatisch ergänzt; der sichtbare Text entsteht aus
`prefix + value + suffix`. `handwritten=True` nutzt die bestehende
Handwriting-Pipeline für den gesamten sichtbaren Text und benötigt dieselben
lokalen ScrabbleGAN-Voraussetzungen wie `--font-family handwriting`.
`documentType` akzeptiert `dcm` und `jpg`, unabhaengig von Gross- und
Kleinschreibung. `dcm` wählt eine `.dcm`-Datei aus
`DicomData/Dicom-Files`; `jpg` wählt eine `.jpg`- oder `.jpeg`-Datei aus
`DicomData/images`. Die Quelldatei wird passend zum Typ zufaellig aus den
lokalen Standardkandidaten gewählt, sofern `input_path` fehlt. Position und
Rotation werden zufaellig bestimmt, sofern keine deterministischen Parameter
angegeben sind. `seed`, `input_path`, `rotation_degrees` und `run_timestamp`
ermöglichen reproduzierbare Aufrufe, ohne das bisherige nondeterministische
Legacy-Verhalten ohne diese Parameter zu ändern.

Jeder API-Aufruf erzeugt weiterhin einen vollständigen Run unter
`output/<run-id>/` mit injiziertem Dokument, `ground_truth.json`,
`preview.png`, `preview_annotated.png` und `run_manifest.json`. Wenn
`output_dir` gesetzt ist, werden zusaetzlich nur das injizierte Dokument und
`ground_truth.json` in dieses Exportverzeichnis kopiert; vorhandene andere
Dateien in diesem Ordner werden nicht bereinigt. Die Rückgabe ist ein Tupel
`(injected_path, ground_truth_path)` mit den Pfaden zu diesen beiden Dateien.
Ungültige Parameter oder fehlende lokale Standard-Eingabedateien führen zu
`ValueError`.

Die öffentliche PDF-Kompositions-API fügt mehrere bereits injizierte
Bildartefakte und mehrere PDF-Textinjektionen zu einer PDF-Datei zusammen:

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

`images` enthält bereits injizierte Bilddateien und ihre vorhandenen
Bildraum-Annotationen; die API bindet diese Bilder ein und transformiert ihre
Annotationen in PDF-Koordinaten. Dictionaries im Stil von `BoxAnnotation` sind
zulässig:
`label` wird auf `category`, `text` auf `value` und `corners` auf
`image_corners` abgebildet. Präfix- und Suffix-Ecken aus Legacy-Annotationen
bleiben erhalten, sofern vorhanden.

`texts` enthält eine oder mehrere direkte PDF-Textspezifikationen mit derselben
Bedeutung wie die Parameter `category`, `value`, `prefix`, `suffix` und
`handwritten` von `inject_function`, jedoch ohne Ausgabepfad. Normaler Text
wird als PDF-nativer Text geschrieben. `handwritten=True` für direkten PDF-Text
bricht mit einem eindeutigen Fehler ab, weil die öffentliche API für diesen
Fall keine sichere Handschrift-Asset- oder Manifestquelle besitzt. Bereits
gerenderte Handschrift wird als Bild mit Annotation übergeben.

`pdf` ist das Eingabe-Template, `output_dir` ist erforderlich. `seed` steuert
nur Layoutentscheidungen, Anordnung, Seitenumbrüche und zufällige
Bildrotationen; die Textinhalte stammen immer aus den übergebenen Parametern.
Das Layout platziert alle Bilder und Textboxen ohne Überlappung, kombiniert
nebeneinanderliegende und gestapelte Anordnungen, rotiert Bilder um einen
seedbaren kleinen Winkel und hängt Seiten an, wenn auf der aktuellen Seite
nicht genügend Platz vorhanden ist. Ungültige Eingaben, fehlerhafte
Annotationen, unmögliche Platzierungen oder nicht unterstützte
Handschriftanfragen brechen mit einem eindeutigen Fehler ab.

Jeder Aufruf schreibt `pdf_make.pdf`, `pdf_make_annotated.pdf` und
`pdf_make_annotations.json` unter `output_dir`. Das zurückgegebene Objekt
`PdfMakeArtifacts` stellt diese Pfade sowie den geparsten Sidecar-Datensatz
bereit, einschließlich Layout-Metadaten und Haupt-, Präfix- und Suffix-Quads,
sofern die Quellannotation diese liefert.

Für die Handschrift-Integration muss das ScrabbleGAN-Docker-Image einmalig
aus dem Projektstamm gebaut werden:

```powershell
docker build --platform linux/amd64 -t injection-scrabblegan tools/handwriting/scrabblegan
```

Auf macOS mit zsh/bash sind die POSIX-Befehle und der Docker-Volume-Mount in
`tools/handwriting/scrabblegan/README.md` dokumentiert. Apple-Silicon-Hosts
verwenden für die Legacy-Runtime weiterhin `linux/amd64`-Emulation.

Das Image verwendet für die historische Python-3.6/PyTorch-1.2-Umgebung
Micromamba. Dadurch bleibt der Amazon-Kompatibilitätsvertrag erhalten, ohne
den speicherintensiven alten Conda-Solver zu verwenden. Der ScrabbleGAN-
Runtime-Container ist fest auf `linux/amd64` gesetzt, weil diese alten Conda-
Pakete nicht für `linux-aarch64` verfügbar sind. Linux- und Windows-x86_64-
Hosts führen dieses Image nativ aus; Apple-Silicon- und Windows-on-ARM-Hosts
verwenden Docker-Emulation. Unter Windows mit WSL2 sollten für den initialen
Build ungefähr 12 GB WSL-RAM und 8 GB Swap konfiguriert sein.

Der aktuell getestete CPU-Container belegt ungefähr 1,9 GB als Docker-Image.
Für BuildKit-Zwischenschichten, lokale Checkpoints und den Docker-Cache sollten
mindestens 5 GB freier Speicherplatz eingeplant werden. Die tatsächliche Größe
kann je nach Docker-Cache und Plattform abweichen; IAM-Datensätze oder ein
Training benötigen deutlich mehr Speicher und sind nicht Bestandteil des
Containers.

Ein erneuter Build ist nur nach Änderungen am `Dockerfile` oder an den
Runtime-Abhängigkeiten nötig. Bei neuen Seeds, Checkpoints oder Faker-Daten
startet die Pipeline den Container bei einem Cache-Miss automatisch. Bereits
kompatible Assets werden aus `DicomData/HandwritingAssets/` wiederverwendet.
Die Voraussetzungen für Source-Checkout, Checkpoint und Options-Sidecar sind
unter `tools/handwriting/scrabblegan/README.md` beschrieben.

Ein bereits injiziertes DICOM in ein vorhandenes PDF-Template injizieren:

```bash
uv run injection-pipeline inject-pdf --input-pdf DicomData/pdf/Briefmarken.1Stk.17.03.2026_1345.pdf --input-dicom DicomData/InjectedDicom/<run-id>/<source-stem>_injected.dcm --dicom-annotation DicomData/InjectedDicom/<run-id>/ground_truth.json
```

`compose-pdf` ist ein Alias. Beide Befehle akzeptieren `--output-dir`, `--slot`
und `--page-index`; sie schreiben eine neue PDF-Datei und
`pdf_annotations.json` unter `output/pdf/<run_id>/<template-stem>-<slot>/`,
ohne Quelldateien zu verändern.

Dieselbe CLI ist auch über `uv run python -m injection_pipeline` verfügbar.

Ohne CLI-Argumente startet der Befehl eine interaktive Parametereinrichtung.
Wenn mindestens ein CLI-Argument gesetzt ist und `--input` fehlt, wählt die
Pipeline einen seed-basierten Standard aus `DicomData/Dicom-Files` und
`DicomData/images`.

| Option | Standard | Mögliche Werte | Beschreibung |
|--------|---------|-----------------|-------------|
| `--seed` | `42` | Jede Ganzzahl | Seed für Identitätsgenerierung, Standard-Eingabeauswahl und Layoutentscheidungen |
| `--input` | Seed-basierte Autoauswahl | Pfad mit Endung `.dcm`, `.jpg` oder `.jpeg` | Pfad des Quelldokuments |
| `--output-dir` | `output` | Pfad | Ausgabe-Stammverzeichnis; jeder Run erzeugt ein Unterverzeichnis |
| `--identifier-schema` | `configs/identifier_schemas/dicom-prototype.json` | Vorhandener JSON-Schema-Pfad | Externes Identifier-Schema für Identitätsfelder und Routen |
| `--rotation-angle` | `0` | `0`, `20`, `90`, `180`, `270` | Rotationswinkel des sichtbar injizierten Texts |
| `--font-size-pct` | `100` | Ganzzahl `>= 1` | Sichtbare Textgröße als Prozentsatz des Prototype-Standards |
| `--placement-mode` | `corners` | `corners`, `free` | Platzierungsstrategie für sichtbar injizierten Text |
| `--font-family` | `arial` | `arial`, `calibri`, `tahoma`, `consolas`, `handwriting` | Gemeinsame Font-/Renderer-Auswahl |
| `--text-background` | none | `white` | Optionaler weißer Hintergrund hinter sichtbarem Text |
| `--handwriting-ink-color` | `auto` | `auto`, `black`, `gray`, `white` | Handschriftfarbe; `auto` wählt anhand der lokalen Luminanz Schwarz oder Weiß |
| `--handwriting-contrast-mode` | `none` | `none`, `halo` | Optionaler Handschrift-Halo; `auto` aktiviert ihn bei unsicherem Kontrast |
| `--show-label-boxes` | `n` | `y`, `n` | Generische Präfix-Boxen in `preview_annotated.png` zeichnen |
| `--run-timestamp` | Aktuelle Zeit | ISO-8601-Datetime | Fester Zeitstempel für deterministische Run-IDs |
| `--handwriting-manifest` | none | JSONL-Manifest oder JSON-Manifest mit `assets` | Manifest für erzeugte Handschrift-Assets |
| `--handwriting-asset` | none | Wiederholbare Zuordnung `identity_field=asset_id` | Schemafelder Handschrift-Assets zuordnen; erfordert `--handwriting-manifest` |
| `--handwriting-asset-root` | `DicomData/HandwritingAssets` | Pfad | Persistenter Cache-Stamm für erzeugte Handschrift-Assets |
| `--handwriting-checkpoint` | `DicomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth` | Pfad | Lokaler ScrabbleGAN-Generator-Checkpoint |
| `--handwriting-checkpoint-sha256` | Hash der lokalen Datei | SHA-256-Hex-Digest | Erwarteter Checkpoint-Hash |
| `--handwriting-options-json` | Sidecar neben dem Checkpoint | Pfad | Optionaler Options-Sidecar; andernfalls wird neben dem Checkpoint `options.json`, `test_opt.json`, `train_opt.json`, `test_opt.txt` oder `train_opt.txt` aufgelöst |
| `--handwriting-source-dir` | `DicomData/HandwritingAssets/scrabblegan/source` | Pfad | Lokaler offizieller Amazon-Source-Checkout oder eine Source-Kopie |
| `--handwriting-upstream-commit` | Source `.git_commit` oder Git HEAD | Commit-Hash | In erzeugten Manifesten festgehaltener Upstream-Commit |
| `--handwriting-runtime-command` | Automatische Docker-Runtime | Befehlsstring | Optionaler Generator-Override auf dem Host; Standard startet das konfigurierte Docker-Image |
| `--handwriting-container-image` | `injection-scrabblegan` | Docker-Image-Tag | Von der automatischen Handschrift-Runtime verwendetes Image |
| `--handwriting-generator-command` | Eingebauter `generate_single.py`-Wrapper | Befehls-Template | Optionales Single-Text-Generator-Override für das Batch-Tool |

Im interaktiven Modus wird zuerst der Seed ausgewählt; danach wird die
gemeinsame Font-/Renderer-Auswahl und anschließend Eingabe/Schema sowie die
übrigen Render-Parameter abgefragt. Im Handschriftmodus werden zuerst die
Faker-Werte erzeugt. Fehlende kompatible Assets werden über die isolierte
ScrabbleGAN-Runtime erzeugt, unter `DicomData/HandwritingAssets/` gespeichert
und sofort injiziert. Der separate Befehl `generate-handwriting --seed`
erzeugt dasselbe wiederverwendbare Bundle vorab. Handschrift wird nur für
`patient_name`, `patient_id` und `accession_number` unterstützt; der Cache
unterscheidet Seed, Schema, Feld, erzeugten Text, Checkpoint-SHA-256,
Upstream-Commit, Generator-Manifest-Hash und `options_sha256`. Fehlen
Checkpoint, Sidecar, Source-Metadaten oder Runtime, bricht der Befehl ohne
Font-Fallback ab.

Das Erscheinungsbild der Handschrift wird beim Rendern aus der separaten
Tintenmaske rekonstruiert. Bei `--handwriting-ink-color auto` wird bei einer
mittleren Luminanz unter `128` weiße, sonst schwarze Tinte gewählt. Eine
Luminanzspanne p10-p90 über `96`, ein Kontrast unter `64` oder zu wenige gültige
Abtastpixel aktivieren einen deterministischen Zwei-Pixel-Halo; ohne Samples
ist weiße Tinte mit schwarzem Halo der Fallback. Explizite Werte `black`,
`gray` und `white` überschreiben die automatische Auswahl. Der Halo ist rein
visuell und wird aus der Ground-Truth-Tintenmaske ausgeschlossen.

## Ausgaben

Jeder DICOM/JPG-Run erzeugt:

| Artefakt | Beschreibung |
|----------|-------------|
| Geändertes Dokument | Eingabedokument mit injizierter synthetischer PII |
| Ground Truth | Separates Annotationsartefakt mit Positionen, Identifier-Typ, Wert und Metadaten |

Der migrierte DICOM/JPG-Pfad schreibt `ground_truth.json` mit dem Schema
`0.2.0-prototype`. PDF schreibt `pdf_annotations.json` mit dem Schema
`0.3.0-pdf-prototype` innerhalb der gemeinsamen ADR-0008-Linie. Ein PDF-Aufruf
erzeugt neue Artefakte `pdf_injected.pdf`, `pdf_injected_annotated.pdf` und
`pdf_annotations.json`; die Quell-PDF, das DICOM und die JSON-Annotation werden
niemals verändert.

Sichtbare `box_annotations` behalten die kompatiblen Felder
`label`/`label_corners` und enthalten zusätzlich `category`, `prefix`,
`suffix`, `prefix_corners` und `suffix_corners`. Der PII-Wert in `text` ist nur
der injizierte Wert; `rendered_text` ist die exakt sichtbare Zeichenkette
`prefix + value + suffix`. Native `dicom_tag_annotations` können ebenfalls
`category` enthalten, wenn der Wert aus einem Identifier-Schema-Feld geplant
wurde.

## Aktueller Validierungsstand

Stand 2026-07-15 ist der reale Docker-/Upstream-Checkpoint-Pfad lokal
verifiziert: `generate-handwriting --seed 42` erzeugte drei Assets, ein
zweiter Lauf meldete drei Cache-Hits, `scrabblegan-validate` war erfolgreich
und eine vollständige DICOM-Handschriftinjektion erzeugte Preview und Ground
Truth. `uv run ruff check` und `uv run mypy src/` sind erfolgreich. Einige
pytest-Fälle bleiben auf dieser Windows-Maschine wegen Berechtigungsfehlern
beim Erzeugen temporärer Verzeichnisse blockiert; das ist eine
Umgebungseinschränkung und kein fehlgeschlagener Modelllauf.

## Nicht im Umfang

- De-Identifikation
- Definition der PII-Taxonomie
- Klinische Nutzung
- Arbeiten an Webanwendungen
- Echte Patientendaten

## Referenzen

Dieses Projekt injiziert vollständig synthetische PII; einzelne Experimente
können jedoch externen Forschungscode, Datensätze oder Standards verwenden.

### Handschriftgenerierung

- ScrabbleGAN-Methode und erzeugte Handschrift-Assets:
  Fogel, S., Averbuch-Elor, H., Cohen, S., Mazor, S., & Litman, R. (2020).
  ScrabbleGAN: Semi-Supervised Varying Length Handwritten Text Generation. In
  *Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern
  Recognition (CVPR)*.
- Offizielle ScrabbleGAN-Implementierung, die von den isolierten
  Handschrift-Tools verwendet wird:
  Amazon Science / Amazon Rekognition Israel. (2020). *ScrabbleGAN:
  Semi-Supervised Varying Length Handwritten Text Generation* [Source code].
  GitHub. <https://github.com/amzn/convolutional-handwriting-gan>

### MIMIC-IV und PhysioNet

- Zitat für die MIMIC-IV-v3.1-Ressource:
  Johnson, A., Bulgarelli, L., Pollard, T., Gow, B., Moody, B., Horng, S.,
  Celi, L. A., & Mark, R. (2024). *MIMIC-IV* (version 3.1). PhysioNet.
  RRID:SCR_007345. <https://doi.org/10.13026/kpb9-mt58>
- Veröffentlichung zum MIMIC-IV-Datensatz:
  Johnson, A. E. W., Bulgarelli, L., Shen, L., et al. (2023). MIMIC-IV, a
  freely accessible electronic health record dataset. *Scientific Data, 10*, 1.
  <https://doi.org/10.1038/s41597-022-01899-x>
- Zitat für die PhysioNet-Plattform:
  Goldberger, A., Amaral, L., Glass, L., Hausdorff, J., Ivanov, P. C.,
  Mark, R., Mietus, J. E., Moody, G. B., Peng, C. K., & Stanley, H. E. (2000).
  PhysioBank, PhysioToolkit, and PhysioNet: Components of a new research
  resource for complex physiologic signals. *Circulation, 101*(23), e215-e220.
  RRID:SCR_007345.
