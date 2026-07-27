"""Writer for composing several injected images and direct texts into one PDF."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image
from pypdf import PdfReader
from pypdf import PdfWriter as PypdfWriter
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

from injection_pipeline.models.geometry import ImagePoint, PdfPoint, Quad
from injection_pipeline.pdf.make_layout import (
    PAGE_MARGIN,
    build_make_pdf_layout,
    page_size_for,
    rotate_point_in_rect,
    rotated_quad,
)
from injection_pipeline.pdf.models import (
    PdfMakeAnnotationRecord,
    PdfMakeArtifacts,
    PdfMakeImageAnnotation,
    PdfMakeImageInput,
    PdfMakeLayoutDecision,
    PdfMakeLayoutPlacement,
    PdfMakeOutputFiles,
    PdfMakeTextAnnotation,
    PdfMakeTextInput,
    PdfQuad,
    PdfTemplate,
)

DEFAULT_MAKE_PDF_SEED = 0
TEXT_FONT_NAME = "Helvetica"
TEXT_FONT_SIZE = 11.0
TEXT_LEADING = 13.5
TEXT_PADDING = 4.0
TEXT_MAX_WIDTH = 260.0
ANNOTATION_STROKE_WIDTH = 1.25
SIZE_TOLERANCE = 0.01


@dataclass(frozen=True)
class _TextRenderPlan:
    """Measured PDF-native text layout for one direct text input."""

    rendered_text: str
    lines: tuple[str, ...]
    width: float
    height: float
    font_name: str
    font_size: float
    leading: float
    padding: float


# Input: PDF-Template, bereits injizierte Bilder, Text-Inputs, Ausgabeordner und Seed.
# Output: `PdfMakeArtifacts` mit clean PDF, annotated PDF und JSON-Sidecar.
# Die Funktion validiert alle Eingaben vor dem ersten Schreibzugriff, schreibt
# drei Dateien in `output_dir` und bricht bei unaufloesbaren Handschrift-Texten ab.
def make_pdf_composition(
    *,
    template: PdfTemplate,
    images: list[PdfMakeImageInput],
    texts: list[PdfMakeTextInput],
    output_dir: Path,
    seed: int | None = None,
) -> PdfMakeArtifacts:
    resolved_seed = DEFAULT_MAKE_PDF_SEED if seed is None else seed
    _validate_template(template)
    _validate_make_inputs(images, texts)
    _ensure_pdf_native_texts(texts)
    image_sizes = _load_image_sizes(images)
    for image_input, image_size in zip(images, image_sizes, strict=True):
        _validate_image_annotations(image_input, image_size)

    output_dir = _prepare_output_dir(output_dir)
    text_plans = _prepare_text_plans(texts, template.page_sizes[0])
    layout_decisions = build_make_pdf_layout(
        template,
        image_sizes,
        [(plan.width, plan.height) for plan in text_plans],
        resolved_seed,
    )
    image_annotations, text_annotations = _build_annotation_records(
        images,
        texts,
        image_sizes,
        text_plans,
        layout_decisions,
    )

    outputs = PdfMakeOutputFiles(
        clean_pdf=output_dir / "pdf_make.pdf",
        annotated_pdf=output_dir / "pdf_make_annotated.pdf",
        annotation_json=output_dir / "pdf_make_annotations.json",
    )
    record = PdfMakeAnnotationRecord(
        source_pdf=template.source_file,
        output_dir=output_dir,
        seed=resolved_seed,
        outputs=outputs,
        template=template,
        images=images,
        texts=texts,
        layout_decisions=layout_decisions,
        image_annotations=image_annotations,
        text_annotations=text_annotations,
    )
    _write_composed_pdf(
        template,
        images,
        text_plans,
        layout_decisions,
        outputs.clean_pdf,
        image_annotations=[],
        text_annotations=[],
    )
    _write_composed_pdf(
        template,
        images,
        text_plans,
        layout_decisions,
        outputs.annotated_pdf,
        image_annotations=image_annotations,
        text_annotations=text_annotations,
    )
    outputs.annotation_json.write_text(
        json.dumps(record.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return PdfMakeArtifacts(
        clean_pdf=outputs.clean_pdf,
        annotated_pdf=outputs.annotated_pdf,
        annotation_json=outputs.annotation_json,
        record=record,
    )


# Input: `template` mit Quelldatei und Seitenmetadaten.
# Output: Keine Rueckgabe; wirft bei ungueltigem Template.
# Die Funktion gleicht die Modellmetadaten mit dem lesbaren PDF ab, bevor
# Overlays erzeugt oder Dateien geschrieben werden.
def _validate_template(template: PdfTemplate) -> None:
    if not template.source_file.is_file():
        raise FileNotFoundError(f"PDF template does not exist: {template.source_file}")
    if template.page_count < 1 or not template.page_sizes:
        raise ValueError("PDF template must contain at least one page.")
    if template.page_count != len(template.page_sizes):
        raise ValueError("PDF template page_count must match page_sizes.")
    if any(width <= 0 or height <= 0 for width, height in template.page_sizes):
        raise ValueError("PDF template page sizes must be positive.")
    reader = PdfReader(str(template.source_file))
    if len(reader.pages) != template.page_count:
        raise ValueError("PDF template metadata does not match the source PDF.")
    for page, expected_size in zip(reader.pages, template.page_sizes, strict=True):
        actual_size = (float(page.mediabox.width), float(page.mediabox.height))
        if (
            abs(actual_size[0] - expected_size[0]) > SIZE_TOLERANCE
            or abs(actual_size[1] - expected_size[1]) > SIZE_TOLERANCE
        ):
            raise ValueError(
                "PDF template page size metadata does not match the source PDF."
            )


# Input: Bild- und Textlisten.
# Output: Keine Rueckgabe; wirft bei fehlenden Pflichtwerten.
# Die Pruefung uebernimmt den bestehenden API-Rand fuer Kategorie und Wert,
# ohne leere Prefix-/Suffix-Strings zu verbieten.
def _validate_make_inputs(
    images: list[PdfMakeImageInput],
    texts: list[PdfMakeTextInput],
) -> None:
    if not images:
        raise ValueError("images must contain at least one image.")
    if not texts:
        raise ValueError("texts must contain at least one text.")
    for image_input in images:
        if not image_input.path.is_file():
            raise FileNotFoundError(
                f"PDF make image does not exist: {image_input.path}"
            )
        for annotation in image_input.annotations:
            _validate_text_fields(
                annotation.category,
                annotation.value,
                annotation.prefix,
                annotation.suffix,
            )
            if annotation.rendered_text != (
                annotation.prefix + annotation.value + annotation.suffix
            ):
                raise ValueError(
                    "image annotation rendered_text must match prefix + value + suffix."
                )
    for text in texts:
        _validate_text_fields(text.category, text.value, text.prefix, text.suffix)


# Input: Textfelder analog zur bestehenden Public API.
# Output: Keine Rueckgabe; wirft bei ungueltigen Strings.
# `prefix` und `suffix` duerfen leer sein, `category` und `value` nicht.
def _validate_text_fields(
    category: str,
    value: str,
    prefix: str,
    suffix: str,
) -> None:
    if category.strip() == "":
        raise ValueError("category must be a non-empty string.")
    if value == "":
        raise ValueError("value must be a non-empty string.")
    if not isinstance(prefix, str) or not isinstance(suffix, str):
        raise ValueError("prefix and suffix must be strings.")


# Input: Direct-text Inputs.
# Output: Keine Rueckgabe; wirft bei `handwritten=True`.
# Der isolierte Writer besitzt ohne Public-API-Parameter keine sichere Asset-Quelle;
# Handschrift muss als Bildinput uebergeben oder spaeter per Resolver angebunden
# werden.
def _ensure_pdf_native_texts(texts: list[PdfMakeTextInput]) -> None:
    handwritten_indices = [
        index for index, text in enumerate(texts) if text.handwritten
    ]
    if handwritten_indices:
        raise ValueError(
            "handwritten PDF text requires a resolved handwriting asset. "
            "Pass pre-rendered handwriting as an image annotation or add a "
            "future make_pdf handwriting resolver; direct text indices are "
            f"{handwritten_indices}."
        )


# Input: Bild-Inputs mit existierenden Pfaden.
# Output: Bildgroessen als Pixel-Tupel.
# Die Funktion liest nur Metadaten ueber PIL und veraendert die Bilddateien nicht.
def _load_image_sizes(images: list[PdfMakeImageInput]) -> list[tuple[int, int]]:
    sizes: list[tuple[int, int]] = []
    for image_input in images:
        try:
            with Image.open(image_input.path) as image:
                width, height = image.size
        except Exception as exc:
            raise ValueError(
                f"Unable to read PDF make image: {image_input.path}"
            ) from exc
        if width <= 0 or height <= 0:
            raise ValueError("PDF make image dimensions must be positive.")
        sizes.append((width, height))
    return sizes


# Input: Ausgabeordner.
# Output: Existierender, normalisierter Ausgabeordner.
# Die Funktion legt fehlende Verzeichnisse an und lehnt Dateipfade als Ziel ab.
def _prepare_output_dir(output_dir: Path) -> Path:
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"output_dir must be a directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# Input: Bild-Input und seine Pixelgroesse.
# Output: Keine Rueckgabe; wirft bei Annotationen ausserhalb des Bildes.
# Geprueft werden Haupt-, Prefix- und Suffix-Quads, damit spaetere API-Anschluesse
# keine unplausiblen Bildkoordinaten weiterreichen.
def _validate_image_annotations(
    image_input: PdfMakeImageInput,
    image_size: tuple[int, int],
) -> None:
    for annotation in image_input.annotations:
        _validate_quad_bounds(annotation.image_corners, image_size, "image_corners")
        if annotation.prefix_corners is not None:
            _validate_quad_bounds(
                annotation.prefix_corners, image_size, "prefix_corners"
            )
        if annotation.suffix_corners is not None:
            _validate_quad_bounds(
                annotation.suffix_corners, image_size, "suffix_corners"
            )


# Input: Quad im Bildraum, Bildgroesse und Feldname fuer Fehlermeldungen.
# Output: Keine Rueckgabe; wirft bei Punkten ausserhalb der Bildgrenzen.
# Die Bildkoordinaten nutzen einen Top-left Ursprung und duerfen auf den Kanten
# des Bildes liegen.
def _validate_quad_bounds(
    quad: Quad,
    image_size: tuple[int, int],
    field_name: str,
) -> None:
    width, height = image_size
    for point in quad.root:
        if point.x < 0 or point.x > width or point.y < 0 or point.y > height:
            raise ValueError(f"{field_name} must lie inside the image bounds.")


# Input: Text-Inputs und erste PDF-Seitengroesse.
# Output: Gemessene Renderplaene fuer PDF-native Texte.
# Die Funktion bricht lange Texte in Zeilen um, damit ihre Annotation-Quads in
# die layoutbare Seitenbreite passen.
def _prepare_text_plans(
    texts: list[PdfMakeTextInput],
    first_page_size: tuple[float, float],
) -> list[_TextRenderPlan]:
    content_width = first_page_size[0] - PAGE_MARGIN * 2
    if content_width <= TEXT_PADDING * 2:
        raise ValueError("PDF page is too narrow for text placement.")
    max_text_width = min(TEXT_MAX_WIDTH, content_width)
    return [_prepare_text_plan(text, max_text_width) for text in texts]


# Input: Einzelner Text-Input und maximale Textbox-Breite.
# Output: Gemessener Renderplan mit Zeilen und Boxgroesse.
# Das sichtbare PDF-Rendering ist immer `prefix + value + suffix`.
def _prepare_text_plan(
    text: PdfMakeTextInput,
    max_text_width: float,
) -> _TextRenderPlan:
    rendered_text = text.prefix + text.value + text.suffix
    usable_width = max_text_width - TEXT_PADDING * 2
    lines = tuple(
        _wrap_text(rendered_text, usable_width, TEXT_FONT_NAME, TEXT_FONT_SIZE)
    )
    widest_line = max(
        _string_width(line, TEXT_FONT_NAME, TEXT_FONT_SIZE) for line in lines
    )
    return _TextRenderPlan(
        rendered_text=rendered_text,
        lines=lines,
        width=widest_line + TEXT_PADDING * 2,
        height=len(lines) * TEXT_LEADING + TEXT_PADDING * 2,
        font_name=TEXT_FONT_NAME,
        font_size=TEXT_FONT_SIZE,
        leading=TEXT_LEADING,
        padding=TEXT_PADDING,
    )


# Input: Text, Zielbreite und Fontdaten.
# Output: Zeilenliste fuer ReportLab-Rendering.
# Leerzeichen werden als Umbruchpunkte genutzt; sehr lange Woerter werden
# zeichenweise aufgeteilt.
def _wrap_text(
    text: str,
    max_width: float,
    font_name: str,
    font_size: float,
) -> list[str]:
    if max_width <= 0:
        raise ValueError("Text layout width must be positive.")
    lines: list[str] = []
    for segment in text.splitlines() or [text]:
        lines.extend(_wrap_segment(segment, max_width, font_name, font_size))
    return lines or [""]


# Input: Einzeiliger Textabschnitt, Zielbreite und Fontdaten.
# Output: Umgebrochene Zeilen fuer diesen Abschnitt.
# Der Algorithmus ist deterministisch und unabhaengig vom Seed.
def _wrap_segment(
    segment: str,
    max_width: float,
    font_name: str,
    font_size: float,
) -> list[str]:
    words = segment.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        fragments = _split_word(word, max_width, font_name, font_size)
        for fragment in fragments:
            candidate = fragment if current == "" else f"{current} {fragment}"
            if _string_width(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = fragment
    if current or not lines:
        lines.append(current)
    return lines


# Input: Einzelnes Wort, Zielbreite und Fontdaten.
# Output: Eine oder mehrere Fragmente, die jeweils in die Zielbreite passen.
# Damit fuehren lange Kennungen oder IDs nicht zu ueberbreiten Textboxen.
def _split_word(
    word: str,
    max_width: float,
    font_name: str,
    font_size: float,
) -> list[str]:
    if _string_width(word, font_name, font_size) <= max_width:
        return [word]
    fragments: list[str] = []
    current = ""
    for character in word:
        candidate = current + character
        if current and _string_width(candidate, font_name, font_size) > max_width:
            fragments.append(current)
            current = character
        else:
            current = candidate
    if current:
        fragments.append(current)
    return fragments


# Input: Text und Fontdaten.
# Output: Breite in PDF-Punkten.
# Der Wrapper wandelt ReportLab-Rueckgaben in einen stabil typisierten Float um.
def _string_width(text: str, font_name: str, font_size: float) -> float:
    return float(pdfmetrics.stringWidth(text, font_name, font_size))


# Input: Inputs, Bildgroessen, Textplaene und Layoutentscheidungen.
# Output: Transformierte Bild- und Textannotations-Records.
# Die Funktion erzeugt nur Sidecar-Daten; sichtbare PDF-Markierungen werden
# spaeter aus denselben Quads gezeichnet.
def _build_annotation_records(
    images: list[PdfMakeImageInput],
    texts: list[PdfMakeTextInput],
    image_sizes: list[tuple[int, int]],
    text_plans: list[_TextRenderPlan],
    layout_decisions: list[PdfMakeLayoutDecision],
) -> tuple[list[PdfMakeImageAnnotation], list[PdfMakeTextAnnotation]]:
    placements = {
        (
            decision.placement.item_type,
            decision.placement.source_index,
        ): decision.placement
        for decision in layout_decisions
    }
    image_annotations = _build_image_annotations(images, image_sizes, placements)
    text_annotations = _build_text_annotations(texts, text_plans, placements)
    return image_annotations, text_annotations


# Input: Bildinputs, Bildgroessen und Layout-Platzierungen.
# Output: Bildannotation-Records mit PDF-Quads.
# Bildpunkte werden aus Pixelkoordinaten inklusive Bildrotation in PDF-Koordinaten
# transformiert.
def _build_image_annotations(
    images: list[PdfMakeImageInput],
    image_sizes: list[tuple[int, int]],
    placements: dict[tuple[Literal["image", "text"], int], PdfMakeLayoutPlacement],
) -> list[PdfMakeImageAnnotation]:
    records: list[PdfMakeImageAnnotation] = []
    for image_index, image_input in enumerate(images):
        placement = placements[("image", image_index)]
        for annotation_index, annotation in enumerate(image_input.annotations):
            records.append(
                PdfMakeImageAnnotation(
                    source_image_index=image_index,
                    source_annotation_index=annotation_index,
                    category=annotation.category,
                    value=annotation.value,
                    prefix=annotation.prefix,
                    suffix=annotation.suffix,
                    rendered_text=annotation.rendered_text,
                    image_corners=annotation.image_corners,
                    pdf_corners=_image_quad_to_pdf(
                        annotation.image_corners,
                        image_sizes[image_index],
                        placement,
                    ),
                    prefix_corners=annotation.prefix_corners,
                    prefix_pdf_corners=_optional_image_quad_to_pdf(
                        annotation.prefix_corners,
                        image_sizes[image_index],
                        placement,
                    ),
                    suffix_corners=annotation.suffix_corners,
                    suffix_pdf_corners=_optional_image_quad_to_pdf(
                        annotation.suffix_corners,
                        image_sizes[image_index],
                        placement,
                    ),
                    placement=placement,
                )
            )
    return records


# Input: Textinputs, gemessene Renderplaene und Layout-Platzierungen.
# Output: Textannotation-Records mit PDF-Quads.
# Das Quad beschreibt die gesamte sichtbare PDF-native Textbox.
def _build_text_annotations(
    texts: list[PdfMakeTextInput],
    text_plans: list[_TextRenderPlan],
    placements: dict[tuple[Literal["image", "text"], int], PdfMakeLayoutPlacement],
) -> list[PdfMakeTextAnnotation]:
    records: list[PdfMakeTextAnnotation] = []
    for text_index, text in enumerate(texts):
        placement = placements[("text", text_index)]
        records.append(
            PdfMakeTextAnnotation(
                source_text_index=text_index,
                category=text.category,
                value=text.value,
                prefix=text.prefix,
                suffix=text.suffix,
                rendered_text=text_plans[text_index].rendered_text,
                handwritten=text.handwritten,
                pdf_corners=rotated_quad(
                    placement.x,
                    placement.y,
                    placement.width,
                    placement.height,
                    placement.rotation_degrees,
                ),
                placement=placement,
            )
        )
    return records


# Input: Bildraum-Quad, Bildgroesse und PDF-Platzierung.
# Output: Entsprechendes PDF-Quad inklusive Platzierungsrotation.
# Die Y-Achse wird von Top-left-Bildraum nach Bottom-left-PDF-Raum invertiert.
def _image_quad_to_pdf(
    quad: Quad,
    image_size: tuple[int, int],
    placement: PdfMakeLayoutPlacement,
) -> PdfQuad:
    return PdfQuad.model_validate(
        [_image_point_to_pdf(point, image_size, placement) for point in quad.root]
    )


# Input: Optionales Bildraum-Quad, Bildgroesse und PDF-Platzierung.
# Output: Transformiertes PDF-Quad oder `None`.
# Prefix-/Suffix-Quads bleiben dadurch im Sidecar erhalten, ohne Pflichtfelder
# fuer alte Annotationen einzufuehren.
def _optional_image_quad_to_pdf(
    quad: Quad | None,
    image_size: tuple[int, int],
    placement: PdfMakeLayoutPlacement,
) -> PdfQuad | None:
    if quad is None:
        return None
    return _image_quad_to_pdf(quad, image_size, placement)


# Input: Bildpunkt, Bildgroesse und PDF-Platzierung.
# Output: Transformierter PDF-Punkt.
# Der Punkt wird erst in das unrotierte Bildrechteck skaliert und dann um dessen
# Zentrum rotiert.
def _image_point_to_pdf(
    point: ImagePoint,
    image_size: tuple[int, int],
    placement: PdfMakeLayoutPlacement,
) -> PdfPoint:
    image_width, image_height = image_size
    unrotated = PdfPoint(
        x=placement.x + point.x / image_width * placement.width,
        y=placement.y + placement.height - point.y / image_height * placement.height,
    )
    return rotate_point_in_rect(
        placement.x,
        placement.y,
        placement.width,
        placement.height,
        placement.rotation_degrees,
        unrotated,
    )


# Input: Template, Eingaben, Layout, Zielpfad und optionale Annotationen.
# Output: Keine Rueckgabe; schreibt eine neue PDF-Datei.
# Das Overlay wird seitenweise erzeugt, mit bestehenden Template-Seiten gemergt
# und bei Bedarf um leere Seiten in erster Template-Groesse erweitert.
def _write_composed_pdf(
    template: PdfTemplate,
    images: list[PdfMakeImageInput],
    text_plans: list[_TextRenderPlan],
    layout_decisions: list[PdfMakeLayoutDecision],
    output_path: Path,
    image_annotations: list[PdfMakeImageAnnotation],
    text_annotations: list[PdfMakeTextAnnotation],
) -> None:
    page_count = _output_page_count(template, layout_decisions)
    page_sizes = [page_size_for(template, index) for index in range(page_count)]
    overlay_reader = _build_overlay_pdf(
        page_sizes,
        images,
        text_plans,
        layout_decisions,
        image_annotations,
        text_annotations,
    )
    writer = PypdfWriter(clone_from=str(template.source_file))
    while len(writer.pages) < page_count:
        page_width, page_height = page_sizes[len(writer.pages)]
        writer.add_blank_page(width=page_width, height=page_height)
    for page_index, overlay_page in enumerate(overlay_reader.pages):
        writer.pages[page_index].merge_page(overlay_page)
    with output_path.open("wb") as handle:
        writer.write(handle)


# Input: Template und Layoutentscheidungen.
# Output: Anzahl der benoetigten Ausgabeseiten.
# Bestehende Template-Seiten bleiben immer Teil der Ausgabe, auch wenn keine
# neuen Items darauf liegen.
def _output_page_count(
    template: PdfTemplate,
    layout_decisions: list[PdfMakeLayoutDecision],
) -> int:
    max_layout_page = max(
        (decision.placement.page_index for decision in layout_decisions),
        default=-1,
    )
    return max(template.page_count, max_layout_page + 1)


# Input: Seitenformate, Inhalte, Layout und optionale Annotationen.
# Output: In-Memory-PDF mit nur den neu zu mergenden Overlay-Inhalten.
# ReportLab wird mit `invariant=1` verwendet, um Zeitstempel in Overlays stabil
# zu halten.
def _build_overlay_pdf(
    page_sizes: list[tuple[float, float]],
    images: list[PdfMakeImageInput],
    text_plans: list[_TextRenderPlan],
    layout_decisions: list[PdfMakeLayoutDecision],
    image_annotations: list[PdfMakeImageAnnotation],
    text_annotations: list[PdfMakeTextAnnotation],
) -> PdfReader:
    overlay_bytes = io.BytesIO()
    canvas = Canvas(overlay_bytes, pagesize=page_sizes[0], invariant=1)
    for page_index, page_size in enumerate(page_sizes):
        if page_index > 0:
            canvas.showPage()
        canvas.setPageSize(page_size)
        _draw_page_overlay(
            canvas,
            page_index,
            images,
            text_plans,
            layout_decisions,
            image_annotations,
            text_annotations,
        )
    canvas.save()
    overlay_bytes.seek(0)
    return PdfReader(overlay_bytes)


# Input: Canvas, Seitenindex, Inhalte, Layout und optionale Annotationen.
# Output: Keine Rueckgabe; mutiert die aktuelle Overlay-Seite.
# Erst werden Bild/Text-Inhalte gezeichnet, danach die roten Annotation-Quads.
def _draw_page_overlay(
    canvas: Canvas,
    page_index: int,
    images: list[PdfMakeImageInput],
    text_plans: list[_TextRenderPlan],
    layout_decisions: list[PdfMakeLayoutDecision],
    image_annotations: list[PdfMakeImageAnnotation],
    text_annotations: list[PdfMakeTextAnnotation],
) -> None:
    for decision in layout_decisions:
        if decision.placement.page_index != page_index:
            continue
        if decision.placement.item_type == "image":
            _draw_image(
                canvas, images[decision.placement.source_index], decision.placement
            )
        else:
            _draw_text(
                canvas, text_plans[decision.placement.source_index], decision.placement
            )
    _draw_annotation_outlines(canvas, page_index, image_annotations, text_annotations)


# Input: Canvas, Bildinput und PDF-Platzierung.
# Output: Keine Rueckgabe; zeichnet das Bild auf die aktuelle PDF-Seite.
# Das Bild wird nur transformiert eingebettet; die Quelldatei und Pixel bleiben
# unveraendert.
def _draw_image(
    canvas: Canvas,
    image_input: PdfMakeImageInput,
    placement: PdfMakeLayoutPlacement,
) -> None:
    canvas.saveState()
    canvas.translate(
        placement.x + placement.width / 2.0,
        placement.y + placement.height / 2.0,
    )
    canvas.rotate(placement.rotation_degrees)
    canvas.drawImage(
        ImageReader(str(image_input.path)),
        -placement.width / 2.0,
        -placement.height / 2.0,
        width=placement.width,
        height=placement.height,
        preserveAspectRatio=True,
        mask="auto",
    )
    canvas.restoreState()


# Input: Canvas, Text-Renderplan und PDF-Platzierung.
# Output: Keine Rueckgabe; zeichnet PDF-native Textzeilen.
# Die Annotation-Box umfasst die gemessene Textbox inklusive Padding.
def _draw_text(
    canvas: Canvas,
    text_plan: _TextRenderPlan,
    placement: PdfMakeLayoutPlacement,
) -> None:
    canvas.saveState()
    canvas.setFont(text_plan.font_name, text_plan.font_size)
    x = placement.x + text_plan.padding
    y = placement.y + placement.height - text_plan.padding - text_plan.font_size
    for line in text_plan.lines:
        canvas.drawString(x, y, line)
        y -= text_plan.leading
    canvas.restoreState()


# Input: Canvas, Seitenindex und Annotationen.
# Output: Keine Rueckgabe; zeichnet rote Umrisse auf die aktuelle Seite.
# Es werden nur Ground-Truth-Quads markiert, nicht die groben Layout-Slots.
def _draw_annotation_outlines(
    canvas: Canvas,
    page_index: int,
    image_annotations: list[PdfMakeImageAnnotation],
    text_annotations: list[PdfMakeTextAnnotation],
) -> None:
    if not image_annotations and not text_annotations:
        return
    canvas.saveState()
    canvas.setStrokeColorRGB(1, 0, 0)
    canvas.setLineWidth(ANNOTATION_STROKE_WIDTH)
    for quad in _page_annotation_quads(page_index, image_annotations, text_annotations):
        _draw_quad_outline(canvas, quad)
    canvas.restoreState()


# Input: Seitenindex und Annotationen.
# Output: PDF-Quads, die auf dieser Seite liegen.
# Die Zuordnung erfolgt ueber die jeweilige gespeicherte Layout-Platzierung.
def _page_annotation_quads(
    page_index: int,
    image_annotations: list[PdfMakeImageAnnotation],
    text_annotations: list[PdfMakeTextAnnotation],
) -> list[PdfQuad]:
    quads: list[PdfQuad] = []
    for image_annotation in image_annotations:
        if image_annotation.placement.page_index == page_index:
            quads.extend(_image_annotation_quads(image_annotation))
    for text_annotation in text_annotations:
        if text_annotation.placement.page_index == page_index:
            quads.append(text_annotation.pdf_corners)
    return quads


# Input: Eine transformierte Bildannotation.
# Output: Alle vorhandenen PDF-Quads der Annotation.
# Haupt-, Prefix- und Suffix-Quads werden in stabiler Reihenfolge fuer Preview
# und Sidecar-nahe Sichtpruefung bereitgestellt.
def _image_annotation_quads(annotation: PdfMakeImageAnnotation) -> list[PdfQuad]:
    quads = [annotation.pdf_corners]
    if annotation.prefix_pdf_corners is not None:
        quads.append(annotation.prefix_pdf_corners)
    if annotation.suffix_pdf_corners is not None:
        quads.append(annotation.suffix_pdf_corners)
    return quads


# Input: Canvas und vier PDF-Punkte.
# Output: Keine Rueckgabe; zeichnet einen geschlossenen Linienzug.
# Die Reihenfolge der Punkte stammt aus dem Sidecar-Quad.
def _draw_quad_outline(canvas: Canvas, quad: PdfQuad) -> None:
    points = quad.root
    canvas.line(points[0].x, points[0].y, points[1].x, points[1].y)
    canvas.line(points[1].x, points[1].y, points[2].x, points[2].y)
    canvas.line(points[2].x, points[2].y, points[3].x, points[3].y)
    canvas.line(points[3].x, points[3].y, points[0].x, points[0].y)
