"""Command-line interface for the DICOM/JPG injection pipeline."""

import argparse
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from injection_pipeline.config import DEFAULT_IDENTIFIER_SCHEMA_PATH
from injection_pipeline.engine.pixel_injection import ALLOWED_ROTATIONS_DEGREES
from injection_pipeline.loaders.pdf import PdfLoader
from injection_pipeline.pdf.models import PdfCompositionArtifacts
from injection_pipeline.runtime.inputs import DEFAULT_INPUT_EXTENSIONS
from injection_pipeline.runtime.options import (
    DEFAULT_HANDWRITING_ASSET_ROOT,
    DEFAULT_HANDWRITING_CHECKPOINT_PATH,
    DEFAULT_HANDWRITING_CONTAINER_IMAGE,
    DEFAULT_HANDWRITING_SOURCE_DIR,
    DEFAULT_OUTPUT_DIR,
    FONT_FAMILY_CHOICES,
    HANDWRITING_FONT_FAMILY,
    SHOW_LABEL_BOX_CHOICES,
    TEXT_BACKGROUND_CHOICES,
)
from injection_pipeline.runtime.runner import generate_handwriting_assets, run
from injection_pipeline.writers.pdf import PdfWriterAdapter


# Input: `raw_value` mit Nutzereingabe, `parameter_name` fuer Fehlermeldungen.
# Output: Geparster Integer.
# Die Funktion kapselt die CLI-Fehlermeldung und wirft bei ungueltigen Werten
# einen ValueError mit Parameterbezug.
def _parse_int(raw_value: str, parameter_name: str) -> int:
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{parameter_name} must be a whole number.") from exc


# Input: `raw_value` mit ISO-8601-Zeitstempel.
# Output: Geparster `datetime`.
# Die Funktion nutzt Pythons ISO-Parser und kapselt die Fehlermeldung fuer CLI
# und interaktiven Modus.
def _parse_run_timestamp(raw_value: str) -> datetime:
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError("--run-timestamp must be an ISO-8601 datetime.") from exc


# Input: `rotation_angle` mit angefordertem Winkel.
# Output: Validierter Winkel.
# Die Funktion akzeptiert nur die prototypeigenen Rotationen und meldet andere
# Werte mit ValueError.
def _validate_rotation_angle(rotation_angle: int) -> int:
    if rotation_angle not in ALLOWED_ROTATIONS_DEGREES:
        allowed = ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        raise ValueError(f"rotation-angle must be one of [{allowed}].")
    return rotation_angle


# Input: `font_size_pct` mit relativer Schriftgroesse.
# Output: Validierter Prozentwert.
# Die Funktion verhindert nichtpositive Schriftgroessen und gibt gueltige Werte
# unveraendert zurueck.
def _validate_font_size_pct(font_size_pct: int) -> int:
    if font_size_pct < 1:
        raise ValueError("font-size-pct must be >= 1.")
    return font_size_pct


# Input: `parameter_name`, `value` und erlaubte `choices`.
# Output: Validierter Auswahlwert.
# Die Funktion prueft interaktive und CLI-nahe Auswahlwerte und erzeugt eine
# knappe ValueError-Meldung mit allen erlaubten Optionen.
def _validate_choice(parameter_name: str, value: str, choices: tuple[str, ...]) -> str:
    if value not in choices:
        allowed = ", ".join(choices)
        raise ValueError(f"{parameter_name} must be one of: {allowed}.")
    return value


# Input: Prompt-Metadaten, optionaler Default und `parser` fuer die Eingabe.
# Output: Geparster interaktiver Wert.
# Die Funktion wiederholt die Eingabe bis ein valider Wert vorliegt und schreibt
# Validierungsfehler auf stdout.
def _prompt_for_value(
    *,
    parameter_name: str,
    purpose: str,
    expected_inputs: str,
    default_value: str | int | None,
    parser: Callable[[str], Any],
) -> Any:
    default_suffix = "" if default_value is None else f" Default: {default_value}."
    prompt = (
        f"{parameter_name}: {purpose} Expected input: "
        f"{expected_inputs}.{default_suffix}\n> "
    )
    while True:
        raw_value = input(prompt).strip()
        if raw_value == "" and default_value is not None:
            return default_value
        if raw_value == "":
            print("Please enter a value.")
            continue
        try:
            return parser(raw_value)
        except ValueError as exc:
            print(f"Invalid {parameter_name}: {exc}")


