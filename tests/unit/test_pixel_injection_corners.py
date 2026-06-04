import sys
from pathlib import Path

import numpy as np
import pydicom
import pytest
from PIL import Image, ImageFont
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "prototypes" / "dicom"))

from pixel_injection import (
    _build_box_annotation,
    _estimate_rotated_size,
    _prepare_annotation_overlay,
    _render_single_annotation,
    _rotated_corners,
    _split_prefix_and_pii_text,
    _write_pixel_array,
)


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


def test_split_prefix_and_pii_text_for_prefixed_identifier() -> None:
    prefix_text, pii_text = _split_prefix_and_pii_text(
        [
            {"kind": "generic", "text": "ACC-"},
            {"kind": "pii", "text": "0013389"},
        ]
    )
    assert prefix_text == "ACC-"
    assert pii_text == "0013389"


def test_build_box_annotation_keeps_optional_label_corners() -> None:
    annotation = _build_box_annotation(
        {
            "label": "PatientID",
            "text": "433218",
            "rendered_text": "SYNTH-433218",
            "region": "top_left",
            "corners": [{"x": 1.0, "y": 2.0}] * 4,
            "label_corners": [{"x": 3.0, "y": 4.0}] * 4,
            "rotation_degrees": 20,
        },
        font_size_pct=120,
    )
    assert annotation["label_corners"] == [{"x": 3.0, "y": 4.0}] * 4
    assert annotation["font_size_pct"] == 120


def test_prepare_annotation_overlay_tracks_mask_bounds_separately() -> None:
    font = ImageFont.load_default()
    overlay = _prepare_annotation_overlay(
        {
            "label": "PatientID",
            "text": "SYNTH-433218",
            "text_segments": [
                {"kind": "generic", "text": "SYNTH-"},
                {"kind": "pii", "text": "433218"},
            ],
            "rotation_degrees": 0,
            "padding": 4,
            "stroke_width": 0,
        },
        font,
        font_family="unit_test",
        text_background="white",
    )

    pii_bounds = overlay["pii_rotated_bounds"]
    label_bounds = overlay["label_rotated_bounds"]
    text_bounds = overlay["text_rotated_bounds"]

    assert label_bounds is not None
    assert label_bounds[0] < pii_bounds[0]
    assert label_bounds[2] <= pii_bounds[0] + 1
    assert text_bounds[0] <= label_bounds[0]
    assert text_bounds[2] >= pii_bounds[2]
    assert (
        overlay["render_metadata"]["geometry_source"]
        == "mask_bbox_after_final_rotation"
    )


def test_render_single_annotation_background_does_not_expand_pii_box() -> None:
    image = Image.new("RGB", (220, 80), (0, 0, 0))
    font = ImageFont.load_default()
    _, record = _render_single_annotation(
        image,
        {
            "label": "AccessionNumber",
            "text": "ACC-0013389",
            "text_segments": [
                {"kind": "generic", "text": "ACC-"},
                {"kind": "pii", "text": "0013389"},
            ],
            "rotation_degrees": 0,
            "padding": 4,
            "stroke_width": 0,
            "position": (20, 10),
        },
        font,
        font_family="unit_test",
        text_background="white",
    )

    pii_width = record["corners"][1]["x"] - record["corners"][0]["x"]
    rendered_width = (
        record["render_metadata"]["rendered_text_corners"][1]["x"]
        - record["render_metadata"]["rendered_text_corners"][0]["x"]
    )

    assert record["label_corners"] is not None
    assert record["render_metadata"]["background_enabled"] is True
    assert record["render_metadata"]["pii_mask_bounds"]["width"] == pytest.approx(
        pii_width, abs=1.0
    )
    assert rendered_width > pii_width


def test_render_single_annotation_rotated_box_uses_polygon_corners() -> None:
    image = Image.new("RGB", (260, 120), (0, 0, 0))
    font = ImageFont.load_default()
    _, record = _render_single_annotation(
        image,
        {
            "label": "PatientID",
            "text": "ACC-0013389",
            "text_segments": [
                {"kind": "generic", "text": "ACC-"},
                {"kind": "pii", "text": "0013389"},
            ],
            "rotation_degrees": 20,
            "padding": 4,
            "stroke_width": 0,
            "position": (20, 20),
        },
        font,
        font_family="unit_test",
        text_background="white",
    )

    corners = record["corners"]
    assert corners[0]["y"] != pytest.approx(corners[1]["y"], abs=0.5)
    assert corners[1]["x"] != pytest.approx(corners[2]["x"], abs=0.5)
    assert record["render_metadata"]["rendered_text_corners"][0]["y"] != pytest.approx(
        record["render_metadata"]["rendered_text_corners"][1]["y"], abs=0.5
    )


def test_write_pixel_array_updates_metadata_for_rgb_output(tmp_path: Path) -> None:
    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.ImplementationClassUID = generate_uid()

    dataset = FileDataset(
        str(tmp_path / "source.dcm"),
        {},
        file_meta=file_meta,
        preamble=b"\0" * 128,
    )
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    dataset.Rows = 2
    dataset.Columns = 2
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.PixelData = (np.zeros((2, 2), dtype=np.uint16)).tobytes()
    dataset.is_implicit_VR = False
    dataset.is_little_endian = True

    rgb_pixels = np.zeros((2, 2, 3), dtype=np.uint8)
    _write_pixel_array(dataset, rgb_pixels)

    output_path = tmp_path / "rewritten.dcm"
    pydicom.dcmwrite(str(output_path), dataset)
    reloaded = pydicom.dcmread(str(output_path))

    assert reloaded.SamplesPerPixel == 3
    assert reloaded.PhotometricInterpretation == "RGB"
    assert reloaded.BitsAllocated == 8
    assert reloaded.BitsStored == 8
    assert reloaded.HighBit == 7
    assert reloaded.PixelRepresentation == 0
    assert reloaded.PlanarConfiguration == 0
    assert reloaded.pixel_array.shape == (2, 2, 3)
