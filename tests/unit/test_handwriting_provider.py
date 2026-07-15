import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

import injection_pipeline.handwriting.provider as provider_module
from injection_pipeline.config import load_identifier_schema
from injection_pipeline.config.identifier_schema import DEFAULT_IDENTIFIER_SCHEMA_PATH
from injection_pipeline.handwriting import (
    ALLOWED_HANDWRITING_FIELDS,
    DockerHandwritingGenerator,
    GeneratedHandwritingManifest,
    HandwritingAlphabetError,
    HandwritingAssetProvider,
    HandwritingCacheIdentity,
    HandwritingGenerationRequest,
    HandwritingGenerationResult,
    HandwritingGeneratorOptions,
    HandwritingProviderError,
    HandwritingRuntimeConfig,
    MissingHandwritingCheckpointError,
)
from injection_pipeline.models import Identity


class FakeHandwritingGenerator:
    def __init__(self) -> None:
        self.calls: list[HandwritingGenerationRequest] = []

    def generate(
        self, request: HandwritingGenerationRequest
    ) -> HandwritingGenerationResult:
        self.calls.append(request)
        run_dir = request.output_root / request.run_id
        records = []
        for asset in request.assets:
            image_path = run_dir / "images" / f"{asset.asset_id}.png"
            mask_path = run_dir / "masks" / f"{asset.asset_id}-mask.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            mask_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (2, 2), (0, 0, 0, 255)).save(image_path)
            Image.new("L", (2, 2), 255).save(mask_path)
            records.append(
                {
                    "asset_id": asset.asset_id,
                    "field": asset.field,
                    "text": asset.text,
                    "image_path": image_path.relative_to(run_dir).as_posix(),
                    "mask_path": mask_path.relative_to(run_dir).as_posix(),
                    "image_sha256": _sha256_file(image_path),
                    "mask_sha256": _sha256_file(mask_path),
                    "checkpoint_sha256": request.checkpoint_sha256,
                    "generator_options_sha256": request.options.options_sha256,
                    "scrabblegan_repo_url": "local-test",
                    "scrabblegan_commit": request.upstream_commit,
                    "ink_color": request.options.ink_color,
                    "background": request.options.background,
                    "seed": asset.identity.seed,
                    "ink_bbox": {"x": 0, "y": 0, "width": 2, "height": 2},
                    "image_size": {"width": 2, "height": 2},
                }
            )
        manifest_path = run_dir / "manifest.jsonl"
        manifest_path.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )
        return HandwritingGenerationResult(manifest_path=manifest_path)


class FailingHandwritingGenerator:
    def generate(
        self, request: HandwritingGenerationRequest
    ) -> HandwritingGenerationResult:
        raise HandwritingProviderError("generator exploded")


class MismatchedOptionsGenerator(FakeHandwritingGenerator):
    def generate(
        self, request: HandwritingGenerationRequest
    ) -> HandwritingGenerationResult:
        result = super().generate(request)
        records = [
            {
                **json.loads(line),
                "generator_options_sha256": "0" * 64,
            }
            for line in result.manifest_path.read_text(encoding="utf-8").splitlines()
        ]
        result.manifest_path.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )
        return result


def test_cache_identity_key_includes_required_inputs() -> None:
    base = _cache_identity(text="Doe^Jane")
    changed_text = _cache_identity(text="Roe^Jane")
    changed_schema = _cache_identity(text="Doe^Jane", schema_version="2.0.0")
    changed_options = _cache_identity(
        text="Doe^Jane",
        generator_options={
            "generator_name": "scrabblegan",
            "ink_color": "gray",
            "background": "transparent",
            "alphabet": "abc",
            "options_sha256": _options_sha(),
            "word_gap_px": 12,
            "cpu_only": True,
            "extra": {"options_sidecar_name": "test_opt.txt"},
        },
    )

    assert base.cache_key == _cache_identity(text="Doe^Jane").cache_key
    assert len(base.cache_key) == 64
    assert changed_text.cache_key != base.cache_key
    assert changed_schema.cache_key != base.cache_key
    assert changed_options.cache_key != base.cache_key