# Input: `default_value` mit voreingestelltem Hintergrundmodus.
# Output: `white` oder `None`.
# Die Funktion fragt interaktiv nach einem weissen Texthintergrund und wiederholt
# die Eingabe bei ungueltigen Antworten.
def _prompt_for_text_background(default_value: str | None) -> str | None:
    default_label = "n" if default_value is None else "y"
    prompt = (
        "text-background: Choose whether visible injected text should get a white "
        "background box for readability. Expected input: y or n. "
        f"Default: {default_label} ({default_value}).\n> "
    )
    while True:
        raw_value = input(prompt).strip().lower()
        if raw_value == "":
            return default_value
        if raw_value == "y":
            return "white"
        if raw_value == "n":
            return None
        print("Invalid text-background: enter 'y' for white or 'n' for no background.")


# Input: `default_value` mit voreingestellter Ja/Nein-Auswahl.
# Output: `y` oder `n`.
# Die Funktion fragt interaktiv, ob generische Label-Boxen angezeigt werden, und
# akzeptiert nur die prototypeigenen Auswahlwerte.
def _prompt_for_show_label_boxes(default_value: str) -> str:
    prompt = (
        "show-label-boxes: Choose whether schema-defined generic prefixes "
        "should be outlined in preview_annotated.png. Expected input: y or n. "
        f"Default: {default_value}.\n> "
    )
    while True:
        raw_value = input(prompt).strip().lower()
        if raw_value == "":
            return default_value
        if raw_value in SHOW_LABEL_BOX_CHOICES:
            return raw_value
        print("Invalid show-label-boxes: enter 'y' or 'n'.")


# Input: Keine Parameter.
# Output: Expliziter Eingabepfad als String oder `None` fuer Zufallsauswahl.
# Die Funktion fragt im interaktiven Modus zuerst nach Zufallsauswahl und
# validiert bei manueller Auswahl, dass der angegebene Pfad existiert.
def _prompt_for_input_path() -> str | None:
    prompt = (
        "input: Use a random local DICOM/JPG input file? Expected input: y or n. "
        "Default: y.\n> "
    )
    while True:
        raw_value = input(prompt).strip().lower()
        if raw_value in ("", "y"):
            return None
        if raw_value == "n":
            while True:
                raw_path = input(
                    "input-path: Enter path to a .dcm, .jpg, or .jpeg file.\n> "
                ).strip()
                if raw_path == "":
                    print("Invalid input-path: please enter a path.")
                    continue
                input_path = Path(raw_path)
                if not input_path.exists():
                    print(f"Invalid input-path: file not found: {input_path}")
                    continue
                if input_path.suffix.lower() not in DEFAULT_INPUT_EXTENSIONS:
                    print(
                        "Invalid input-path: expected one of "
                        f"{', '.join(DEFAULT_INPUT_EXTENSIONS)}."
                    )
                    continue
                return raw_path
        print("Invalid input: enter 'y' for random input or 'n' to provide a path.")


# Input: `default_path` mit voreingestelltem Identifier-Schema.
# Output: Schema-Pfad als String.
# Die Funktion fragt den externen Taxonomiepfad ab und validiert die Existenz
# vor dem Pipeline-Start.
def _prompt_for_identifier_schema_path(default_path: Path) -> str:
    prompt = (
        "identifier-schema: Path to identifier schema JSON. Expected input: "
        f"a JSON file path. Default: {default_path}.\n> "
    )
    while True:
        raw_value = input(prompt).strip()
        schema_path = default_path if raw_value == "" else Path(raw_value)
        if schema_path.exists() and schema_path.is_file():
            return str(schema_path)
        print(f"Invalid identifier-schema: file not found: {schema_path}")


# Input: Keine Parameter.
# Output: Optionaler Run-Zeitstempel fuer reproduzierbare Run-IDs.
# Die Funktion erlaubt leere Eingaben als aktuelle Uhrzeit und validiert
# nichtleere Werte als ISO-8601-Datetime.
def _prompt_for_run_timestamp() -> datetime | None:
    prompt = (
        "run-timestamp: Optional ISO-8601 timestamp for the run ID. "
        "Expected input: YYYY-MM-DDTHH:MM:SS or blank for current time.\n> "
    )
    while True:
        raw_value = input(prompt).strip()
        if raw_value == "":
            return None
        try:
            return _parse_run_timestamp(raw_value)
        except ValueError as exc:
            print(f"Invalid run-timestamp: {exc}")


