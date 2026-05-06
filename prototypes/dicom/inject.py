"""Prototype orchestrator: inject a synthetic identity into a DICOM file."""

import argparse
import json
import re
from pathlib import Path
from typing import Any

from dicom_writer import inject_tags, load_dicom, save_dicom, summarize_dicom
from identity import generate_identity
from pixel_injection import ALLOWED_ROTATIONS_DEGREES, inject_visible_text
from view import create_annotated_preview

_DEFAULT_INPUT = (
    "DycomData/Anonymization/original_data/"
    "patient_10080695_23273240/echo/91180014_0001.dcm"
)

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


def _derive_example_type(input_path: Path) -> str:
    for part in reversed(input_path.parts[:-1]):
        normalized = re.sub(r"[^a-z0-9]+", "-", part.lower()).strip("-")
        if normalized and normalized not in {"original-data", "anonymization"}:
            return normalized
    return "dicom"


def _build_short_id(input_path: Path) -> str:
    stem = input_path.stem.split("_")[0]
    normalized = re.sub(r"[^a-z0-9]+", "", stem.lower())
    return normalized[:12] or "sample"


def _build_run_id(
    seed: int,
    rotation_degrees: int,
    placement_mode: str,
    example_type: str,
    short_id: str,
) -> str:
    return f"seed{seed:04d}-angle{rotation_degrees:03d}-{placement_mode}-{example_type}-{short_id}"


def _build_output_paths(output_root: Path, run_id: str, source_stem: str) -> dict[str, Path]:
    run_dir = output_root / run_id
    return {
        "run_dir": run_dir,
        "output_dcm": run_dir / f"{source_stem}_injected.dcm",
        "output_jsonl": run_dir / "ground_truth.jsonl",
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
        render_plan.append(
            {
                "label": keyword,
                "text": tag_map[keyword],
                "identity_field": _IDENTITY_FIELD_MAP[keyword],
                "region": placement_mode,
                "rotation_degrees": rotation_degrees,
                "line_index": index,
            }
        )
    return render_plan


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
    )
    return result.get("dataset", ds), {
        "status": result.get("status", "rendered"),
        "renderer_name": "pixel_injection.inject_visible_text",
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
    example_type: str,
    input_path: Path,
    output_path: Path,
    preview_path: Path,
    annotated_preview_path: Path,
    identity: dict[str, str],
    source_dicom_context: dict[str, Any],
    output_dicom_context: dict[str, Any],
    tag_annotations: list[dict[str, Any]],
    box_annotations: list[dict[str, Any]],
    visible_render_plan: list[dict[str, Any]],
    pixel_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "record_type": "dicom_injection_run",
        "run_id": run_id,
        "seed": seed,
        "rotation_degrees": rotation_degrees,
        "source_file": str(input_path),
        "output_file": str(output_path),
        "preview_file": pixel_result["preview_file"] or str(preview_path),
        "annotated_preview_file": str(annotated_preview_path),
        "document_type": "dicom",
        "example_type": example_type,
        "modality": output_dicom_context["modality"],
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
            "source_dicom_context": source_dicom_context,
            "output_dicom_context": output_dicom_context,
        },
        "render_metadata": {
            "rotation_degrees": rotation_degrees,
            "placement_mode": placement_mode,
            "font_size_pct": font_size_pct,
            "visible_render_plan": visible_render_plan,
            **pixel_result["render_metadata"],
        },
    }


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
    args = parser.parse_args()

    if args.rotation_angle not in ALLOWED_ROTATIONS_DEGREES:
        allowed = ", ".join(str(angle) for angle in ALLOWED_ROTATIONS_DEGREES)
        raise ValueError(
            f"--rotation-angle must be one of [{allowed}], got {args.rotation_angle}."
        )
    if args.font_size_pct < 1:
        raise ValueError("--font-size-pct must be >= 1.")

    input_path = Path(args.input)
    output_root = Path(args.output_dir)
    example_type = _derive_example_type(input_path)
    short_id = _build_short_id(input_path)
    run_id = _build_run_id(
        args.seed, args.rotation_angle, args.placement_mode, example_type, short_id
    )
    output_paths = _build_output_paths(output_root, run_id, input_path.stem)

    identity_a = generate_identity(args.seed)
    identity_b = generate_identity(args.seed + 1)

    ds = load_dicom(input_path)
    source_dicom_context = summarize_dicom(ds)
    tag_map = _build_tag_map(identity_a)
    ds = inject_tags(ds, tag_map)
    visible_render_plan = _build_visible_render_plan(
        tag_map=tag_map,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
    )
    ds, pixel_result = _run_pixel_injection(
        ds=ds,
        visible_injections=visible_render_plan,
        output_path=output_paths["output_dcm"],
        preview_path=output_paths["preview_file"],
        seed=args.seed,
        rotation_degrees=args.rotation_angle,
        example_type=example_type,
        font_size_pct=args.font_size_pct,
        placement_mode=args.placement_mode,
    )
    output_dicom_context = summarize_dicom(ds)

    output_paths["run_dir"].mkdir(parents=True, exist_ok=True)
    save_dicom(ds, output_paths["output_dcm"])

    create_annotated_preview(
        dicom_path=output_paths["output_dcm"],
        box_annotations=pixel_result["box_annotations"],
        output_path=output_paths["annotated_preview_file"],
        title=run_id,
    )

    tag_annotations = _build_tag_annotations(
        tag_map=tag_map,
        identity=identity_a,
        input_path=input_path,
        output_path=output_paths["output_dcm"],
    )
    record = _build_record(
        run_id=run_id,
        seed=args.seed,
        rotation_degrees=args.rotation_angle,
        placement_mode=args.placement_mode,
        font_size_pct=args.font_size_pct,
        example_type=example_type,
        input_path=input_path,
        output_path=output_paths["output_dcm"],
        preview_path=output_paths["preview_file"],
        annotated_preview_path=output_paths["annotated_preview_file"],
        identity=identity_a,
        source_dicom_context=source_dicom_context,
        output_dicom_context=output_dicom_context,
        tag_annotations=tag_annotations,
        box_annotations=pixel_result["box_annotations"],
        visible_render_plan=visible_render_plan,
        pixel_result=pixel_result,
    )

    with output_paths["output_jsonl"].open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    with output_paths["output_manifest"].open("w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)

    print(
        f"Run {run_id} written to {output_paths['run_dir']}\n"
        f"Injected {len(tag_annotations)} tags into {output_paths['output_dcm']}\n"
        f"Ground truth written to {output_paths['output_jsonl']}\n"
        f"Preview:            {output_paths['preview_file']}\n"
        f"Annotated preview:  {output_paths['annotated_preview_file']}"
    )
    print(f"Pixel injection status: {pixel_result['status']}")

    print("\nSecond identity (seed+1, not injected):")
    for key, value in identity_b.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
