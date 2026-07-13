"""Canonical Pydantic models for pipeline boundaries and run artifacts."""

from injection_pipeline.models.adapters import (
    DocumentLoader,
    DocumentWriter,
    InjectedDocument,
    SourceDocument,
    TagPlan,
)
from injection_pipeline.models.annotations import (
    BoxAnnotation,
    DicomTagAnnotation,
    SpanAnnotation,
)
from injection_pipeline.models.dicom import DicomContext
from injection_pipeline.models.geometry import ImagePoint, MaskBounds, PdfPoint, Quad
from injection_pipeline.models.identity import Identity
from injection_pipeline.models.record import (
    RecordRenderMetadata,
    RunMetadata,
    RunRecord,
    load_run_record,
)
from injection_pipeline.models.rendering import (
    AnnotationRenderDetail,
    EngineRenderMetadata,
    HandwritingAssetRef,
    HandwritingRenderAsset,
    PixelPosition,
    PixelSize,
    RenderedAnnotation,
    RenderPlanItem,
)
from injection_pipeline.models.segments import TextSegment

__all__ = [
    "AnnotationRenderDetail",
    "BoxAnnotation",
    "DicomContext",
    "DicomTagAnnotation",
    "DocumentLoader",
    "DocumentWriter",
    "EngineRenderMetadata",
    "HandwritingAssetRef",
    "HandwritingRenderAsset",
    "Identity",
    "ImagePoint",
    "InjectedDocument",
    "MaskBounds",
    "PdfPoint",
    "PixelPosition",
    "PixelSize",
    "Quad",
    "RecordRenderMetadata",
    "RenderPlanItem",
    "RenderedAnnotation",
    "RunMetadata",
    "RunRecord",
    "SourceDocument",
    "SpanAnnotation",
    "TagPlan",
    "TextSegment",
    "load_run_record",
]
