"""Typed prepared-overlay payloads shared by placement and rendering."""

from typing import Any, TypedDict, cast

from PIL import Image

MaskBounds = tuple[int, int, int, int]
_PREPARED_OVERLAY_KEY = "_injection_pipeline_prepared_overlay"


class PreparedOverlay(TypedDict):
    """Internal prepared overlay shared between sizing and final composition."""

    label: str
    text: str
    generic_text: str
    pii_text: str
    prefix_text: str
    suffix_text: str
    region: str
    rotation_degrees: int
    rotated_layer: Image.Image
    rotated_size: tuple[int, int]
    text_box_size: tuple[int, int]
    text_source_bounds: MaskBounds
    pii_source_bounds: MaskBounds
    label_source_bounds: MaskBounds | None
    suffix_source_bounds: MaskBounds | None
    text_rotated_bounds: MaskBounds
    pii_rotated_bounds: MaskBounds
    label_rotated_bounds: MaskBounds | None
    suffix_rotated_bounds: MaskBounds | None
    render_metadata: dict[str, Any]


# Input: `annotation` mit internem Cache-Eintrag.
# Output: Vorbereitetes Overlay oder None.
# Die Funktion liest nur den privaten Pipeline-Key und laesst externe
# Annotation-Felder unveraendert.
def get_prepared_overlay(annotation: dict[str, Any]) -> PreparedOverlay | None:
    prepared = annotation.get(_PREPARED_OVERLAY_KEY)
    if prepared is None:
        return None
    return cast(PreparedOverlay, prepared)


# Input: `annotation` und ein vorbereitetes Overlay aus dem Placement-Pass.
# Output: Neue Annotation mit privatem Cache-Eintrag.
# Die Funktion kapselt den internen Key, damit er nicht in oeffentliche Modelle
# oder Ground-Truth-Artefakte wandert.
def with_prepared_overlay(
    annotation: dict[str, Any],
    prepared_overlay: PreparedOverlay,
) -> dict[str, Any]:
    return {**annotation, _PREPARED_OVERLAY_KEY: prepared_overlay}
