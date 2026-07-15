import hashlib
import json
from argparse import Namespace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

import injection_pipeline.engine.injector as injector
import injection_pipeline.engine.placement as placement
from injection_pipeline.config.identifier_schema import (
    DEFAULT_IDENTIFIER_SCHEMA_PATH,
    IdentifierSchema,
    load_identifier_schema,
)
from injection_pipeline.handwriting import (
    DockerHandwritingGenerator,
    GeneratedHandwritingManifest,
)
from injection_pipeline.identity.generator import generate_identity
from injection_pipeline.models import Identity
from injection_pipeline.runtime import runner
from injection_pipeline.runtime.options import HANDWRITING_FONT_FAMILY
from injection_pipeline.runtime.planning import build_visible_render_plan


class FakeProvider:
    def __init__(self, generated: GeneratedHandwritingManifest) -> None:
        self.generated = generated
        self.calls: list[tuple[Identity, IdentifierSchema]] = []

    def resolve_assets(
        self,
        identity: Identity,
        schema: IdentifierSchema,
    ) -> GeneratedHandwritingManifest:
        self.calls.append((identity, schema))
        return self.generated


def test_runner_attaches_provider_assets_for_handwriting_font(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = load_identifier_schema(DEFAULT_IDENTIFIER_SCHEMA_PATH)
    identity = generate_identity(42, schema)
    manifest_path = _write_handwriting_manifest(tmp_path, identity)
    generated = GeneratedHandwritingManifest(
        manifest_path=manifest_path,
        assets={},
        asset_mappings={
            "patient_name": "patient_name-asset",
            "patient_id": "patient_id-asset",
            "accession_number": "accession_number-asset",
        },
        generated_asset_ids=["patient_name-asset"],
        cache_hit_asset_ids=[],
    )
    provider = FakeProvider(generated)
    monkeypatch.setattr(runner, "_build_handwriting_provider", lambda args: provider)
    render_plan = build_visible_render_plan(
        identity=identity,
        schema=schema,
        rotation_degrees=0,
        placement_mode="corners",
    )

    updated = runner._resolve_handwriting_render_plan(
        _handwriting_args(tmp_path),
        identity,
        schema,
        render_plan,
    )

    assert len(provider.calls) == 1
    assert all(item["renderer_type"] == "handwriting_asset" for item in updated)
    assert {item["asset_id"] for item in updated} == {
        "patient_name-asset",
        "patient_id-asset",
        "accession_number-asset",
    }


def test_generate_handwriting_assets_uses_seeded_identity_and_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = load_identifier_schema(DEFAULT_IDENTIFIER_SCHEMA_PATH)
    identity = generate_identity(7, schema)
    manifest_path = _write_handwriting_manifest(tmp_path, identity)
    generated = GeneratedHandwritingManifest(
        manifest_path=manifest_path,
        assets={},
        asset_mappings={"patient_name": "patient_name-asset"},
        generated_asset_ids=["patient_name-asset"],
        cache_hit_asset_ids=[],
    )
    provider = FakeProvider(generated)
    monkeypatch.setattr(runner, "_build_handwriting_provider", lambda args: provider)

    result = runner.generate_handwriting_assets(_handwriting_args(tmp_path, seed=7))

    assert result == generated
    assert provider.calls[0][0].fields == identity.fields
    assert provider.calls[0][1].schema_id == schema.schema_id


def test_runner_provider_uses_checkpoint_options_sidecar_and_commit(
    tmp_path: Path,
) -> None:
    args = _handwriting_args(tmp_path)
    source_dir = Path(args.handwriting_source_dir)
    source_dir.mkdir()
    (source_dir / ".git_commit").write_text("upstream-sidecar\n", encoding="utf-8")
    options_path = Path(args.handwriting_checkpoint).with_name("test_opt.txt")
    options_path.write_text("alphabet: ABC123-\n", encoding="utf-8")

    provider = runner._build_handwriting_provider(args)

    assert provider._runtime.upstream_commit == "upstream-sidecar"
    assert provider._runtime.options_sidecar_path == options_path
    assert provider._options.alphabet == "ABC123-"
    assert provider._options.options_sha256 == _sha256_file(options_path)


def test_runner_defaults_to_docker_generator(tmp_path: Path) -> None:
    args = _handwriting_args(tmp_path)
    args.handwriting_runtime_command = None
    args.handwriting_container_image = "injection-scrabblegan"
    source_dir = Path(args.handwriting_source_dir)
    source_dir.mkdir()
    (source_dir / ".git_commit").write_text("upstream-sidecar\n", encoding="utf-8")
    Path(args.handwriting_checkpoint).with_name("test_opt.txt").write_text(
        "alphabet: ABC123-\n",
        encoding="utf-8",
    )

    provider = runner._build_handwriting_provider(args)

    assert isinstance(provider._generator, DockerHandwritingGenerator)
    assert provider._generator._image == "injection-scrabblegan"


def test_runner_provider_rejects_source_without_commit_metadata(
    tmp_path: Path,
) -> None:
    args = _handwriting_args(tmp_path)
    Path(args.handwriting_source_dir).mkdir()
    Path(args.handwriting_checkpoint).with_name("test_opt.txt").write_text(
        "alphabet: ABC123-\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source metadata missing"):
        runner._build_handwriting_provider(args)


def test_handwriting_font_bypasses_default_font_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _write_single_asset(tmp_path, "patient_name-asset", "Doe^Jane")

    def fail_font_loader(**kwargs: Any) -> object:
        raise AssertionError("font loader must not run for handwriting assets")

    monkeypatch.setattr(injector, "load_default_font", fail_font_loader)
    monkeypatch.setattr(placement, "load_default_font", fail_font_loader)

    result = injector._inject_visible_text_into_frame(
        frame=np.full((80, 120, 3), 255, dtype=np.uint8),
        visible_injections=[
            {
                "label": "PatientName",
                "text": "Doe^Jane",
                "text_segments": [{"kind": "pii", "text": "Doe^Jane"}],
                "identity_field": "patient_name",
                "region": "corners",
                "rotation_degrees": 0,
                "line_index": 0,
                "renderer_type": "handwriting_asset",
                "asset_id": "patient_name-asset",
                "asset": asset,
            }
        ],
        preview_path=tmp_path / "preview.png",
        seed=42,
        rotation_degrees=0,
        font_size_pct=100,
        placement_mode="corners",
        font_family=HANDWRITING_FONT_FAMILY,
        text_background=None,
        frame_count=1,
    )

    assert result["render_metadata"]["renderer_types"] == ["handwriting_asset"]
    assert result["render_metadata"]["effective_font_family"] == "handwriting"


def test_handwriting_font_rejects_missing_asset_renderer(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires handwriting assets"):
        injector._inject_visible_text_into_frame(
            frame=np.full((80, 120, 3), 255, dtype=np.uint8),
            visible_injections=[
                {
                    "label": "PatientName",
                    "text": "Doe^Jane",
                    "text_segments": [{"kind": "pii", "text": "Doe^Jane"}],
                    "identity_field": "patient_name",
                    "region": "corners",
                    "rotation_degrees": 0,
                    "line_index": 0,
                }
            ],
            preview_path=tmp_path / "preview.png",
            seed=42,
            rotation_degrees=0,
            font_size_pct=100,
            placement_mode="corners",
            font_family=HANDWRITING_FONT_FAMILY,
            text_background=None,
            frame_count=1,
        )


def _handwriting_args(tmp_path: Path, seed: int = 42) -> Namespace:
    checkpoint_path = tmp_path / "checkpoint.pth"
    checkpoint_path.write_bytes(b"checkpoint")
    return Namespace(
        seed=seed,
        identifier_schema=str(DEFAULT_IDENTIFIER_SCHEMA_PATH),
        font_family=HANDWRITING_FONT_FAMILY,
        handwriting_manifest=None,
        handwriting_asset=[],
        handwriting_asset_root=str(tmp_path / "assets"),
        handwriting_checkpoint=str(checkpoint_path),
        handwriting_checkpoint_sha256="fe4a8b211f52fb3cfbd8895b7576071e0f329ca810269dc56e1e2965a7cdbfd4",
        handwriting_options_json=None,
        handwriting_source_dir=str(tmp_path / "source"),
        handwriting_upstream_commit=None,
        handwriting_runtime_command=(
            "uv run python -m tools.handwriting.scrabblegan.scrabblegan_tool.cli render"
        ),
        handwriting_generator_command=None,
    )


def _write_handwriting_manifest(tmp_path: Path, identity: Identity) -> Path:
    assets = [
        _write_single_asset(tmp_path, f"{field}-asset", identity.fields[field])
        for field in ("patient_name", "patient_id", "accession_number")
    ]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0-handwriting-assets",
                "assets": [
                    {
                        **asset,
                        "image_path": Path(asset["image_path"])
                        .relative_to(tmp_path)
                        .as_posix(),
                        "mask_path": Path(asset["mask_path"])
                        .relative_to(tmp_path)
                        .as_posix(),
                    }
                    for asset in assets
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def _write_single_asset(tmp_path: Path, asset_id: str, text: str) -> dict[str, Any]:
    image_path = tmp_path / "images" / f"{asset_id}.png"
    mask_path = tmp_path / "masks" / f"{asset_id}-mask.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (12, 6), (0, 0, 0, 0)).save(image_path)
    image = Image.open(image_path).convert("RGBA")
    for x in range(2, 10):
        image.putpixel((x, 3), (0, 0, 0, 255))
    image.save(image_path)
    mask = Image.new("L", (12, 6), 0)
    for x in range(2, 10):
        mask.putpixel((x, 3), 255)
    mask.save(mask_path)
    field = asset_id.removesuffix("-asset")
    return {
        "asset_id": asset_id,
        "identity_field": field,
        "text": text,
        "image_path": image_path,
        "mask_path": mask_path,
        "ink_color": "black",
        "background_mode": "transparent",
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
