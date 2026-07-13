"""pydicom helpers for loading and summarizing DICOM files."""

from pathlib import Path
from typing import ClassVar

import numpy as np
import pydicom

from injection_pipeline.models.adapters import SourceDocument
from injection_pipeline.models.dicom import DicomContext


class DicomLoader:
    """Adapter for loading DICOM documents into the shared source model."""

    format_id: ClassVar[str] = "dcm"
    extensions: ClassVar[tuple[str, ...]] = (".dcm",)

    # Input: `path` mit absolutem oder relativem Pfad zur DICOM-Datei.
    # Output: `SourceDocument` mit Preview-Frame, Dataset und DICOM-Kontext.
    # Die Methode laedt das Dataset einmal und behaelt den nativen Handle fuer
    # Tag- und Pixel-Writer-Schritte.
    def load(self, path: Path) -> SourceDocument:
        from injection_pipeline.engine.frames import extract_preview_frame

        ds = load_dicom(path)
        pixel_array = np.asarray(ds.pixel_array)
        return SourceDocument(
            format_id=self.format_id,
            path=path,
            frame=extract_preview_frame(ds),
            frame_count=resolve_dicom_frame_count(ds, pixel_array),
            native=ds,
            context=summarize_dicom(ds),
        )


# Input: `path` mit absolutem oder relativem Pfad zur DICOM-Datei.
# Output: Geparstes pydicom-Dataset.
# Die Funktion laedt die Datei direkt ueber pydicom.
def load_dicom(path: Path) -> pydicom.Dataset:
    return pydicom.dcmread(str(path))


# Input: `ds` mit geparstem DICOM-Dataset.
# Output: Validierter DICOM-Kontext fuer Manifest und Ground Truth.
# Die Funktion liest nur leichte Kontextfelder und faellt bei ungueltigen
# Frame-Zahlen auf `None` zurueck. Pydicom-spezifische Werte werden vor der
# Modellvalidierung explizit in primitive Python-Typen ueberfuehrt.
def summarize_dicom(ds: pydicom.Dataset) -> DicomContext:
    frame_count = None
    if hasattr(ds, "NumberOfFrames"):
        try:
            frame_count = int(ds.NumberOfFrames)
        except (TypeError, ValueError):
            frame_count = None

    return DicomContext(
        modality=_as_optional_string(getattr(ds, "Modality", None)),
        sop_instance_uid=_as_optional_string(getattr(ds, "SOPInstanceUID", None)),
        study_instance_uid=_as_optional_string(getattr(ds, "StudyInstanceUID", None)),
        series_instance_uid=_as_optional_string(getattr(ds, "SeriesInstanceUID", None)),
        rows=_as_optional_int(getattr(ds, "Rows", None)),
        columns=_as_optional_int(getattr(ds, "Columns", None)),
        samples_per_pixel=_as_optional_int(getattr(ds, "SamplesPerPixel", None)),
        photometric_interpretation=_as_optional_string(
            getattr(ds, "PhotometricInterpretation", None)
        ),
        number_of_frames=frame_count,
        has_pixel_data=hasattr(ds, "PixelData"),
    )


# Input: `ds` mit DICOM-Metadaten und `pixel_array` aus pydicom.
# Output: Anzahl der renderrelevanten DICOM-Frames.
# Die Funktion nutzt `NumberOfFrames` zuerst und faellt auf Shape plus
# Samples/Photometric-Metadaten zurueck, ohne RGB-Single-frames zu verwechseln.
def resolve_dicom_frame_count(
    ds: pydicom.Dataset,
    pixel_array: np.ndarray,
) -> int:
    number_of_frames = _as_optional_int(getattr(ds, "NumberOfFrames", None))
    if number_of_frames is not None and number_of_frames > 1:
        return number_of_frames
    if pixel_array.ndim == 4:
        return int(pixel_array.shape[0])
    if is_multiframe_grayscale(ds, pixel_array):
        return int(pixel_array.shape[0])
    return 1


# Input: `ds` mit DICOM-Pixelmetadaten und `pixel_array` aus pydicom.
# Output: `True`, wenn ein 3D-Array als `(frames, rows, columns)` zu behandeln ist.
# Die Funktion vermeidet Heuristik-Konflikte: `NumberOfFrames > 1` gewinnt,
# Shape-Fallbacks greifen nur, wenn die letzte Achse nicht wie RGB aussieht.
def is_multiframe_grayscale(
    ds: pydicom.Dataset,
    pixel_array: np.ndarray,
) -> bool:
    if pixel_array.ndim != 3 or _is_color_pixel_data(ds):
        return False
    number_of_frames = _as_optional_int(getattr(ds, "NumberOfFrames", None))
    if number_of_frames is not None and number_of_frames > 1:
        return int(pixel_array.shape[0]) == number_of_frames
    samples_per_pixel = _as_optional_int(getattr(ds, "SamplesPerPixel", None))
    return samples_per_pixel == 1 and pixel_array.shape[-1] not in {3, 4}


# Input: `ds` mit DICOM-Pixelmetadaten.
# Output: `True`, wenn die Metadaten Farb-Pixel beschreiben.
# Die Funktion fasst SamplesPerPixel und PhotometricInterpretation zusammen,
# damit 3D-Grayscale-Frames mit drei oder vier Spalten nicht wie RGB wirken.
def _is_color_pixel_data(ds: pydicom.Dataset) -> bool:
    samples_per_pixel = _as_optional_int(getattr(ds, "SamplesPerPixel", None))
    if samples_per_pixel is not None and samples_per_pixel > 1:
        return True
    photometric = _as_optional_string(getattr(ds, "PhotometricInterpretation", None))
    if photometric is None:
        return False
    return photometric.upper().startswith(("RGB", "YBR", "PALETTE"))


# Input: `value` mit pydicom- oder Python-Wert.
# Output: String oder `None` fuer fehlende DICOM-Kontextwerte.
# Die Funktion verhindert, dass pydicom-Unterklassen in den Domain-Modellen landen.
def _as_optional_string(value: object) -> str | None:
    return None if value is None else str(value)


# Input: `value` mit pydicom- oder Python-Zahlenwert.
# Output: Integer oder `None` fuer fehlende oder nicht konvertierbare Werte.
# Die Funktion bildet die bisherige tolerante Frame-Kontextbehandlung ab.
def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
