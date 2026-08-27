"""Integrationstest für den vollständigen YBR_FULL_422-Adapterdurchlauf."""

from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
)

from injection_pipeline.loaders.dicom import DicomLoader
from injection_pipeline.models import InjectedDocument
from injection_pipeline.writers.dicom import DicomWriter


# Input: Zielpfad für eine minimale synthetische YBR_FULL_422-Quelldatei.
# Output: Keine Rückgabe; die Datei wird ausschließlich als Testfixture geschrieben.
# Die Fixture enthält keine Patientendaten und nutzt unkomprimierte 4:2:2-Bytes.
def _write_integration_fixture(path: Path) -> None:
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
    dataset.PixelData = bytes([100, 110, 120, 130, 140, 150, 160, 170])
    dataset.save_as(path, enforce_file_format=True)


# Input: temporäres synthetisches YBR-DICOM.
# Output: Keine Rückgabe; der Test validiert Laden, Renderframe und Schreiben.
# Der Roundtrip muss RGB und ExplicitVRLittleEndian im Ergebnis manifestieren.
def test_ybr_full_422_roundtrip_through_adapters(tmp_path: Path) -> None:
    source_path = tmp_path / "source.dcm"
    output_path = tmp_path / "output.dcm"
    _write_integration_fixture(source_path)

    source = DicomLoader().load(source_path)
    DicomWriter().write(
        InjectedDocument(
            source=source,
            rendered_frame=np.asarray(source.frame),
            native=source.native,
            tag_annotations=[],
            box_annotations=[],
            output_context=None,
        ),
        output_path,
    )
    output = pydicom.dcmread(output_path)

    assert source.frame.shape == (2, 2, 3)
    assert output.PhotometricInterpretation == "RGB"
    assert output.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian
    assert output.pixel_array.shape == (2, 2, 3)
