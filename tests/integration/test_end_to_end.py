"""End-to-end regression coverage for the DICOM and JPG pipeline paths."""

import hashlib
import json
import os
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
_BINARY_REFERENCE_HASHES: dict[str, dict[str, str]] = {
    "dcm": {
        "ground_truth.json": (
            "ab32d18ac71d9f97e0dc2de02c0f5029f726136a62a02277e2d111c9d67a062e"
        ),
        "preview.png": (
            "008b68b3b6f741f8b5e5e70efb54584ce0e7380f597121c1f8b091b66f27817e"
        ),
        "preview_annotated.png": (
            "72c098a322f41d1ffaf1d0e5aea953050d19e6f432fc196ad7bcbcc12e52772e"
        ),
        "run_manifest.json": (
            "1bab55ce3a37e587fe85fdf789bcc480c3dba0d80780d116518353d666e74098"
        ),
        "synthetic_injected.dcm": (
            "a040f800edec2649dcaa67407d98599fceb4dcee858d9cdaea6f9d6af32557e3"
        ),
    },
    "jpg": {
        "ground_truth.json": (
            "cc580063aaf36afebc96130b9537e41ef3a8b7d895826a1cacc99ffd8b62555c"
        ),
        "preview.png": (
            "1ecae9e8798567a5e48baa475cb8e25b9b51dad6a5f822ba91680a99ead21724"
        ),
        "preview_annotated.png": (
            "d8109a29c3c6ff5ef01ec30533a16f629162dd2c2d0fc7bd5c593c31cda4c162"
        ),
        "run_manifest.json": (
            "ba57f8db2dd426d919487503b027ddead80046386e785381d965f32139f24594"
        ),
        "synthetic_injected.jpg": (
            "ae66c33fa49e6b0a705d762cff13c489d129db0845711ebbbd583c3c484f922c"
        ),
    },
}
_RECORD_REFERENCE_HASHES = {
    "dcm": "62e64daa3693f621e46824a94aa261fe8b057ad693580e619ad91455efa147de",
    "jpg": "4720d1e37662c68bd5e1e1c9204dd65bd2bc2431df4e2b232387a5ef3e27c8e8",
}


# Input: `path` with an artifact whose bytes need a stable fingerprint.
# Output: Lowercase SHA-256 digest for the complete file contents.
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    font_path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    monkeypatch.setitem(pixel_injection._FONT_PATHS, "arial", str(font_path))
    monkeypatch.chdir(tmp_path)

    input_dir = Path("fixtures")
    input_dir.mkdir()
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
    font_path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    monkeypatch.setitem(pixel_injection._FONT_PATHS, "arial", str(font_path))
    monkeypatch.chdir(tmp_path)

    input_dir = Path("fixtures")
    input_dir.mkdir()
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
