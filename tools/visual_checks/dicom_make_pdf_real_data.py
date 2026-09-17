"""Erzeuge manuelle Visual-Checks fuer echte DICOM- und Rasterdaten."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

from injection_pipeline import (
    PdfMakeImageAnnotationInput,
    PdfMakeImageInput,
    PdfMakeTextInput,
    inject_function,
    make_pdf,
)
from injection_pipeline.loaders.dicom import DicomLoader
from injection_pipeline.runtime.options import DEFAULT_OUTPUT_DIR
from injection_pipeline.runtime.run_layout import build_run_id

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PARENT = (
    REPOSITORY_ROOT / "output" / "visual-checks" / "dicom-make-pdf-real-data"
)
ROTATIONS = (0, 90, 20)
PLACEMENT_MODE = "corners"
FONT_SIZE_PCT = 100
FONT_FAMILY = "arial"
TEXT_BACKGROUND = None
SHOW_LABEL_BOXES = "n"
HANDWRITING_INK_COLOR = "auto"
HANDWRITING_CONTRAST_MODE = "none"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pruefe make_pdf mit echten lokalen DICOM- und Rasterdateien."
    )
    parser.add_argument(
        "--cases",
        type=int,
        choices=range(1, 4),
        default=3,
        help="Anzahl der deterministischen Faelle (1 bis 3, Standard: 3).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=9100,
        help="Stabiler Basis-Seed fuer die drei Visual-Check-Faelle.",
    )
    parser.add_argument(
        "--run-timestamp",
        type=_parse_timestamp,
        default=None,
        help="Optionaler ISO-8601-Zeitstempel fuer reproduzierbare Run-IDs.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help=(
            "Ausgabeordner fuer die Visual-Check-Artefakte; ohne Angabe wird "
            "ein Zeitstempel-Unterordner verwendet."
        ),
    )
    return parser.parse_args()


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "run-timestamp muss ein ISO-8601-Zeitstempel sein."
        ) from exc


def _jpg_seed(seed: int, case_number: int, jpg_number: int) -> int:
    return seed + (case_number * 100) + jpg_number


def _case_run_ids(timestamp: datetime, seed: int, cases: int) -> list[str]:
    run_ids: list[str] = []
    for case_number in range(1, cases + 1):
        run_ids.append(
            build_run_id(
                filetype="dcm",
                run_timestamp=timestamp,
                seed=seed + case_number,
                rotation_degrees=ROTATIONS[case_number - 1],
                placement_mode=PLACEMENT_MODE,
                font_size_pct=FONT_SIZE_PCT,
                font_family=FONT_FAMILY,
                text_background=TEXT_BACKGROUND,
                show_label_boxes=SHOW_LABEL_BOXES,
                handwriting_ink_color=HANDWRITING_INK_COLOR,
                handwriting_contrast_mode=HANDWRITING_CONTRAST_MODE,
            )
        )
        for jpg_number in range(1, 3):
            run_ids.append(
                build_run_id(
                    filetype="jpg",
                    run_timestamp=timestamp,
                    seed=_jpg_seed(seed, case_number, jpg_number),
                    rotation_degrees=0,
                    placement_mode=PLACEMENT_MODE,
                    font_size_pct=FONT_SIZE_PCT,
                    font_family=FONT_FAMILY,
                    text_background=TEXT_BACKGROUND,
                    show_label_boxes=SHOW_LABEL_BOXES,
                    handwriting_ink_color=HANDWRITING_INK_COLOR,
                    handwriting_contrast_mode=HANDWRITING_CONTRAST_MODE,
                )
            )
    return run_ids


def _resolve_session_timestamp(
    timestamp: datetime | None,
    seed: int,
    cases: int,
) -> datetime:
    candidate = timestamp or datetime.now()
    output_root = REPOSITORY_ROOT / DEFAULT_OUTPUT_DIR
    if timestamp is not None:
        occupied = [
            run_id
            for run_id in _case_run_ids(candidate, seed, cases)
            if (output_root / run_id).exists()
        ]
        if occupied:
            raise ValueError(
                "Expliziter --run-timestamp ist bereits belegt fuer interne "
                f"DICOM-Run-ID(s): {', '.join(occupied)}"
            )
        return candidate

    while any(
        (output_root / run_id).exists()
        for run_id in _case_run_ids(candidate, seed, cases)
    ):
        candidate += timedelta(minutes=1)
    return candidate


def _select_supported_dicoms(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"DICOM-Verzeichnis fehlt: {directory}")
    supported: list[Path] = []
    loader = DicomLoader()
    for path in sorted(directory.rglob("*"), key=lambda item: str(item).casefold()):
        if not path.is_file() or path.suffix.casefold() != ".dcm":
            continue
        try:
            source = loader.load(path)
        except (OSError, ValueError, RuntimeError):
            continue
        if source.frame_count == 1:
            supported.append(path)
    if not supported:
        raise FileNotFoundError(
            f"Keine unterstuetzte Single-Frame-DICOM-Datei gefunden: {directory}"
        )
    return supported


def _select_jpgs(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Bildverzeichnis fehlt: {directory}")
    jpgs = sorted(
        (
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.casefold() in {".jpg", ".jpeg"}
        ),
        key=lambda item: str(item).casefold(),
    )
    if len(jpgs) < 2:
        raise FileNotFoundError(
            f"Mindestens zwei JPG/JPEG-Dateien benoetigt: {directory}"
        )
    return jpgs


def _annotation_from_ground_truth(path: Path) -> PdfMakeImageAnnotationInput:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    annotations = payload.get("box_annotations")
    if not isinstance(annotations, list) or not annotations:
        raise ValueError(f"Keine box_annotations in Ground Truth: {path}")
    return PdfMakeImageAnnotationInput.model_validate(annotations[0])


def _write_template(path: Path, case_number: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(path), pagesize=A4, invariant=1)
    canvas.setFont("Helvetica", 14)
    canvas.drawString(36, 806, f"make_pdf Visual Check – Fall {case_number}")
    canvas.setFont("Helvetica", 10)
    canvas.drawString(36, 788, "Echte DICOM-Datei, Rasterbilder und PDF-Text")
    canvas.save()


def _run_case(
    case_number: int,
    source_dicom: Path,
    jpg_paths: list[Path],
    output_root: Path,
    session_timestamp: datetime,
    session_seed: int,
) -> None:
    case_root = output_root / f"case-{case_number}"
    injection_root = case_root / "dicom-injection"
    pdf_root = case_root / "pdf"
    seed = session_seed + case_number
    rotation = ROTATIONS[case_number - 1]

    injected_path, ground_truth_path = inject_function(
        category="PatientID",
        value=f"VISUAL-CHECK-{case_number}",
        prefix="ID: ",
        suffix="",
        handwritten=False,
        documentType="dcm",
        output_dir=injection_root,
        seed=seed,
        input_path=source_dicom,
        rotation_degrees=rotation,
        run_timestamp=session_timestamp,
    )
    dicom_annotation = _annotation_from_ground_truth(ground_truth_path)
    template_path = case_root / "template.pdf"
    _write_template(template_path, case_number)

    jpg_inputs: list[PdfMakeImageInput] = []
    jpg_outputs: list[tuple[Path, Path, Path]] = []
    for jpg_number, source_jpg in enumerate(jpg_paths, start=1):
        jpg_seed = _jpg_seed(session_seed, case_number, jpg_number)
        injected_jpg, jpg_ground_truth = inject_function(
            category="JPGIdentifier",
            value=f"JPG-CHECK-{case_number}-{jpg_number}",
            prefix="JPG-ID: ",
            suffix="",
            handwritten=False,
            documentType="jpg",
            output_dir=case_root / "jpg-injection" / f"jpg-{jpg_number}",
            seed=jpg_seed,
            input_path=source_jpg,
            rotation_degrees=0,
            run_timestamp=session_timestamp,
        )
        jpg_inputs.append(
            PdfMakeImageInput(
                path=injected_jpg,
                annotations=[_annotation_from_ground_truth(jpg_ground_truth)],
            )
        )
        jpg_outputs.append((source_jpg, injected_jpg, jpg_ground_truth))

    artifacts = make_pdf(
        images=[
            PdfMakeImageInput(path=injected_path, annotations=[dicom_annotation]),
            *jpg_inputs,
        ],
        texts=[
            PdfMakeTextInput(
                category="Study",
                value=f"VISUAL-STUDY-{case_number}",
                prefix="Study: ",
                suffix="",
                handwritten=False,
            ),
            PdfMakeTextInput(
                category="Comment",
                value="Normaler PDF-Text",
                prefix="Info: ",
                suffix="",
                handwritten=False,
            ),
        ],
        pdf=template_path,
        output_dir=pdf_root,
        seed=seed,
    )
    pdf_rotations = [
        decision.placement.rotation_degrees
        for decision in artifacts.record.layout_decisions
        if decision.placement.item_type == "image"
    ]
    print(f"\n=== Fall {case_number} ===")
    print(f"Quell-DICOM:      {source_dicom}")
    print(f"Injizierte DICOM: {injected_path}")
    print(f"DICOM-Rotation:   {rotation} Grad")
    for jpg_number, (source_jpg, injected_jpg, _) in enumerate(jpg_outputs, start=1):
        print(f"Quell-JPG {jpg_number}:      {source_jpg}")
        print(f"Injiziertes JPG {jpg_number}: {injected_jpg}")
    print(f"PDF-Rotationen:   {pdf_rotations}")
    print(f"PDF:              {artifacts.clean_pdf}")
    print(f"Annotierte PDF:   {artifacts.annotated_pdf}")
    print(f"Sidecar:          {artifacts.annotation_json}")


def main() -> None:
    args = _parse_args()
    output_root = args.output_root
    session_timestamp = _resolve_session_timestamp(
        args.run_timestamp,
        args.seed,
        args.cases,
    )
    if output_root is None:
        output_root = DEFAULT_OUTPUT_PARENT / (
            "run-"
            + session_timestamp.strftime("%Y%m%d-%H%M%S-%f")
            + f"-seed{args.seed}"
        )
    if not output_root.is_absolute():
        output_root = REPOSITORY_ROOT / output_root
    dicoms = _select_supported_dicoms(REPOSITORY_ROOT / "DicomData" / "Dicom-Files")
    jpgs = _select_jpgs(REPOSITORY_ROOT / "DicomData" / "images")
    output_root.mkdir(parents=True, exist_ok=True)
    for index in range(args.cases):
        jpg_start = index * 2
        case_jpgs = [
            jpgs[(jpg_start + offset) % len(jpgs)] for offset in range(2)
        ]
        _run_case(
            index + 1,
            dicoms[index % len(dicoms)],
            case_jpgs,
            output_root,
            session_timestamp,
            args.seed,
        )


if __name__ == "__main__":
    main()
