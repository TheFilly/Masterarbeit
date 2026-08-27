from datetime import datetime
from pathlib import Path

import pytest

from injection_pipeline.runtime.run_layout import (
    build_output_paths,
    build_run_id,
    ensure_run_directory_available,
)


def test_build_output_paths_rejects_unsafe_run_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="safe single path segment"):
        build_output_paths(tmp_path, "..\\escape", "source", ".jpg")


def test_run_directory_reuse_is_rejected(tmp_path: Path) -> None:
    run_id = build_run_id(
        filetype="jpg",
        run_timestamp=datetime(2026, 7, 10, 12, 34, 0),
        seed=42,
        rotation_degrees=0,
        placement_mode="corners",
        font_size_pct=100,
        font_family="arial",
        text_background=None,
    )
    run_dir = tmp_path / run_id
    run_dir.mkdir()

    with pytest.raises(ValueError, match="run directory already exists"):
        ensure_run_directory_available(run_dir)


def test_build_run_id_includes_result_relevant_options(tmp_path: Path) -> None:
    base = dict(
        filetype="dcm",
        run_timestamp=datetime(2026, 7, 10, 12, 34, 0),
        seed=42,
        rotation_degrees=0,
        placement_mode="corners",
        font_size_pct=100,
        font_family="arial",
        text_background=None,
    )
    default = build_run_id(**base)
    label_boxes = build_run_id(**base, show_label_boxes="y")
    ink_color = build_run_id(**base, handwriting_ink_color="black")
    contrast_mode = build_run_id(**base, handwriting_contrast_mode="halo")

    assert len({default, label_boxes, ink_color, contrast_mode}) == 4
    assert default == build_run_id(**base)
    assert all(
        build_output_paths(tmp_path, run_id, "source", ".dcm")["run_dir"].name
        == run_id
        for run_id in (default, label_boxes, ink_color, contrast_mode)
    )