# Input: Keine Parameter.
# Output: argparse-Namespace mit interaktiv gesammelten Laufparametern.
# Die Funktion fuehrt den parametergefuehrten Prompt-Modus aus und validiert
# Einzelwerte direkt waehrend der Eingabe.
def _collect_interactive_args() -> argparse.Namespace:
    print("No CLI arguments were provided. Starting interactive parameter setup.\n")
    seed = _prompt_for_value(
        parameter_name="seed",
        purpose=(
            "Seed for reproducible synthetic identity generation and placement "
            "randomness."
        ),
        expected_inputs="an integer",
        default_value=42,
        parser=lambda raw: _parse_int(raw, "seed"),
    )
    font_family = _prompt_for_value(
        parameter_name="font-family",
        purpose=(
            "Renderer choice for visible injected text; 'handwriting' uses "
            "generated asset overlays."
        ),
        expected_inputs=f"one of {', '.join(FONT_FAMILY_CHOICES)}",
        default_value="arial",
        parser=lambda raw: _validate_choice("font-family", raw, FONT_FAMILY_CHOICES),
    )
    input_path = _prompt_for_input_path()
    identifier_schema = _prompt_for_identifier_schema_path(
        DEFAULT_IDENTIFIER_SCHEMA_PATH
    )
    rotation_angle = _prompt_for_value(
        parameter_name="rotation-angle",
        purpose="Rotation angle in degrees for visible injected text.",
        expected_inputs=(
            "one of " + ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        ),
        default_value=0,
        parser=lambda raw: _validate_rotation_angle(_parse_int(raw, "rotation-angle")),
    )
    font_size_pct = _prompt_for_value(
        parameter_name="font-size-pct",
        purpose=(
            "Font size for visible injected text as a percentage of the "
            "prototype default."
        ),
        expected_inputs="an integer >= 1",
        default_value=100,
        parser=lambda raw: _validate_font_size_pct(_parse_int(raw, "font-size-pct")),
    )
    placement_mode = _prompt_for_value(
        parameter_name="placement-mode",
        purpose="Placement strategy for visible injected text.",
        expected_inputs="free or corners",
        default_value="corners",
        parser=lambda raw: _validate_choice("placement-mode", raw, ("free", "corners")),
    )
    text_background = _prompt_for_text_background(default_value=None)
    show_label_boxes = _prompt_for_show_label_boxes(default_value="n")
    run_timestamp = _prompt_for_run_timestamp()
    return argparse.Namespace(
        seed=seed,
        input=input_path,
        output_dir=str(DEFAULT_OUTPUT_DIR),
        identifier_schema=identifier_schema,
        handwriting_manifest=None,
        handwriting_asset=[],
        handwriting_asset_root=str(DEFAULT_HANDWRITING_ASSET_ROOT),
        handwriting_checkpoint=str(DEFAULT_HANDWRITING_CHECKPOINT_PATH),
        handwriting_checkpoint_sha256=None,
        handwriting_options_json=None,
        handwriting_source_dir=str(DEFAULT_HANDWRITING_SOURCE_DIR),
        handwriting_upstream_commit=None,
        handwriting_runtime_command=None,
        handwriting_container_image=DEFAULT_HANDWRITING_CONTAINER_IMAGE,
        handwriting_generator_command=None,
        rotation_angle=rotation_angle,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
        show_label_boxes=show_label_boxes,
        run_timestamp=run_timestamp,
    )


# Input: `args` mit geparsten CLI- oder interaktiven Parametern.
# Output: Keine Rueckgabe.
# Die Funktion validiert die globalen Grenzwerte vor dem Lauf, parst optionale
# Timestamp-Strings und wirft bei ungueltigen Optionen ValueError.
def _validate_args(args: argparse.Namespace) -> None:
    if not Path(args.identifier_schema).is_file():
        raise ValueError(
            f"--identifier-schema must point to a JSON file: {args.identifier_schema}"
        )
    if args.rotation_angle not in ALLOWED_ROTATIONS_DEGREES:
        allowed = ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        raise ValueError(
            f"--rotation-angle must be one of [{allowed}], got {args.rotation_angle}."
        )
    if args.font_size_pct < 1:
        raise ValueError("--font-size-pct must be >= 1.")
    if args.handwriting_asset and args.handwriting_manifest is None:
        raise ValueError("--handwriting-asset requires --handwriting-manifest.")
    if (
        args.font_family == HANDWRITING_FONT_FAMILY
        and args.handwriting_manifest is not None
        and not args.handwriting_asset
    ):
        raise ValueError(
            "--font-family handwriting with --handwriting-manifest requires "
            "--handwriting-asset mappings for every visible field."
        )
    if not hasattr(args, "run_timestamp"):
        args.run_timestamp = None
    if isinstance(args.run_timestamp, str):
        args.run_timestamp = _parse_run_timestamp(args.run_timestamp)


