"""pydicom helpers for loading, modifying, and saving DICOM files."""

from pathlib import Path

import pydicom


def load_dicom(path: Path) -> pydicom.Dataset:
    """Load a DICOM file from disk.

    Args:
        path: Absolute or relative path to the .dcm file.

    Returns:
        Parsed pydicom Dataset.
    """
    return pydicom.dcmread(str(path))


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
