from pathlib import Path

from injection_pipeline.pdf.make_layout import build_make_pdf_layout, quad_bounds
from injection_pipeline.pdf.models import PdfTemplate


def _template(page_size: tuple[float, float]) -> PdfTemplate:
    return PdfTemplate(
        source_file=Path("template.pdf"),
        page_count=1,
        page_sizes=[page_size],
    )


def _overlap(
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


def test_layout_places_items_inside_pages_without_overlap() -> None:
    template = _template((360.0, 420.0))

    decisions = build_make_pdf_layout(
        template,
        image_sizes=[(120, 80), (96, 72), (110, 70)],
        text_sizes=[(84.0, 28.0), (92.0, 28.0), (88.0, 28.0)],
        seed=11,
    )

    assert len(decisions) == 6
    by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    for decision in decisions:
        page_width, page_height = decision.page_size
        x, y, width, height = quad_bounds(decision.occupied_corners)
        assert x >= 0.0
        assert y >= 0.0
        assert x + width <= page_width
        assert y + height <= page_height
        by_page.setdefault(decision.placement.page_index, []).append(
            (
                x,
                y,
                width,
                height,
            )
        )

    for bounds in by_page.values():
        for first_index, first in enumerate(bounds):
            for second in bounds[first_index + 1 :]:
                assert not _overlap(first, second)


def test_layout_adds_pages_when_content_does_not_fit_first_page() -> None:
    template = _template((240.0, 320.0))

    decisions = build_make_pdf_layout(
        template,
        image_sizes=[(120, 80)] * 8,
        text_sizes=[(58.0, 24.0)] * 8,
        seed=4,
    )

    assert max(decision.placement.page_index for decision in decisions) > 0


def test_layout_is_repeatable_for_same_seed_and_changes_for_different_seed() -> None:
    template = _template((360.0, 420.0))
    image_sizes = [(120, 80), (96, 72), (110, 70)]
    text_sizes = [(84.0, 28.0), (92.0, 28.0), (88.0, 28.0)]

    first = build_make_pdf_layout(template, image_sizes, text_sizes, seed=1)
    repeated = build_make_pdf_layout(template, image_sizes, text_sizes, seed=1)
    changed = build_make_pdf_layout(template, image_sizes, text_sizes, seed=2)

    assert repeated == first
    assert changed != first