# Input: `args` mit Standalone-Handschriftargumenten.
# Output: Keine Rueckgabe.
# Die Funktion validiert nur die schematischen Eingaben fuer die Asset-Erzeugung;
# Checkpoint- und Runtime-Fehler bleiben harte Provider-Fehler beim Aufruf.
def _validate_generate_handwriting_args(args: argparse.Namespace) -> None:
    if not Path(args.identifier_schema).is_file():
        raise ValueError(
            f"--identifier-schema must point to a JSON file: {args.identifier_schema}"
        )


# Input: CLI-Argumente fuer PDF, DICOM und DICOM-Ground-Truth.
# Output: Keine Rueckgabe; schreibt PDF- und Sidecar-Artefakte.
# Die Funktion verbindet den PDF-Loader mit dem PDF-Writer und laesst die
# bestehenden DICOM/JPG-Argumente und den normalen Runner unveraendert.
def _run_pdf_injection(args: argparse.Namespace) -> PdfCompositionArtifacts:
    template = PdfLoader().load(Path(args.input_pdf))
    artifacts = PdfWriterAdapter().write(
        template=template,
        dicom_path=Path(args.input_dicom),
        annotation_path=Path(args.dicom_annotation),
        output_root=Path(args.output_dir),
        slot=args.slot,
        page_index=args.page_index,
    )
    print(
        f"PDF written to {artifacts.clean_pdf}\n"
        f"Annotated PDF written to {artifacts.annotated_pdf}\n"
        f"PDF annotations written to {artifacts.annotation_json}"
    )
    return artifacts


# Input: Keine Parameter.
# Output: PDF-CLI-Parser fuer den separaten PDF-Aufruf.
# Die Funktion kapselt die Subcommand-Argumente, damit der etablierte
# DICOM/JPG-Aufruf rueckwaertskompatibel bleibt.
def _build_pdf_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inject an already injected DICOM image into a PDF template."
    )
    parser.add_argument("--input-pdf", required=True)
    parser.add_argument("--input-dicom", required=True)
    parser.add_argument("--dicom-annotation", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--slot", choices=["top_left", "top_right"], default="top_left")
    parser.add_argument("--page-index", type=int, default=0)
    return parser


# Input: `parser` fuer normale oder Standalone-Handschrift-CLI.
# Output: Keine Rueckgabe; erweitert den Parser.
# Die Funktion haelt die Provider-Konfiguration fuer Runner und Generatorbefehl
# identisch und setzt repo-relative Defaults fuer lokale Artefakte.
def _add_handwriting_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--handwriting-asset-root",
        type=str,
        default=str(DEFAULT_HANDWRITING_ASSET_ROOT),
        help="Root directory for deterministic handwriting cache bundles.",
    )
    parser.add_argument(
        "--handwriting-checkpoint",
        type=str,
        default=str(DEFAULT_HANDWRITING_CHECKPOINT_PATH),
        help="ScrabbleGAN generator checkpoint used by the handwriting provider.",
    )
    parser.add_argument(
        "--handwriting-checkpoint-sha256",
        type=str,
        default=None,
        help=(
            "Expected checkpoint SHA-256. When omitted, the local checkpoint is "
            "hashed before provider execution."
        ),
    )
    parser.add_argument(
        "--handwriting-options-json",
        type=str,
        default=None,
        help=(
            "Optional ScrabbleGAN options sidecar. Defaults to options/test_opt/"
            "train_opt next to the checkpoint."
        ),
    )
    parser.add_argument(
        "--handwriting-source-dir",
        type=str,
        default=str(DEFAULT_HANDWRITING_SOURCE_DIR),
        help="Mounted ScrabbleGAN source directory for the isolated generator.",
    )
    parser.add_argument(
        "--handwriting-upstream-commit",
        type=str,
        default=None,
        help="Pinned ScrabbleGAN upstream commit; defaults to source .git_commit.",
    )
    parser.add_argument(
        "--handwriting-runtime-command",
        type=str,
        default=None,
        help=(
            "Optional host-side batch command override. By default the provider "
            "starts the configured Docker image."
        ),
    )
    parser.add_argument(
        "--handwriting-container-image",
        type=str,
        default=DEFAULT_HANDWRITING_CONTAINER_IMAGE,
        help="Docker image used for handwriting generation on cache misses.",
    )
    parser.add_argument(
        "--handwriting-generator-command",
        type=str,
        default=None,
        help=(
            "Optional single-text generator command template passed to the batch tool."
        ),
    )


