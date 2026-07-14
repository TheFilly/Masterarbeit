"""Aspect-fit placement and image-to-PDF coordinate transforms."""

from pathlib import Path

from PIL import Image

from injection_pipeline.models.geometry import ImagePoint, PdfPoint
from injection_pipeline.pdf.models import PdfPlacement


# Input: `page_size` und `image_size` in Punkten beziehungsweise Pixeln.
# Output: Breite, Hoehe und Skalierungsfaktor der platzierten Bildflaeche.
# Das Bild wird nur verkleinert und bei nativer Groesse zentriert.
def aspect_fit_size(
    page_size: tuple[float, float],
    image_size: tuple[int, int],
    slot: str,
    margin: float = 36.0,
) -> PdfPlacement:
    page_width, page_height = page_size
    image_width, image_height = image_size
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image dimensions must be positive.")
    slot_width = page_width * 0.45
    slot_height = page_height * 0.35
    if slot not in {"top_left", "top_right"}:
        raise ValueError("Unsupported PDF slot. Choose 'top_left' or 'top_right'.")
    if margin * 2 + slot_width > page_width or margin * 2 + slot_height > page_height:
        raise ValueError("PDF image slot does not fit inside the target page.")
    scale = min(1.0, slot_width / image_width, slot_height / image_height)
    width = image_width * scale
    height = image_height * scale
    slot_x = margin if slot == "top_left" else page_width - margin - slot_width
    slot_y = page_height - margin - slot_height
    x = slot_x + (slot_width - width) / 2
    y = slot_y + (slot_height - height) / 2
    return PdfPlacement(
        page_index=0,
        slot=slot,
        x=x,
        y=y,
        width=width,
        height=height,
        scale=scale,
        image_width_px=image_width,
        image_height_px=image_height,
    )


# Input: `point` im Bildraum und die berechnete PDF-Platzierung.
# Output: Derselbe Punkt im PDF-Raum mit invertierter Y-Achse.
# Die Funktion bewahrt die Eckreihenfolge und nutzt ausschliesslich das
# tatsaechliche aspect-fit Rechteck.
def image_to_pdf_point(point: ImagePoint, placement: PdfPlacement) -> PdfPoint:
    return PdfPoint(
        x=placement.x + point.x / placement.image_width_px * placement.width,
        y=placement.y
        + placement.height
        - point.y / placement.image_height_px * placement.height,
    )


# Input: `image_path` mit einem PNG/JPG und Seiten-/Slotparametern.
# Output: Validierte Platzierung fuer das Bild.
# Die Bildabmessungen werden aus der Datei gelesen; die Quelldatei wird nicht
# veraendert.
def placement_for_image(
    image_path: Path,
    page_size: tuple[float, float],
    slot: str,
    page_index: int,
) -> PdfPlacement:
    with Image.open(image_path) as image:
        placement = aspect_fit_size(page_size, image.size, slot)
    return placement.model_copy(update={"page_index": page_index})
