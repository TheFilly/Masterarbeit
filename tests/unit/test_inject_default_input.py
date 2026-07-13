from pathlib import Path

import pytest

import injection_pipeline.runtime.cli as cli
import injection_pipeline.runtime.inputs as inputs


def test_collect_default_input_candidates_uses_dicom_and_image_dirs(
    tmp_path: Path,
) -> None:
    dicom_dir = tmp_path / "Dicom-Files"
    image_dir = tmp_path / "images"
    dicom_dir.mkdir()
    image_dir.mkdir()
    (dicom_dir / "scan_b.dcm").write_bytes(b"")
    (dicom_dir / "ignore.txt").write_text("not an input", encoding="utf-8")
    (image_dir / "face.jpeg").write_bytes(b"")
    (image_dir / "face.jpg").write_bytes(b"")
    (image_dir / "ignore.png").write_bytes(b"")

    candidates = inputs.collect_default_input_candidates(dicom_dir, image_dir)

    assert candidates == [
        dicom_dir / "scan_b.dcm",
        image_dir / "face.jpeg",
        image_dir / "face.jpg",
    ]


def test_select_seeded_default_input_rejects_empty_candidates() -> None:
    with pytest.raises(ValueError, match="No default input files found"):
        inputs.select_seeded_default_input([], seed=42)


def test_select_seeded_default_input_is_stable_over_sorted_candidates(
    tmp_path: Path,
) -> None:
    candidates = [
        tmp_path / "b.jpg",
        tmp_path / "a.dcm",
        tmp_path / "c.jpeg",
    ]

    assert inputs.select_seeded_default_input(candidates, seed=42) == tmp_path / "b.jpg"
    assert (
        inputs.select_seeded_default_input(list(reversed(candidates)), seed=42)
        == tmp_path / "b.jpg"
    )


def test_resolve_input_path_prefers_explicit_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit_path = Path("custom/source.dcm")

    def fail_if_called(seed: int) -> Path:
        _ = seed
        raise AssertionError("default selector should not run for explicit input")

    monkeypatch.setattr(inputs, "select_default_input_path", fail_if_called)

    input_path, was_auto_selected = inputs.resolve_input_path(str(explicit_path), 42)

    assert input_path == explicit_path
    assert was_auto_selected is False


def test_resolve_input_path_uses_default_selector_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_path = Path("DycomData/images/random.jpg")

    monkeypatch.setattr(inputs, "select_default_input_path", lambda seed: selected_path)

    input_path, was_auto_selected = inputs.resolve_input_path(None, 42)

    assert input_path == selected_path
    assert was_auto_selected is True


def test_prompt_for_input_path_accepts_random_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = iter([""])

    monkeypatch.setattr("builtins.input", lambda _: next(prompts))

    assert cli._prompt_for_input_path() is None


def test_prompt_for_input_path_accepts_explicit_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "source.dcm"
    input_path.write_bytes(b"")
    prompts = iter(["n", str(input_path)])

    monkeypatch.setattr("builtins.input", lambda _: next(prompts))

    assert cli._prompt_for_input_path() == str(input_path)


def test_prompt_for_input_path_retries_missing_explicit_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "source.jpg"
    input_path.write_bytes(b"")
    prompts = iter(["n", str(tmp_path / "missing.jpg"), str(input_path)])

    monkeypatch.setattr("builtins.input", lambda _: next(prompts))

    assert cli._prompt_for_input_path() == str(input_path)
