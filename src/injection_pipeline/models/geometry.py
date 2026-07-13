"""Coordinate and image-mask geometry models."""

from pydantic import BaseModel, ConfigDict, RootModel, field_validator, model_validator


class ImagePoint(BaseModel):
    """A point in image pixels with a top-left origin."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class PdfPoint(BaseModel):
    """A point in PDF points with a bottom-left origin."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class Quad(RootModel[list[ImagePoint]]):
    """Four ordered image points describing a quadrilateral."""

    @field_validator("root")
    @classmethod
    # Input: `value` mit geordneten Bildpunkten.
    # Output: Unveraenderte Liste mit genau vier Punkten.
    # Die Funktion sichert die Polygon-Arity fuer alle sichtbaren Boxen.
    def _validate_arity(cls, value: list[ImagePoint]) -> list[ImagePoint]:
        if len(value) != 4:
            raise ValueError("A quad must contain exactly four points.")
        return value


class MaskBounds(BaseModel):
    """A half-open rectangular mask bound and its derived dimensions."""

    model_config = ConfigDict(extra="forbid")

    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int

    @model_validator(mode="after")
    # Input: `self` mit absoluten Bounds und gespeicherten Dimensionen.
    # Output: Das validierte `MaskBounds`-Objekt.
    # Die Funktion verhindert widerspruechliche Breiten- und Hoehenangaben.
    def _validate_dimensions(self) -> "MaskBounds":
        if self.width != self.right - self.left:
            raise ValueError("Mask width must equal right - left.")
        if self.height != self.bottom - self.top:
            raise ValueError("Mask height must equal bottom - top.")
        return self
