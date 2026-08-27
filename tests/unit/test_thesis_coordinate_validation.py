"""Tests für die reproduzierbare Thesis-Koordinatenauswertung."""

import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from tools.thesis_results.coordinate_validation.coordinate_validation import (
    analyse_distribution,
    analyse_ground_truth,
    bounding_box_from_corners,
    compare_rendered_bbox,
    compare_rendered_image,
    foreground_mask,
    load_rendered_pixels,
    normalize_bounding_box,
    pdf_corners_to_pixel,
    pdf_point_to_pixel,
    render_pdf_page,
    validate_bounding_box,
    write_results_csv,
)


def test_bounding_box_from_rotated_corners_uses_all_points() -> None:
    corners = [(10, 20), (30, 10), (40, 30), (20, 40)]

    assert bounding_box_from_corners(corners) == (10.0, 10.0, 40.0, 40.0)


def test_normalize_bounding_box_is_independent_of_image_size() -> None:
    corners = [
        {"x": 10, "y": 20},
        {"x": 30, "y": 20},
        {"x": 30, "y": 40},
        {"x": 10, "y": 40},
    ]

    result = normalize_bounding_box(corners, 100, 100)

    assert result["center_x"] == pytest.approx(0.2)
    assert result["center_y"] == pytest.approx(0.3)


def test_validate_bounding_box_detects_clipping_and_tolerance() -> None:
    corners = [(-1, 5), (20, 5), (20, 15), (-1, 15)]

    invalid = validate_bounding_box(corners, 100, 100)
    tolerated = validate_bounding_box(corners, 100, 100, tolerance=1)

    assert not invalid.within_bounds
    assert not invalid.text_not_clipped
    assert invalid.issues == "left_out_of_bounds"
    assert tolerated.within_bounds