def test_provider_filters_to_three_visible_handwriting_fields(tmp_path: Path) -> None:
    provider, generator = _provider(tmp_path)
    result = provider.resolve_assets(_identity(), _schema())

    assert isinstance(result, GeneratedHandwritingManifest)
    assert set(result.asset_mappings) == ALLOWED_HANDWRITING_FIELDS
    assert len(generator.calls) == 1
    request = generator.calls[0]
    assert [asset.field for asset in request.assets] == [
        "patient_name",
        "patient_id",
        "accession_number",
    ]


def test_cache_miss_generates_and_cache_hit_skips_generator(tmp_path: Path) -> None:
    provider, generator = _provider(tmp_path)
    first_result = provider.resolve_assets(_identity(), _schema())

    assert len(generator.calls) == 1
    assert len(first_result.generated_asset_ids) == 3
    assert first_result.cache_hit_asset_ids == []
    assert (
        first_result.manifest_path == tmp_path / "assets" / "seed-42" / "manifest.json"
    )

    payload = json.loads(first_result.manifest_path.read_text(encoding="utf-8"))
    for asset in payload["assets"]:
        assert not Path(asset["image_path"]).is_absolute()
        assert not Path(asset["mask_path"]).is_absolute()
        assert asset["cache_identity"]["seed"] == 42
        assert asset["cache_identity"]["schema_id"] == "dicom-prototype"
        assert asset["cache_identity"]["schema_version"] == "1.0.0"
        assert asset["cache_identity"]["checkpoint_sha256"] == _checkpoint_sha()
        assert asset["cache_identity"]["upstream_commit"] == "upstream-abc"
        assert (
            asset["cache_identity"]["generator_options"]["options_sha256"]
            == _options_sha()
        )

    second_generator = FakeHandwritingGenerator()
    second_provider = HandwritingAssetProvider(
        runtime=_runtime(tmp_path),
        options=_options(),
        generator=second_generator,
    )
    second_result = second_provider.resolve_assets(_identity(), _schema())

    assert second_generator.calls == []
    assert second_result.generated_asset_ids == []
    assert set(second_result.cache_hit_asset_ids) == set(
        first_result.generated_asset_ids
    )


