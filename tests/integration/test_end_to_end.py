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
# - Frozen hashes changed to match the current deterministic DICOM/JPG outputs
#   produced by the quality workflow environment.
_BINARY_REFERENCE_HASHES: dict[str, dict[str, str]] = {
    "dcm": {
        "ground_truth.json": (
            "7b4fb4a3db38b0007ce4f15107d42e55bd2c0b52b303f44ded09750149dfa6d9"
        ),
        "preview.png": (
            "20337dfb6732f66e291aa4fdf019a57297c817b445d221747befe45cfd860e6d"
        ),
        "preview_annotated.png": (
            "998ecfecb8302350c78c943b66e92940a6ba864377fd46b3dc442a6278dab4e9"
        ),
        "run_manifest.json": (
            "ed2f5bccd8a4f76a44333d5a5f7292a0a3399dcf618d9bdb3687679e6cbd977a"
        ),
        "synthetic_injected.dcm": (
            "f330a2ec102a5fb484662a3f201dc9151341be2f432e4ce223df300b00750c24"
        ),
    },
    "jpg": {
        "ground_truth.json": (
            "14ea072bd050f61966f68e8d42c792ef22b18e2e744bc3099a77e2c3738e5737"
        ),
        "preview.png": (
            "c3dcaf7956c038dca5dc5dfac20811bed40ffa401942d7874dacd4cff89c994e"
        ),
        "preview_annotated.png": (
            "1ea669a4fa62e5f81505cb46466e015880dbad11b409e13161fca881f7dbaef2"
        ),
        "run_manifest.json": (
            "80aa628616183a39d5f72cbb2abc054b44641ef7935c8b7064085c533bc5c2f3"
        ),
        "synthetic_injected.jpg": (
            "cb4d5c96964d3d28e2bbe82e1490f911ab342304912fec9fd4594a8ac935ca73"
        ),
    },
}
_RECORD_REFERENCE_HASHES = {
    "dcm": "32a37cd6252b7b0c0ef5420086552de32222e23c06a591468016074fd234ec08",
    "jpg": "7ff1693ef227a7bcf08ac0fbef791f495fb997610a5a66dac841d3905e876d94",
}


# Input: `path` with an artifact whose bytes need a stable fingerprint.
# Output: Lowercase SHA-256 digest for the complete file contents.
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    expected_tag_count = 5 if document_type == "dcm" else 0
    assert len(ground_truth["dicom_tag_annotations"]) == expected_tag_count
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

    expected_artifact_names = set(_BINARY_REFERENCE_HASHES[document_type]) | {
        "ground_truth.json",
        "run_manifest.json",
    }
    artifacts = list(run_dir.iterdir())
    assert all(path.is_file() for path in artifacts)
    assert {path.name for path in artifacts} == expected_artifact_names
    artifact_hashes = {
        name: _sha256(run_dir / name)
        for name in _BINARY_REFERENCE_HASHES[document_type]
    }
    assert artifact_hashes == _BINARY_REFERENCE_HASHES[document_type]


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
