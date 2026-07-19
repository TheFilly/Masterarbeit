from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

import injection_pipeline
import injection_pipeline.api as api
from injection_pipeline.engine.pixel_injection import ALLOWED_ROTATIONS_DEGREES


def test_top_level_package_exports_inject_function() -> None:
    assert injection_pipeline.inject_function is api.inject_function


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "category": "",
                "value": "95",
                "prefix": "",
                "suffix": "",
                "handwritten": False,
                "documentType": "jpg",
            },
            "category must be a non-empty string",
        ),
        (
            {
                "category": "Age",
                "value": "",
                "prefix": "",
                "suffix": "",
                "handwritten": False,
                "documentType": "jpg",
            },
            "value must be a non-empty string",
        ),
        (
            {
                "category": "Age",
                "value": "95",
                "prefix": "",
                "suffix": "",
                "handwritten": "false",
                "documentType": "jpg",
            },
            "handwritten must be a boolean",
        ),
        (
            {
                "category": "Age",
                "value": "95",
                "prefix": "",
                "suffix": "",
                "handwritten": False,
                "documentType": "pdf",
            },
            "documentType must be one of: dcm, jpg",
        ),
    ],
)
def test_inject_function_validates_public_inputs(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        api.inject_function(**kwargs)


def test_inject_function_runs_jpg_and_exports_only_main_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    source_path = image_dir / "source.jpg"
    source_path.write_bytes(b"source")
    export_dir = tmp_path / "export"
    captured: dict[str, Any] = {}

    def fake_run_pipeline(args: Namespace, now: object) -> dict[str, Path]:
        captured["args"] = args
        captured["now"] = now
        run_dir = tmp_path / "output" / "run-id"
        run_dir.mkdir(parents=True)
        output_file = run_dir / "source_injected.jpg"
        output_json = run_dir / "ground_truth.json"
        output_file.write_bytes(b"injected")
        output_json.write_text('{"ok": true}\n', encoding="utf-8")
        (run_dir / "preview_annotated.png").write_bytes(b"preview")
        return {"output_file": output_file, "output_json": output_json}

    monkeypatch.setattr(
        api, "_DOCUMENT_TYPE_INPUT_DIRS", {"jpg": image_dir, "dcm": tmp_path}
    )
    monkeypatch.setattr(api, "run_pipeline", fake_run_pipeline)

    injected_path, json_path = api.inject_function(
        "Age",
        "95",
        "Patient is ",
        " years old",
        False,
        "JPG",
        output_dir=export_dir,
    )

    assert injected_path == export_dir / "source_injected.jpg"
    assert json_path == export_dir / "ground_truth.json"
    assert {path.name for path in export_dir.iterdir()} == {
        "source_injected.jpg",
        "ground_truth.json",
    }
    assert injected_path.read_bytes() == b"injected"
    assert json_path.read_text(encoding="utf-8") == '{"ok": true}\n'

    args = captured["args"]
    assert args.input == str(source_path)
    assert args.output_dir == str(api.DEFAULT_OUTPUT_DIR)
    assert args.font_family == "arial"
    assert args.font_size_pct == 100
    assert args.placement_mode == "corners"
    assert args.rotation_angle in ALLOWED_ROTATIONS_DEGREES
    assert args.identity_override.fields == {"age": "95"}
    assert args.tag_identity_override.fields == {"age": "95"}
    assert args.handwriting_identity_override is None
    assert args.handwriting_text_asset_override is None
    assert args.visible_render_plan_override == [
        {
            "label": "Age",
            "category": "Age",
            "text": "Patient is 95 years old",
            "text_segments": [
                {"kind": "generic", "text": "Patient is "},
                {"kind": "pii", "text": "95"},
                {"kind": "generic", "text": " years old"},
            ],
            "identity_field": "age",
            "region": "corners",
            "rotation_degrees": args.rotation_angle,
            "line_index": 0,
        }
    ]


def test_inject_function_routes_known_dicom_category_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dicom_dir = tmp_path / "dicom"
    dicom_dir.mkdir()
    source_path = dicom_dir / "source.dcm"
    source_path.write_bytes(b"source")
    captured: dict[str, Any] = {}

    def fake_run_pipeline(args: Namespace, now: object) -> dict[str, Path]:
        _ = now
        captured["args"] = args
        output_file = tmp_path / "output" / "source_injected.dcm"
        output_json = tmp_path / "output" / "ground_truth.json"
        output_file.parent.mkdir()
        output_file.write_bytes(b"injected")
        output_json.write_text("{}", encoding="utf-8")
        return {"output_file": output_file, "output_json": output_json}

    monkeypatch.setattr(
        api, "_DOCUMENT_TYPE_INPUT_DIRS", {"dcm": dicom_dir, "jpg": tmp_path}
    )
    monkeypatch.setattr(api, "run_pipeline", fake_run_pipeline)

    injected_path, json_path = api.inject_function(
        "patientid",
        "SYNTH-123456",
        "",
        "",
        False,
        "DcM",
    )

    assert injected_path == tmp_path / "output" / "source_injected.dcm"
    assert json_path == tmp_path / "output" / "ground_truth.json"
    args = captured["args"]
    assert args.input == str(source_path)
    assert args.identifier_schema_override.fields[0].name == "patient_id"
    assert (
        args.identifier_schema_override.fields[0].routing.dicom_tag.keyword
        == "PatientID"
    )
    assert args.visible_render_plan_override[0]["label"] == "patientid"


def test_inject_function_keeps_ambiguous_category_visible_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dicom_dir = tmp_path / "dicom"
    dicom_dir.mkdir()
    (dicom_dir / "source.dcm").write_bytes(b"source")
    captured: dict[str, Any] = {}

    def fake_run_pipeline(args: Namespace, now: object) -> dict[str, Path]:
        _ = now
        captured["args"] = args
        output_file = tmp_path / "output" / "source_injected.dcm"
        output_json = tmp_path / "output" / "ground_truth.json"
        output_file.parent.mkdir()
        output_file.write_bytes(b"injected")
        output_json.write_text("{}", encoding="utf-8")
        return {"output_file": output_file, "output_json": output_json}

    monkeypatch.setattr(
        api, "_DOCUMENT_TYPE_INPUT_DIRS", {"dcm": dicom_dir, "jpg": tmp_path}
    )
    monkeypatch.setattr(api, "run_pipeline", fake_run_pipeline)

    api.inject_function("identifier", "SYNTH-123456", "", "", False, "dcm")

    field = captured["args"].identifier_schema_override.fields[0]
    assert field.name == "identifier"
    assert field.routing.dicom_tag is None


def test_inject_function_uses_handwriting_renderer_and_full_render_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    (image_dir / "source.jpeg").write_bytes(b"source")
    captured: dict[str, Any] = {}

    def fake_run_pipeline(args: Namespace, now: object) -> dict[str, Path]:
        _ = now
        captured["args"] = args
        output_file = tmp_path / "output" / "source_injected.jpg"
        output_json = tmp_path / "output" / "ground_truth.json"
        output_file.parent.mkdir()
        output_file.write_bytes(b"injected")
        output_json.write_text("{}", encoding="utf-8")
        return {"output_file": output_file, "output_json": output_json}

    monkeypatch.setattr(
        api, "_DOCUMENT_TYPE_INPUT_DIRS", {"jpg": image_dir, "dcm": tmp_path}
    )
    monkeypatch.setattr(api, "run_pipeline", fake_run_pipeline)

    api.inject_function("Unknown Field", "AB12", "pre ", " suf", True, "jpg")

    args = captured["args"]
    assert args.font_family == api.HANDWRITING_FONT_FAMILY
    assert args.identity_override.fields == {"unknown_field": "AB12"}
    assert args.handwriting_identity_override is None
    assert args.handwriting_text_asset_override == {
        "field": "unknown_field",
        "text": "pre AB12 suf",
    }
    assert args.visible_render_plan_override[0]["identity_field"] == "unknown_field"
    assert args.visible_render_plan_override[0]["text"] == "pre AB12 suf"


def test_inject_function_rejects_missing_default_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    empty_dir = tmp_path / "images"
    empty_dir.mkdir()
    monkeypatch.setattr(
        api, "_DOCUMENT_TYPE_INPUT_DIRS", {"jpg": empty_dir, "dcm": tmp_path}
    )

    with pytest.raises(ValueError, match="No default jpg input files found"):
        api.inject_function("Age", "95", "", "", False, "jpg")
