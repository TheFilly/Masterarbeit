"""End-to-end regression coverage for the DICOM and JPG pipeline paths."""

import hashlib
import json
import os
import shutil
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import pytest
from PIL import Image

from injection_pipeline.config import DEFAULT_IDENTIFIER_SCHEMA_PATH
from injection_pipeline.engine import pixel_injection
from injection_pipeline.models import load_run_record
from injection_pipeline.runtime import runner
from tests.fixtures.synthetic_documents import (
    write_synthetic_dicom,
    write_synthetic_jpg,
)

_FIXED_RUN_TIMESTAMP = datetime(2026, 7, 10, 12, 0, 0)
# Reference update 2026-07-12:
# - JSON record hashes changed because E2E now uses `_FIXED_RUN_TIMESTAMP`.
# - DCM bytes changed from b5c13f... to a040f8... because `reference_date`
#   now reproduces Fakers exact 2026-07-10 `date_of_birth` path.
# Reference update 2026-07-13:
# - JSON artifact and record hashes changed because E2E now uses a stable
#   relative font fixture path instead of platform-specific matplotlib paths.
# Reference update 2026-07-14:
# - `ground_truth.json`/`run_manifest.json` and the two preview PNGs are
#   pinned to the values produced on the CI runner (ubuntu-latest), which is
#   the only platform these hashes are asserted against. Their raw bytes are
#   not cross-platform-identical by construction: the JSON files embed
#   `os.linesep`, and the PNGs are pixel-identical across platforms (verified
#   byte-for-byte pixel diff) but re-encoded by a platform-specific
#   Pillow/matplotlib Agg build, which changes PNG compression bytes without
#   changing pixel content. `synthetic_injected.{dcm,jpg}` are unaffected and
#   stay byte-identical across platforms.
# Reference update 2026-07-19:
# - JSON artifact and record hashes changed because visible annotations now
#   serialize `category`, `prefix`, `suffix`, `prefix_corners`, and
#   `suffix_corners`; DICOM tag annotations now serialize schema `category`.
#
# Platform boundary:
# - `ground_truth.json` and `run_manifest.json` keep semantic/model/path checks
#   because their raw bytes include platform-native newlines.
# - Preview PNGs keep pixel/dimension regression checks because PNG compression
#   bytes can vary across Pillow/libpng builds while decoded pixels stay stable.
# - Injected DCM/JPG artifacts remain byte-hashed because they are the actual
#   regression target for document output stability.
_INJECTED_DOCUMENT_REFERENCE_HASHES: dict[str, dict[str, str]] = {
    "dcm": {
        "synthetic_injected.dcm": (
            "a040f800edec2649dcaa67407d98599fceb4dcee858d9cdaea6f9d6af32557e3"
        ),
    },
    "jpg": {
        "synthetic_injected.jpg": (
            "ae66c33fa49e6b0a705d762cff13c489d129db0845711ebbbd583c3c484f922c"
        ),
    },
}
_PREVIEW_REFERENCE_FINGERPRINTS: dict[
    str, dict[str, tuple[tuple[int, int], str]]
] = {
    "dcm": {
        "preview.png": (
            (256, 256),
            "95604e8dedccb04945deaaa5653b699eeccfe27d84716c3d48ce95aa1fb83008",
        ),
        "preview_annotated.png": (
            (954, 985),
            "72a8c3f458e0d4100cc2a28f76c032c3901ae8e297c8ff54fdcb9e2f0c070bfa",
        ),
    },
    "jpg": {
        "preview.png": (
            (256, 256),
            "a95e5b4241cfdce87b6949c196f89a103b6488c9712b0493404e3a8476affaed",
        ),
        "preview_annotated.png": (
            (954, 985),
            "121fb8a9ce2781ece2eea9702b0f9703bdee486cda63b927c5d3ab5e0b7399c3",
        ),
    },
}
_RECORD_REFERENCE_HASHES = {
    "dcm": "a142a3bed9b1c0b96d494d7749fe2b127a4f18405a76ad6b9599abb2768eec07",
    "jpg": "18837b47c05c7882a5177936de23c86a744306d39b87451d2677fb1d2a449300",
}


# Input: `path` with an artifact whose bytes need a stable fingerprint.
# Output: Lowercase SHA-256 digest for the complete file contents.
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Input: `path` with a preview PNG produced by the pipeline.
# Output: Image dimensions and SHA-256 digest of decoded RGBA pixel bytes.
# Raw PNG bytes are intentionally avoided because encoder output varies by
# platform even when the rendered pixels are unchanged.
def _preview_fingerprint(path: Path) -> tuple[tuple[int, int], str]:
    with Image.open(path) as image:
        canonical = image.convert("RGBA")
        return canonical.size, hashlib.sha256(canonical.tobytes()).hexdigest()