# Input: Keine Parameter.
# Output: Parser fuer `generate-handwriting`.
# Die Funktion definiert den Standalone-Durchstich ohne Dokumentinjektion.
def _build_generate_handwriting_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate handwriting assets for the seeded synthetic identity."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--identifier-schema",
        type=str,
        default=str(DEFAULT_IDENTIFIER_SCHEMA_PATH),
        help="Path to the external identifier schema JSON.",
    )
    _add_handwriting_provider_args(parser)
    return parser


# Input: Keine Parameter.
# Output: Keine Rueckgabe.
# Die Funktion parst CLI-Argumente oder startet den interaktiven Modus und
# delegiert danach an den Runner.
def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"inject-pdf", "compose-pdf"}:
        pdf_args = _build_pdf_parser().parse_args(sys.argv[2:])
        _run_pdf_injection(pdf_args)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "generate-handwriting":
        handwriting_args = _build_generate_handwriting_parser().parse_args(sys.argv[2:])
        _validate_generate_handwriting_args(handwriting_args)
        generate_handwriting_assets(handwriting_args)
        return
    parser = argparse.ArgumentParser(description="DICOM injection prototype")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--input", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--identifier-schema",
        type=str,
        default=str(DEFAULT_IDENTIFIER_SCHEMA_PATH),
        help="Path to the external identifier schema JSON.",
    )
    parser.add_argument("--rotation-angle", type=int, default=0)
    parser.add_argument(
        "--font-size-pct",
        type=int,
        default=100,
        metavar="PERCENT",
        help=(
            "Font size as a percentage of the default size "
            "(100 = default, 50 = half size). Must be >= 1."
        ),
    )
    parser.add_argument(
        "--placement-mode",
        type=str,
        default="corners",
        choices=["free", "corners"],
        help=(
            "Placement mode: 'corners' picks a random corner, "
            "'free' picks a fully random position."
        ),
    )
    parser.add_argument(
        "--font-family",
        type=str,
        default="arial",
        choices=list(FONT_FAMILY_CHOICES),
        help=(
            "Renderer/font choice. Use 'handwriting' for generated handwriting "
            "asset overlays."
        ),
    )
    parser.add_argument(
        "--text-background",
        type=str,
        default=None,
        choices=list(TEXT_BACKGROUND_CHOICES),
        help="Optional visible text background. Currently only 'white' is supported.",
    )
    parser.add_argument(
        "--show-label-boxes",
        type=str,
        default="n",
        choices=list(SHOW_LABEL_BOX_CHOICES),
        help=(
            "Show schema-defined generic label-prefix boxes in preview_annotated.png."
        ),
    )
    parser.add_argument(
        "--run-timestamp",
        type=_parse_run_timestamp,
        default=None,
        metavar="ISO_DATETIME",
        help="Optional ISO-8601 timestamp used in the run ID.",
    )
    parser.add_argument(
        "--handwriting-manifest",
        type=str,
        default=None,
        help="Optional handwriting asset manifest for manifest-controlled overlays.",
    )
    parser.add_argument(
        "--handwriting-asset",
        action="append",
        default=[],
        metavar="FIELD=ASSET_ID",
        help="Map an identity schema field to a handwriting asset ID.",
    )
    _add_handwriting_provider_args(parser)
    args = _collect_interactive_args() if len(sys.argv) == 1 else parser.parse_args()
    _validate_args(args)
    run(args, now=args.run_timestamp)


if __name__ == "__main__":
    main()
