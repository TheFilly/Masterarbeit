"""Unit tests for the standalone preview module CLI."""

import sys
from pathlib import Path
from typing import Any

import pytest

from injection_pipeline.writers import preview


def test_preview_cli_requires_explicit_dicom(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["preview"])

    with pytest.raises(SystemExit) as exc_info:
        preview.main()

    assert exc_info.value.code == 2
    assert "--dicom" in capsys.readouterr().err


def test_preview_cli_defaults_to_no_show(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, Any] = {}

    def fake_create_preview(
        source_path: str | Path,
        output_path: str | Path = preview.DEFAULT_PREVIEW_PATH,
        visible_annotations: list[dict[str, Any]] | None = None,
        title: str | None = None,
        show: bool = False,
    ) -> Path:
        calls.update(
            {
                "source_path": source_path,
                "output_path": output_path,
                "visible_annotations": visible_annotations,
                "title": title,
                "show": show,
            }
        )
        return Path(output_path)

    output_path = tmp_path / "preview.png"
    monkeypatch.setattr(preview, "create_preview", fake_create_preview)
    monkeypatch.setattr(
        sys,
        "argv",
        ["preview", "--dicom", "input.dcm", "--output", str(output_path)],
    )

    preview.main()

    assert calls == {
        "source_path": "input.dcm",
        "output_path": str(output_path),
        "visible_annotations": None,
        "title": None,
        "show": False,
    }
