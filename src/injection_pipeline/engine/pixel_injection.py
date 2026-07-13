"""Compatibility exports for the decomposed pixel-injection engine."""

from injection_pipeline.engine.fonts import (
    _DEFAULT_FONT_SIZE_PX,
    _FONT_PATHS,
    _resolve_font_size_px,
    load_default_font,
)
from injection_pipeline.engine.frames import (
    extract_preview_frame,
    frame_to_image,
    normalize_to_uint8,
    save_preview_image,
)
from injection_pipeline.engine.geometry import (
    _MASK_ALPHA_THRESHOLD,
    ALLOWED_ROTATIONS_DEGREES,
    _coerce_position,
    _estimate_rotated_size,
    _mask_bounds_to_corners,
    _require_mask_bounds,
    _rotated_corners,
    _serialize_mask_bounds,
    _thresholded_mask_bounds,
    _validate_rotation,
)
from injection_pipeline.engine.handwriting import (
    _prepare_handwriting_asset_overlay,
    _render_handwriting_annotation,
)
from injection_pipeline.engine.injector import (
    _build_box_annotation,
    _inject_visible_text_into_frame,
    _render_frame_with_annotations,
    inject_visible_text,
    inject_visible_text_into_image,
    render_visible_annotations,
)
from injection_pipeline.engine.overlay import (
    _TEXT_BACKGROUND_COLORS,
    _prepare_annotation_overlay,
    _render_single_annotation,
)
from injection_pipeline.engine.placement import (
    _VALID_PLACEMENT_MODES,
    _materialize_positions,
)
from injection_pipeline.engine.segments import (
    _draw_segment_masks,
    _normalize_text_segments,
    _resolve_segment_draw_bounds,
    _split_prefix_and_pii_text,
)
from injection_pipeline.writers.dicom import _write_pixel_array

__all__ = [
    "ALLOWED_ROTATIONS_DEGREES",
    "_DEFAULT_FONT_SIZE_PX",
    "_FONT_PATHS",
    "_MASK_ALPHA_THRESHOLD",
    "_TEXT_BACKGROUND_COLORS",
    "_VALID_PLACEMENT_MODES",
    "_build_box_annotation",
    "_coerce_position",
    "_draw_segment_masks",
    "_estimate_rotated_size",
    "_inject_visible_text_into_frame",
    "_mask_bounds_to_corners",
    "_materialize_positions",
    "_normalize_text_segments",
    "_prepare_annotation_overlay",
    "_prepare_handwriting_asset_overlay",
    "_render_frame_with_annotations",
    "_render_handwriting_annotation",
    "_render_single_annotation",
    "_require_mask_bounds",
    "_resolve_font_size_px",
    "_resolve_segment_draw_bounds",
    "_rotated_corners",
    "_serialize_mask_bounds",
    "_split_prefix_and_pii_text",
    "_thresholded_mask_bounds",
    "_validate_rotation",
    "_write_pixel_array",
    "extract_preview_frame",
    "frame_to_image",
    "inject_visible_text",
    "inject_visible_text_into_image",
    "load_default_font",
    "normalize_to_uint8",
    "render_visible_annotations",
    "save_preview_image",
]
