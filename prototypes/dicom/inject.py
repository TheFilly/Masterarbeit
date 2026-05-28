"""Prototype orchestrator: inject a synthetic identity into a DICOM file."""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dicom_writer import inject_tags, load_dicom, save_dicom, summarize_dicom
from identity import generate_identity
from PIL import Image

from pixel_injection import (
    ALLOWED_ROTATIONS_DEGREES,
    inject_visible_text,
    inject_visible_text_into_image,
)
from view import create_annotated_preview

_DEFAULT_INPUT = (
    "DycomData/Anonymization/original_data/"
    "patient_10080695_23273240/echo/91180014_0001.dcm"
)
_DEFAULT_INTERACTIVE_INPUT = "DycomData/images/faces-00a0d634ad200ced.jpg"

_TAG_META: dict[str, tuple[str, str]] = {
    "PatientName": ("0010,0010", "PN"),
    "PatientID": ("0010,0020", "LO"),
    "PatientBirthDate": ("0010,0030", "DA"),
    "PatientSex": ("0010,0040", "CS"),
    "AccessionNumber": ("0008,0050", "SH"),
}

_IDENTITY_FIELD_MAP: dict[str, str] = {
    "PatientName": "patient_name",
    "PatientID": "patient_id",
    "PatientBirthDate": "patient_birth_date",
    "PatientSex": "patient_sex",
    "AccessionNumber": "accession_number",
}

_VISIBLE_PIXEL_KEYWORDS: tuple[str, ...] = (
    "PatientName",
    "PatientID",
    "AccessionNumber",
)
_TAG_ONLY_KEYWORDS: tuple[str, ...] = ("PatientBirthDate", "PatientSex")
_SCHEMA_VERSION = "0.2.0-prototype"
_FONT_FAMILY_CHOICES: tuple[str, ...] = ("arial", "calibri", "tahoma", "consolas")
_TEXT_BACKGROUND_CHOICES: tuple[str, ...] = ("white",)
_SHOW_LABEL_BOX_CHOICES: tuple[str, ...] = ("y", "n")


def _derive_example_type(input_path: Path) -> str:
    for part in reversed(input_path.parts[:-1]):
        normalized = re.sub(r"[^a-z0-9]+", "-", part.lower()).strip("-")
        if normalized and normalized not in {"original-data", "anonymization"}:
            return normalized
    return "dicom"


def _detect_input_type(input_path: Path) -> str:
    suffix = input_path.suffix.lower()
    if suffix == ".dcm":
        return "dcm"
    if suffix in {".jpg", ".jpeg"}:
        return "jpg"
    raise ValueError("Unsupported input format. Expected .dcm, .jpg, or .jpeg.")


def _build_run_id(
    *,
    filetype: str,
    run_timestamp: datetime,
    seed: int,
    rotation_degrees: int,
    placement_mode: str,
    font_size_pct: int,
    font_family: str,
    text_background: str | None,
) -> str:
    text_background_label = text_background or "none"
    return (
        f"{filetype}-{run_timestamp.strftime('%d%m%Y')}-{run_timestamp.strftime('%H%M')}"
        f"-seed{seed:04d}-angle{rotation_degrees:03d}-{placement_mode}"
        f"-fs{font_size_pct}-{font_family}-{text_background_label}"
    )


def _build_output_paths(
    output_root: Path,
    run_id: str,
    source_stem: str,
    document_type: str,
) -> dict[str, Path]:
    run_dir = output_root / run_id
    output_suffix = ".dcm" if document_type == "dcm" else ".jpg"
    return {
        "run_dir": run_dir,
        "output_file": run_dir / f"{source_stem}_injected{output_suffix}",
        "output_json": run_dir / "ground_truth.json",
        "output_manifest": run_dir / "run_manifest.json",
        "preview_file": run_dir / "preview.png",
        "annotated_preview_file": run_dir / "preview_annotated.png",
    }


def _build_tag_map(identity: dict[str, str]) -> dict[str, str]:
    return {
        "PatientName": identity["patient_name"],
        "PatientID": identity["patient_id"],
        "PatientBirthDate": identity["patient_birth_date"],
        "PatientSex": identity["patient_sex"],
        "AccessionNumber": identity["accession_number"],
    }


def _build_tag_annotations(
    *,
    tag_map: dict[str, str],
    identity: dict[str, str],
    input_path: Path,
    output_path: Path,
) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for keyword, injected_value in tag_map.items():
        tag_address, dicom_vr = _TAG_META[keyword]
        identity_field = _IDENTITY_FIELD_MAP[keyword]
        annotations.append(
            {
                "label": keyword,
                "tag_address": tag_address,
                "tag_keyword": keyword,
                "dicom_vr": dicom_vr,
                "value": injected_value,
                "identity_field": identity_field,
                "identity_id": identity["patient_id"],
                "source_file": str(input_path),
                "output_file": str(output_path),
            }
        )
    return annotations


