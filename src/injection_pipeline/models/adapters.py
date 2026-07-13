"""Document adapter models and protocols."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict

from injection_pipeline.models.annotations import BoxAnnotation, DicomTagAnnotation
from injection_pipeline.models.dicom import DicomContext

TagPlan = Mapping[str, DicomTagAnnotation]


class SourceDocument(BaseModel):
    """A loaded document at the adapter boundary."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    format_id: str
    path: Path
    frame: Any
    frame_count: int
    native: Any | None
    context: DicomContext | None


class InjectedDocument(BaseModel):
    """A rendered document ready for native-format persistence."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    source: SourceDocument
    rendered_frame: Any
    native: Any | None
    tag_annotations: list[DicomTagAnnotation]
    box_annotations: list[BoxAnnotation]
    output_context: DicomContext | None


class DocumentLoader(Protocol):
    """Structural contract for format-specific loaders."""

    format_id: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]

    # Input: `path` mit Quelleingabedatei fuer das Format.
    # Output: `SourceDocument` mit Renderframe und optionalem nativen Kontext.
    # Die Methode darf formatnative Handles im Dokument speichern, mutiert die
    # Quelle aber nicht.
    def load(self, path: Path) -> SourceDocument: ...


class DocumentWriter(Protocol):
    """Structural contract for format-specific writers."""

    format_id: ClassVar[str]
    output_suffix: ClassVar[str]

    # Input: `document` mit geladenem Quelldokument, `tag_plan` mit DICOM-Annotationen.
    # Output: Native Tag-Annotationen, bei Rasterformaten eine leere Liste.
    # Die Methode darf das native Dokument fuer die spaetere Persistierung mutieren.
    def inject_native_metadata(
        self,
        document: SourceDocument,
        tag_plan: TagPlan,
    ) -> list[DicomTagAnnotation]: ...

    # Input: `document` mit gerendertem Frame, `output_path` mit Zielpfad.
    # Output: Keine Rueckgabe.
    # Die Methode schreibt das native Ausgabeformat und darf `output_context`
    # am Dokument setzen, wenn das Format Kontextdaten besitzt.
    def write(self, document: InjectedDocument, output_path: Path) -> None: ...
