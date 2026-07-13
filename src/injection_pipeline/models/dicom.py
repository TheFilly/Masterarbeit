"""DICOM-specific context carried by a run record."""

from pydantic import BaseModel, ConfigDict


class DicomContext(BaseModel):
    """Lightweight DICOM metadata captured before and after injection."""

    model_config = ConfigDict(extra="forbid")

    modality: str | None
    sop_instance_uid: str | None
    study_instance_uid: str | None
    series_instance_uid: str | None
    rows: int | None
    columns: int | None
    samples_per_pixel: int | None
    photometric_interpretation: str | None
    number_of_frames: int | None
    has_pixel_data: bool
