"""pydicom helpers for saving DICOM files."""

from pathlib import Path

import pydicom


# Input: `ds` mit DICOM-Dataset, `output_path` mit Zielpfad.
# Output: Keine Rueckgabe.
# Die Funktion legt fehlende Elternordner an und schreibt die Datei auf Platte.
def save_dicom(ds: pydicom.Dataset, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pydicom.dcmwrite(str(output_path), ds)
