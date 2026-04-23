"""Prototype orchestrator: inject a synthetic identity into a DICOM file."""

import argparse
import json
from pathlib import Path

from identity import generate_identity
from dicom_writer import load_dicom, inject_tags, save_dicom

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


def _build_tag_map(identity: dict[str, str]) -> dict[str, str]:
    return {
        "PatientName": identity["patient_name"],
        "PatientID": identity["patient_id"],
        "PatientBirthDate": identity["patient_birth_date"],
        "PatientSex": identity["patient_sex"],
        "AccessionNumber": identity["accession_number"],
    }


def main() -> None:
    """Entry point for the DICOM injection prototype."""
    parser = argparse.ArgumentParser(description="DICOM injection prototype")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--input", type=str, default=_DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=str, default="prototypes/dicom/output")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dcm = output_dir / "echo_injected.dcm"
    output_jsonl = output_dir / "ground_truth.jsonl"

    identity_a = generate_identity(args.seed)
    identity_b = generate_identity(args.seed + 1)

    ds = load_dicom(input_path)
    tag_map = _build_tag_map(identity_a)
    ds = inject_tags(ds, tag_map)
    save_dicom(ds, output_dcm)

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for keyword, injected_value in tag_map.items():
        tag_address, dicom_vr = _TAG_META[keyword]
        identity_field = _IDENTITY_FIELD_MAP[keyword]
        records.append(
            {
                "schema_version": "0.1.0-prototype",
                "run_id": f"proto-{args.seed}",
                "seed": args.seed,
                "source_file": str(input_path),
                "output_file": str(output_dcm),
                "injection": {
                    "tag_address": tag_address,
                    "tag_keyword": keyword,
                    "dicom_vr": dicom_vr,
                    "injected_value": injected_value,
                    "identity_field": identity_field,
                    "identity_id": identity_a["patient_id"],
                },
            }
        )

    with output_jsonl.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")

    print(
        f"Injected {len(records)} tags into {output_dcm}\n"
        f"Ground truth written to {output_jsonl}"
    )

    print("\nSecond identity (seed+1, not injected):")
    for key, value in identity_b.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
