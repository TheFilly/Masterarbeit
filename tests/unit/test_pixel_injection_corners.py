import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "prototypes" / "dicom"))

from pixel_injection import _estimate_rotated_size, _rotated_corners

import pytest


def _corners_to_tuples(corners: list[dict[str, float]]) -> list[tuple[float, float]]:
    return [(c["x"], c["y"]) for c in corners]


def test_rotated_corners_zero_degrees() -> None:
    corners = _rotated_corners(
        position=(0, 0),
        unrotated_size=(100, 20),
        rotated_size=(100, 20),
        rotation_degrees=0,
    )
    result = _corners_to_tuples(corners)
    expected = [(0.0, 0.0), (100.0, 0.0), (100.0, 20.0), (0.0, 20.0)]
    assert result == pytest.approx(expected, abs=0.1)


def test_rotated_corners_90_degrees_ccw() -> None:
    corners = _rotated_corners(
        position=(0, 0),
        unrotated_size=(100, 20),
        rotated_size=(20, 100),
        rotation_degrees=90,
    )
    result = _corners_to_tuples(corners)
    expected = [(0.0, 100.0), (0.0, 0.0), (20.0, 0.0), (20.0, 100.0)]
    assert result == pytest.approx(expected, abs=0.1)


def test_rotated_corners_180_degrees() -> None:
    corners = _rotated_corners(
        position=(0, 0),
        unrotated_size=(100, 20),
        rotated_size=(100, 20),
        rotation_degrees=180,
    )
    result = _corners_to_tuples(corners)
    expected = [(100.0, 20.0), (0.0, 20.0), (0.0, 0.0), (100.0, 0.0)]
    assert result == pytest.approx(expected, abs=0.1)


@pytest.mark.parametrize("angle", [0, 20, 90, 180, 270])
def test_rotated_corners_bounding_box_matches_estimate(angle: int) -> None:
    width, height = 100, 20
    rotated_size = _estimate_rotated_size(
        width=width, height=height, rotation_degrees=angle
    )
    corners = _rotated_corners(
        position=(0, 0),
        unrotated_size=(width, height),
        rotated_size=rotated_size,
        rotation_degrees=angle,
    )
    xs = [c["x"] for c in corners]
    ys = [c["y"] for c in corners]
    bbox_width = max(xs) - min(xs)
    bbox_height = max(ys) - min(ys)
    assert bbox_width == pytest.approx(rotated_size[0], abs=1.0)
    assert bbox_height == pytest.approx(rotated_size[1], abs=1.0)
