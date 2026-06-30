"""pydicom helpers for loading and summarizing DICOM files."""

from pathlib import Path
from typing import Any

import pydicom


# Input: `path` mit absolutem oder relativem Pfad zur DICOM-Datei.
# Output: Geparstes pydicom-Dataset.
# Die Funktion laedt die Datei direkt ueber pydicom.
def load_dicom(path: Path) -> pydicom.Dataset:
    return pydicom.dcmread(str(path))


# Input: `ds` mit geparstem DICOM-Dataset.
# Output: JSON-taugliche Metadaten fuer Manifest und Debugging.
# Die Funktion liest nur leichte Kontextfelder und faellt bei ungueltigen
# Frame-Zahlen auf `None` zurueck.
def summarize_dicom(ds: pydicom.Dataset) -> dict[str, Any]:
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
