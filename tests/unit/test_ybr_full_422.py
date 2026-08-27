"""Unit-Tests für den YBR_FULL_422-DICOM-Adapterpfad."""

from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.pixels.processing import convert_color_space
from pydicom.uid import (
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
)

from injection_pipeline.loaders.dicom import (
    DicomLoader,
    normalize_dicom_pixel_array,
)
from injection_pipeline.models import InjectedDocument
from injection_pipeline.writers.dicom import DicomWriter


# Input: Zielpfad für ein synthetisches 2x2-YBR_FULL_422-DICOM.
# Output: Das geschriebene Dataset und die dekodierten YBR-Werte.
# Die Fixture nutzt nur künstliche Pixelwerte und bildet die gepackten 4:2:2-
# Bytes eines 8-Bit-DICOMs ab.
def _write_ybr_fixture(
    path: Path, *, number_of_frames: int = 1
) -> tuple[FileDataset, np.ndarray]:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()
    dataset = FileDataset(path.name, {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    dataset.Modality = "OT"
    dataset.Rows = 2
    dataset.Columns = 2
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = "YBR_FULL_422"
    dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = 8
    dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.NumberOfFrames = number_of_frames
    frame_bytes = bytes([100, 110, 120, 130, 140, 150, 160, 170])
    dataset.PixelData = frame_bytes * number_of_frames
    dataset.save_as(path, enforce_file_format=True)
    return dataset, np.asarray(dataset.pixel_array)


# Input: synthetische YBR_FULL_422-Datei.
# Output: Keine Rückgabe; der Test prüft Loader-Frame und explizite RGB-Konvertierung.
# Der native Kontext bleibt YBR, während der sichtbare Pipeline-Frame RGB ist.
def test_ybr_full_422_loader_normalizes_frame_to_rgb(tmp_path: Path) -> None:
    source_path = tmp_path / "source-ybr.dcm"
    _write_ybr_fixture(source_path)
    loaded = pydicom.dcmread(source_path)
    default_rgb_array = np.asarray(loaded.pixel_array)

    source = DicomLoader().load(source_path)
    double_converted = convert_color_space(default_rgb_array, "YBR_FULL_422", "RGB")

    assert source.context is not None
    assert source.context.photometric_interpretation == "YBR_FULL_422"
    assert np.array_equal(np.asarray(source.frame), default_rgb_array)
    assert not np.array_equal(np.asarray(source.frame), double_converted)
    assert source.native is not None
    assert source.native.PhotometricInterpretation == "YBR_FULL_422"


# Input: synthetische YBR_FULL_422-Datei und geladenes RGB-Frame.
# Output: Keine Rückgabe; der Test prüft RGB/ExplicitVRLittleEndian im Output.
# Der Writer konvertiert auch weitere Multiframe-/Native-Pixel vor der Persistierung.
def test_ybr_full_422_writer_outputs_rgb_explicit_vr_little_endian(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source-ybr.dcm"
    _write_ybr_fixture(source_path)
    source = DicomLoader().load(source_path)
    injected = InjectedDocument(
        source=source,
        rendered_frame=np.asarray(source.frame),
        native=source.native,
        tag_annotations=[],
        box_annotations=[],
        output_context=None,
    )
    output_path = tmp_path / "output-rgb.dcm"

    DicomWriter().write(injected, output_path)
    output = pydicom.dcmread(output_path)

    assert output.PhotometricInterpretation == "RGB"
    assert output.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
    assert output.SamplesPerPixel == 3
    assert output.PlanarConfiguration == 0
    assert np.array_equal(output.pixel_array, np.asarray(source.frame))


# Input: Zwei synthetische YBR_FULL_422-Frames und ein verändertes Preview-Frame.
# Output: Keine Rückgabe; der Test prüft Frame-0-Injektion und Frame-1-Erhalt.
# Die Metadaten und die dekodierte RGB-Shape müssen den Multiframe-Vertrag erfüllen.
def test_ybr_full_422_multiframe_only_preview_frame_is_written(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source-ybr-multiframe.dcm"
    _write_ybr_fixture(source_path, number_of_frames=2)
    source_dataset = pydicom.dcmread(source_path)
    source_pixels = np.asarray(source_dataset.pixel_array)
    source = DicomLoader().load(source_path)
    rendered_frame = np.array(source.frame, copy=True)
    rendered_frame[0, 0] = ((rendered_frame[0, 0].astype(np.uint16) + 1) % 256).astype(
        np.uint8
    )
    injected = InjectedDocument(
        source=source,
        rendered_frame=rendered_frame,
        native=source.native,
        tag_annotations=[],
        box_annotations=[],
        output_context=None,
    )
    output_path = tmp_path / "output-rgb-multiframe.dcm"

    DicomWriter().write(injected, output_path)
    output = pydicom.dcmread(output_path)
    output_pixels = np.asarray(output.pixel_array)

    assert source.frame_count == 2
    assert np.asarray(source.frame).shape == (2, 2, 3)
    assert output.NumberOfFrames == 2
    assert output.SamplesPerPixel == 3
    assert output.PhotometricInterpretation == "RGB"
    assert output.PlanarConfiguration == 0
    assert output_pixels.shape == (2, 2, 2, 3)
    assert np.array_equal(output_pixels[0], rendered_frame)
    assert np.array_equal(output_pixels[1], source_pixels[1])


# Input: synthetischer YBR-Datensatz und bereits dekodiertes Array.
# Output: Keine Rückgabe; der Test sichert die explizite Normalisierungsfunktion.
# Der Test stellt sicher, dass MONOCHROME2/RGB nicht in diesen Sonderpfad geraten.
def test_ybr_normalization_is_noop_for_monochrome_and_rgb() -> None:
    for photometric, shape in (("MONOCHROME2", (2, 2)), ("RGB", (2, 2, 3))):
        dataset = pydicom.Dataset()
        dataset.PhotometricInterpretation = photometric
        pixels = np.arange(np.prod(shape), dtype=np.uint8).reshape(shape)
        assert np.array_equal(normalize_dicom_pixel_array(dataset, pixels), pixels)
