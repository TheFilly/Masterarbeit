"""Run manually inspected visual checks for the complete pipeline surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from injection_pipeline import inject_function, make_pdf
from injection_pipeline.runtime.run_layout import build_run_id

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPOSITORY_ROOT / "DicomData"
DEFAULT_OUTPUT_PARENT = REPOSITORY_ROOT / "output" / "visual-checks"


@dataclass(frozen=True)
class PipelineRun:
    """Paths emitted by one normal DICOM/JPG CLI run."""

    source: Path
    run_dir: Path
    output_file: Path
    preview: Path
    ground_truth: Path


@dataclass(frozen=True)
class CliScenario:
    """Arguments for one manually inspected normal pipeline run."""

    label: str
    source: Path
    seed: int
    rotation_angle: int
    placement_mode: str
    font_size_pct: int
    font_family: str
    text_background: str | None
    show_label_boxes: str
    handwriting_ink_color: str = "auto"
    handwriting_contrast_mode: str = "none"


# Input: Einen Namen fuer ein Kind unter `parent` und ein Fallback-Index.
# Output: Ein vorhandener Pfad mit passender Gross-/Kleinschreibung.
# Die Funktion macht die lokalen Datenpfade auf Windows und case-sensitiven
# macOS-Dateisystemen robust, ohne Pfadtrenner selbst zusammenzusetzen.
def resolve_data_directory(parent: Path, name: str) -> Path:
    for child in parent.iterdir():
        if child.is_dir() and child.name.casefold() == name.casefold():
            return child
    raise FileNotFoundError(f"Data directory not found: {parent / name}")


# Input: Datenordner, bevorzugter Dateiname und erlaubte Endungen.
# Output: Deterministisch ausgewaehlte Quelldatei.
# Der bevorzugte Fixture-Name wird verwendet, falls vorhanden; andernfalls
# faellt der Check auf eine sortierte lokale Datei desselben Formats zurueck.
def choose_source(
    directory: Path,
    preferred_name: str,
    extensions: set[str],
    fallback_index: int,
) -> Path:
    preferred = directory / preferred_name
    if preferred.is_file():
        return preferred
    candidates = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.casefold() in extensions
    )
    if not candidates:
        raise FileNotFoundError(
            f"No files with extensions {sorted(extensions)} found in {directory}."
        )
    return candidates[fallback_index % len(candidates)]


# Input: Ein Verzeichnis mit PDFs und ein bevorzugter Dateiname.
# Output: Vorhandene PDF-Vorlage.
# Die Vorlage wird ueber `Path` weitergereicht und bleibt unveraendert.
def choose_pdf_template(directory: Path, preferred_name: str) -> Path:
    return choose_source(directory, preferred_name, {".pdf"}, 0)


# Input: Kommandoargumente ohne Shell-Syntax und eine kurze Bezeichnung.
# Output: Keine Rueckgabe; der Kindprozess schreibt seine normalen Ausgaben.
# Der Prozess wird ohne Shell gestartet, wodurch Leerzeichen in Windows- und
# macOS-Pfaden sicher funktionieren und keine plattformspezifischen Quotes
# benoetigt werden.
def run_command(arguments: list[str], label: str) -> None:
    print(f"\n=== {label} ===")
    print("$ " + " ".join(_display_argument(argument) for argument in arguments))
    subprocess.run(arguments, cwd=REPOSITORY_ROOT, check=True)


# Input: Ein einzelnes Kommandoargument.
# Output: Lesbare Darstellung fuer die manuelle Konsolenausgabe.
# Die Funktion markiert nur Argumente mit Leerzeichen; sie veraendert nicht das
# tatsaechlich ausgefuehrte Argument.
def _display_argument(argument: str) -> str:
    return f'"{argument}"' if " " in argument else argument


# Input: Quelle und alle renderrelevanten CLI-Optionen.
# Output: Die Pfade des erzeugten Run-Bundles.
# Die Funktion fuehrt den normalen CLI-Pfad aus und berechnet anschliessend
# denselben Run-Identifier wie der Runner einschliesslich aller Renderoptionen
# fuer nachgelagerte Artefakt- und PDF-Checks.
def run_cli_scenario(
    scenario: CliScenario,
    output_root: Path,
    run_timestamp: datetime,
) -> PipelineRun:
    arguments = [
        sys.executable,
        "-m",
        "injection_pipeline",
        "--seed",
        str(scenario.seed),
        "--input",
        str(scenario.source),
        "--output-dir",
        str(output_root),
        "--rotation-angle",
        str(scenario.rotation_angle),
        "--placement-mode",
        scenario.placement_mode,
        "--font-size-pct",
        str(scenario.font_size_pct),
        "--font-family",
        scenario.font_family,
        "--show-label-boxes",
        scenario.show_label_boxes,
        "--run-timestamp",
        run_timestamp.isoformat(),
    ]
    if scenario.text_background is not None:
        arguments.extend(["--text-background", scenario.text_background])
    if scenario.font_family == "handwriting":
        arguments.extend(
            [
                "--handwriting-ink-color",
                scenario.handwriting_ink_color,
                "--handwriting-contrast-mode",
                scenario.handwriting_contrast_mode,
            ]
        )
    run_command(arguments, scenario.label)

    filetype = "dcm" if scenario.source.suffix.casefold() == ".dcm" else "jpg"
    run_id = build_run_id(
        filetype=filetype,
        run_timestamp=run_timestamp,
        seed=scenario.seed,
        rotation_degrees=scenario.rotation_angle,
        placement_mode=scenario.placement_mode,
        font_size_pct=scenario.font_size_pct,
        font_family=scenario.font_family,
        text_background=scenario.text_background,
        show_label_boxes=scenario.show_label_boxes,
        handwriting_ink_color=scenario.handwriting_ink_color,
        handwriting_contrast_mode=scenario.handwriting_contrast_mode,
    )
    run_dir = output_root / run_id
    output_suffix = ".dcm" if filetype == "dcm" else ".jpg"
    run = PipelineRun(
        source=scenario.source,
        run_dir=run_dir,
        output_file=run_dir / f"{scenario.source.stem}_injected{output_suffix}",
        preview=run_dir / "preview.png",
        ground_truth=run_dir / "ground_truth.json",
    )
    for path in (run.output_file, run.preview, run.ground_truth):
        if not path.is_file():
            raise FileNotFoundError(f"Expected visual-check artifact not found: {path}")
    return run


# Input: Einen erzeugten DICOM-Run, PDF-Vorlage und Zielordner.
# Output: Keine Rueckgabe; schreibt zwei PDFs und ein PDF-Sidecar.
# Beide historischen PDF-Subcommands werden separat ausgefuehrt, damit Alias-
# und Slot-Verhalten visuell verglichen werden koennen.
def run_pdf_cli_check(
    command_name: str,
    run: PipelineRun,
    pdf_template: Path,
    output_root: Path,
    slot: str,
) -> None:
    arguments = [
        sys.executable,
        "-m",
        "injection_pipeline",
        command_name,
        "--input-pdf",
        str(pdf_template),
        "--input-dicom",
        str(run.output_file),
        "--dicom-annotation",
        str(run.ground_truth),
        "--output-dir",
        str(output_root),
        "--slot",
        slot,
        "--page-index",
        "0",
    ]
    run_command(arguments, f"PDF CLI: {command_name} ({slot})")


# Input: Ein normaler Pipeline-Run und gewuenschte Anzahl Ground-Truth-Boxen.
# Output: Mapping fuer `make_pdf(images=...)`.
# Die Funktion uebernimmt nur bestehende Preview-/Annotation-Artefakte und
# laesst die Quelldokumente unberuehrt.
def make_pdf_image_input(run: PipelineRun, annotation_count: int) -> dict[str, object]:
    payload = json.loads(run.ground_truth.read_text(encoding="utf-8"))
    annotations = payload.get("box_annotations", [])[:annotation_count]
    return {"path": run.preview, "annotations": annotations}


# Input: Erzeugte Runs, PDF-Vorlage und Ausgabeordner.
# Output: Keine Rueckgabe; schreibt zwei `make_pdf`-Kompositionen.
# Die Szenarien decken direkte PDF-Texte, mehrere Bilder, Annotationstransfer,
# Seitenlayout, Rotation und unterschiedliche deterministische Seeds ab.
def run_make_pdf_checks(
    runs: list[PipelineRun], pdf_template: Path, output_root: Path
) -> None:
    images = [make_pdf_image_input(run, 3) for run in runs[:2]]
    artifacts = make_pdf(
        images=images,
        texts=[
            {
                "category": "PdfBatchId",
                "value": "PDF-API-7001",
                "prefix": "Batch ",
                "suffix": " composed",
                "handwritten": False,
            },
            {
                "category": "Reviewer",
                "value": "Synthetic QA",
                "prefix": "Checked by ",
                "suffix": "",
                "handwritten": False,
            },
        ],
        pdf=pdf_template,
        output_dir=output_root / "api-make-pdf-two-images",
        seed=7001,
    )
    print(f"\nmake_pdf two-images clean PDF: {artifacts.clean_pdf}")
    print(f"make_pdf two-images annotated PDF: {artifacts.annotated_pdf}")

    stress_images = [make_pdf_image_input(run, 2) for run in runs[:3]]
    stress_texts = [
        {
            "category": "CaseNote",
            "value": f"API-PDF-{index:02d}",
            "prefix": "Direct text ",
            "suffix": " / layout check",
            "handwritten": False,
        }
        for index in range(1, 7)
    ]
    stress_artifacts = make_pdf(
        images=stress_images,
        texts=stress_texts,
        pdf=pdf_template,
        output_dir=output_root / "api-make-pdf-layout-stress",
        seed=7002,
    )
    print(f"make_pdf stress clean PDF: {stress_artifacts.clean_pdf}")
    print(f"make_pdf stress annotated PDF: {stress_artifacts.annotated_pdf}")


# Input: Keine fachlichen Eingaben ausser dem Repository-Kontext.
# Output: Keine Rueckgabe; fuehrt die fokussierten API-/PDF-Unit-Tests aus.
# Die Tests werden nur durch dieses manuell gestartete Skript aufgerufen und
# bleiben fuer normale pytest-Laeufe unveraendert.
def run_api_unit_tests() -> None:
    run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_api.py",
            "tests/unit/test_make_pdf_api.py",
            "-q",
        ],
        "Focused API unit tests",
    )


# Input: Lokale Quellen, Ausgabeordner und einen repräsentativen DICOM-/JPG-Run.
# Output: Keine Rueckgabe; schreibt vier Public-API-Ergebnisse.
# Die Aufrufe pruefen native DICOM-Zuordnung, freie Kategorien, DICOM/JPG-
# Ausgabe sowie API-Handschrift mit einem kurzen, alphabetkompatiblen Text.
def run_api_checks(
    dcm_source: Path,
    jpg_source: Path,
    output_root: Path,
) -> None:
    api_cases = [
        (
            "inject_function DICOM native field",
            {
                "category": "PatientID",
                "value": "API-900001",
                "prefix": "ID: ",
                "suffix": " / verified",
                "handwritten": False,
                "documentType": "dcm",
                "input_path": dcm_source,
                "output_dir": output_root / "api-inject-dcm-patient-id",
                "seed": 8101,
            },
        ),
        (
            "inject_function JPG custom category",
            {
                "category": "VisitReason",
                "value": "Follow-up screening",
                "prefix": "Reason: ",
                "suffix": " / outpatient",
                "handwritten": False,
                "documentType": "jpg",
                "input_path": jpg_source,
                "output_dir": output_root / "api-inject-jpg-custom-category",
                "seed": 8102,
            },
        ),
        (
            "inject_function DICOM handwriting",
            {
                "category": "PatientID",
                "value": "ID-123456",
                "prefix": "",
                "suffix": "",
                "handwritten": True,
                "documentType": "dcm",
                "input_path": dcm_source,
                "output_dir": output_root / "api-inject-dcm-handwriting",
                "seed": 8103,
                "handwriting_ink_color": "black",
                "handwriting_contrast_mode": "none",
            },
        ),
        (
            "inject_function JPG handwriting",
            {
                "category": "PatientID",
                "value": "ID-654321",
                "prefix": "",
                "suffix": "",
                "handwritten": True,
                "documentType": "jpg",
                "input_path": jpg_source,
                "output_dir": output_root / "api-inject-jpg-handwriting",
                "seed": 8104,
                "handwriting_ink_color": "gray",
                "handwriting_contrast_mode": "halo",
            },
        ),
    ]
    for label, kwargs in api_cases:
        print(f"\n=== {label} ===")
        injected, ground_truth = inject_function(**kwargs)
        print(f"Bild/Dokument: {injected}")
        print(f"Ground Truth: {ground_truth}")


# Input: Ausgabeparent und optionaler Modus zum Ueberspringen teurer Checks.
# Output: Eine eindeutige Sitzungsausgabe und normalisierte Optionen.
# Jeder Lauf verwendet einen neuen Zeitstempelordner, damit die Pipeline ihre
# Run-Verzeichnisse nicht mit frueheren manuellen Pruefungen ueberschreibt.
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run manually inspected visual checks for InjectionPipeline."
    )
    parser.add_argument(
        "--output-parent",
        type=Path,
        default=DEFAULT_OUTPUT_PARENT,
        help="Parent directory for a new timestamped visual-check session.",
    )
    parser.add_argument(
        "--skip-handwriting",
        action="store_true",
        help="Skip Docker-backed handwriting and standalone handwriting checks.",
    )
    parser.add_argument(
        "--skip-pdf",
        action="store_true",
        help="Skip inject-pdf, compose-pdf, and make_pdf checks.",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Skip direct public API checks.",
    )
    parser.add_argument(
        "--skip-unit-tests",
        action="store_true",
        help="Skip the focused API and make_pdf pytest checks.",
    )
    return parser.parse_args()


# Input: Keine Parameter ausser den geparsten CLI-Optionen.
# Output: Keine Rueckgabe; fuehrt die manuelle Visual-Check-Suite aus.
# Die Funktion deckt CLI, isolierte Handschrift, PDF-Adapter und Public APIs
# ab und stoppt beim ersten Fehler, damit fehlerhafte Vorstufen nicht verdeckt
# werden.
def main() -> None:
    args = parse_arguments()
    session_start = datetime.now().replace(second=0, microsecond=0)
    session_name = f"functionality-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output_parent = args.output_parent.expanduser()
    if not output_parent.is_absolute():
        output_parent = REPOSITORY_ROOT / output_parent
    output_root = (output_parent / session_name).resolve()
    output_root.mkdir(parents=True, exist_ok=False)

    dicom_dir = resolve_data_directory(DATA_ROOT, "Dicom-Files")
    image_dir = resolve_data_directory(DATA_ROOT, "images")
    pdf_dir = resolve_data_directory(DATA_ROOT, "PDF")
    pdf_template = choose_pdf_template(pdf_dir, "Briefmarken.1Stk.17.03.2026_1345.pdf")
    dcm_sources = [
        choose_source(
            dicom_dir, "91180014_0004.dcm", {".dcm"}, 0
        ),
        choose_source(dicom_dir, "91180014_0001.dcm", {".dcm"}, 1),
        choose_source(dicom_dir, "91180014_0020.dcm", {".dcm"}, 2),
        choose_source(dicom_dir, "91180014_0002.dcm", {".dcm"}, 3),
        choose_source(dicom_dir, "91180014_0003.dcm", {".dcm"}, 4),
    ]
    jpg_sources = [
        choose_source(image_dir, "faces-00a0d634ad200ced.jpg", {".jpg", ".jpeg"}, 0),
        choose_source(image_dir, "faces-0a0d7a87378422e3.jpg", {".jpg", ".jpeg"}, 1),
        choose_source(image_dir, "faces-0a0de81fc9d37ade.jpg", {".jpg", ".jpeg"}, 2),
        choose_source(image_dir, "faces-0a2a14701d899d8f.jpg", {".jpg", ".jpeg"}, 3),
    ]

    scenarios = [
        CliScenario(
            "CLI DICOM Arial corners",
            dcm_sources[0],
            111,
            0,
            "corners",
            100,
            "arial",
            None,
            "n",
        ),
        CliScenario(
            "CLI DICOM Calibri free background",
            dcm_sources[1],
            112,
            20,
            "free",
            125,
            "calibri",
            "white",
            "y",
        ),
        CliScenario(
            "CLI DICOM Tahoma 90 degrees",
            dcm_sources[2],
            113,
            90,
            "corners",
            80,
            "tahoma",
            None,
            "y",
        ),
        CliScenario(
            "CLI DICOM Consolas 180 degrees",
            dcm_sources[0],
            114,
            180,
            "free",
            150,
            "consolas",
            "white",
            "n",
        ),
        CliScenario(
            "CLI JPG Arial background",
            jpg_sources[0],
            115,
            0,
            "free",
            90,
            "arial",
            "white",
            "y",
        ),
        CliScenario(
            "CLI JPG Calibri",
            jpg_sources[1],
            116,
            20,
            "corners",
            140,
            "calibri",
            None,
            "n",
        ),
        CliScenario(
            "CLI JPG Tahoma 270 degrees",
            jpg_sources[2],
            117,
            270,
            "free",
            70,
            "tahoma",
            "white",
            "n",
        ),
    ]
    normal_runs: list[PipelineRun] = []
    for index, scenario in enumerate(scenarios):
        normal_runs.append(
            run_cli_scenario(
                scenario, output_root, session_start + timedelta(minutes=index)
            )
        )

    handwriting_runs: list[PipelineRun] = []
    if not args.skip_handwriting:
        handwriting_scenarios = [
            CliScenario(
                "CLI handwriting DICOM auto halo",
                dcm_sources[3],
                301,
                0,
                "corners",
                100,
                "handwriting",
                None,
                "y",
                "auto",
                "halo",
            ),
            CliScenario(
                "CLI handwriting JPG black none",
                jpg_sources[3],
                302,
                20,
                "free",
                100,
                "handwriting",
                "white",
                "n",
                "black",
                "none",
            ),
            CliScenario(
                "CLI handwriting DICOM gray halo",
                dcm_sources[4],
                303,
                90,
                "corners",
                110,
                "handwriting",
                None,
                "y",
                "gray",
                "halo",
            ),
            CliScenario(
                "CLI handwriting JPG white none",
                jpg_sources[0],
                304,
                270,
                "free",
                90,
                "handwriting",
                "white",
                "n",
                "white",
                "none",
            ),
        ]
        for index, scenario in enumerate(handwriting_scenarios, start=len(scenarios)):
            handwriting_runs.append(
                run_cli_scenario(
                    scenario, output_root, session_start + timedelta(minutes=index)
                )
            )
        run_command(
            [
                sys.executable,
                "-m",
                "injection_pipeline",
                "generate-handwriting",
                "--seed",
                "42",
            ],
            "Standalone generate-handwriting",
        )

    if not args.skip_pdf:
        # Ein kurzer, sitzungsspezifischer Geschwisterpfad haelt PDF-Artefakte
        # auch bei langen Handschrift-Run-IDs unter Windows unter dem Limit.
        pdf_session_id = hashlib.sha256(
            output_root.name.encode("utf-8")
        ).hexdigest()[:8]
        pdf_output_root = (
            output_root.parent.parent
            / "pdfs"
            / pdf_session_id
        )
        pdf_runs = normal_runs + handwriting_runs
        dcm_run = next(
            run for run in pdf_runs if run.output_file.suffix.casefold() == ".dcm"
        )
        handwriting_dcm = next(
            (
                run
                for run in handwriting_runs
                if run.output_file.suffix.casefold() == ".dcm"
            ),
            dcm_run,
        )
        run_pdf_cli_check(
            "inject-pdf",
            dcm_run,
            pdf_template,
            pdf_output_root,
            "top_left",
        )
        run_pdf_cli_check(
            "compose-pdf",
            handwriting_dcm,
            pdf_template,
            pdf_output_root,
            "top_right",
        )
        run_make_pdf_checks(
            (normal_runs[0], normal_runs[1], handwriting_dcm),
            pdf_template,
            output_root,
        )

    if not args.skip_api:
        run_api_checks(dcm_sources[0], jpg_sources[0], output_root)
    if not args.skip_unit_tests:
        run_api_unit_tests()

    print(f"\nVisual-check session completed: {output_root}")


if __name__ == "__main__":
    main()