def _build_visible_render_plan(
    *,
    tag_map: dict[str, str],
    rotation_degrees: int,
    placement_mode: str,
) -> list[dict[str, Any]]:
    render_plan: list[dict[str, Any]] = []
    for index, keyword in enumerate(_VISIBLE_PIXEL_KEYWORDS):
        render_text, text_segments = _build_text_segments(keyword, tag_map[keyword])
        render_plan.append(
            {
                "label": keyword,
                "text": render_text,
                "text_segments": text_segments,
                "identity_field": _IDENTITY_FIELD_MAP[keyword],
                "region": placement_mode,
                "rotation_degrees": rotation_degrees,
                "line_index": index,
            }
        )
    return render_plan


def _build_text_segments(keyword: str, value: str) -> tuple[str, list[dict[str, str]]]:
    if keyword == "PatientID" and value.startswith("SYNTH-"):
        return value, [
            {"kind": "generic", "text": "SYNTH-"},
            {"kind": "pii", "text": value.removeprefix("SYNTH-")},
        ]
    if keyword == "AccessionNumber" and value.startswith("ACC-"):
        return value, [
            {"kind": "generic", "text": "ACC-"},
            {"kind": "pii", "text": value.removeprefix("ACC-")},
        ]
    return value, [{"kind": "pii", "text": value}]


def _run_pixel_injection(
    *,
    ds: Any,
    visible_injections: list[dict[str, Any]],
    output_path: Path,
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    example_type: str,
    font_size_pct: int,
    placement_mode: str,
    font_family: str,
    text_background: str | None,
) -> tuple[Any, dict[str, Any]]:
    result = inject_visible_text(
        ds=ds,
        visible_injections=visible_injections,
        output_path=output_path,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        example_type=example_type,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
    )
    return result.get("dataset", ds), {
        "status": result.get("status", "rendered"),
        "renderer_name": "pixel_injection.inject_visible_text",
        "box_annotations": result.get("box_annotations", []),
        "preview_file": result.get("preview_file"),
        "render_metadata": result.get("render_metadata", {}),
    }


def _run_jpg_pixel_injection(
    *,
    image: Image.Image,
    visible_injections: list[dict[str, Any]],
    preview_path: Path,
    seed: int,
    rotation_degrees: int,
    example_type: str,
    font_size_pct: int,
    placement_mode: str,
    font_family: str,
    text_background: str | None,
) -> tuple[Image.Image, dict[str, Any]]:
    del example_type
    result = inject_visible_text_into_image(
        image=image,
        visible_injections=visible_injections,
        preview_path=preview_path,
        seed=seed,
        rotation_degrees=rotation_degrees,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
    )
    return result["image"], {
        "status": result.get("status", "rendered"),
        "renderer_name": "pixel_injection.inject_visible_text_into_image",
        "box_annotations": result.get("box_annotations", []),
        "preview_file": result.get("preview_file"),
        "render_metadata": result.get("render_metadata", {}),
    }


def _build_record(
    *,
    run_id: str,
    seed: int,
    rotation_degrees: int,
    placement_mode: str,
    font_size_pct: int,
    font_family: str,
    text_background: str | None,
    document_type: str,
    example_type: str,
    input_path: Path,
    output_path: Path,
    preview_path: Path,
    annotated_preview_path: Path,
    identity: dict[str, str],
    source_dicom_context: dict[str, Any] | None,
    output_dicom_context: dict[str, Any] | None,
    tag_annotations: list[dict[str, Any]],
    box_annotations: list[dict[str, Any]],
    visible_render_plan: list[dict[str, Any]],
    pixel_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "record_type": f"{document_type}_injection_run",
        "run_id": run_id,
        "seed": seed,
        "rotation_degrees": rotation_degrees,
        "source_file": str(input_path),
        "output_file": str(output_path),
        "preview_file": pixel_result["preview_file"] or str(preview_path),
        "annotated_preview_file": str(annotated_preview_path),
        "document_type": document_type,
        "example_type": example_type,
        "modality": (
            output_dicom_context["modality"] if output_dicom_context is not None else None
        ),
        "identity_id": identity["patient_id"],
        "span_annotations": [],
        "box_annotations": box_annotations,
        "dicom_tag_annotations": tag_annotations,
        "run_metadata": {
            "rotation_degrees": rotation_degrees,
            "placement_mode": placement_mode,
            "pixel_injection_status": pixel_result["status"],
            "pixel_renderer": pixel_result["renderer_name"],
            "visible_identity_fields": [
                _IDENTITY_FIELD_MAP[keyword] for keyword in _VISIBLE_PIXEL_KEYWORDS
            ],
            "tag_only_identity_fields": [
                _IDENTITY_FIELD_MAP[keyword] for keyword in _TAG_ONLY_KEYWORDS
            ],
        },
        "render_metadata": {
            "rotation_degrees": rotation_degrees,
            "placement_mode": placement_mode,
            "font_size_pct": font_size_pct,
            "font_family": font_family,
            "text_background": text_background,
            "visible_render_plan": visible_render_plan,
            **pixel_result["render_metadata"],
        },
    }