def test_analyse_ground_truth_and_write_csv(tmp_path: Path) -> None:
    ground_truth = tmp_path / "ground_truth.json"
    output_csv = tmp_path / "results.csv"
    ground_truth.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "document_type": "jpg",
                "box_annotations": [
                    {
                        "label": "PatientID",
                        "region": "top_left",
                        "frame_index": 0,
                        "corners": [
                            {"x": 10, "y": 10},
                            {"x": 30, "y": 10},
                            {"x": 30, "y": 20},
                            {"x": 10, "y": 20},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rows = analyse_ground_truth(ground_truth, 100, 100)
    write_results_csv(rows, output_csv)

    with output_csv.open(encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert written[0]["run_id"] == "run-1"
    assert written[0]["within_bounds"] == "True"
    assert written[0]["normalized_center_x"] == "0.2"


def test_analyse_ground_truth_accepts_utf8_bom(tmp_path: Path) -> None:
    ground_truth = tmp_path / "ground_truth.json"
    ground_truth.write_text(json.dumps({"box_annotations": []}), encoding="utf-8-sig")

    assert analyse_ground_truth(ground_truth, 100, 100) == []


def test_invalid_dimensions_are_rejected() -> None:
    with pytest.raises(ValueError, match="positiv"):
        normalize_bounding_box([(0, 0)] * 4, 0, 100)


def test_pixel_comparison_reports_bbox_center_iou_and_tolerance() -> None:
    ground_truth = [(2, 2), (5, 2), (5, 5), (2, 5)]
    mask = [[x in range(2, 5) and y in range(2, 5) for x in range(8)] for y in range(8)]

    result = compare_rendered_bbox(ground_truth, mask, 8, 8, tolerance=0)

    assert (result.actual_left, result.actual_top) == (2, 2)
    assert (result.actual_right, result.actual_bottom) == (5, 5)
    assert result.center_error_px == pytest.approx(0)
    assert result.iou == pytest.approx(1)
    assert not result.clipping_detected
    assert result.within_tolerance

    shifted = [
        [x in range(3, 6) and y in range(2, 5) for x in range(8)] for y in range(8)
    ]
    shifted_result = compare_rendered_bbox(ground_truth, shifted, 8, 8, 1)
    assert shifted_result.center_error_px == pytest.approx(1)
    assert shifted_result.iou == pytest.approx(0.5)
    assert shifted_result.within_tolerance


def test_pixel_comparison_reads_controlled_rendered_raster(tmp_path: Path) -> None:
    image = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "rendered-page.png"
    ground_truth = tmp_path / "ground_truth.json"
    raster = image.new("L", (8, 8), color=255)
    for y in range(2, 5):
        for x in range(2, 5):
            raster.putpixel((x, y), 0)
    raster.save(image_path)
    ground_truth.write_text(
        json.dumps(
            {
                "box_annotations": [
                    {
                        "corners": [
                            {"x": 2, "y": 2},
                            {"x": 5, "y": 2},
                            {"x": 5, "y": 5},
                            {"x": 2, "y": 5},
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = compare_rendered_image(image_path, ground_truth, 0, 8, 8)

    assert (
        result.actual_left,
        result.actual_top,
        result.actual_right,
        result.actual_bottom,
    ) == (2, 2, 5, 5)
    assert result.iou == pytest.approx(1)


def test_foreground_mask_and_empty_pixel_comparison_are_deterministic() -> None:
    pixels = [[255, 255, 255], [255, 0, 255], [255, 255, 255]]

    assert bounding_box_from_corners([(0, 0)] * 4) == (0.0, 0.0, 0.0, 0.0)
    assert foreground_mask(pixels, threshold=10) == [
        [False, False, False],
        [False, True, False],
        [False, False, False],
    ]
    result = compare_rendered_bbox(
        [(1, 1), (2, 1), (2, 2), (1, 2)], [[False, False], [False, False]], 2, 2
    )
    assert result.actual_left is None
    assert result.iou == 0


def test_distribution_returns_normalized_samples_heatmap_and_chi_square() -> None:
    samples = [
        [(0, 0), (2, 0), (2, 2), (0, 2)],
        [(8, 0), (10, 0), (10, 2), (8, 2)],
        [(0, 8), (2, 8), (2, 10), (0, 10)],
        [(8, 8), (10, 8), (10, 10), (8, 10)],
    ]

    result = analyse_distribution(samples, 10, 10, "corners", bins=2)

    assert result["sample_count"] == 4
    assert [
        result["corner_counts"][name]
        for name in ("top_left", "top_right", "bottom_left", "bottom_right")
    ] == [1, 1, 1, 1]
    assert result["heatmap"] == [[1, 1], [1, 1]]
    assert result["chi_square"] == pytest.approx(0)
    assert result["chi_square_p_value"] == pytest.approx(1)
    assert result["normalized_centers"][0] == {"x": 0.1, "y": 0.1}


def test_pixel_comparison_prefers_baseline_and_limits_each_annotation_to_roi(
    tmp_path: Path,
) -> None:
    image = pytest.importorskip("PIL.Image")
    baseline_path = tmp_path / "baseline.png"
    rendered_path = tmp_path / "rendered.png"
    ground_truth = tmp_path / "ground_truth.json"
    baseline = image.new("L", (12, 8), color=40)
    rendered = image.new("L", (12, 8), color=40)
    for y in range(2, 5):
        for x in range(2, 5):
            rendered.putpixel((x, y), 0)
        for x in range(7, 10):
            rendered.putpixel((x, y), 0)
    baseline.save(baseline_path)
    rendered.save(rendered_path)
    ground_truth.write_text(
        json.dumps(
            {
                "box_annotations": [
                    {
                        "corners": [
                            {"x": 2, "y": 2},
                            {"x": 5, "y": 2},
                            {"x": 5, "y": 5},
                            {"x": 2, "y": 5},
                        ]
                    },
                    {
                        "corners": [
                            {"x": 7, "y": 2},
                            {"x": 10, "y": 2},
                            {"x": 10, "y": 5},
                            {"x": 7, "y": 5},
                        ]
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    first = compare_rendered_image(
        rendered_path, ground_truth, 0, 12, 8, baseline_path=baseline_path
    )
    second = compare_rendered_image(
        rendered_path, ground_truth, 1, 12, 8, baseline_path=baseline_path
    )

    assert (first.actual_left, first.actual_right) == (2, 5)
    assert (second.actual_left, second.actual_right) == (7, 10)
    assert first.iou == pytest.approx(1)
    assert second.iou == pytest.approx(1)


def test_pixel_comparison_reports_smaller_actual_mask_as_clipping() -> None:
    mask = [[x in range(3, 6) and y in range(2, 5) for x in range(8)] for y in range(8)]

    result = compare_rendered_bbox([(2, 2), (6, 2), (6, 5), (2, 5)], mask, 8, 8)

    assert result.mask_clipped
    assert result.clipping_detected
    assert not result.within_tolerance


def test_pdf_point_transform_uses_dpi_and_inverts_y_axis() -> None:
    point = pdf_point_to_pixel({"x": 72, "y": 72}, 612, 792, 144)

    assert point == {"x": 144, "y": 1440}
    assert pdf_corners_to_pixel([{"x": 0, "y": 0}] * 4, 612, 792, 72)[0] == {
        "x": 0,
        "y": 792,
    }


def test_render_pdf_page_uses_pdftoppm_and_writes_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.thesis_results.coordinate_validation.coordinate_validation as module

    output_png = tmp_path / "page.png"
    calls: list[list[str]] = []
    monkeypatch.setattr(module.shutil, "which", lambda _: "pdftoppm.exe")

    def fake_run(command: list[str], **_: object) -> object:
        if command[-1] == "-v":
            return SimpleNamespace(stdout="pdftoppm version test", stderr="")
        calls.append(command)
        Path(f"{command[-1]}.png").write_bytes(b"controlled")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = render_pdf_page(tmp_path / "input.pdf", 2, 200, output_png)

    assert result.renderer == "pdftoppm.exe"
    assert result.page_index == 2
    assert result.dpi == 200
    assert output_png.exists()
    render_call = next(call for call in calls if "-f" in call)
    assert render_call[1:7] == ["-f", "3", "-l", "3", "-r", "200"]
    assert result.renderer_version == "pdftoppm version test"


def test_distribution_excludes_invalid_free_centers_and_counts_outside_corners() -> (
    None
):
    valid = [(2, 2), (4, 2), (4, 4), (2, 4)]
    invalid = [(-2, 2), (4, 2), (4, 4), (-2, 4)]

    free_result = analyse_distribution([valid, invalid], 10, 10, "free", bins=2)
    corner_result = analyse_distribution([valid, invalid], 10, 10, "corners", bins=2)

    assert free_result["outside_valid_count"] == 1
    assert sum(sum(row) for row in free_result["heatmap"]) == 1
    assert corner_result["outside_corner_count"] == 2


def test_heatmap_writer_and_cli_accept_ground_truth_box_annotations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.thesis_results.coordinate_validation.coordinate_validation as module

    input_path = tmp_path / "ground_truth.json"
    output_json = tmp_path / "distribution.json"
    output_png = tmp_path / "distribution.png"
    input_path.write_text(
        json.dumps(
            {
                "box_annotations": [
                    {
                        "corners": [
                            {"x": 1, "y": 1},
                            {"x": 3, "y": 1},
                            {"x": 3, "y": 3},
                            {"x": 1, "y": 3},
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "coordinate_validation",
            "--distribution-input",
            str(input_path),
            "--placement-mode",
            "free",
            "--width",
            "10",
            "--height",
            "10",
            "--distribution-output-json",
            str(output_json),
            "--heatmap-png",
            str(output_png),
        ],
    )

    assert module.main() == 0
    assert json.loads(output_json.read_text(encoding="utf-8"))["sample_count"] == 1
    assert output_png.exists()


@pytest.mark.parametrize("suffix", [".jpg", ".dcm"])
def test_pixel_comparison_covers_jpg_and_dicom_inputs(
    tmp_path: Path, suffix: str
) -> None:
    image = pytest.importorskip("PIL.Image")
    baseline_pixels = image.new("L", (8, 8), color=255)
    rendered_pixels = image.new("L", (8, 8), color=255)
    for y in range(2, 5):
        for x in range(2, 5):
            rendered_pixels.putpixel((x, y), 0)
    baseline_path = tmp_path / f"baseline{suffix}"
    rendered_path = tmp_path / f"rendered{suffix}"
    if suffix == ".jpg":
        baseline_pixels.save(baseline_path, quality=100, subsampling=0)
        rendered_pixels.save(rendered_path, quality=100, subsampling=0)
    else:
        pytest.importorskip("pydicom")
        from pydicom.dataset import FileDataset, FileMetaDataset
        from pydicom.uid import ExplicitVRLittleEndian, generate_uid

        # Input: Zielpfad und flache 8-Bit-Pixelwerte.
        # Output: Ein kleines monochromes DICOM-Fixture am Zielpfad.
        # Die kontrollierte Fixture deckt den produktiven DICOM-Lesepfad ab.
        def write_dicom(path: Path, pixels: list[int]) -> None:
            metadata = FileMetaDataset()
            metadata.MediaStorageSOPClassUID = generate_uid()
            metadata.MediaStorageSOPInstanceUID = generate_uid()
            metadata.ImplementationClassUID = generate_uid()
            metadata.TransferSyntaxUID = ExplicitVRLittleEndian
            dataset = FileDataset(
                str(path), {}, file_meta=metadata, preamble=b"\0" * 128
            )
            dataset.Rows = 8
            dataset.Columns = 8
            dataset.SamplesPerPixel = 1
            dataset.PhotometricInterpretation = "MONOCHROME2"
            dataset.BitsAllocated = 8
            dataset.BitsStored = 8
            dataset.HighBit = 7
            dataset.PixelRepresentation = 0
            dataset.PixelData = bytes(pixels)
            dataset.save_as(path)

        write_dicom(baseline_path, [255] * 64)
        write_dicom(
            rendered_path,
            [
                0 if 2 <= x < 5 and 2 <= y < 5 else 255
                for y in range(8)
                for x in range(8)
            ],
        )
    ground_truth = tmp_path / "ground_truth.json"
    ground_truth.write_text(
        json.dumps(
            {
                "box_annotations": [
                    {
                        "corners": [
                            {"x": 2, "y": 2},
                            {"x": 5, "y": 2},
                            {"x": 5, "y": 5},
                            {"x": 2, "y": 5},
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = compare_rendered_image(
        rendered_path,
        ground_truth,
        0,
        8,
        8,
        baseline_path=baseline_path,
    )

    assert (result.actual_left, result.actual_top) == (2, 2)
    assert result.within_tolerance


def test_pdf_sidecar_ground_truth_is_transformed_and_compared(
    tmp_path: Path,
) -> None:
    image = pytest.importorskip("PIL.Image")
    baseline_path = tmp_path / "pdf-baseline.png"
    rendered_path = tmp_path / "pdf-rendered.png"
    image.new("L", (100, 100), color=255).save(baseline_path)
    rendered = image.new("L", (100, 100), color=255)
    for y in range(70, 80):
        for x in range(20, 30):
            rendered.putpixel((x, y), 0)
    rendered.save(rendered_path)
    ground_truth = tmp_path / "pdf-sidecar.json"
    ground_truth.write_text(
        json.dumps(
            {
                "template": {"page_sizes": [[100, 100]]},
                "image_annotations": [
                    {
                        "placement": {"page_index": 0},
                        "pdf_corners": [
                            {"x": 20, "y": 20},
                            {"x": 30, "y": 20},
                            {"x": 30, "y": 30},
                            {"x": 20, "y": 30},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = compare_rendered_image(
        rendered_path,
        ground_truth,
        0,
        100,
        100,
        baseline_path=baseline_path,
        pdf_page_index=0,
        pdf_dpi=72,
    )

    assert (result.actual_left, result.actual_top) == (20, 70)
    assert result.within_tolerance


# Input: Einzel- und Multiframe-RGB-Arrays aus pydicoms Default-`pixel_array`.
# Output: Helligkeitsmatrizen fuer den Einzel- beziehungsweise ausgewaehlten Frame.
# Der Test sichert die Kanalprojektion und verhindert eine falsche Verarbeitung
# des Multiframe-Arrays als zweidimensionale Bildmatrix.
def test_load_rendered_pixels_projects_single_and_selected_multiframe_rgb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pydicom

    single = SimpleNamespace(
        pixel_array=np.array([[[30, 60, 90]]], dtype=np.uint8),
        BitsStored=8,
        PixelRepresentation=0,
    )
    multi = SimpleNamespace(
        pixel_array=np.array(
            [[[[0, 0, 0]]], [[[30, 60, 90]]]], dtype=np.uint8
        ),
        BitsStored=8,
        PixelRepresentation=0,
    )
    datasets = iter((single, multi))
    monkeypatch.setattr(pydicom, "dcmread", lambda _path: next(datasets))

    assert load_rendered_pixels(Path("single.dcm")) == [[60]]
    assert load_rendered_pixels(Path("multi.dcm"), frame_index=1) == [[60]]
