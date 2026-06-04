import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "prototypes" / "dicom"))

import inject


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

    candidates = inject._collect_default_input_candidates(dicom_dir, image_dir)

    assert candidates == [
        dicom_dir / "scan_b.dcm",
        image_dir / "face.jpeg",
        image_dir / "face.jpg",
    ]


def test_select_random_default_input_rejects_empty_candidates() -> None:
    with pytest.raises(ValueError, match="No default input files found"):
        inject._select_random_default_input([])


def test_resolve_input_path_prefers_explicit_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit_path = Path("custom/source.dcm")

    def fail_if_called() -> Path:
        raise AssertionError("default selector should not run for explicit input")

    monkeypatch.setattr(inject, "_select_default_input_path", fail_if_called)

    input_path, was_auto_selected = inject._resolve_input_path(str(explicit_path))

    assert input_path == explicit_path
    assert was_auto_selected is False


def test_resolve_input_path_uses_default_selector_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_path = Path("DycomData/images/random.jpg")

    monkeypatch.setattr(inject, "_select_default_input_path", lambda: selected_path)

    input_path, was_auto_selected = inject._resolve_input_path(None)

    assert input_path == selected_path
    assert was_auto_selected is True


def test_prompt_for_input_path_accepts_random_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_path = Path("DycomData/images/random.jpg")
    prompts = iter([""])

    monkeypatch.setattr("builtins.input", lambda _: next(prompts))
    monkeypatch.setattr(inject, "_select_default_input_path", lambda: selected_path)

    assert inject._prompt_for_input_path() is None


def test_prompt_for_input_path_accepts_explicit_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "source.dcm"
    input_path.write_bytes(b"")
    prompts = iter(["n", str(input_path)])

    monkeypatch.setattr("builtins.input", lambda _: next(prompts))

    assert inject._prompt_for_input_path() == str(input_path)


def test_prompt_for_input_path_retries_missing_explicit_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "source.jpg"
    input_path.write_bytes(b"")
    prompts = iter(["n", str(tmp_path / "missing.jpg"), str(input_path)])

    monkeypatch.setattr("builtins.input", lambda _: next(prompts))

    assert inject._prompt_for_input_path() == str(input_path)
