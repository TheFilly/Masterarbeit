"""Factories for synthetic image documents used by integration tests."""

from pathlib import Path

import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage

_SOP_INSTANCE_UID = "1.2.826.0.1.3680043.10.543.1"
_STUDY_INSTANCE_UID = "1.2.826.0.1.3680043.10.543.2"
_SERIES_INSTANCE_UID = "1.2.826.0.1.3680043.10.543.3"


# Input: `size` with the square image dimension.
# Output: RGB array containing a deterministic synthetic pattern.
# The pattern has enough contrast to expose one-pixel output changes.
def _synthetic_rgb_array(size: int = 256) -> np.ndarray:
    x_axis = np.arange(size, dtype=np.uint16)
    y_axis = x_axis[:, np.newaxis]
    red = np.broadcast_to((x_axis * 3) % 256, (size, size))
    green = np.broadcast_to((y_axis * 5) % 256, (size, size))
    blue = (x_axis[np.newaxis, :] + y_axis) % 256
    return np.stack((red, green, blue), axis=-1).astype(np.uint8)


# Input: `path` with the destination for the generated DICOM fixture.
# Output: The destination path after writing a synthetic RGB DICOM file.
# The fixture contains no patient-derived values or external binary assets.
def write_synthetic_dicom(path: Path) -> Path:
    pixels = _synthetic_rgb_array()
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = _SOP_INSTANCE_UID
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = "1.2.826.0.1.3680043.10.543.9"

    dataset = FileDataset(path.name, {}, file_meta=file_meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = _SOP_INSTANCE_UID
    dataset.StudyInstanceUID = _STUDY_INSTANCE_UID
    dataset.SeriesInstanceUID = _SERIES_INSTANCE_UID
    dataset.Modality = "OT"
    dataset.PatientName = "SYNTHETIC^SOURCE"
    dataset.PatientID = "SYNTHETIC-SOURCE"
    dataset.Rows = pixels.shape[0]
    dataset.Columns = pixels.shape[1]
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = "RGB"
    dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = 8
    dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.PixelData = pixels.tobytes()
    dataset.save_as(path, enforce_file_format=True)
    return path


# Input: `path` with the destination for the generated JPEG fixture.
# Output: The destination path after writing a deterministic synthetic image.
# The function writes the fixture at test runtime and uses no external data.
def write_synthetic_jpg(path: Path) -> Path:
    Image.fromarray(_synthetic_rgb_array(), mode="RGB").save(
        path,
        format="JPEG",
        quality=95,
        subsampling=0,
    )
    return path
