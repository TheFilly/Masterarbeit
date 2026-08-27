"""pydicom helpers for loading and summarizing DICOM files."""

from pathlib import Path
from typing import ClassVar

import numpy as np
import pydicom
from pydicom.uid import UID

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
        ds = load_dicom(path)
        source_array = np.asarray(ds.pixel_array)
        validate_supported_dicom_dataset(ds, source_array)
        pixel_array = normalize_dicom_pixel_array(ds, source_array)
        return SourceDocument(
            format_id=self.format_id,
            path=path,
            frame=_extract_preview_frame_from_array(ds, pixel_array),
            frame_count=resolve_dicom_frame_count(ds, pixel_array),
            native=ds,
            context=summarize_dicom(ds),
        )


# Input: `path` mit absolutem oder relativem Pfad zur DICOM-Datei.
# Output: Geparstes pydicom-Dataset.
# Die Funktion laedt die Datei direkt ueber pydicom.
def load_dicom(path: Path) -> pydicom.Dataset:
    return pydicom.dcmread(str(path))


# Input: `ds` mit geladenem Dataset und optional dekodiertem Pixelarray.
# Output: Keine Rueckgabe.
# Die Funktion begrenzt den aktuellen Writervertrag auf uint8, Little Endian,
# MONOCHROME2, RGB und 8-Bit-YBR_FULL_422 vor der RGB-Normalisierung.
def validate_supported_dicom_dataset(
    ds: pydicom.Dataset,
    pixel_array: np.ndarray | None = None,
) -> None:
    values = np.asarray(ds.pixel_array if pixel_array is None else pixel_array)
    if values.dtype != np.uint8:
        raise ValueError(
            "Unsupported DICOM pixel representation: only uint8 pixel data "
            f"is supported, got {values.dtype}."
        )

    transfer_syntax = getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", None)
    transfer_uid = None if transfer_syntax is None else UID(str(transfer_syntax))
    if transfer_uid is not None and transfer_uid.is_little_endian is False:
        raise ValueError(
            "Unsupported DICOM transfer syntax: big-endian pixel data is not supported."
        )

    photometric = str(getattr(ds, "PhotometricInterpretation", "")).upper()
    if photometric not in {"MONOCHROME2", "RGB", "YBR_FULL_422"}:
        raise ValueError(
            "Unsupported DICOM photometric interpretation: "
            f"{photometric or '<missing>'}."
        )

    samples_per_pixel = int(getattr(ds, "SamplesPerPixel", 1))
    if photometric == "RGB" and samples_per_pixel != 3:
        raise ValueError("RGB DICOM pixel data must declare SamplesPerPixel=3.")
    if photometric == "YBR_FULL_422" and samples_per_pixel != 3:
        raise ValueError(
            "YBR_FULL_422 DICOM pixel data must declare SamplesPerPixel=3."
        )
    if photometric == "MONOCHROME2" and samples_per_pixel != 1:
        raise ValueError("MONOCHROME2 DICOM pixel data must declare SamplesPerPixel=1.")


# Input: `ds` mit PhotometricInterpretation und optional dekodiertem Pixelarray.
# Output: uint8-Pixelarray im RGB- oder unveränderten Quellfarbraum.
# pydicom liefert bei `ds.pixel_array` standardmäßig bereits RGB für
# YBR_FULL_422; eine zweite Farbkonvertierung wird daher bewusst vermieden.
def normalize_dicom_pixel_array(
    ds: pydicom.Dataset,
    pixel_array: np.ndarray | None = None,
) -> np.ndarray:
    values = np.asarray(ds.pixel_array if pixel_array is None else pixel_array)
    photometric = str(getattr(ds, "PhotometricInterpretation", "")).upper()
    if photometric == "YBR_FULL_422" and values.dtype != np.uint8:
        raise ValueError("YBR_FULL_422 requires 8-bit pixel data.")
    return values


# Input: `ds` und bereits normalisiertes Pixelarray.
# Output: Erstes darstellbares Frame mit RGB-Normalisierung für YBR_FULL_422.
# Die Shape-Entscheidung entspricht dem bisherigen Frame-Vertrag, vermeidet aber
# den erneuten Zugriff auf `ds.pixel_array` mit dem ursprünglichen YBR-Farbraum.
def _extract_preview_frame_from_array(
    ds: pydicom.Dataset,
    pixel_array: np.ndarray,
) -> np.ndarray:
    if pixel_array.ndim == 4:
        return np.asarray(pixel_array[0])
    if is_multiframe_grayscale(ds, pixel_array):
        return np.asarray(pixel_array[0])
    if pixel_array.ndim == 3 and pixel_array.shape[-1] in {3, 4}:
        return np.asarray(pixel_array)
    return np.asarray(pixel_array)


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
