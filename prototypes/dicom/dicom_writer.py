"""pydicom helpers for loading, modifying, and saving DICOM files."""

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


# Input: `ds` mit DICOM-Dataset, `tag_map` mit Keyword-zu-Wert-Mapping.
# Output: Dasselbe Dataset mit aktualisierten Tags.
# Die Funktion mutiert das Dataset in-place.
def inject_tags(ds: pydicom.Dataset, tag_map: dict[str, str]) -> pydicom.Dataset:
    for keyword, value in tag_map.items():
        setattr(ds, keyword, value)
    return ds


# Input: `ds` mit DICOM-Dataset, `output_path` mit Zielpfad.
# Output: Keine Rueckgabe.
# Die Funktion legt fehlende Elternordner an und schreibt die Datei auf Platte.
def save_dicom(ds: pydicom.Dataset, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pydicom.dcmwrite(str(output_path), ds)
