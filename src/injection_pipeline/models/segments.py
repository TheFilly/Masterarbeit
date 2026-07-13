"""Typed text segments used by visible render plans."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TextSegment(BaseModel):
    """A generic or personally identifying part of rendered text."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["generic", "pii"]
    text: str
