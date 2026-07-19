# InjectionPipeline

Python pipeline for injecting fully synthetic PII into already anonymized
medical documents. The project supports a master's thesis and evaluates how
de-identification systems behave when controlled PII is reintroduced.

The pipeline is an injection tool. It modifies documents and writes a separate
ground-truth artifact for every injected value.

## Current Status

- `src/injection_pipeline/` contains the DICOM/JPG core chain plus the PDF
  loader/writer path with pydantic models, an external identifier schema, and
  split runner/engine stages.
- Run the migrated DICOM/JPG path with `uv run injection-pipeline ...` or
  `uv run python -m injection_pipeline ...`.
- DICOM/JPG operational details live in `docs/dicom-injection.md`.
- ScrabbleGAN handwriting generation is specified in
  `docs/scrabblegan-implementation-plan.md`; the integrated cache/provider
  path and automatic Docker runtime wiring are implemented and verified with
  the local Amazon source checkout and checkpoint.
- Architecture status and open implementation gates live in
  `docs/architecture/` and `docs/fable-work-packages.md`.

## Stack

| Tool | Purpose |
|------|---------|
| Python 3.13 | Runtime |
| `uv` | Package and virtual environment management |
| Pydantic v2 | Data models and validation |
| pydicom | DICOM handling |
| reportlab + pypdf | PDF overlay generation and template merging |
| pandas | Tabular data such as MIMIC-IV CSVs |
| pytest + pytest-cov | Tests and coverage |
| ruff | Linting and formatting |
| mypy strict mode | Static type checking |

## Structure

```text
InjectionPipeline/
|-- src/injection_pipeline/       # Package code and migrated DICOM/JPG pipeline
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
|-- tools/handwriting/            # Isolated handwriting tooling
|-- configs/
|-- docs/
|   |-- architecture/
|   |-- archive/
|   `-- decisions/
|-- tests/
|   |-- fixtures/
|   |-- integration/
|   `-- unit/
|-- DycomData/                    # Local input data, not committed
|-- output/                       # Local generated outputs, not committed
|-- .github/
|-- pyproject.toml
|-- uv.lock
|-- README.md
`-- AGENTS.md
```

## Setup

```bash
git clone <repo-url>
cd InjectionPipeline
uv sync --extra dev
```

Run `uv sync --extra dev` after a fresh clone or new virtual environment. The
dev extra installs `pytest`, `ruff`, and `mypy`.

## Commands

```bash
uv run pytest tests/ -x
uv run pytest tests/ --cov=src/injection_pipeline
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

Run all local gates:

```bash
uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest tests/ -x
```

Run the migrated DICOM/JPG pipeline:

```bash
uv run injection-pipeline --seed 42 --rotation-angle 20
uv run injection-pipeline --seed 42 --font-family handwriting
uv run injection-pipeline generate-handwriting --seed 42
```

Use the public Python API for one controlled DICOM/JPG injection:

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
from pathlib import Path

def inject_function(
    category: str,
    value: str,
    prefix: str,
    suffix: str,
    handwritten: bool,
    documentType: str,
    output_dir: str | PathLike[str] | None = None,
) -> tuple[Path, Path]:
    ...