def _install_reference_font(relative_font_path: Path) -> Path:
    source_font_path = (
        Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    )
    relative_font_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_font_path, relative_font_path)
    return relative_font_path


# Input: Run record and its expected document type.
# Output: A copy without path fields after checking every path exactly.
# The checked fields stay platform-native and retain the complete run directory.
def _record_without_checked_paths(
    record: dict[str, Any],
    *,
    document_type: str,
) -> dict[str, Any]:
    run_id = record["run_id"]
    source_path = Path("fixtures") / f"synthetic.{document_type}"
    run_dir = Path("output") / run_id
    output_suffix = ".dcm" if document_type == "dcm" else ".jpg"
    output_path = run_dir / f"synthetic_injected{output_suffix}"
    expected_paths = {
        "source_file": source_path,
        "output_file": output_path,
        "preview_file": run_dir / "preview.png",
        "annotated_preview_file": run_dir / "preview_annotated.png",
    }
    for field, expected_path in expected_paths.items():
        assert record[field] == str(expected_path)

    record_copy = json.loads(json.dumps(record))
    for field in expected_paths:
        del record_copy[field]
    for annotation in record_copy["dicom_tag_annotations"]:
        assert annotation["source_file"] == str(source_path)
        assert annotation["output_file"] == str(output_path)
        del annotation["source_file"]
        del annotation["output_file"]
    return record_copy


# Input: `input_path`, output root, and fixed pipeline options.
# Output: The single run directory created by the pipeline.
# The helper invokes the public runner and asserts that one run was produced.
def _run_pipeline(input_path: Path, output_root: Path) -> Path:
    args = Namespace(
        input=str(input_path),
        output_dir=str(output_root),
        identifier_schema=str(DEFAULT_IDENTIFIER_SCHEMA_PATH),
        seed=42,
        rotation_angle=20,
        font_size_pct=100,
        placement_mode="corners",
        font_family="arial",
        text_background=None,
        show_label_boxes="n",
        handwriting_manifest=None,
        handwriting_asset=[],
    )
    runner.run(args, now=_FIXED_RUN_TIMESTAMP)
    run_directories = list(output_root.iterdir())
    assert len(run_directories) == 1
    return run_directories[0]


# Input: `run_dir` and expected document type.
# Output: Ground-truth record after validating both JSON artifacts.
# The helper preserves the prototype newline asymmetry while comparing payloads.
def _load_and_validate_records(
    run_dir: Path,
    *,
    document_type: str,
) -> dict[str, Any]:
    ground_truth_path = run_dir / "ground_truth.json"
    manifest_path = run_dir / "run_manifest.json"
    assert ground_truth_path.read_bytes().endswith(b"\n")
    assert not manifest_path.read_bytes().endswith(b"\n")

    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert ground_truth == manifest
    loaded_record = load_run_record(ground_truth_path)
    serialized_ground_truth = json.dumps(
        loaded_record.model_dump(mode="json"), indent=2
    )
    platform_newlines = serialized_ground_truth.replace("\n", os.linesep)
    assert (platform_newlines + os.linesep).encode(
        "utf-8"
    ) == ground_truth_path.read_bytes()
    assert platform_newlines.encode("utf-8") == manifest_path.read_bytes()
    assert ground_truth["document_type"] == document_type
    assert ground_truth["seed"] == 42
    assert len(ground_truth["box_annotations"]) == 3
    box_by_label = {
        annotation["label"]: annotation
        for annotation in ground_truth["box_annotations"]
    }
    assert box_by_label["PatientName"]["category"] == "person_name"
    assert box_by_label["PatientName"]["prefix"] == ""
    assert box_by_label["PatientName"]["suffix"] == ""
    assert box_by_label["PatientName"]["prefix_corners"] is None
    assert box_by_label["PatientName"]["suffix_corners"] is None
    assert box_by_label["PatientID"]["category"] == "identifier"
    assert box_by_label["PatientID"]["prefix"] == "SYNTH-"
    assert box_by_label["PatientID"]["suffix"] == ""
    assert box_by_label["PatientID"]["prefix_corners"] is not None
    assert box_by_label["PatientID"]["suffix_corners"] is None
    assert box_by_label["AccessionNumber"]["category"] == "identifier"
    assert box_by_label["AccessionNumber"]["prefix"] == "ACC-"
    assert box_by_label["AccessionNumber"]["suffix"] == ""
    assert box_by_label["AccessionNumber"]["prefix_corners"] is not None
    assert box_by_label["AccessionNumber"]["suffix_corners"] is None
    expected_tag_count = 5 if document_type == "dcm" else 0
    assert len(ground_truth["dicom_tag_annotations"]) == expected_tag_count
    if document_type == "dcm":
        tag_categories = {
            annotation["tag_keyword"]: annotation["category"]
            for annotation in ground_truth["dicom_tag_annotations"]
        }
        assert tag_categories == {
            "PatientName": "person_name",
            "PatientID": "identifier",
            "PatientBirthDate": "date",
            "PatientSex": "code",
            "AccessionNumber": "identifier",
        }
    return ground_truth


