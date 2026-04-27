"""pydicom helpers for loading, modifying, and saving DICOM files."""

from pathlib import Path
from typing import Any

import pydicom


def load_dicom(path: Path) -> pydicom.Dataset:
    """Load a DICOM file from disk.

    Args:
        path: Absolute or relative path to the .dcm file.

    Returns:
        Parsed pydicom Dataset.
    """
    return pydicom.dcmread(str(path))


def summarize_dicom(ds: pydicom.Dataset) -> dict[str, Any]:
    """Collect lightweight dataset metadata for prototype manifests.

    Args:
        ds: Parsed DICOM dataset.

    Returns:
        JSON-serializable metadata for validation and debugging.
    """
    frame_count = None
    if hasattr(ds, "NumberOfFrames"):
        try:
            frame_count = int(ds.NumberOfFrames)
        except (TypeError, ValueError):
            frame_count = None

    return {
        "modality": getattr(ds, "Modality", None),
        "sop_instance_uid": getattr(ds, "SOPInstanceUID", None),
        "study_instance_uid": getattr(ds, "StudyInstanceUID", None),
        "series_instance_uid": getattr(ds, "SeriesInstanceUID", None),
        "rows": getattr(ds, "Rows", None),
        "columns": getattr(ds, "Columns", None),
        "samples_per_pixel": getattr(ds, "SamplesPerPixel", None),
        "photometric_interpretation": getattr(ds, "PhotometricInterpretation", None),
        "number_of_frames": frame_count,
        "has_pixel_data": hasattr(ds, "PixelData"),
    }


def inject_tags(ds: pydicom.Dataset, tag_map: dict[str, str]) -> pydicom.Dataset:
    """Inject PII values into DICOM tags. Returns the modified dataset.

    Args:
        ds: The DICOM dataset to modify (mutated in place).
        tag_map: Mapping of DICOM keyword to string value,
                 e.g. {"PatientName": "Smith^John"}.

    Returns:
        The same dataset with updated tags.
    """
    for keyword, value in tag_map.items():
        setattr(ds, keyword, value)
    return ds


def save_dicom(ds: pydicom.Dataset, output_path: Path) -> None:
    """Write a DICOM dataset to disk.

    Args:
        ds: The DICOM dataset to write.
        output_path: Destination file path. Parent directories are created if absent.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pydicom.dcmwrite(str(output_path), ds)