```

`category` ist ein freier String fuer die PII-Kategorie, die in
`ground_truth.json` erscheint. Native DICOM-Tags werden nur verwendet, wenn
`category` case-insensitive eindeutig zu einem Schema-Feldnamen wie
`patient_id` oder einem DICOM-Keyword wie `PatientID` passt; freie Labels wie
`identifier` bleiben sichtbar/pixelbasiert. `value` ist der zu injizierende
PII-Wert als String.
`prefix` und `suffix` sind nicht-PII-Text vor und nach dem Wert. Leerzeichen
werden nicht automatisch ergaenzt; der sichtbare Text entsteht aus
`prefix + value + suffix`. `handwritten=True` nutzt die bestehende
Handwriting-Pipeline fuer den gesamten sichtbaren Text und benoetigt dieselben
lokalen ScrabbleGAN-Voraussetzungen wie `--font-family handwriting`.
`documentType` akzeptiert `dcm` und `jpg`, unabhaengig von Gross- und
Kleinschreibung. `dcm` waehlt eine `.dcm`-Datei aus
`DycomData/Dicom-Files`; `jpg` waehlt eine `.jpg`- oder `.jpeg`-Datei aus
`DycomData/images`. Die Quelldatei wird passend zum Typ zufaellig aus den
lokalen Standardkandidaten gewaehlt. Position und Rotation werden zufaellig
bestimmt; Schriftgroesse, Farbe und die uebrigen Renderoptionen verwenden die
Pipeline-Defaults, inklusive `placement_mode="corners"`.

Jeder API-Aufruf erzeugt weiterhin einen vollstaendigen Run unter
`output/<run-id>/` mit injiziertem Dokument, `ground_truth.json`,
`preview.png`, `preview_annotated.png` und `run_manifest.json`. Wenn
`output_dir` gesetzt ist, werden zusaetzlich nur das injizierte Dokument und
`ground_truth.json` in dieses Exportverzeichnis kopiert; vorhandene andere
Dateien in diesem Ordner werden nicht bereinigt. Die Rueckgabe ist ein Tupel
`(injected_path, ground_truth_path)` mit den Pfaden zu diesen beiden Dateien.
Ungueltige Parameter oder fehlende lokale Standard-Eingabedateien fuehren zu
`ValueError`.

Für die Handschrift-Integration muss das ScrabbleGAN-Docker-Image einmalig
aus dem Projektstamm gebaut werden:

```powershell
docker build -t injection-scrabblegan tools/handwriting/scrabblegan
```

Das Image verwendet für die historische Python-3.6/PyTorch-1.2-Umgebung
Micromamba. Dadurch bleibt der Amazon-Kompatibilitätsvertrag erhalten, ohne
den speicherintensiven alten Conda-Solver zu verwenden. Unter Windows mit
WSL2 sollten für den initialen Build ungefähr 12 GB WSL-RAM und 8 GB Swap
konfiguriert sein.

Der aktuell getestete CPU-Container belegt ungefähr 1,9 GB als Docker-Image.
Für BuildKit-Zwischenschichten, lokale Checkpoints und den Docker-Cache sollten
mindestens 5 GB freier Speicherplatz eingeplant werden. Die tatsächliche Größe
kann je nach Docker-Cache und Plattform abweichen; IAM-Datensätze oder ein
Training benötigen deutlich mehr Speicher und sind nicht Bestandteil des
Containers.

Ein erneuter Build ist nur nach Änderungen am `Dockerfile` oder an den
Runtime-Abhängigkeiten nötig. Bei neuen Seeds, Checkpoints oder Faker-Daten
startet die Pipeline den Container bei einem Cache-Miss automatisch. Bereits
kompatible Assets werden aus `DycomData/HandwritingAssets/` wiederverwendet.
Die Voraussetzungen für Source-Checkout, Checkpoint und Options-Sidecar sind
unter `tools/handwriting/scrabblegan/README.md` beschrieben.

Inject an already injected DICOM into an existing PDF template:

```bash
uv run injection-pipeline inject-pdf --input-pdf DycomData/pdf/Briefmarken.1Stk.17.03.2026_1345.pdf --input-dicom DycomData/InjectedDicom/<run-id>/<source-stem>_injected.dcm --dicom-annotation DycomData/InjectedDicom/<run-id>/ground_truth.json
```

`compose-pdf` is an alias. Both commands accept `--output-dir`, `--slot`, and
`--page-index`; they write a new PDF and `pdf_annotations.json` under
`output/pdf/<run_id>/<template-stem>-<slot>/` without changing source files.

The same CLI is also available through `uv run python -m injection_pipeline`.

With no CLI arguments, the command starts an interactive parameter setup. If at
least one CLI argument is set and `--input` is missing, the pipeline chooses a
seeded default from `DycomData/Dicom-Files` and `DycomData/images`.

| Option | Default | Possible values | Description |
|--------|---------|-----------------|-------------|
| `--seed` | `42` | Any integer | Seed for identity generation, default input selection, and layout choices |
| `--input` | Seeded auto-selection | Path ending in `.dcm`, `.jpg`, or `.jpeg` | Source document path |
| `--output-dir` | `output` | Path | Root output directory; each run creates a subdirectory |
| `--identifier-schema` | `configs/identifier_schemas/dicom-prototype.json` | Existing JSON schema path | External identifier schema for identity fields and routes |
| `--rotation-angle` | `0` | `0`, `20`, `90`, `180`, `270` | Rotation angle for visible injected text |
| `--font-size-pct` | `100` | Integer `>= 1` | Visible text size as a percentage of the prototype default |
| `--placement-mode` | `corners` | `corners`, `free` | Placement strategy for visible injected text |
| `--font-family` | `arial` | `arial`, `calibri`, `tahoma`, `consolas`, `handwriting` | Common font/renderer choice |
| `--text-background` | none | `white` | Optional white background behind visible text |
| `--show-label-boxes` | `n` | `y`, `n` | Draw generic prefix boxes in `preview_annotated.png` |
| `--run-timestamp` | Current time | ISO-8601 datetime | Fixed timestamp for deterministic run IDs |
| `--handwriting-manifest` | none | JSONL manifest or JSON manifest with `assets` | Manifest for generated handwriting assets |
| `--handwriting-asset` | none | Repeatable `identity_field=asset_id` mapping | Map schema fields to handwriting assets; requires `--handwriting-manifest` |
| `--handwriting-asset-root` | `DycomData/HandwritingAssets` | Path | Persistent cache for generated handwriting assets |
| `--handwriting-checkpoint` | `DycomData/HandwritingAssets/scrabblegan/checkpoints/latest_net_G.pth` | Path | Local ScrabbleGAN generator checkpoint |
| `--handwriting-checkpoint-sha256` | auto-hash local file | SHA-256 hex digest | Expected checkpoint hash |
| `--handwriting-options-json` | checkpoint-adjacent sidecar | Path | Optional options sidecar; otherwise `options.json`, `test_opt.json`, `train_opt.json`, `test_opt.txt`, or `train_opt.txt` is resolved next to the checkpoint |
| `--handwriting-source-dir` | `DycomData/HandwritingAssets/scrabblegan/source` | Path | Local official Amazon source checkout or source copy |
| `--handwriting-upstream-commit` | source `.git_commit` or Git HEAD | Commit hash | Pinned upstream commit recorded in generated manifests |
| `--handwriting-runtime-command` | automatic Docker runtime | Command string | Optional host-side generator override; default starts the configured Docker image |
| `--handwriting-container-image` | `injection-scrabblegan` | Docker image tag | Image used by the automatic handwriting runtime |
| `--handwriting-generator-command` | built-in `generate_single.py` wrapper | Command template | Optional single-text generator override passed to the batch tool |

In interactive mode, the seed is selected first, then the common
font-family/renderer choice is asked before input/schema and the remaining
render parameters. In handwriting mode, Faker values are generated first;
missing compatible assets are generated through the isolated ScrabbleGAN
runtime, stored below `DycomData/HandwritingAssets/`, and injected immediately.
A separate `generate-handwriting --seed` command pre-generates the same
reusable bundle. Handwriting covers only `patient_name`, `patient_id`, and
`accession_number`; the cache distinguishes seed, schema, field, generated
text, checkpoint SHA-256, upstream commit, generator manifest hash, and
`options_sha256`. If the checkpoint, sidecar, source metadata, or runtime is
missing, the command aborts without a font fallback.

## Outputs

Each DICOM/JPG run produces:

| Artifact | Description |
|----------|-------------|
| Modified document | Input document with injected synthetic PII |
| Ground truth | Separate annotation artifact with positions, identifier type, value, and metadata |

The migrated DICOM/JPG path writes `ground_truth.json` with schema
`0.2.0-prototype`. PDF writes `pdf_annotations.json` with schema
`0.3.0-pdf-prototype` under the shared ADR-0008 lineage. A PDF invocation
creates new `pdf_injected.pdf`, `pdf_injected_annotated.pdf`, and
`pdf_annotations.json` artifacts; it never modifies the source PDF, DICOM, or
JSON annotation.

Visible `box_annotations` keep the compatible `label`/`label_corners` fields
and additionally include `category`, `prefix`, `suffix`, `prefix_corners`, and
`suffix_corners`. The PII `text` is only the injected value, while
`rendered_text` is the exact visible string `prefix + value + suffix`.
Native `dicom_tag_annotations` may also include `category` when the value was
planned from an identifier-schema field.

## Current validation snapshot

As of 2026-07-15, the real Docker/upstream checkpoint path is verified locally:
`generate-handwriting --seed 42` generated three assets, a second run reported
three cache hits, `scrabblegan-validate` passed, and a full DICOM handwriting
injection produced a rendered preview and ground truth. `uv run ruff check`
and `uv run mypy src/` are green. Some pytest cases remain blocked on this
Windows machine by permission errors while pytest creates its temporary
directories; this is an environment limitation, not a failed model run.

## Not In Scope

- De-identification
- Defining the PII taxonomy
- Clinical use
- Web application work
- Real patient data

## References

This project injects fully synthetic PII, but individual experiments may use
external research code, datasets, or standards. 

### Handwriting Generation

- ScrabbleGAN method and generated handwriting assets:
  Fogel, S., Averbuch-Elor, H., Cohen, S., Mazor, S., & Litman, R. (2020).
  ScrabbleGAN: Semi-Supervised Varying Length Handwritten Text Generation. In
  *Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern
  Recognition (CVPR)*.
- Official ScrabbleGAN implementation used by the isolated handwriting tooling:
  Amazon Science / Amazon Rekognition Israel. (2020). *ScrabbleGAN:
  Semi-Supervised Varying Length Handwritten Text Generation* [Source code].
  GitHub. <https://github.com/amzn/convolutional-handwriting-gan>

### MIMIC-IV and PhysioNet

- MIMIC-IV v3.1 resource citation:
  Johnson, A., Bulgarelli, L., Pollard, T., Gow, B., Moody, B., Horng, S.,
  Celi, L. A., & Mark, R. (2024). *MIMIC-IV* (version 3.1). PhysioNet.
  RRID:SCR_007345. <https://doi.org/10.13026/kpb9-mt58>
- MIMIC-IV dataset publication:
  Johnson, A. E. W., Bulgarelli, L., Shen, L., et al. (2023). MIMIC-IV, a
  freely accessible electronic health record dataset. *Scientific Data, 10*, 1.
  <https://doi.org/10.1038/s41597-022-01899-x>
- PhysioNet platform citation:
  Goldberger, A., Amaral, L., Glass, L., Hausdorff, J., Ivanov, P. C.,
  Mark, R., Mietus, J. E., Moody, G. B., Peng, C. K., & Stanley, H. E. (2000).
  PhysioBank, PhysioToolkit, and PhysioNet: Components of a new research
  resource for complex physiologic signals. *Circulation, 101*(23), e215-e220.
  RRID:SCR_007345.

