"""JPG writer adapter."""

from pathlib import Path
from typing import ClassVar

import numpy as np
from PIL import Image

from injection_pipeline.models.adapters import InjectedDocument, SourceDocument, TagPlan
from injection_pipeline.models.annotations import DicomTagAnnotation


class JpgWriter:
    """Adapter for writing rendered JPG documents."""

    format_id: ClassVar[str] = "jpg"
    output_suffix: ClassVar[str] = ".jpg"

    # Input: `document` mit geladenem JPG, `tag_plan` mit ignorierten DICOM-Tags.
    # Output: Leere Liste, da JPG keine native DICOM-Metadaten injiziert.
    # Die Methode hat keine Nebeneffekte und erhaelt den bisherigen Rasterpfad.
    def inject_native_metadata(
        self,
        document: SourceDocument,
        tag_plan: TagPlan,
    ) -> list[DicomTagAnnotation]:
        del document, tag_plan
        return []

    # Input: `document` mit gerendertem RGB-Frame, `output_path` mit Zielpfad.
    # Output: Keine Rueckgabe.
    # Die Methode schreibt das JPG mit den bisherigen Pillow-Defaults und setzt
    # keinen Formatkontext.
    def write(self, document: InjectedDocument, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.asarray(document.rendered_frame)).convert("RGB").save(
            output_path,
            format="JPEG",
        )
        document.output_context = None
