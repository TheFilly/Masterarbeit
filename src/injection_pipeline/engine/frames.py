"""Frame extraction and image conversion helpers for pixel injection."""

import math
from pathlib import Path

import numpy as np
import pydicom
from PIL import Image

from injection_pipeline.loaders.dicom import is_multiframe_grayscale


# Input: `ds` mit geladenem DICOM-Dataset.
# Output: Numpy-Array mit dem ersten darstellbaren Preview-Frame.
# Die Funktion reduziert DICOM-Multi-frame-Daten auf Frame 0 und nutzt
# Metadaten, damit RGB-Single-frames nicht als Frame-Stacks gelten.
def extract_preview_frame(ds: pydicom.Dataset) -> np.ndarray:
    pixel_array = np.asarray(ds.pixel_array)
    if pixel_array.ndim == 4:
        return np.asarray(pixel_array[0])
    if is_multiframe_grayscale(ds, pixel_array):
        return np.asarray(pixel_array[0])
    if pixel_array.ndim == 3 and pixel_array.shape[-1] in {3, 4}:
        return np.asarray(pixel_array)
    return np.asarray(pixel_array)


# Input: `frame` mit Graustufen- oder RGB-Pixelwerten.
# Output: Numpy-Array mit auf uint8 normalisierten Pixelwerten.
# Die Funktion behaelt bestehende uint8-Werte bei und skaliert andere Datentypen.
def normalize_to_uint8(frame: np.ndarray) -> np.ndarray:
    array = np.asarray(frame)
    if array.dtype == np.uint8:
        return array

    working = array.astype(np.float32)
    min_value = float(np.min(working))
    max_value = float(np.max(working))
    if math.isclose(min_value, max_value):
        return np.zeros_like(array, dtype=np.uint8)

    normalized = (working - min_value) / (max_value - min_value)
    return np.asarray(np.clip(normalized * 255.0, 0, 255).astype(np.uint8))


# Input: `frame` mit Graustufen- oder RGB-Pixelwerten.
# Output: PIL-RGB-Bild fuer den Renderer.
# Die Funktion normalisiert den Frame zuerst nach uint8 und konvertiert ihn dann
# in den einheitlichen RGB-Farbraum.
def frame_to_image(frame: np.ndarray) -> Image.Image:
    normalized = normalize_to_uint8(frame)
    if normalized.ndim == 2:
        return Image.fromarray(normalized, mode="L").convert("RGB")
    return Image.fromarray(normalized).convert("RGB")


# Input: `image` mit gerendertem Preview und `output_path` als Zielpfad.
# Output: Geschriebener Zielpfad.
# Die Funktion legt fehlende Elternordner an und schreibt die Preview-Datei als
# Nebeneffekt.
def save_preview_image(image: Image.Image, output_path: str | Path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return destination
