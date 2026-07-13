"""Format-specific document loaders (adapters)."""

from injection_pipeline.loaders.dicom import DicomLoader, load_dicom, summarize_dicom
from injection_pipeline.loaders.jpg import JpgLoader

__all__ = [
    "DicomLoader",
    "JpgLoader",
    "load_dicom",
    "summarize_dicom",
]
