import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

TOOL_ROOT = (
    Path(__file__).parent.parent.parent / "tools" / "handwriting" / "scrabblegan"
)
sys.path.insert(0, str(TOOL_ROOT))

from scrabblegan_tool.cli import run_render, run_validate  # noqa: E402
from scrabblegan_tool.hashing import sha256_file  # noqa: E402
from scrabblegan_tool.manifest import load_input_manifest  # noqa: E402
from scrabblegan_tool.masks import build_asset_images  # noqa: E402
from scrabblegan_tool.validate import validate_output_manifest  # noqa: E402


def _write_checkpoint(tmp_path: Path) -> tuple[Path, str]:
    checkpoint_path = tmp_path / "model.pth"
    checkpoint_path.write_bytes(b"checkpoint")
    return checkpoint_path, hashlib.sha256(b"checkpoint").hexdigest()


def _write_source(tmp_path: Path) -> Path:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / ".git_commit").write_text("abc123\n", encoding="utf-8")
    return source_dir


def _write_input_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "batch.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "asset_id": "patient-name-001",
                "field": "patient_name",
                "text": "Doe^Jane",
                "ink_color": "black",
                "background": "transparent",
                "seed": 42,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_load_input_manifest_rejects_duplicate_asset_ids(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.jsonl"
    record = {
        "asset_id": "dup",
        "field": "patient_name",
        "text": "Doe^Jane",
        "ink_color": "black",
        "background": "transparent",
        "seed": 42,
    }
    manifest_path.write_text(
        json.dumps(record) + "\n" + json.dumps(record) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate asset_id"):
        load_input_manifest(manifest_path)


@pytest.mark.parametrize(
    ("field", "ink_color", "background", "text"),
    [
        ("patient_birth_date", "black", "transparent", "Doe^Jane"),
        ("patient_name", "blue", "transparent", "Doe^Jane"),
        ("patient_name", "black", "paper", "Doe^Jane"),
        ("patient_name", "black", "transparent", ""),
    ],
)
def test_load_input_manifest_rejects_invalid_records(
    tmp_path: Path,
    field: str,
    ink_color: str,
    background: str,
    text: str,
) -> None:
    manifest_path = tmp_path / "batch.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "asset_id": "asset-001",
                "field": field,
                "text": text,
                "ink_color": ink_color,
                "background": background,
                "seed": 42,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_input_manifest(manifest_path)


def test_build_asset_images_writes_rgba_image_mask_and_bbox(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.png"
    raw = Image.new("RGBA", (6, 5), (0, 0, 0, 0))
    raw.putpixel((2, 1), (10, 10, 10, 255))
    raw.putpixel((4, 3), (10, 10, 10, 255))
    raw.save(raw_path)

    image_path = tmp_path / "images" / "asset.png"
    mask_path = tmp_path / "masks" / "asset-mask.png"
    metadata = build_asset_images(
        raw_path=raw_path,
        image_path=image_path,
        mask_path=mask_path,
        ink_color="black",
        background="transparent",
    )

    assert Image.open(image_path).mode == "RGBA"
    assert Image.open(mask_path).mode == "L"
    assert metadata["ink_bbox"] == {"x": 2, "y": 1, "width": 3, "height": 3}
    assert metadata["image_size"] == {"width": 6, "height": 5}


def test_build_asset_images_rejects_empty_masks(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.png"
    Image.new("RGBA", (6, 5), (0, 0, 0, 0)).save(raw_path)

    with pytest.raises(ValueError, match="empty ink mask"):
        build_asset_images(
            raw_path=raw_path,
            image_path=tmp_path / "image.png",
            mask_path=tmp_path / "mask.png",
            ink_color="black",
            background="transparent",
        )


def test_validate_output_manifest_rejects_hash_mismatch(tmp_path: Path) -> None:
    image_path = tmp_path / "images" / "asset.png"
    mask_path = tmp_path / "masks" / "asset-mask.png"
    image_path.parent.mkdir()
    mask_path.parent.mkdir()
    Image.new("RGBA", (2, 2), (0, 0, 0, 255)).save(image_path)
    Image.new("L", (2, 2), 255).save(mask_path)
    checkpoint_path, checkpoint_sha = _write_checkpoint(tmp_path)
    manifest_path = tmp_path / "manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "asset_id": "asset",
                "field": "patient_name",
                "text": "Doe^Jane",
                "image_path": "images/asset.png",
                "mask_path": "masks/asset-mask.png",
                "image_sha256": "wrong",
                "mask_sha256": sha256_file(mask_path),
                "checkpoint_sha256": checkpoint_sha,
                "scrabblegan_repo_url": "local",
                "scrabblegan_commit": "abc123",
                "ink_color": "black",
                "background": "transparent",
                "seed": 42,
                "ink_bbox": {"x": 0, "y": 0, "width": 2, "height": 2},
                "image_size": {"width": 2, "height": 2},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="image_sha256"):
        validate_output_manifest(manifest_path, checkpoint_path, checkpoint_sha)


def test_render_cli_with_fake_renderer_writes_valid_manifest(tmp_path: Path) -> None:
    input_path = _write_input_manifest(tmp_path)
    source_dir = _write_source(tmp_path)
    checkpoint_path, checkpoint_sha = _write_checkpoint(tmp_path)
    output_root = tmp_path / "runs"

    manifest_path = run_render(
        [
            "--input",
            str(input_path),
            "--output-root",
            str(output_root),
            "--run-id",
            "unit-run",
            "--source-dir",
            str(source_dir),
            "--checkpoint",
            str(checkpoint_path),
            "--checkpoint-sha256",
            checkpoint_sha,
            "--fake-renderer",
        ]
    )

    assert manifest_path == output_root / "unit-run" / "manifest.jsonl"
    assert (
        run_validate(
            [
                "--manifest",
                str(manifest_path),
                "--checkpoint",
                str(checkpoint_path),
                "--checkpoint-sha256",
                checkpoint_sha,
            ]
        )
        == 0
    )
    record = json.loads(manifest_path.read_text(encoding="utf-8").strip())
    assert record["image_path"] == "images/patient-name-001.png"
    assert record["mask_path"] == "masks/patient-name-001-mask.png"
    assert record["image_sha256"] == sha256_file(
        manifest_path.parent / record["image_path"]
    )
