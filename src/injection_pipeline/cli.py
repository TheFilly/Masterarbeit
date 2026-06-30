"""Command-line interface for the DICOM/JPG injection pipeline."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from injection_pipeline.engine.pixel_injection import ALLOWED_ROTATIONS_DEGREES
from injection_pipeline.runner import (
    _DEFAULT_INPUT_EXTENSIONS,
    _DEFAULT_OUTPUT_DIR,
    _FONT_FAMILY_CHOICES,
    _SHOW_LABEL_BOX_CHOICES,
    _TEXT_BACKGROUND_CHOICES,
    _select_default_input_path,
    run,
)
# Input: `raw_value` mit Nutzereingabe, `parameter_name` fuer Fehlermeldungen.
# Output: Geparster Integer.
# Die Funktion kapselt die CLI-Fehlermeldung und wirft bei ungueltigen Werten
# einen ValueError mit Parameterbezug.
def _parse_int(raw_value: str, parameter_name: str) -> int:
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{parameter_name} must be a whole number.") from exc


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
        "show-label-boxes: Choose whether generic label prefixes such as "
        "SYNTH- or ACC- "
        "should be outlined in preview_annotated.png. Expected input: y or n. "
        f"Default: {default_value}.\n> "
    )
    while True:
        raw_value = input(prompt).strip().lower()
        if raw_value == "":
            return default_value
        if raw_value in _SHOW_LABEL_BOX_CHOICES:
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
                if input_path.suffix.lower() not in _DEFAULT_INPUT_EXTENSIONS:
                    print(
                        "Invalid input-path: expected one of "
                        f"{', '.join(_DEFAULT_INPUT_EXTENSIONS)}."
                    )
                    continue
                return raw_path
        print("Invalid input: enter 'y' for random input or 'n' to provide a path.")


# Input: Keine Parameter.
# Output: argparse-Namespace mit interaktiv gesammelten Laufparametern.
# Die Funktion fuehrt den parametergefuehrten Prompt-Modus aus und validiert
# Einzelwerte direkt waehrend der Eingabe.
def _collect_interactive_args() -> argparse.Namespace:
    print("No CLI arguments were provided. Starting interactive parameter setup.\n")
    input_path = _prompt_for_input_path()
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
        parser=lambda raw: _validate_choice(
            "placement-mode", raw, ("free", "corners")
        ),
    )
    font_family = _prompt_for_value(
        parameter_name="font-family",
        purpose="Prototype font family used for visible injected text rendering.",
        expected_inputs=f"one of {', '.join(_FONT_FAMILY_CHOICES)}",
        default_value="arial",
        parser=lambda raw: _validate_choice("font-family", raw, _FONT_FAMILY_CHOICES),
    )
    text_background = _prompt_for_text_background(default_value=None)
    show_label_boxes = _prompt_for_show_label_boxes(default_value="n")
    return argparse.Namespace(
        seed=seed,
        input=input_path,
        output_dir=str(_DEFAULT_OUTPUT_DIR),
        handwriting_manifest=None,
        handwriting_asset=[],
        rotation_angle=rotation_angle,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
        show_label_boxes=show_label_boxes,
    )


# Input: `args` mit geparsten CLI- oder interaktiven Parametern.
# Output: Keine Rueckgabe.
# Die Funktion validiert die globalen Grenzwerte vor dem Lauf und wirft bei
# ungueltigen Optionen ValueError.
def _validate_args(args: argparse.Namespace) -> None:
    if args.rotation_angle not in ALLOWED_ROTATIONS_DEGREES:
        allowed = ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        raise ValueError(
            f"--rotation-angle must be one of [{allowed}], got {args.rotation_angle}."
        )
    if args.font_size_pct < 1:
        raise ValueError("--font-size-pct must be >= 1.")
    if args.handwriting_asset and args.handwriting_manifest is None:
        raise ValueError("--handwriting-asset requires --handwriting-manifest.")



# Entry point for the DICOM/JPG injection pipeline.
def main() -> None:
    parser = argparse.ArgumentParser(description="DICOM injection prototype")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--input", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=str(_DEFAULT_OUTPUT_DIR))
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
        choices=list(_FONT_FAMILY_CHOICES),
        help=(
            "Prototype font family choice. Only fixed Windows-style choices "
            "are supported."
        ),
    )
    parser.add_argument(
        "--text-background",
        type=str,
        default=None,
        choices=list(_TEXT_BACKGROUND_CHOICES),
        help="Optional visible text background. Currently only 'white' is supported.",
    )
    parser.add_argument(
        "--show-label-boxes",
        type=str,
        default="n",
        choices=list(_SHOW_LABEL_BOX_CHOICES),
        help=(
            "Show generic label-prefix boxes such as SYNTH- or ACC- in "
            "preview_annotated.png."
        ),
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
        help="Map an identity field such as patient_name to a handwriting asset ID.",
    )
    args = _collect_interactive_args() if len(sys.argv) == 1 else parser.parse_args()
    _validate_args(args)
    run(args)


if __name__ == "__main__":
    main()