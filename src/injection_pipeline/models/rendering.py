"""Typed planning and rendering metadata models."""

from pathlib import Path
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from injection_pipeline.models.geometry import MaskBounds, Quad
from injection_pipeline.models.segments import TextSegment


class PixelPosition(BaseModel):
    """An integer pixel offset for a rendered overlay."""

    model_config = ConfigDict(extra="forbid")

    x: int
    y: int


class PixelSize(BaseModel):
    """An integer width and height in pixels."""

    model_config = ConfigDict(extra="forbid")

    width: int
    height: int


class HandwritingAssetRef(BaseModel):
    """A normalized handwriting manifest entry with generator extras."""

    model_config = ConfigDict(extra="allow")

    asset_id: str
    text: str
    identity_field: str
    image_path: Path
    mask_path: Path
    ink_color: str | None
    background_mode: str | None


class RenderPlanItem(BaseModel):
    """One planned visible identity field before pixel placement."""

    model_config = ConfigDict(extra="forbid")

    label: str
    category: str | None = None
    text: str
    text_segments: list[TextSegment]
    identity_field: str
    region: str
    rotation_degrees: int
    line_index: int
    renderer_type: Literal["font_text", "handwriting_asset"] = Field(
        default="font_text", exclude_if=lambda value: value == "font_text"
    )
    asset_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    asset: HandwritingAssetRef | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    # Input: `self` mit Volltext und geordneten Rendersegmenten.
    # Output: Das validierte Renderplan-Element.
    # Die Funktion ergaenzt alte Plaene um eine Kategorie und erzwingt
    # Rekonstruktion des Volltexts sowie einen PII-Anteil.
    def _validate_segments(self) -> "RenderPlanItem":
        if self.category is None:
            self.category = self.label
        if "".join(segment.text for segment in self.text_segments) != self.text:
            raise ValueError("Text segments must reconstruct the render text.")
        if not any(
            segment.kind == "pii" and segment.text for segment in self.text_segments
        ):
            raise ValueError("At least one non-empty pii text segment is required.")
        if self.renderer_type == "handwriting_asset" and (
            self.asset_id is None or self.asset is None
        ):
            raise ValueError("Handwriting render items require asset_id and asset.")
        return self


class AnnotationRenderDetail(BaseModel):
    """Renderer details for one visible annotation."""

    model_config = ConfigDict(extra="forbid")

    position: PixelPosition
    font_family: str | None = None
    font_name: str | None = None
    font_size: int | None = None
    padding: int | None = None
    fill_rgb: list[int] | None = None
    stroke_fill_rgb: list[int] | None = None
    stroke_width: int | None = None
    background_enabled: bool | None = None
    background_color: list[int] | None = None
    text_segments: list[TextSegment] | None = None
    renderer_type: Literal["handwriting_asset"] | None = None
    asset_id: str | None = None
    asset_path: Path | None = None
    mask_path: Path | None = None
    ink_color: str | None = None
    background_mode: str | None = None
    geometry_source: str
    segment_geometry_source: str | None = None
    mask_coordinate_space: str
    mask_alpha_threshold: int
    text_mask_bounds: MaskBounds | None
    pii_mask_bounds: MaskBounds | None
    label_mask_bounds: MaskBounds | None
    prefix_mask_bounds: MaskBounds | None = None
    suffix_mask_bounds: MaskBounds | None = None
    text_box_size: PixelSize
    rotated_box_size: PixelSize
    rendered_text_corners: Quad

    @model_validator(mode="after")
    # Input: `self` mit optionalen Font- oder Handschriftfeldern.
    # Output: Das validierte Renderdetail.
    # Die Funktion stellt sicher, dass jeder Renderer die passende Metadatenform nutzt.
    def _validate_renderer_fields(self) -> "AnnotationRenderDetail":
        if self.renderer_type == "handwriting_asset":
            if (
                self.asset_id is None
                or self.asset_path is None
                or self.mask_path is None
            ):
                raise ValueError("Handwriting render details require asset paths.")
        elif self.font_family is None:
            raise ValueError("Font render details require font_family.")
        return self

    @model_serializer(mode="wrap")
    # Input: `handler` mit Pydantic-Serializer fuer das Renderdetail.
    # Output: Rendererabhaengiger JSON-/Python-Datensatz in Bestandsreihenfolge.
    # Die Funktion laesst Font- und Handschriftfelder jeweils nur in ihrer
    # prototypeigenen Teilform erscheinen und bewahrt vorhandene `null`s.
    def _serialize_renderer_fields(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        data = cast(dict[str, Any], handler(self))
        if self.renderer_type == "handwriting_asset":
            for field_name in (
                "font_family",
                "font_name",
                "font_size",
                "padding",
                "fill_rgb",
                "stroke_fill_rgb",
                "stroke_width",
                "background_enabled",
                "background_color",
            ):
                data.pop(field_name, None)
        else:
            for field_name in (
                "renderer_type",
                "asset_id",
                "asset_path",
                "mask_path",
                "ink_color",
                "background_mode",
            ):
                data.pop(field_name, None)
        return data


class RenderedAnnotation(BaseModel):
    """A rendered annotation with its final image-space geometry."""

    model_config = ConfigDict(extra="forbid")

    label: str
    category: str | None = None
    text: str
    rendered_text: str
    generic_text: str
    pii_text: str
    prefix: str = ""
    suffix: str = ""
    region: str
    rotation_degrees: int
    corners: Quad
    label_corners: Quad | None
    prefix_corners: Quad | None = None
    suffix_corners: Quad | None = None
    render_metadata: AnnotationRenderDetail

    @model_validator(mode="after")
    # Input: `self` mit neuer oder alter Renderer-Annotation.
    # Output: Normalisierte Renderer-Annotation.
    # Die Funktion haelt alte `label_corners`-Records kompatibel und fuellt
    # Kategorie sowie Prefix-/Suffix-Text aus dem gerenderten Text nach.
    def _normalize_segment_fields(self) -> "RenderedAnnotation":
        if self.category is None:
            self.category = self.label
        if self.prefix_corners is None:
            self.prefix_corners = self.label_corners
        if not self.prefix and not self.suffix and self.text in self.rendered_text:
            prefix_text, _, suffix_text = self.rendered_text.partition(self.text)
            self.prefix = prefix_text
            self.suffix = suffix_text
        return self


class HandwritingRenderAsset(BaseModel):
    """Handwriting asset summary recorded by the pixel engine."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str | None
    asset_path: Path | None
    mask_path: Path | None
    ink_color: str | None
    background_mode: str | None


class EngineRenderMetadata(BaseModel):
    """Complete metadata emitted by the visible pixel renderer."""

    model_config = ConfigDict(extra="forbid")

    seed: int
    rotation_degrees: int
    allowed_rotations_degrees: list[int]
    frame_count: int
    applied_frame_indices: list[int]
    effective_font_family: str
    effective_font_size_px: int
    background_enabled: bool
    background_color: list[int] | None
    geometry_source: str
    renderer_types: list[str]
    handwriting_assets: list[HandwritingRenderAsset]
    geometry_notes: str
    mask_alpha_threshold: int
    visible_annotations: list[RenderedAnnotation]
