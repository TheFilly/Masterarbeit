import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image, ImageFont

import injection_pipeline.engine.handwriting as handwriting
import injection_pipeline.engine.injector as injector
import injection_pipeline.engine.overlay as overlay
import injection_pipeline.engine.placement as placement
from injection_pipeline.engine.handwriting_manifest import load_handwriting_manifest
from injection_pipeline.engine.prepared_overlay import PreparedOverlay


def _use_pillow_default_font(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        placement,
        "load_default_font",
        lambda **_: ImageFont.load_default(),
    )
    monkeypatch.setattr(
        injector,
        "load_default_font",
        lambda **_: ImageFont.load_default(),
    )


def _write_handwriting_asset(tmp_path: Path) -> dict[str, Any]:
    image_path = tmp_path / "name.png"
    mask_path = tmp_path / "name_mask.png"
    manifest_path = tmp_path / "manifest.json"

    image = Image.new("RGBA", (10, 7), (0, 0, 0, 0))
    pixels = image.load()
    mask = Image.new("L", (10, 7), 0)
    mask_pixels = mask.load()
    for y in range(1, 6):
        for x in range(2, 8):
            pixels[x, y] = (0, 0, 0, 255)
            mask_pixels[x, y] = 255
    image.save(image_path)
    mask.save(mask_path)

    manifest_path.write_text(
        json.dumps(
            {
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
                        "hashes": {
                            "image_sha256": "placeholder",
                            "mask_sha256": "placeholder",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return load_handwriting_manifest(manifest_path)["patient-name-001"]


def _run_font_fixture(tmp_path: Path) -> dict[str, Any]:
    return injector._inject_visible_text_into_frame(
        frame=np.full((80, 180, 3), 255, dtype=np.uint8),
        visible_injections=[
            {
                "label": "PatientID",
                "text": "SYNTH-123456",
                "identity_field": "patient_id",
                "rotation_degrees": 20,
            },
            {
                "label": "AccessionNumber",
                "text": "ACC-0013389",
                "identity_field": "accession_number",
                "rotation_degrees": 20,
            },
        ],
        preview_path=tmp_path / "preview.png",
        seed=42,
        rotation_degrees=20,
        font_size_pct=100,
        placement_mode="corners",
        font_family="arial",
        text_background=None,
        frame_count=1,
    )


def test_font_overlay_is_prepared_once_per_annotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_pillow_default_font(monkeypatch)
    original_prepare = overlay._prepare_annotation_overlay
    prepare_calls = 0

    def counting_prepare(
        annotation: dict[str, Any],
        font: Any,
        *,
        font_family: str,
        text_background: str | None,
    ) -> PreparedOverlay:
        nonlocal prepare_calls
        prepare_calls += 1
        return original_prepare(
            annotation,
            font,
            font_family=font_family,
            text_background=text_background,
        )

    monkeypatch.setattr(placement, "_prepare_annotation_overlay", counting_prepare)
    monkeypatch.setattr(overlay, "_prepare_annotation_overlay", counting_prepare)

    result = _run_font_fixture(tmp_path)

    assert len(result["render_metadata"]["visible_annotations"]) == 2
    assert prepare_calls == 2


def test_handwriting_overlay_is_prepared_once_per_annotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_pillow_default_font(monkeypatch)
    asset = _write_handwriting_asset(tmp_path)
    original_prepare = handwriting._prepare_handwriting_asset_overlay
    prepare_calls = 0

    def counting_prepare(annotation: dict[str, Any]) -> PreparedOverlay:
        nonlocal prepare_calls
        prepare_calls += 1
        return original_prepare(annotation)

    monkeypatch.setattr(
        placement,
        "_prepare_handwriting_asset_overlay",
        counting_prepare,
    )
    monkeypatch.setattr(
        handwriting,
        "_prepare_handwriting_asset_overlay",
        counting_prepare,
    )

    result = injector._inject_visible_text_into_frame(
        frame=np.full((80, 180, 3), 255, dtype=np.uint8),
        visible_injections=[
            {
                "label": "PatientName",
                "text": "Doe^Jane",
                "identity_field": "patient_name",
                "renderer_type": "handwriting_asset",
                "asset_id": "patient-name-001",
                "asset": asset,
                "rotation_degrees": 0,
            },
            {
                "label": "PatientName",
                "text": "Doe^Jane",
                "identity_field": "patient_name",
                "renderer_type": "handwriting_asset",
                "asset_id": "patient-name-001",
                "asset": asset,
                "rotation_degrees": 0,
            },
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

    assert len(result["render_metadata"]["visible_annotations"]) == 2
    assert prepare_calls == 2


def test_overlay_reuse_microbenchmark_fixture_is_reproducible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_pillow_default_font(monkeypatch)

    first = _run_font_fixture(tmp_path)
    second = _run_font_fixture(tmp_path)

    first_digest = hashlib.sha256(first["output_array"].tobytes()).hexdigest()
    second_digest = hashlib.sha256(second["output_array"].tobytes()).hexdigest()
    assert first_digest == second_digest
    assert (
        len(first["render_metadata"]["visible_annotations"])
        == len(second["render_metadata"]["visible_annotations"])
        == 2
    )