@pytest.mark.parametrize("document_type", ["dcm", "jpg"])
def test_pipeline_artifacts_match_frozen_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    document_type: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    font_path = _install_reference_font(Path("fixtures") / "fonts" / "DejaVuSans.ttf")
    monkeypatch.setitem(pixel_injection._FONT_PATHS, "arial", font_path.as_posix())

    input_dir = Path("fixtures")
    input_dir.mkdir(exist_ok=True)
    input_path = input_dir / f"synthetic.{document_type}"
    if document_type == "dcm":
        write_synthetic_dicom(input_path)
    else:
        write_synthetic_jpg(input_path)

    output_root = Path("output")
    run_dir = _run_pipeline(input_path, output_root)
    stdout = capsys.readouterr().out
    assert "Second identity" not in stdout
    assert "identity_b" not in stdout
    record = _load_and_validate_records(
        run_dir,
        document_type=document_type,
    )
    assert run_dir == output_root / record["run_id"]
    record_without_paths = _record_without_checked_paths(
        record,
        document_type=document_type,
    )
    assert record_without_paths["run_id"].startswith(
        f"{document_type}-10072026-1200-seed0042"
    )
    record_bytes = json.dumps(
        record_without_paths,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert (
        hashlib.sha256(record_bytes).hexdigest()
        == (_RECORD_REFERENCE_HASHES[document_type])
    )

    document_references = _INJECTED_DOCUMENT_REFERENCE_HASHES[document_type]
    preview_references = _PREVIEW_REFERENCE_FINGERPRINTS[document_type]
    expected_artifact_names = set(document_references) | set(preview_references) | {
        "ground_truth.json",
        "run_manifest.json",
    }
    artifacts = list(run_dir.iterdir())
    assert all(path.is_file() for path in artifacts)
    assert {path.name for path in artifacts} == expected_artifact_names
    artifact_hashes = {
        name: _sha256(run_dir / name) for name in document_references
    }
    assert artifact_hashes == document_references
    preview_fingerprints = {
        name: _preview_fingerprint(run_dir / name) for name in preview_references
    }
    assert preview_fingerprints == preview_references


def test_pipeline_accepts_toy_identifier_schema_without_code_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    font_path = _install_reference_font(Path("fixtures") / "fonts" / "DejaVuSans.ttf")
    monkeypatch.setitem(pixel_injection._FONT_PATHS, "arial", font_path.as_posix())

    input_dir = Path("fixtures")
    input_dir.mkdir(exist_ok=True)
    input_path = input_dir / "synthetic.jpg"
    write_synthetic_jpg(input_path)

    schema_path = tmp_path / "toy-schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "schema_id": "toy-schema",
                "version": "1.0.0",
                "identity_id_field": "case_id",
                "generator": {"provider": "faker", "locale": "en_US"},
                "fields": [
                    {
                        "name": "case_id",
                        "category": "identifier",
                        "generation": {
                            "recipe": "numerify",
                            "arguments": {"text": "##"},
                            "value_template": "CASE-{value}",
                        },
                        "generic_prefix": "CASE-",
                        "routing": {
                            "dicom_tag": None,
                            "visible_pixel": {"enabled": True, "line_index": 0},
                        },
                    },
                    {
                        "name": "site_code",
                        "category": "code",
                        "generation": {
                            "recipe": "random_element",
                            "arguments": {"elements": ["ALPHA", "BETA"]},
                            "value_template": "{value}",
                        },
                        "generic_prefix": None,
                        "routing": {
                            "dicom_tag": None,
                            "visible_pixel": {"enabled": True, "line_index": 1},
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(
        input=str(input_path),
        output_dir="output",
        identifier_schema=str(schema_path),
        seed=42,
        rotation_angle=0,
        font_size_pct=100,
        placement_mode="corners",
        font_family="arial",
        text_background=None,
        show_label_boxes="n",
        handwriting_manifest=None,
        handwriting_asset=[],
    )

    runner.run(args)

    run_dir = next(Path("output").iterdir())
    record = json.loads((run_dir / "ground_truth.json").read_text(encoding="utf-8"))
    assert record["identity_id"].startswith("CASE-")
    assert record["run_metadata"]["visible_identity_fields"] == [
        "case_id",
        "site_code",
    ]
    assert record["run_metadata"]["tag_only_identity_fields"] == []
    assert len(record["box_annotations"]) == 2
    assert record["dicom_tag_annotations"] == []
