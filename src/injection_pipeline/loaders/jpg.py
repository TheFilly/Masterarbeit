"""JPG loader adapter."""

from pathlib import Path
from typing import ClassVar

import numpy as np
from PIL import Image

from injection_pipeline.models.adapters import SourceDocument


class JpgLoader:
    """Adapter for loading JPG documents into the shared source model."""

    format_id: ClassVar[str] = "jpg"
    extensions: ClassVar[tuple[str, ...]] = (".jpg", ".jpeg")

    # Input: `path` mit absolutem oder relativem Pfad zur JPG-Datei.
    # Output: `SourceDocument` mit RGB-Frame und PIL-Bild als nativer Handle.
    # Die Methode nutzt die bisherige RGB-Konvertierung und veraendert die
    # Quelldatei nicht.
    def load(self, path: Path) -> SourceDocument:
        image = Image.open(path).convert("RGB")
        return SourceDocument(
            format_id=self.format_id,
            path=path,
            frame=np.asarray(image),
            frame_count=1,
            native=image,
            context=None,
        )
