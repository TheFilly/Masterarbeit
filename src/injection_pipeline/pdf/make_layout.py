"""Deterministic page layout for multi-item PDF composition."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal

from injection_pipeline.models.geometry import PdfPoint
from injection_pipeline.pdf.models import (
    PdfMakeLayoutDecision,
    PdfMakeLayoutPlacement,
    PdfQuad,
    PdfTemplate,
)

type Arrangement = Literal["beside", "stacked"]
type ItemType = Literal["image", "text"]

PAGE_MARGIN = 36.0
ITEM_GAP = 18.0
IMAGE_ROTATION_CHOICES: tuple[float, ...] = (-8.0, -4.0, 0.0, 4.0, 8.0)


@dataclass(frozen=True)
class MakeLayoutItem:
    """Input geometry for one image or text item before page placement."""

    item_type: ItemType
    source_index: int
    width: float
    height: float


@dataclass(frozen=True)
class _GroupItem:
    """Resolved geometry for one item inside a grouped layout block."""

    item_type: ItemType
    source_index: int
    occupied_x: float
    occupied_y: float
    occupied_width: float
    occupied_height: float
    draw_width: float
    draw_height: float
    rotation_degrees: float


@dataclass(frozen=True)
class _LayoutGroup:
    """One image/text pair or single unpaired item to place together."""

    image: MakeLayoutItem | None
    text: MakeLayoutItem | None
    arrangement: Arrangement | None
    rotation_degrees: float


@dataclass(frozen=True)
class _ResolvedGroup:
    """Page-independent group dimensions and relative item positions."""

    width: float
    height: float
    items: tuple[_GroupItem, ...]
    arrangement: Arrangement | None


# Input: `template` mit Seitenformaten und `page_index`.
# Output: Seitengroesse in PDF-Punkten.
# Neue Seiten verwenden reproduzierbar die Groesse der ersten Template-Seite.
def page_size_for(template: PdfTemplate, page_index: int) -> tuple[float, float]:
    if page_index < len(template.page_sizes):
        return template.page_sizes[page_index]
    return template.page_sizes[0]


# Input: Rechteck, Winkel und einen Punkt in PDF-Koordinaten.
# Output: Um das Rechteckzentrum rotierter PDF-Punkt.
# Die Funktion bildet die gemeinsame Geometriebasis fuer Layout-Quads und
# Bildannotations-Transformationen.
def rotate_point_in_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    rotation_degrees: float,
    point: PdfPoint,
) -> PdfPoint:
    if rotation_degrees == 0:
        return point
    radians = math.radians(rotation_degrees)
    center_x = x + width / 2.0
    center_y = y + height / 2.0
    translated_x = point.x - center_x
    translated_y = point.y - center_y
    return PdfPoint(
        x=center_x
        + translated_x * math.cos(radians)
        - translated_y * math.sin(radians),
        y=center_y
        + translated_x * math.sin(radians)
        + translated_y * math.cos(radians),
    )


# Input: Rechteck und Winkel in PDF-Koordinaten.
# Output: Vier Eckpunkte des rotierten Rechtecks.
# Die Punktreihenfolge bleibt unten-links, unten-rechts, oben-rechts, oben-links
# bezogen auf das unrotierte Rechteck.
def rotated_quad(
    x: float,
    y: float,
    width: float,
    height: float,
    rotation_degrees: float,
) -> PdfQuad:
    corners = [
        PdfPoint(x=x, y=y),
        PdfPoint(x=x + width, y=y),
        PdfPoint(x=x + width, y=y + height),
        PdfPoint(x=x, y=y + height),
    ]
    return PdfQuad.model_validate(
        [
            rotate_point_in_rect(x, y, width, height, rotation_degrees, corner)
            for corner in corners
        ]
    )


# Input: `quad` mit vier PDF-Punkten.
# Output: Axis-aligned Bounds als `x`, `y`, `width`, `height`.
# Die Bounds werden fuer Kollisionserkennung und Gruppierung rotierten Inhalts
# genutzt.
def quad_bounds(quad: PdfQuad) -> tuple[float, float, float, float]:
    xs = [point.x for point in quad.root]
    ys = [point.y for point in quad.root]
    min_x = min(xs)
    min_y = min(ys)
    return min_x, min_y, max(xs) - min_x, max(ys) - min_y


# Input: Groesse und Rotation eines Bildes sowie maximale Bounds.
# Output: Zeichenbreite/-hoehe und rotierte Bounds nach Skalierung.
# Bilder werden nur verkleinert, damit bereits injizierte Pixel nicht kuenstlich
# vergroessert werden.
def fit_rotated_image(
    width: float,
    height: float,
    rotation_degrees: float,
    max_bounds_width: float,
    max_bounds_height: float,
) -> tuple[float, float, float, float]:
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive.")
    if max_bounds_width <= 0 or max_bounds_height <= 0:
        raise ValueError("Image layout bounds must be positive.")
    unit_quad = rotated_quad(0.0, 0.0, width, height, rotation_degrees)
    _, _, rotated_width, rotated_height = quad_bounds(unit_quad)
    scale = min(
        1.0, max_bounds_width / rotated_width, max_bounds_height / rotated_height
    )
    if scale <= 0:
        raise ValueError("Image cannot be scaled into the PDF layout bounds.")
    return (
        width * scale,
        height * scale,
        rotated_width * scale,
        rotated_height * scale,
    )


# Input: Template, Bild- und Textgroessen sowie Seed.
# Output: Deterministische Platzierungsentscheidungen fuer alle Items.
# Die Funktion packt Gruppen kollisionsfrei in bestehende Seiten und haengt bei
# Platzmangel neue Seiten in erster Template-Groesse an.
def build_make_pdf_layout(
    template: PdfTemplate,
    image_sizes: list[tuple[int, int]],
    text_sizes: list[tuple[float, float]],
    seed: int,
) -> list[PdfMakeLayoutDecision]:
    groups = _build_groups(image_sizes, text_sizes, random.Random(seed))
    decisions: list[PdfMakeLayoutDecision] = []
    page_index = 0
    page_width, page_height = page_size_for(template, page_index)
    cursor_x = PAGE_MARGIN
    cursor_top = page_height - PAGE_MARGIN
    row_height = 0.0
    occupied: dict[int, list[tuple[float, float, float, float]]] = {}

    for group in groups:
        while True:
            page_width, page_height = page_size_for(template, page_index)
            resolved = _resolve_group(group, page_width, page_height)
            if cursor_x + resolved.width > page_width - PAGE_MARGIN and row_height > 0:
                cursor_x = PAGE_MARGIN
                cursor_top -= row_height + ITEM_GAP
                row_height = 0.0
                continue
            if cursor_top - resolved.height < PAGE_MARGIN:
                page_index += 1
                page_width, page_height = page_size_for(template, page_index)
                cursor_x = PAGE_MARGIN
                cursor_top = page_height - PAGE_MARGIN
                row_height = 0.0
                continue

            group_x = cursor_x
            group_y = cursor_top - resolved.height
            new_decisions = _absolute_decisions(
                resolved,
                group_x,
                group_y,
                page_index,
                (page_width, page_height),
            )
            if _collides(new_decisions, occupied.get(page_index, [])):
                cursor_x = PAGE_MARGIN
                cursor_top -= max(row_height, resolved.height) + ITEM_GAP
                row_height = 0.0
                continue

            decisions.extend(new_decisions)
            occupied.setdefault(page_index, []).extend(
                quad_bounds(decision.occupied_corners) for decision in new_decisions
            )
            cursor_x += resolved.width + ITEM_GAP
            row_height = max(row_height, resolved.height)
            break

    return decisions


# Input: Bild- und Textgroessen sowie ein initialisierter Zufallsgenerator.
# Output: Geordnete Layout-Gruppen mit deterministischer Anordnung und Rotation.
# Der Seed beeinflusst nur Layout-Metadaten, niemals Textwerte oder Bildinhalte.
def _build_groups(
    image_sizes: list[tuple[int, int]],
    text_sizes: list[tuple[float, float]],
    rng: random.Random,
) -> list[_LayoutGroup]:
    groups: list[_LayoutGroup] = []
    count = max(len(image_sizes), len(text_sizes))
    for index in range(count):
        image = (
            MakeLayoutItem(
                "image",
                index,
                float(image_sizes[index][0]),
                float(image_sizes[index][1]),
            )
            if index < len(image_sizes)
            else None
        )
        text = (
            MakeLayoutItem("text", index, text_sizes[index][0], text_sizes[index][1])
            if index < len(text_sizes)
            else None
        )
        arrangement = (
            _choose_arrangement(rng) if image is not None and text is not None else None
        )
        rotation_degrees = (
            rng.choice(IMAGE_ROTATION_CHOICES) if image is not None else 0.0
        )
        groups.append(_LayoutGroup(image, text, arrangement, rotation_degrees))
    return groups


# Input: Initialisierter Zufallsgenerator.
# Output: Eine der erlaubten Paar-Anordnungen.
# Der kleine Wrapper haelt den Literal-Typ fuer Mypy stabil.
def _choose_arrangement(rng: random.Random) -> Arrangement:
    return "beside" if rng.randrange(2) == 0 else "stacked"


# Input: Layout-Gruppe und Seitengroesse.
# Output: Relativ platzierte Gruppe, gegebenenfalls mit alternativer Anordnung.
# Wenn die seed-basierte Anordnung nicht passt, wird die andere erlaubte
# Anordnung versucht; passt keine, wird ein ValueError geworfen.
def _resolve_group(
    group: _LayoutGroup,
    page_width: float,
    page_height: float,
) -> _ResolvedGroup:
    if page_width <= PAGE_MARGIN * 2 or page_height <= PAGE_MARGIN * 2:
        raise ValueError("PDF page is too small for make_pdf margins.")
    arrangements = _candidate_arrangements(group)
    for arrangement in arrangements:
        resolved = _try_resolve_group(group, arrangement, page_width, page_height)
        if resolved is not None:
            return resolved
    raise ValueError("PDF make item does not fit on a page.")


# Input: Layout-Gruppe.
# Output: Priorisierte Anordnungen fuer diese Gruppe.
# Gepaarte Items behalten die seed-basierte Wahl als ersten Kandidaten.
def _candidate_arrangements(group: _LayoutGroup) -> tuple[Arrangement | None, ...]:
    if group.image is None or group.text is None:
        return (None,)
    first = group.arrangement if group.arrangement is not None else "beside"
    second: Arrangement = "stacked" if first == "beside" else "beside"
    return first, second


# Input: Layout-Gruppe, Anordnung und Seitengroesse.
# Output: Relativ platzierte Gruppe oder `None`, wenn sie nicht passt.
# Die Funktion skaliert nur Bilder; Textboxen behalten ihre gemessene Groesse.
def _try_resolve_group(
    group: _LayoutGroup,
    arrangement: Arrangement | None,
    page_width: float,
    page_height: float,
) -> _ResolvedGroup | None:
    content_width = page_width - PAGE_MARGIN * 2
    content_height = page_height - PAGE_MARGIN * 2
    if group.image is None:
        return _resolve_single_text(group.text, content_width, content_height)
    if group.text is None:
        return _resolve_single_image(
            group.image, group.rotation_degrees, content_width, content_height
        )
    if arrangement == "beside":
        return _resolve_beside(
            group.image,
            group.text,
            group.rotation_degrees,
            content_width,
            content_height,
        )
    return _resolve_stacked(
        group.image, group.text, group.rotation_degrees, content_width, content_height
    )


# Input: Text-Item und verfuegbare Seitengroesse.
# Output: Relativ platzierte Einzelgruppe oder `None`.
# Einzelne Texte werden ohne Rotation in ihrer gemessenen Bounding-Box platziert.
def _resolve_single_text(
    text: MakeLayoutItem | None,
    content_width: float,
    content_height: float,
) -> _ResolvedGroup | None:
    if text is None or text.width > content_width or text.height > content_height:
        return None
    return _ResolvedGroup(
        width=text.width,
        height=text.height,
        arrangement=None,
        items=(
            _GroupItem(
                "text",
                text.source_index,
                0.0,
                0.0,
                text.width,
                text.height,
                text.width,
                text.height,
                0.0,
            ),
        ),
    )


# Input: Bild-Item, Rotation und verfuegbare Seitengroesse.
# Output: Relativ platzierte Einzelgruppe oder `None`.
# Das Bild wird aspect-fit in eine grosszuegige Einzelbildflaeche gesetzt.
def _resolve_single_image(
    image: MakeLayoutItem,
    rotation_degrees: float,
    content_width: float,
    content_height: float,
) -> _ResolvedGroup | None:
    draw_width, draw_height, occupied_width, occupied_height = fit_rotated_image(
        image.width,
        image.height,
        rotation_degrees,
        content_width * 0.72,
        content_height * 0.48,
    )
    if occupied_width > content_width or occupied_height > content_height:
        return None
    return _ResolvedGroup(
        width=occupied_width,
        height=occupied_height,
        arrangement=None,
        items=(
            _GroupItem(
                "image",
                image.source_index,
                0.0,
                0.0,
                occupied_width,
                occupied_height,
                draw_width,
                draw_height,
                rotation_degrees,
            ),
        ),
    )


# Input: Bild-/Text-Items, Rotation und verfuegbare Seitengroesse.
# Output: Relativ platzierte Nebeneinander-Gruppe oder `None`.
# Text und Bild werden vertikal zentriert und durch einen festen Gap getrennt.
def _resolve_beside(
    image: MakeLayoutItem,
    text: MakeLayoutItem,
    rotation_degrees: float,
    content_width: float,
    content_height: float,
) -> _ResolvedGroup | None:
    if text.width + ITEM_GAP >= content_width or text.height > content_height:
        return None
    max_image_width = min(content_width * 0.45, content_width - text.width - ITEM_GAP)
    draw_width, draw_height, occupied_width, occupied_height = fit_rotated_image(
        image.width,
        image.height,
        rotation_degrees,
        max_image_width,
        content_height * 0.38,
    )
    group_width = occupied_width + ITEM_GAP + text.width
    group_height = max(occupied_height, text.height)
    if group_width > content_width or group_height > content_height:
        return None
    image_y = (group_height - occupied_height) / 2.0
    text_y = (group_height - text.height) / 2.0
    return _ResolvedGroup(
        width=group_width,
        height=group_height,
        arrangement="beside",
        items=(
            _GroupItem(
                "image",
                image.source_index,
                0.0,
                image_y,
                occupied_width,
                occupied_height,
                draw_width,
                draw_height,
                rotation_degrees,
            ),
            _GroupItem(
                "text",
                text.source_index,
                occupied_width + ITEM_GAP,
                text_y,
                text.width,
                text.height,
                text.width,
                text.height,
                0.0,
            ),
        ),
    )


# Input: Bild-/Text-Items, Rotation und verfuegbare Seitengroesse.
# Output: Relativ platzierte Uebereinander-Gruppe oder `None`.
# Das Bild steht ueber dem Text; beide werden horizontal zentriert.
def _resolve_stacked(
    image: MakeLayoutItem,
    text: MakeLayoutItem,
    rotation_degrees: float,
    content_width: float,
    content_height: float,
) -> _ResolvedGroup | None:
    if text.width > content_width or text.height + ITEM_GAP >= content_height:
        return None
    draw_width, draw_height, occupied_width, occupied_height = fit_rotated_image(
        image.width,
        image.height,
        rotation_degrees,
        content_width * 0.64,
        content_height - text.height - ITEM_GAP,
    )
    group_width = max(occupied_width, text.width)
    group_height = occupied_height + ITEM_GAP + text.height
    if group_width > content_width or group_height > content_height:
        return None
    image_x = (group_width - occupied_width) / 2.0
    text_x = (group_width - text.width) / 2.0
    return _ResolvedGroup(
        width=group_width,
        height=group_height,
        arrangement="stacked",
        items=(
            _GroupItem(
                "image",
                image.source_index,
                image_x,
                text.height + ITEM_GAP,
                occupied_width,
                occupied_height,
                draw_width,
                draw_height,
                rotation_degrees,
            ),
            _GroupItem(
                "text",
                text.source_index,
                text_x,
                0.0,
                text.width,
                text.height,
                text.width,
                text.height,
                0.0,
            ),
        ),
    )


# Input: Relative Gruppe, absolute Position, Seite und Seitengroesse.
# Output: Layout-Entscheidungen mit PDF-Koordinaten.
# Bild-Platzierungen speichern das unrotierte Zeichenrechteck; `occupied_corners`
# enthaelt die tatsaechlich rotierte belegte Flaeche.
def _absolute_decisions(
    group: _ResolvedGroup,
    group_x: float,
    group_y: float,
    page_index: int,
    page_size: tuple[float, float],
) -> list[PdfMakeLayoutDecision]:
    decisions: list[PdfMakeLayoutDecision] = []
    for item in group.items:
        occupied_x = group_x + item.occupied_x
        occupied_y = group_y + item.occupied_y
        placement_x = occupied_x + item.occupied_width / 2.0 - item.draw_width / 2.0
        placement_y = occupied_y + item.occupied_height / 2.0 - item.draw_height / 2.0
        placement = PdfMakeLayoutPlacement(
            item_type=item.item_type,
            source_index=item.source_index,
            page_index=page_index,
            x=placement_x,
            y=placement_y,
            width=item.draw_width,
            height=item.draw_height,
            rotation_degrees=item.rotation_degrees,
            arrangement=group.arrangement,
        )
        decisions.append(
            PdfMakeLayoutDecision(
                placement=placement,
                page_size=page_size,
                occupied_corners=rotated_quad(
                    placement.x,
                    placement.y,
                    placement.width,
                    placement.height,
                    placement.rotation_degrees,
                ),
            )
        )
    return decisions


# Input: Neue Layout-Entscheidungen und bereits belegte Bounds.
# Output: `True`, wenn eine neue Entscheidung vorhandene Bounds schneidet.
# Die Pruefung ist eine Sicherheitskante zusaetzlich zur zeilenweisen Packlogik.
def _collides(
    decisions: list[PdfMakeLayoutDecision],
    existing_bounds: list[tuple[float, float, float, float]],
) -> bool:
    for decision in decisions:
        new_bounds = quad_bounds(decision.occupied_corners)
        if any(
            _rectangles_overlap(new_bounds, old_bounds)
            for old_bounds in existing_bounds
        ):
            return True
    return False


# Input: Zwei Bounds als `x`, `y`, `width`, `height`.
# Output: `True`, wenn sich die Rechtecke echt ueberlappen.
# Kantenberuehrung gilt nicht als Kollision, damit Items exakt am Gap ausgerichtet
# werden koennen.
def _rectangles_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    first_x, first_y, first_width, first_height = first
    second_x, second_y, second_width, second_height = second
    return not (
        first_x + first_width <= second_x
        or second_x + second_width <= first_x
        or first_y + first_height <= second_y
        or second_y + second_height <= first_y
    )