def _attach_dicom_contexts(
    record: dict[str, Any],
    *,
    source_dicom_context: dict[str, Any] | None,
    output_dicom_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if source_dicom_context is not None and output_dicom_context is not None:
        record["run_metadata"]["source_dicom_context"] = source_dicom_context
        record["run_metadata"]["output_dicom_context"] = output_dicom_context
    return record


def _parse_int(raw_value: str, parameter_name: str) -> int:
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{parameter_name} must be a whole number.") from exc


def _validate_rotation_angle(rotation_angle: int) -> int:
    if rotation_angle not in ALLOWED_ROTATIONS_DEGREES:
        allowed = ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        raise ValueError(f"rotation-angle must be one of [{allowed}].")
    return rotation_angle


def _validate_font_size_pct(font_size_pct: int) -> int:
    if font_size_pct < 1:
        raise ValueError("font-size-pct must be >= 1.")
    return font_size_pct


def _validate_choice(parameter_name: str, value: str, choices: tuple[str, ...]) -> str:
    if value not in choices:
        allowed = ", ".join(choices)
        raise ValueError(f"{parameter_name} must be one of: {allowed}.")
    return value


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
        f"{parameter_name}: {purpose} Expected input: {expected_inputs}.{default_suffix}\n> "
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


def _prompt_for_show_label_boxes(default_value: str) -> str:
    prompt = (
        "show-label-boxes: Choose whether generic label prefixes such as SYNTH- or ACC- "
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


def _collect_interactive_args() -> argparse.Namespace:
    print("No CLI arguments were provided. Starting interactive parameter setup.\n")
    seed = _prompt_for_value(
        parameter_name="seed",
        purpose="Seed for reproducible synthetic identity generation and placement randomness.",
        expected_inputs="an integer",
        default_value=42,
        parser=lambda raw: _parse_int(raw, "seed"),
    )
    input_path = _prompt_for_value(
        parameter_name="input",
        purpose="Path to the source DICOM or JPG file that will be loaded and injected.",
        expected_inputs="a valid file path",
        default_value=_DEFAULT_INTERACTIVE_INPUT,
        parser=lambda raw: raw,
    )
    output_dir = _prompt_for_value(
        parameter_name="output-dir",
        purpose="Directory where the injected DICOM, previews, and JSON outputs will be written.",
        expected_inputs="a directory path",
        default_value="prototypes/dicom/output",
        parser=lambda raw: raw,
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
        purpose="Font size for visible injected text as a percentage of the prototype default.",
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
        output_dir=output_dir,
        rotation_angle=rotation_angle,
        font_size_pct=font_size_pct,
        placement_mode=placement_mode,
        font_family=font_family,
        text_background=text_background,
        show_label_boxes=show_label_boxes,
    )


def _validate_args(args: argparse.Namespace) -> None:
    if args.rotation_angle not in ALLOWED_ROTATIONS_DEGREES:
        allowed = ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        raise ValueError(
            f"--rotation-angle must be one of [{allowed}], got {args.rotation_angle}."
        )
    if args.font_size_pct < 1:
        raise ValueError("--font-size-pct must be >= 1.")


def main() -> None:
    """Entry point for the DICOM injection prototype."""
    parser = argparse.ArgumentParser(description="DICOM injection prototype")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--input", type=str, default=_DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=str, default="prototypes/dicom/output")
    parser.add_argument("--rotation-angle", type=int, default=0)
    parser.add_argument(
        "--font-size-pct",
        type=int,
        default=100,
        metavar="PERCENT",
        help="Font size as a percentage of the default size (100 = default, 50 = half size). Must be >= 1.",
    )
    parser.add_argument(
        "--placement-mode",
        type=str,
        default="corners",
        choices=["free", "corners"],
        help="Placement mode: 'corners' picks a random corner, 'free' picks a fully random position.",
    )
    parser.add_argument(
        "--font-family",
        type=str,
        default="arial",
        choices=list(_FONT_FAMILY_CHOICES),
        help="Prototype font family choice. Only fixed Windows-style choices are supported.",
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
        help="Show generic label-prefix boxes such as SYNTH- or ACC- in preview_annotated.png.",
    )
    args = _collect_interactive_args() if len(sys.argv) == 1 else parser.parse_args()
    _validate_args(args)

    input_path = Path(args.input)
    output_root = Path(args.output_dir)
    document_type = _detect_input_type(input_path)
    example_type = _derive_example_type(input_path)
    run_id = _build_run_id(
        filetype=document_type,
        run_timestamp=datetime.now(),
        seed=args.seed,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
        font_size_pct=args.font_size_pct,
        font_family=args.font_family,
        text_background=args.text_background,
    )
    output_paths = _build_output_paths(
        output_root,
        run_id,
        input_path.stem,
        document_type,
    )

    identity_a = generate_identity(args.seed)
    identity_b = generate_identity(args.seed + 1)

    tag_map = _build_tag_map(identity_a)
    visible_render_plan = _build_visible_render_plan(
        tag_map=tag_map,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
    )
    output_paths["run_dir"].mkdir(parents=True, exist_ok=True)
    source_dicom_context: dict[str, Any] | None = None
    output_dicom_context: dict[str, Any] | None = None

    # DICOM keeps the tag-injection path; JPG reuses only the visible-rendering path.
    if document_type == "dcm":
        ds = load_dicom(input_path)
        source_dicom_context = summarize_dicom(ds)
        ds = inject_tags(ds, tag_map)
        ds, pixel_result = _run_pixel_injection(
            ds=ds,
            visible_injections=visible_render_plan,
            output_path=output_paths["output_file"],
            preview_path=output_paths["preview_file"],
            seed=args.seed,
            rotation_degrees=args.rotation_angle,
            example_type=example_type,
            font_size_pct=args.font_size_pct,
            placement_mode=args.placement_mode,
            font_family=args.font_family,
            text_background=args.text_background,
        )
        output_dicom_context = summarize_dicom(ds)
        save_dicom(ds, output_paths["output_file"])
        tag_annotations = _build_tag_annotations(
            tag_map=tag_map,
            identity=identity_a,
            input_path=input_path,
            output_path=output_paths["output_file"],
        )
    else:
        image = Image.open(input_path).convert("RGB")
        image, pixel_result = _run_jpg_pixel_injection(
            image=image,
            visible_injections=visible_render_plan,
            preview_path=output_paths["preview_file"],
            seed=args.seed,
            rotation_degrees=args.rotation_angle,
            example_type=example_type,
            font_size_pct=args.font_size_pct,
            placement_mode=args.placement_mode,
            font_family=args.font_family,
            text_background=args.text_background,
        )
        image.save(output_paths["output_file"], format="JPEG")
        tag_annotations = []

    create_annotated_preview(
        source_path=pixel_result["preview_file"] or output_paths["preview_file"],
        box_annotations=pixel_result["box_annotations"],
        output_path=output_paths["annotated_preview_file"],
        title=input_path.stem,
        show_label_boxes=args.show_label_boxes == "y",
    )

    record = _attach_dicom_contexts(
        _build_record(
        run_id=run_id,
        seed=args.seed,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
        font_size_pct=args.font_size_pct,
        font_family=args.font_family,
        text_background=args.text_background,
        document_type=document_type,
        example_type=example_type,
        input_path=input_path,
        output_path=output_paths["output_file"],
        preview_path=output_paths["preview_file"],
        annotated_preview_path=output_paths["annotated_preview_file"],
        identity=identity_a,
        source_dicom_context=source_dicom_context,
        output_dicom_context=output_dicom_context,
        tag_annotations=tag_annotations,
        box_annotations=pixel_result["box_annotations"],
        visible_render_plan=visible_render_plan,
        pixel_result=pixel_result,
        ),
        source_dicom_context=source_dicom_context,
        output_dicom_context=output_dicom_context,
    )

    with output_paths["output_json"].open("w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")

    with output_paths["output_manifest"].open("w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)

    print(
        f"Run {run_id} written to {output_paths['run_dir']}\n"
        f"Injected {len(tag_annotations)} tags into {output_paths['output_file']}\n"
        f"Ground truth written to {output_paths['output_json']}\n"
        f"Preview:            {output_paths['preview_file']}\n"
        f"Annotated preview:  {output_paths['annotated_preview_file']}"
    )
    print(f"Pixel injection status: {pixel_result['status']}")

    print("\nSecond identity (seed+1, not injected):")
    for key, value in identity_b.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
