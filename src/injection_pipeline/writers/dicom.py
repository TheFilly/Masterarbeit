"""pydicom helpers for saving DICOM files."""

from pathlib import Path
from typing import ClassVar

import numpy as np
import pydicom
from pydicom.uid import ExplicitVRLittleEndian

from injection_pipeline.loaders.dicom import is_multiframe_grayscale, summarize_dicom
from injection_pipeline.models.adapters import InjectedDocument, SourceDocument, TagPlan
from injection_pipeline.models.annotations import DicomTagAnnotation


class DicomWriter:
    """Adapter for DICOM metadata and pixel persistence."""

    format_id: ClassVar[str] = "dcm"
    output_suffix: ClassVar[str] = ".dcm"

    # Input: `document` mit pydicom-Dataset, `tag_plan` mit Tag-Annotationen.
    # Output: Liste der injizierten DICOM-Tag-Annotationen.
    # Die Methode mutiert das native Dataset mit den Werten aus dem Plan.
    def inject_native_metadata(
        self,
        document: SourceDocument,
        tag_plan: TagPlan,
    ) -> list[DicomTagAnnotation]:
        from injection_pipeline.engine.dicom_tags import inject_tags

        ds = _require_dataset(document.native)
        tag_values = {
            keyword: annotation.value for keyword, annotation in tag_plan.items()
        }
        inject_tags(ds, tag_values)
        return list(tag_plan.values())

    # Input: `document` mit gerendertem Frame, `output_path` mit Zielpfad.
    # Output: Keine Rueckgabe.
    # Die Methode schreibt Pixel in das Dataset, speichert die Datei und setzt
    # den Ausgabe-DICOM-Kontext am Dokument.
    def write(self, document: InjectedDocument, output_path: Path) -> None:
        ds = _require_dataset(document.native)
        rendered_frame = np.asarray(document.rendered_frame)
        pixel_array = np.asarray(ds.pixel_array)
        if is_multiframe_grayscale(ds, pixel_array):
            output_array = np.array(pixel_array, copy=True)
            output_array[0] = _coerce_rendered_frame_to_source_shape(
                rendered_frame,
                np.asarray(document.source.frame),
            ).astype(output_array.dtype, copy=False)
        elif pixel_array.ndim == 4:
            output_array = np.array(pixel_array, copy=True)
            output_array[0] = rendered_frame
        else:
            output_array = rendered_frame
        _write_pixel_array(ds, output_array)
        document.output_context = summarize_dicom(ds)
        save_dicom(ds, output_path)


# Input: `ds` mit DICOM-Dataset, `output_path` mit Zielpfad.
# Output: Keine Rueckgabe.
# Die Funktion legt fehlende Elternordner an und schreibt die Datei auf Platte.
def save_dicom(ds: pydicom.Dataset, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pydicom.dcmwrite(str(output_path), ds)


# Input: `ds` mit Zieldataset und `output_array` mit gerenderten Pixeln.
# Output: Keine Rueckgabe.
# Die Funktion mutiert PixelData und die noetigen DICOM-Pixelmetadaten fuer
# die native Persistierung.
def _write_pixel_array(ds: pydicom.Dataset, output_array: np.ndarray) -> None:
    contiguous = np.ascontiguousarray(output_array)
    ds.PixelData = contiguous.tobytes()
    if contiguous.ndim == 4:
        ds.NumberOfFrames = contiguous.shape[0]
        ds.Rows = contiguous.shape[1]
        ds.Columns = contiguous.shape[2]
        ds.SamplesPerPixel = contiguous.shape[3]
    elif is_multiframe_grayscale(ds, contiguous):
        ds.NumberOfFrames = contiguous.shape[0]
        ds.Rows = contiguous.shape[1]
        ds.Columns = contiguous.shape[2]
        ds.SamplesPerPixel = 1
    elif contiguous.ndim == 3 and contiguous.shape[-1] in {3, 4}:
        ds.Rows = contiguous.shape[0]
        ds.Columns = contiguous.shape[1]
        ds.SamplesPerPixel = contiguous.shape[2]
    else:
        ds.Rows = contiguous.shape[0]
        ds.Columns = contiguous.shape[1]
        ds.SamplesPerPixel = 1

    if (
        contiguous.ndim >= 3
        and contiguous.shape[-1] in {3, 4}
        and not is_multiframe_grayscale(ds, contiguous)
    ):
        ds.PhotometricInterpretation = "RGB"
        ds.PlanarConfiguration = 0
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
    else:
        ds.PhotometricInterpretation = "MONOCHROME2"
        _set_grayscale_bit_metadata(ds, contiguous)

    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.is_implicit_VR = False
    ds.is_little_endian = True


# Input: `rendered_frame` vom Renderer und `source_frame` aus dem DICOM-Stack.
# Output: Frame in der Shape des Quellframes.
# Die Funktion reduziert RGB-Renderer-Ausgaben fuer Grayscale-DICOMs auf einen
# Kanal, damit nur Frame 0 ersetzt und der Frame-Stack konsistent bleibt.
def _coerce_rendered_frame_to_source_shape(
    rendered_frame: np.ndarray,
    source_frame: np.ndarray,
) -> np.ndarray:
    if rendered_frame.shape == source_frame.shape:
        return rendered_frame
    if source_frame.ndim == 2 and rendered_frame.ndim == 3:
        single_channel = rendered_frame[..., 0]
        if single_channel.shape == source_frame.shape:
            return single_channel
    raise ValueError(
        "Rendered frame shape does not match the source DICOM frame shape."
    )


# Input: `ds` mit Zieldataset und `pixels` mit Mono-Pixelarray.
# Output: Keine Rueckgabe.
# Die Funktion setzt BitsAllocated/BitsStored/HighBit passend zum Numpy-Dtype
# und laesst PixelData-Laenge und Metadaten zusammenpassen.
def _set_grayscale_bit_metadata(ds: pydicom.Dataset, pixels: np.ndarray) -> None:
    bits_allocated = int(pixels.dtype.itemsize * 8)
    ds.BitsAllocated = bits_allocated
    ds.BitsStored = bits_allocated
    ds.HighBit = bits_allocated - 1
    ds.PixelRepresentation = int(np.issubdtype(pixels.dtype, np.signedinteger))


# Input: `native` aus einem `SourceDocument` oder `InjectedDocument`.
# Output: pydicom-Dataset oder ValueError bei falschem Adapterzustand.
# Die Funktion kapselt die Runtime-Pruefung, damit Writer-Methoden typisiert
# mit dem nativen Handle arbeiten koennen.
def _require_dataset(native: object) -> pydicom.Dataset:
    if not isinstance(native, pydicom.Dataset):
        raise ValueError("DICOM writer requires a pydicom Dataset.")
    return native
