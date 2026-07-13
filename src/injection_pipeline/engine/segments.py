"""Text segment helpers for pixel-injection masks."""

from typing import Any

from PIL import Image, ImageDraw, ImageFont


# Input: `annotation` mit optionalen Textsegmenten, `full_text` mit Rendertext.
# Output: Normalisierte Textsegmente.
# Die Funktion faellt ohne gueltige Segmente auf ein reines PII-Segment zurueck
# und validiert sonst Rekonstruktion und PII-Anteil.
def _normalize_text_segments(
    annotation: dict[str, Any], full_text: str
) -> list[dict[str, str]]:
    raw_segments = annotation.get("text_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        return [{"kind": "pii", "text": full_text}]

    normalized: list[dict[str, str]] = []
    reconstructed = ""
    pii_seen = False
    for segment in raw_segments:
        if not isinstance(segment, dict):
            continue
        kind = str(segment.get("kind", "generic"))
        text = str(segment.get("text", ""))
        reconstructed += text
        if kind == "pii" and text:
            pii_seen = True
        normalized.append({"kind": kind, "text": text})

    if reconstructed != full_text or not pii_seen:
        raise ValueError(
            f"Invalid text_segments for {annotation.get('label', 'visible_text')!r}."
        )
    return normalized


# Input: Textsegmente, Font, Textursprung und Zielmasken.
# Output: Keine Rueckgabe.
# Die Funktion rendert PII- und Label-Segmente in getrennte Masken bei identischer
# Textreihenfolge und mutiert beide Masken als Nebeneffekt.
def _draw_segment_masks(
    *,
    text_segments: list[dict[str, str]],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    origin: tuple[float, float],
    stroke_width: int,
    pii_mask: Image.Image,
    label_mask: Image.Image,
) -> None:
    cursor_x = origin[0]
    pii_draw = ImageDraw.Draw(pii_mask)
    label_draw = ImageDraw.Draw(label_mask)

    for segment in text_segments:
        segment_text = segment["text"]
        if not segment_text:
            continue

        segment_bounds = _resolve_segment_draw_bounds(
            font=font,
            origin=(cursor_x, origin[1]),
            segment_text=segment_text,
            stroke_width=stroke_width,
        )
        if segment["kind"] == "pii":
            pii_draw.text(
                (cursor_x, origin[1]),
                segment_text,
                font=font,
                fill=255,
                stroke_width=stroke_width,
                stroke_fill=255,
            )
        else:
            label_draw.text(
                (cursor_x, origin[1]),
                segment_text,
                font=font,
                fill=255,
                stroke_width=stroke_width,
                stroke_fill=255,
            )
        cursor_x = segment_bounds[2]


# Input: `text_segments` mit geordneten generischen und PII-Anteilen.
# Output: Generisches Praefix und zusammengefuegter PII-Text.
# Die Funktion sammelt nur vorangestellte Nicht-PII-Segmente als Label und
# verlangt mindestens ein nicht leeres PII-Segment.
def _split_prefix_and_pii_text(
    text_segments: list[dict[str, str]],
) -> tuple[str, str]:
    prefix_text = ""
    pii_text = ""
    for segment in text_segments:
        segment_kind = segment["kind"]
        segment_text = segment["text"]
        if segment_kind == "pii":
            pii_text += segment_text
        elif not pii_text:
            prefix_text += segment_text
    if not pii_text:
        raise ValueError("At least one non-empty pii text segment is required.")
    return prefix_text, pii_text


# Input: Font, Ursprung, Segmenttext und Stroke-Breite.
# Output: Text-Bounds im Draw-Koordinatensystem.
# Die Funktion misst ein Segment separat, damit das naechste Segment denselben
# Textfluss fortsetzen kann.
def _resolve_segment_draw_bounds(
    *,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    origin: tuple[float, float],
    segment_text: str,
    stroke_width: int,
) -> tuple[float, float, float, float]:
    scratch = ImageDraw.Draw(Image.new("L", (1, 1), 0))
    left, top, right, bottom = scratch.textbbox(
        origin,
        segment_text,
        font=font,
        stroke_width=stroke_width,
    )
    return float(left), float(top), float(right), float(bottom)
