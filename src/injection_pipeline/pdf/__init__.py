"""PDF input and output adapters for image-based PII injection."""

from injection_pipeline.pdf.models import (
    PdfAnnotationRecord,
    PdfCompositionArtifacts,
    PdfMakeArtifacts,
    PdfMakeImageAnnotationInput,
    PdfMakeImageInput,
    PdfMakeTextInput,
    PdfPlacement,
    PdfTemplate,
)

__all__ = [
    "PdfAnnotationRecord",
    "PdfCompositionArtifacts",
    "PdfMakeArtifacts",
    "PdfMakeImageAnnotationInput",
    "PdfMakeImageInput",
    "PdfMakeTextInput",
    "PdfPlacement",
    "PdfTemplate",
]
