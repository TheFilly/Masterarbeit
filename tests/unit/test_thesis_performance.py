"""Deterministische Tests für die Thesis-Performance-Werkzeuge."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from tools.thesis_results.performance.common import iter_blocks, write_csv
from tools.thesis_results.performance.pdf_scaling_benchmark import (
    build_image_inputs,
    image_counts,
)
from tools.thesis_results.performance.scalability_benchmark import (
    _is_supported_source,
    _stage_sources,
    build_jobs,
    discover_sources,
    run_benchmark,
)


# Input: Zielpfad und DICOM-Bitbreite.
# Output: Kleines monochromes DICOM-Fixture am Zielpfad.
# Das Fixture deckt die Quellenfilterung ohne echte Patientendaten ab.
def _write_dicom_fixture(path: Path, bits_allocated: int) -> None:
    metadata = FileMetaDataset()
    metadata.MediaStorageSOPClassUID = generate_uid()
    metadata.MediaStorageSOPInstanceUID = generate_uid()
    metadata.ImplementationClassUID = generate_uid()
    metadata.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(str(path), {}, file_meta=metadata, preamble=b"\0" * 128)
    dataset.Rows = 2
    dataset.Columns = 2
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = bits_allocated
    dataset.BitsStored = bits_allocated
    dataset.HighBit = bits_allocated - 1
    dataset.PixelRepresentation = 0
    dataset.PixelData = bytes(4 * bits_allocated // 8)
    dataset.save_as(path)


# Input: Zielpfad fuer ein kuenstliches 8-Bit-YBR_FULL_422-DICOM.
# Output: Keine Rueckgabe; die Fixture wird fuer den Quellenfilter gespeichert.
# Die Headerwerte entsprechen einer unterstuetzten dreikanaligen Farbquelle.
def _write_ybr_fixture(path: Path) -> None:
    metadata = FileMetaDataset()
    metadata.MediaStorageSOPClassUID = generate_uid()
    metadata.MediaStorageSOPInstanceUID = generate_uid()
    metadata.ImplementationClassUID = generate_uid()
    metadata.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(str(path), {}, file_meta=metadata, preamble=b"\0" * 128)
    dataset.Rows = 2
    dataset.Columns = 2
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = "YBR_FULL_422"
    dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = 8
    dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.PixelData = bytes([100, 110, 120, 130, 140, 150, 160, 170])
    dataset.save_as(path)


def test_iter_blocks_preserves_order_and_last_partial_block() -> None:
    assert list(iter_blocks(range(5), 2)) == [[0, 1], [2, 3], [4]]


def test_iter_blocks_rejects_non_positive_block_size() -> None:
    with pytest.raises(ValueError, match="mindestens 1"):
        list(iter_blocks([1], 0))


def test_write_csv_is_reproducible(tmp_path: Path) -> None:
    output = tmp_path / "measurements.csv"
    write_csv(output, [{"a": 1, "b": "x"}], ["a", "b"])

    with output.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"a": "1", "b": "x"}]


def test_image_counts_are_powers_of_two() -> None:
    assert image_counts(16) == [1, 2, 4, 8, 16]
    assert image_counts(10) == [1, 2, 4, 8]


def test_build_image_inputs_reuses_one_controlled_image(tmp_path: Path) -> None:
    image = tmp_path / "source.jpg"
    Image.new("RGB", (20, 20), color=(240, 240, 240)).save(image, format="JPEG")

    inputs = build_image_inputs(image, 3)

    assert len(inputs) == 3
    assert [item.path for item in inputs] == [image, image, image]
    assert all(len(item.annotations) == 1 for item in inputs)
    assert all(
        item.annotations[0].rendered_text == "ID: SYNTH-IMAGE" for item in inputs
    )


def test_build_jobs_cycles_sources_and_changes_seed_and_timestamp(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.dcm"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    jobs = list(
        build_jobs(
            [first, second],
            count=3,
            output_dir=tmp_path / "output",
            seed=42,
            run_timestamp=datetime(2026, 1, 1),
        )
    )

    assert [job.source for job in jobs] == [first, second, first]
    assert [job.document_type for job in jobs] == ["jpg", "dcm", "jpg"]
    assert [job.seed for job in jobs] == [42, 43, 44]
    assert jobs[0].run_timestamp < jobs[1].run_timestamp < jobs[2].run_timestamp


def test_discover_sources_is_sorted_and_filters_formats(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "b.JPG").write_bytes(b"jpg")
    _write_dicom_fixture(tmp_path / "a.dcm", 8)
    _write_dicom_fixture(tmp_path / "unsupported.dcm", 16)
    (tmp_path / "invalid.dcm").write_bytes(b"dcm")

    assert discover_sources(tmp_path) == [tmp_path / "a.dcm", tmp_path / "b.JPG"]


def test_dicom_source_filter_accepts_uint8_and_rejects_uint16(
    tmp_path: Path,
) -> None:
    supported = tmp_path / "supported.dcm"
    unsupported = tmp_path / "unsupported.dcm"
    _write_dicom_fixture(supported, 8)
    _write_dicom_fixture(unsupported, 16)

    assert _is_supported_source(supported)
    assert not _is_supported_source(unsupported)
    assert not _is_supported_source(tmp_path / "missing.dcm")


# Input: Kuenstliches YBR_FULL_422-DICOM mit drei Samples pro Pixel.
# Output: Keine Rueckgabe; der Test bestaetigt die Aufnahme in die Benchmark-Quellen.
# Damit wird verhindert, dass reale YBR-DICOMs beim Skalierbarkeitstest herausfallen.
def test_dicom_source_filter_accepts_ybr_full_422(tmp_path: Path) -> None:
    source = tmp_path / "supported-ybr.dcm"
    _write_ybr_fixture(source)

    assert _is_supported_source(source)


def test_stage_sources_uses_short_deterministic_names(tmp_path: Path) -> None:
    first = tmp_path / ("very-long-source-name-" + "x" * 80 + ".jpg")
    second = tmp_path / ("another-long-source-name-" + "y" * 80 + ".dcm")
    first.write_bytes(b"jpg")
    _write_dicom_fixture(second, 8)

    staged = _stage_sources([first, second], tmp_path / "cache")

    assert [path.name for path in staged] == ["source-000000.jpg", "source-000001.dcm"]
    assert [path.read_bytes() for path in staged] == [
        first.read_bytes(),
        second.read_bytes(),
    ]


# Input: Benchmarkoptionen und ein absichtlich vorhandener Fremdordner.
# Output: Der Fremdordner bleibt nach einem simulierten Benchmarkfehler erhalten.
# Der Test sichert den laufbezogenen Cleanup-Vertrag des Benchmarks ab.
def test_benchmark_cleanup_does_not_remove_existing_sources_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.thesis_results.performance.scalability_benchmark as module

    output_dir = tmp_path / "benchmark"
    existing = output_dir / "_sources"
    existing.mkdir(parents=True)
    marker = existing / "foreign.txt"
    marker.write_text("keep", encoding="utf-8")

    def fail(_: argparse.Namespace) -> None:
        raise RuntimeError("controlled benchmark failure")

    monkeypatch.setattr(module, "_run_benchmark_impl", fail)

    with pytest.raises(RuntimeError, match="controlled"):
        run_benchmark(argparse.Namespace(output_dir=output_dir))

    assert marker.read_text(encoding="utf-8") == "keep"
    assert not list(output_dir.glob(".sources-*"))
