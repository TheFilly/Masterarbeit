import pytest

from injection_pipeline.models import ImagePoint
from injection_pipeline.pdf.geometry import aspect_fit_size, image_to_pdf_point


def test_aspect_fit_scales_wide_image_inside_slot() -> None:
    placement = aspect_fit_size((612.0, 792.0), (320, 180), "top_left")

    assert placement.slot == "top_left"
    assert placement.scale < 1.0
    assert placement.x == pytest.approx(36.0)
    assert placement.width == pytest.approx(612.0 * 0.45)
    assert placement.height == pytest.approx(180 * placement.scale)


def test_small_image_is_centered_at_native_size() -> None:
    placement = aspect_fit_size((612.0, 792.0), (100, 50), "top_left")
    slot_width = 612.0 * 0.45
    slot_height = 792.0 * 0.35

    assert placement.scale == pytest.approx(1.0)
    assert placement.x == pytest.approx(36.0 + (slot_width - 100.0) / 2)
    assert placement.y == pytest.approx(792.0 - 36.0 - (slot_height + 50.0) / 2)


def test_image_to_pdf_point_inverts_y_axis_in_placement() -> None:
    placement = aspect_fit_size((612.0, 792.0), (320, 180), "top_right")

    top_left = image_to_pdf_point(ImagePoint(x=0, y=0), placement)
    bottom_right = image_to_pdf_point(
        ImagePoint(x=320, y=180),
        placement,
    )

    assert top_left.x == pytest.approx(placement.x)
    assert top_left.y == pytest.approx(placement.y + placement.height)
    assert bottom_right.x == pytest.approx(placement.x + placement.width)
    assert bottom_right.y == pytest.approx(placement.y)


def test_aspect_fit_rejects_unknown_slot() -> None:
    with pytest.raises(ValueError, match="Unsupported PDF slot"):
        aspect_fit_size((612.0, 792.0), (320, 180), "center")
