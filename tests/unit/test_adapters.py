from pathlib import Path
from typing import ClassVar

import numpy as np
import pydicom
import pytest
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
)

import injection_pipeline.loaders.registry as registry
from injection_pipeline.loaders.dicom import DicomLoader
from injection_pipeline.loaders.jpg import JpgLoader
from injection_pipeline.models import (
    DicomTagAnnotation,
    InjectedDocument,
    SourceDocument,
    TagPlan,
)
from injection_pipeline.writers.dicom import DicomWriter
from injection_pipeline.writers.jpg import JpgWriter
from tests.fixtures.synthetic_documents import (
    write_synthetic_dicom,
    write_synthetic_jpg,
)


def _write_multiframe_grayscale_dicom(path: Path) -> np.ndarray:
    pixels = np.arange(18, dtype=np.uint8).reshape(3, 2, 3)
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    dataset = FileDataset(path.name, {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    dataset.Modality = "OT"
    dataset.Rows = pixels.shape[1]
    dataset.Columns = pixels.shape[2]
    dataset.NumberOfFrames = pixels.shape[0]
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 8
    dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.PixelData = pixels.tobytes()
    dataset.save_as(path, enforce_file_format=True)
    return pixels


def test_registry_resolves_default_adapters_deterministically() -> None:
    assert registry.registered_extensions()[:3] == (".dcm", ".jpg", ".jpeg")

    dcm_loader, dcm_writer = registry.resolve(Path("SCAN.DCM"))
    jpg_loader, jpg_writer = registry.resolve(Path("photo.JPEG"))

    assert dcm_loader.format_id == "dcm"
    assert dcm_writer.output_suffix == ".dcm"
    assert jpg_loader.format_id == "jpg"
    assert jpg_writer.output_suffix == ".jpg"


def test_registry_miss_keeps_unsupported_format_message() -> None:
    with pytest.raises(
        ValueError,
        match=r"Unsupported input format\. Expected \.dcm, \.jpg, or \.jpeg\.",
    ):
        registry.resolve(Path("document.pdf"))


def test_registry_accepts_test_only_fake_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeLoader:
        format_id: ClassVar[str] = "fake"
        extensions: ClassVar[tuple[str, ...]] = (".fake",)

        def load(self, path: Path) -> SourceDocument:
            return SourceDocument(
                format_id=self.format_id,
                path=path,
                frame=np.zeros((1, 1, 3), dtype=np.uint8),
                frame_count=1,
                native=None,
                context=None,
            )

    class FakeWriter:
        format_id: ClassVar[str] = "fake"
        output_suffix: ClassVar[str] = ".fake"

        def inject_native_metadata(
            self,
            document: SourceDocument,
            tag_plan: TagPlan,
        ) -> list[DicomTagAnnotation]:
            del document, tag_plan
            return []

        def write(self, document: InjectedDocument, output_path: Path) -> None:
            del document
            output_path.write_bytes(b"fake")

    monkeypatch.setattr(registry, "_ADAPTERS_BY_EXTENSION", {})
    monkeypatch.setattr(registry, "_REGISTERED_EXTENSIONS", [])
    registry.register(FakeLoader(), FakeWriter())

    loader, writer = registry.resolve(tmp_path / "source.fake")

    assert loader.format_id == "fake"
    assert writer.output_suffix == ".fake"


def test_jpg_loader_and_writer_round_trip_rendered_frame(tmp_path: Path) -> None:
    source_path = write_synthetic_jpg(tmp_path / "source.jpg")
    loader = JpgLoader()
    writer = JpgWriter()
    source = loader.load(source_path)
    rendered_frame = np.asarray(source.frame)
    injected = InjectedDocument(
        source=source,
        rendered_frame=rendered_frame,
        native=source.native,
        tag_annotations=writer.inject_native_metadata(source, {}),
        box_annotations=[],
        output_context=None,
    )
    output_path = tmp_path / "out.jpg"

    writer.write(injected, output_path)

    assert source.format_id == "jpg"
    assert source.frame_count == 1
    assert injected.tag_annotations == []
    assert injected.output_context is None
    assert Image.open(output_path).mode == "RGB"


def test_dicom_loader_and_writer_inject_metadata_and_pixels(tmp_path: Path) -> None:
    source_path = write_synthetic_dicom(tmp_path / "source.dcm")
    loader = DicomLoader()
    writer = DicomWriter()
    source = loader.load(source_path)
    annotation = DicomTagAnnotation(
        label="PatientID",
        tag_address="0010,0020",
        tag_keyword="PatientID",
        dicom_vr="LO",
        value="SYNTH-UNIT",
        identity_field="patient_id",
        identity_id="SYNTH-UNIT",
        source_file=source_path,
        output_file=tmp_path / "out.dcm",
    )

    tag_annotations = writer.inject_native_metadata(source, {"PatientID": annotation})
    injected = InjectedDocument(
        source=source,
        rendered_frame=np.asarray(source.frame),
        native=source.native,
        tag_annotations=tag_annotations,
        box_annotations=[],
        output_context=None,
    )
    writer.write(injected, tmp_path / "out.dcm")
    reloaded = pydicom.dcmread(str(tmp_path / "out.dcm"))

    assert source.format_id == "dcm"
    assert tag_annotations == [annotation]
    assert reloaded.PatientID == "SYNTH-UNIT"
    assert reloaded.pixel_array.shape == np.asarray(source.frame).shape
    assert injected.output_context is not None
    assert injected.output_context.has_pixel_data is True


def test_dicom_writer_preserves_unrendered_grayscale_multiframe_bytes(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "multiframe.dcm"
    original_pixels = _write_multiframe_grayscale_dicom(source_path)
    loader = DicomLoader()
    writer = DicomWriter()
    source = loader.load(source_path)
    rendered_grayscale = np.array(source.frame, copy=True)
    rendered_grayscale[0, 0] = 255
    rendered_rgb = np.repeat(rendered_grayscale[..., np.newaxis], 3, axis=-1)
    injected = InjectedDocument(
        source=source,
        rendered_frame=rendered_rgb,
        native=source.native,
        tag_annotations=[],
        box_annotations=[],
        output_context=None,
    )
    output_path = tmp_path / "out.dcm"

    writer.write(injected, output_path)
    reloaded = pydicom.dcmread(str(output_path))
    reloaded_pixels = np.asarray(reloaded.pixel_array)

    assert source.frame_count == 3
    assert np.asarray(source.frame).shape == (2, 3)
    assert reloaded_pixels.shape == original_pixels.shape
    assert not np.array_equal(reloaded_pixels[0], original_pixels[0])
    assert np.array_equal(reloaded_pixels[1:], original_pixels[1:])
    frame_byte_count = original_pixels[0].nbytes
    assert (
        reloaded.PixelData[frame_byte_count:]
        == original_pixels.tobytes()[frame_byte_count:]
    )
    assert int(str(reloaded.NumberOfFrames)) == 3
    assert reloaded.Rows == 2
    assert reloaded.Columns == 3
    assert reloaded.SamplesPerPixel == 1
    assert len(reloaded.PixelData) == original_pixels.nbytes
    assert injected.output_context is not None
    assert injected.output_context.number_of_frames == 3
