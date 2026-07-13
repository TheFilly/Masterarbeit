import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from injection_pipeline.artifacts.ground_truth import build_record
from injection_pipeline.config import load_identifier_schema
from injection_pipeline.config.identifier_schema import DEFAULT_IDENTIFIER_SCHEMA_PATH
from injection_pipeline.engine.handwriting_manifest import (
    apply_handwriting_assets,
    load_handwriting_manifest,
)
from injection_pipeline.engine.injector import (
    _inject_visible_text_into_frame,
    _render_frame_with_annotations,
)
from injection_pipeline.models import Identity


def _write_asset(tmp_path: Path) -> Path:
    image_path = tmp_path / "name.png"
    mask_path = tmp_path / "name_mask.png"
    manifest_path = tmp_path / "manifest.json"

    image = Image.new("RGBA", (8, 6), (0, 0, 0, 0))
    pixels = image.load()
    mask = Image.new("L", (8, 6), 0)
    mask_pixels = mask.load()
    for y in range(1, 5):
        for x in range(2, 7):
            pixels[x, y] = (0, 0, 0, 255)
            mask_pixels[x, y] = 255
    image.save(image_path)
    mask.save(mask_path)

    manifest = {
        "schema_version": "0.1.0-handwriting-assets",
        "assets": [
            {
                "asset_id": "patient-name-001",
                "text": "Doe^Jane",
                "identity_field": "patient_name",
                "image_path": image_path.name,
                "mask_path": mask_path.name,
                "ink_color": "black",
                "background_mode": "transparent",
                "hashes": {"image_sha256": "placeholder", "mask_sha256": "placeholder"},
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_load_handwriting_manifest_resolves_relative_paths(tmp_path: Path) -> None:
    manifest_path = _write_asset(tmp_path)

    manifest = load_handwriting_manifest(manifest_path)

    asset = manifest["patient-name-001"]
    assert asset["asset_id"] == "patient-name-001"
    assert asset["image_path"] == tmp_path / "name.png"
    assert asset["mask_path"] == tmp_path / "name_mask.png"


def test_load_handwriting_manifest_rejects_missing_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "missing.jsonl"

    with pytest.raises(FileNotFoundError, match="Handwriting manifest not found"):
        load_handwriting_manifest(manifest_path)


def test_load_handwriting_manifest_accepts_jsonl_generator_output(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "id.png"
    mask_path = tmp_path / "id_mask.png"
    image_path.write_bytes(b"")
    mask_path.write_bytes(b"")
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "asset_id": "patient-id-001",
                "field": "patient_id",
                "text": "SYNTH-123456",
                "image_path": image_path.name,
                "mask_path": mask_path.name,
                "ink_color": "gray",
                "background": "white",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = load_handwriting_manifest(manifest_path)

    asset = manifest["patient-id-001"]
    assert asset["identity_field"] == "patient_id"
    assert asset["background_mode"] == "white"


def test_apply_handwriting_assets_attaches_manifest_asset(tmp_path: Path) -> None:
    manifest = load_handwriting_manifest(_write_asset(tmp_path))
    render_plan = [
        {
            "label": "PatientName",
            "text": "Doe^Jane",
            "identity_field": "patient_name",
            "rotation_degrees": 0,
        }
    ]

    updated = apply_handwriting_assets(
        render_plan,
        manifest,
        {"patient_name": "patient-name-001"},
    )

    assert updated[0]["renderer_type"] == "handwriting_asset"
    assert updated[0]["asset_id"] == "patient-name-001"
    assert updated[0]["asset"]["text"] == "Doe^Jane"


def test_apply_handwriting_assets_rejects_field_mismatch(tmp_path: Path) -> None:
    manifest = load_handwriting_manifest(_write_asset(tmp_path))
    render_plan = [
        {
            "label": "PatientID",
            "text": "SYNTH-123456",
            "identity_field": "patient_id",
            "rotation_degrees": 0,
        }
    ]

    with pytest.raises(ValueError, match="identity field"):
        apply_handwriting_assets(
            render_plan,
            manifest,
            {"patient_id": "patient-name-001"},
        )


def test_apply_handwriting_assets_rejects_text_mismatch(tmp_path: Path) -> None:
    manifest = load_handwriting_manifest(_write_asset(tmp_path))
    render_plan = [
        {
            "label": "PatientName",
            "text": "Other^Name",
            "identity_field": "patient_name",
            "rotation_degrees": 0,
        }
    ]

    with pytest.raises(ValueError, match="text"):
        apply_handwriting_assets(
            render_plan,
            manifest,
            {"patient_name": "patient-name-001"},
        )


def test_render_handwriting_asset_uses_transformed_ink_mask(tmp_path: Path) -> None:
    manifest = load_handwriting_manifest(_write_asset(tmp_path))
    asset = manifest["patient-name-001"]
    frame = np.full((32, 32, 3), 255, dtype=np.uint8)
    annotations = [
        {
            "label": "PatientName",
            "text": "Doe^Jane",
            "identity_field": "patient_name",
            "renderer_type": "handwriting_asset",
            "asset_id": "patient-name-001",
            "asset": asset,
            "position": (10, 9),
            "region": "unit_test",
            "rotation_degrees": 0,
        }
    ]

    _, records = _render_frame_with_annotations(frame, annotations)

    record = records[0]
    assert record["corners"] == [
        {"x": 12.0, "y": 10.0},
        {"x": 17.0, "y": 10.0},
        {"x": 17.0, "y": 14.0},
        {"x": 12.0, "y": 14.0},
    ]
    assert record["label_corners"] is None
    assert record["render_metadata"]["renderer_type"] == "handwriting_asset"
    assert record["render_metadata"]["geometry_source"] == "transformed_ink_mask"


def test_frame_renderer_reports_handwriting_assets_in_metadata(tmp_path: Path) -> None:
    manifest = load_handwriting_manifest(_write_asset(tmp_path))
    asset = manifest["patient-name-001"]
    frame = np.full((32, 32, 3), 255, dtype=np.uint8)

    result = _inject_visible_text_into_frame(
        frame=frame,
        visible_injections=[
            {
                "label": "PatientName",
                "text": "Doe^Jane",
                "identity_field": "patient_name",
                "renderer_type": "handwriting_asset",
                "asset_id": "patient-name-001",
                "asset": asset,
                "region": "unit_test",
                "rotation_degrees": 0,
            }
        ],
        preview_path=tmp_path / "preview.png",
        seed=42,
        rotation_degrees=0,
        font_size_pct=100,
        placement_mode="corners",
        font_family="arial",
        text_background=None,
        frame_count=1,
    )

    assert result["render_metadata"]["renderer_types"] == ["handwriting_asset"]
    assert result["render_metadata"]["handwriting_assets"] == [
        {
            "asset_id": "patient-name-001",
            "asset_path": str(asset["image_path"]),
            "mask_path": str(asset["mask_path"]),
            "ink_color": "black",
            "background_mode": "transparent",
        }
    ]


def test_build_record_serializes_handwriting_asset_paths(tmp_path: Path) -> None:
    manifest = load_handwriting_manifest(_write_asset(tmp_path))
    visible_render_plan = [
        {
            "label": "PatientName",
            "text": "Doe^Jane",
            "text_segments": [{"kind": "pii", "text": "Doe^Jane"}],
            "identity_field": "patient_name",
            "region": "corners",
            "rotation_degrees": 0,
            "line_index": 0,
            "renderer_type": "handwriting_asset",
            "asset_id": "patient-name-001",
            "asset": manifest["patient-name-001"],
        }
    ]

    record = build_record(
        run_id="unit-test-run",
        seed=42,
        rotation_degrees=0,
        placement_mode="corners",
        font_size_pct=100,
        font_family="arial",
        text_background=None,
        document_type="jpg",
        example_type="unit",
        input_path=tmp_path / "input.jpg",
        output_path=tmp_path / "output.jpg",
        preview_path=tmp_path / "preview.png",
        annotated_preview_path=tmp_path / "preview_annotated.png",
        identity=Identity(
            identity_id="SYNTH-123456",
            seed=42,
            fields={"patient_id": "SYNTH-123456"},
        ),
        identifier_schema=load_identifier_schema(DEFAULT_IDENTIFIER_SCHEMA_PATH),
        source_dicom_context=None,
        output_dicom_context=None,
        tag_annotations=[],
        box_annotations=[],
        visible_render_plan=visible_render_plan,
        pixel_result={
            "status": "rendered",
            "renderer_name": "unit",
            "preview_file": str(tmp_path / "preview.png"),
            "render_metadata": {
                "seed": 42,
                "rotation_degrees": 0,
                "allowed_rotations_degrees": [0, 20, 90, 180, 270],
                "frame_count": 1,
                "applied_frame_indices": [0],
                "effective_font_family": "arial",
                "effective_font_size_px": 18,
                "background_enabled": False,
                "background_color": None,
                "geometry_source": "mask_bbox_after_final_rotation",
                "renderer_types": ["handwriting_asset"],
                "handwriting_assets": [],
                "geometry_notes": "unit",
                "mask_alpha_threshold": 8,
                "visible_annotations": [],
            },
        },
    )

    serialized = record.model_dump(mode="json")
    asset = serialized["render_metadata"]["visible_render_plan"][0]["asset"]
    assert asset["image_path"] == str(tmp_path / "name.png")
    assert asset["mask_path"] == str(tmp_path / "name_mask.png")