def test_provider_rejects_incompatible_alphabet_without_generator_call(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "checkpoint.pth"
    checkpoint_path.write_bytes(b"checkpoint")
    generator = FakeHandwritingGenerator()
    provider = HandwritingAssetProvider(
        runtime=_runtime(tmp_path),
        options=HandwritingGeneratorOptions(
            alphabet="ABC123-",
            options_sha256=_options_sha(),
        ),
        generator=generator,
    )

    with pytest.raises(HandwritingAlphabetError, match="outside"):
        provider.resolve_assets(_identity(), _schema())

    assert generator.calls == []


def test_provider_rejects_missing_checkpoint_before_generator_call(
    tmp_path: Path,
) -> None:
    runtime = HandwritingRuntimeConfig(
        checkpoint_path=tmp_path / "missing.pth",
        checkpoint_sha256=_checkpoint_sha(),
        upstream_commit="upstream-abc",
        asset_root=tmp_path / "assets",
    )
    generator = FakeHandwritingGenerator()
    provider = HandwritingAssetProvider(
        runtime=runtime,
        options=_options(),
        generator=generator,
    )

    with pytest.raises(MissingHandwritingCheckpointError, match="not found"):
        provider.resolve_assets(_identity(), _schema())

    assert generator.calls == []


def test_provider_propagates_generator_errors(tmp_path: Path) -> None:
    provider = HandwritingAssetProvider(
        runtime=_runtime(tmp_path),
        options=_options(),
        generator=FailingHandwritingGenerator(),
    )

    with pytest.raises(HandwritingProviderError, match="generator exploded"):
        provider.resolve_assets(_identity(), _schema())


def test_docker_generator_mounts_workspace_and_translates_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    checkpoint_path = tmp_path / "checkpoint.pth"
    checkpoint_path.write_bytes(b"checkpoint")
    options_path = tmp_path / "test_opt.txt"
    options_path.write_text("alphabet: ABC123-\n", encoding="utf-8")
    input_manifest_path = tmp_path / "work" / "input.jsonl"
    input_manifest_path.parent.mkdir()
    input_manifest_path.write_text("{}\n", encoding="utf-8")
    output_root = tmp_path / "work" / "generated"
    request = HandwritingGenerationRequest(
        input_manifest_path=input_manifest_path,
        output_root=output_root,
        run_id="run-001",
        source_dir=source_dir,
        options_sidecar_path=options_path,
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=_checkpoint_sha(),
        upstream_commit="upstream-abc",
        generator_command=None,
        options=HandwritingGeneratorOptions(
            alphabet="ABC123-",
            options_sha256=_options_sha(),
        ),
        assets=[],
    )
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[1:3] == ["image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        manifest_path = output_root / "run-001" / "manifest.jsonl"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(provider_module.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(provider_module.subprocess, "run", fake_run)

    result = DockerHandwritingGenerator(
        image="injection-scrabblegan",
        workspace_root=tmp_path,
    ).generate(request)

    assert result.manifest_path == output_root / "run-001" / "manifest.jsonl"
    docker_run = calls[1]
    assert docker_run[:3] == ["docker", "run", "--rm"]
    assert "type=bind,source=" in docker_run[6]
    assert "target=/workspace" in docker_run[6]
    assert "/workspace/work/input.jsonl" in docker_run
    assert "/workspace/source" in docker_run
    assert "/workspace/checkpoint.pth" in docker_run
    assert "/workspace/test_opt.txt" in docker_run


def test_provider_passes_options_sidecar_to_generator_request(tmp_path: Path) -> None:
    provider, generator = _provider(tmp_path)
    provider.resolve_assets(_identity(), _schema())

    assert generator.calls[0].options_sidecar_path == tmp_path / "test_opt.txt"
    assert generator.calls[0].options.options_sha256 == _options_sha()


def test_provider_rejects_generated_manifest_with_wrong_options_hash(
    tmp_path: Path,
) -> None:
    provider = HandwritingAssetProvider(
        runtime=_runtime(tmp_path),
        options=_options(),
        generator=MismatchedOptionsGenerator(),
    )

    with pytest.raises(HandwritingProviderError, match="generator_options_sha256"):
        provider.resolve_assets(_identity(), _schema())


def _schema():
    return load_identifier_schema(DEFAULT_IDENTIFIER_SCHEMA_PATH)


def _identity() -> Identity:
    return Identity(
        identity_id="SYNTH-123456",
        seed=42,
        fields={
            "patient_name": "Doe^Jane",
            "patient_id": "SYNTH-123456",
            "patient_birth_date": "19800101",
            "patient_sex": "F",
            "accession_number": "ACC-7654321",
        },
    )


def _provider(
    tmp_path: Path,
) -> tuple[HandwritingAssetProvider, FakeHandwritingGenerator]:
    generator = FakeHandwritingGenerator()
    return (
        HandwritingAssetProvider(
            runtime=_runtime(tmp_path),
            options=_options(),
            generator=generator,
        ),
        generator,
    )


def _runtime(tmp_path: Path) -> HandwritingRuntimeConfig:
    checkpoint_path = tmp_path / "checkpoint.pth"
    checkpoint_path.write_bytes(b"checkpoint")
    options_path = tmp_path / "test_opt.txt"
    options_path.write_text("alphabet: Doe^JaneSYNTH-123456ACC-7654321\n")
    return HandwritingRuntimeConfig(
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=_checkpoint_sha(),
        upstream_commit="upstream-abc",
        asset_root=tmp_path / "assets",
        options_sidecar_path=options_path,
    )


def _checkpoint_sha() -> str:
    return hashlib.sha256(b"checkpoint").hexdigest()


def _options_sha() -> str:
    return hashlib.sha256(b"options").hexdigest()


def _options() -> HandwritingGeneratorOptions:
    return HandwritingGeneratorOptions(
        alphabet="Doe^JaneSYNTH-123456ACC-7654321",
        options_sha256=_options_sha(),
        extra={"options_sidecar_name": "test_opt.txt"},
    )


def _cache_identity(
    *,
    text: str,
    schema_version: str = "1.0.0",
    generator_options: dict[str, object] | None = None,
) -> HandwritingCacheIdentity:
    return HandwritingCacheIdentity(
        seed=42,
        schema_id="dicom-prototype",
        schema_version=schema_version,
        field="patient_name",
        text=text,
        checkpoint_sha256=_checkpoint_sha(),
        upstream_commit="upstream-abc",
        generator_options=generator_options or _options().model_dump(mode="json"),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
