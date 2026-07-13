"""Taxonomy-agnostic synthetic identity models."""

from pydantic import BaseModel, ConfigDict


class Identity(BaseModel):
    """A generated identity whose fields come from an external taxonomy."""

    model_config = ConfigDict(extra="forbid")

    identity_id: str
    seed: int
    fields: dict[str, str]
