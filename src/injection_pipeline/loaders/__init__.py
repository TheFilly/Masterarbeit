"""Format-specific document loaders (adapters)."""

from injection_pipeline.loaders.dicom import load_dicom, summarize_dicom

__all__ = ["load_dicom", "summarize_dicom"]
