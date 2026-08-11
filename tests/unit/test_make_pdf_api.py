import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

import injection_pipeline
import injection_pipeline.api as api
from injection_pipeline import (
    PdfMakeImageAnnotationInput,
    PdfMakeImageInput,
    PdfMakeTextInput,
    make_pdf,
)
from injection_pipeline.pdf.models import (
    PdfMakeAnnotationRecord,
    PdfMakeLayoutPlacement,
    PdfTemplate,
)
from injection_pipeline.writers.pdf_make import (
    _draw_annotation_outlines,
    _string_width,
    _text_annotation_quad,
    _TextRenderPlan,
    make_pdf_composition,
)


def _write_pdf(path: Path, page_size: tuple[float, float], page_count: int = 1) -> Path:
    canvas = Canvas(str(path), pagesize=page_size, invariant=1)
    for page_index in range(page_count):
        canvas.drawString(24, page_size[1] - 28, f"TEMPLATE PAGE {page_index + 1}")
        if page_index < page_count - 1:
            canvas.showPage()
    canvas.save()
    return path


def _write_image(
    path: Path,
    *,
    size: tuple[int, int] = (120, 80),
    color: tuple[int, int, int] = (230, 240, 255),
) -> Path:
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 12, 76, 34), fill=(255, 255, 255), outline=(10, 60, 120))
    draw.text((16, 16), path.stem, fill=(0, 0, 0))
    image.save(path, format="PNG")
    return path


def _quad(
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> list[dict[str, int]]:
    return [
        {"x": left, "y": top},
        {"x": right, "y": top},
        {"x": right, "y": bottom},
        {"x": left, "y": bottom},
    ]


def _image_payload(path: Path, index: int) -> dict[str, Any]:
    value = f"IMG-{index}"
    prefix = "Image "
    suffix = " injected"
    return {
        "path": path,
        "annotations": [
            {
                "category": "ImageIdentifier",
                "value": value,
                "prefix": prefix,
                "suffix": suffix,
                "rendered_text": f"{prefix}{value}{suffix}",
                "image_corners": _quad(12, 12, 76, 34),
            }
        ],
    }


def _text_payload(index: int, *, handwritten: bool = False) -> dict[str, Any]:
    return {
        "category": "DirectText",
        "value": f"TXT-{index}",
        "prefix": "Direct ",
        "suffix": " value",
        "handwritten": handwritten,
    }


def _template(
    path: Path,
    page_size: tuple[float, float],
    page_count: int = 1,
) -> PdfTemplate:
    return PdfTemplate(
        source_file=_write_pdf(path, page_size, page_count),
        page_count=page_count,
        page_sizes=[page_size] * page_count,
    )


def _make_inputs(
    tmp_path: Path,
    *,
    image_count: int = 3,
    text_count: int = 3,
) -> tuple[Path, list[dict[str, Any]], list[dict[str, Any]]]:
    pdf = _write_pdf(tmp_path / "template.pdf", (612.0, 792.0), page_count=2)
    images = [
        _image_payload(_write_image(tmp_path / f"image_{index}.png"), index)
        for index in range(image_count)
    ]
    texts = [_text_payload(index) for index in range(text_count)]
    return pdf, images, texts


def test_text_annotation_quad_is_tight_and_rotates_with_text() -> None:
    text_plan = _TextRenderPlan(
        rendered_text="Direct value",
        lines=("Direct value",),
        width=100.0,
        height=25.5,
        font_name="Helvetica",
        font_size=11.0,
        leading=13.5,
        padding=4.0,
    )
    placement = {
        "item_type": "text",
        "source_index": 0,
        "page_index": 0,
        "x": 100.0,
        "y": 200.0,
        "width": text_plan.width,
        "height": text_plan.height,
        "rotation_degrees": 20.0,
    }

    quad = _text_annotation_quad(text_plan, PdfMakeLayoutPlacement(**placement))
    points = quad.root
    horizontal_width = (
        (points[1].x - points[0].x) ** 2
        + (points[1].y - points[0].y) ** 2
    ) ** 0.5
    vertical_height = (
        (points[3].x - points[0].x) ** 2
        + (points[3].y - points[0].y) ** 2
    ) ** 0.5

    assert horizontal_width == pytest.approx(
        _string_width("Direct value", "Helvetica", 11.0)
    )
    assert vertical_height < text_plan.height
    assert points[0].y != pytest.approx(points[1].y)
    assert points[0].x != pytest.approx(points[3].x)


def _bounds(quad: Iterable[Any]) -> tuple[float, float, float, float]:
    points = list(quad)
    xs = [float(point.x) for point in points]
    ys = [float(point.y) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    first_left, first_bottom, first_right, first_top = first
    second_left, second_bottom, second_right, second_top = second
    return not (
        first_right <= second_left
        or second_right <= first_left
        or first_top <= second_bottom
        or second_top <= first_bottom
    )


def test_top_level_package_exports_make_pdf_and_models_validate(tmp_path: Path) -> None:
    assert injection_pipeline.make_pdf is api.make_pdf
    assert make_pdf is api.make_pdf

    image_path = tmp_path / "injected.png"
    annotation = PdfMakeImageAnnotationInput.model_validate(
        {
            "category": "PatientID",
            "value": "SYNTH-001",
            "prefix": "ID ",
            "suffix": "",
            "rendered_text": "ID SYNTH-001",
            "image_corners": _quad(1, 2, 11, 12),
        }
    )
    image = PdfMakeImageInput(path=image_path, annotations=[annotation])
    text = PdfMakeTextInput(
        category="PatientName",
        value="SYNTHETIC",
        prefix="Name ",
        suffix="",
        handwritten=False,
    )

    assert image.path == image_path
    assert text.prefix + text.value + text.suffix == "Name SYNTHETIC"
    with pytest.raises(ValidationError, match="Extra inputs"):
        PdfMakeTextInput(
            category="PatientName",
            value="SYNTHETIC",
            prefix="",
            suffix="",
            handwritten=False,
            output_dir="not-part-of-text-input",
        )
    with pytest.raises(ValidationError, match="exactly four"):
        PdfMakeImageAnnotationInput.model_validate(
            {
                "category": "PatientID",
                "value": "SYNTH-001",
                "prefix": "",
                "suffix": "",
                "rendered_text": "SYNTH-001",
                "image_corners": _quad(1, 2, 11, 12)[:3],
            }
        )


def test_make_pdf_public_api_creates_artifacts_for_multiple_images_and_texts(
    tmp_path: Path,
) -> None:
    pdf, images, texts = _make_inputs(tmp_path)

    artifacts = make_pdf(images, texts, pdf, tmp_path / "output", seed=4)

    assert artifacts.clean_pdf.is_file()
    assert artifacts.annotated_pdf.is_file()
    assert artifacts.annotation_json.is_file()
    assert PdfReader(str(artifacts.clean_pdf)).pages[0].extract_text()
    assert len(PdfReader(str(artifacts.clean_pdf)).pages) == 2
    assert len(PdfReader(str(artifacts.annotated_pdf)).pages) == 2
    assert len(artifacts.record.image_annotations) == 3
    assert len(artifacts.record.text_annotations) == 3
    assert [item.rendered_text for item in artifacts.record.text_annotations] == [
        "Direct TXT-0 value",
        "Direct TXT-1 value",
        "Direct TXT-2 value",
    ]
    text_points = artifacts.record.text_annotations[0].pdf_corners.root
    text_width = (
        (text_points[1].x - text_points[0].x) ** 2
        + (text_points[1].y - text_points[0].y) ** 2
    ) ** 0.5
    assert text_width == pytest.approx(_string_width("TXT-0", "Helvetica", 11.0))

    sidecar = PdfMakeAnnotationRecord.model_validate_json(
        artifacts.annotation_json.read_text(encoding="utf-8")
    )
    assert sidecar.model_dump(mode="json") == artifacts.record.model_dump(mode="json")


def test_make_pdf_draws_values_red_and_image_labels_blue(
    tmp_path: Path,
) -> None:
    pdf, images, texts = _make_inputs(tmp_path, image_count=1, text_count=1)
    artifacts = make_pdf_composition(
        template=PdfTemplate(
            source_file=pdf,
            page_count=2,
            page_sizes=[(612.0, 792.0), (612.0, 792.0)],
        ),
        images=[PdfMakeImageInput.model_validate(images[0])],
        texts=[PdfMakeTextInput.model_validate(texts[0])],
        output_dir=tmp_path / "output",
        seed=4,
    )

    class RecordingCanvas:
        def __init__(self) -> None:
            self.colors: list[tuple[float, float, float]] = []

        def saveState(self) -> None:
            pass

        def restoreState(self) -> None:
            pass

        def setStrokeColorRGB(self, red: float, green: float, blue: float) -> None:
            self.colors.append((red, green, blue))

        def setLineWidth(self, width: float) -> None:
            pass

        def line(self, *coordinates: float) -> None:
            pass

    canvas = RecordingCanvas()
    _draw_annotation_outlines(
        canvas,
        page_index=0,
        image_annotations=artifacts.record.image_annotations,
        text_annotations=artifacts.record.text_annotations,
    )

    assert canvas.colors == [(1, 0, 0), (0, 0, 1)]


def test_make_pdf_writer_preserves_pages_and_adds_pages_for_small_templates(
    tmp_path: Path,
) -> None:
    template = _template(tmp_path / "small.pdf", (240.0, 320.0), page_count=2)
    images = [
        PdfMakeImageInput.model_validate(
            _image_payload(_write_image(tmp_path / f"small_{index}.png"), index)
        )
        for index in range(8)
    ]
    texts = [
        PdfMakeTextInput.model_validate(_text_payload(index)) for index in range(8)
    ]

    artifacts = make_pdf_composition(
        template=template,
        images=images,
        texts=texts,
        output_dir=tmp_path / "small-output",
        seed=4,
    )

    clean_reader = PdfReader(str(artifacts.clean_pdf))
    annotated_reader = PdfReader(str(artifacts.annotated_pdf))
    assert len(clean_reader.pages) > template.page_count
    assert len(annotated_reader.pages) == len(clean_reader.pages)
    assert "TEMPLATE PAGE 1" in clean_reader.pages[0].extract_text()
    assert "TEMPLATE PAGE 2" in clean_reader.pages[1].extract_text()


def test_make_pdf_writer_transforms_image_annotations_to_pdf_coordinates(
    tmp_path: Path,
) -> None:
    image_path = _write_image(tmp_path / "source.png", size=(100, 80))
    template = _template(tmp_path / "template.pdf", (612.0, 792.0))
    image = PdfMakeImageInput.model_validate(
        {
            **_image_payload(image_path, 0),
            "annotations": [
                {
                    "category": "PatientID",
                    "value": "SYNTH-001",
                    "prefix": "",
                    "suffix": "",
                    "rendered_text": "SYNTH-001",
                    "image_corners": _quad(10, 20, 40, 50),
                }
            ],
        }
    )
    text = PdfMakeTextInput.model_validate(_text_payload(0))

    artifacts = make_pdf_composition(
        template=template,
        images=[image],
        texts=[text],
        output_dir=tmp_path / "output",
        seed=4,
    )

    annotation = artifacts.record.image_annotations[0]
    placement = annotation.placement
    assert placement.rotation_degrees == 0.0
    expected = [
        (
            placement.x + 10 / 100 * placement.width,
            placement.y + placement.height - 20 / 80 * placement.height,
        ),
        (
            placement.x + 40 / 100 * placement.width,
            placement.y + placement.height - 20 / 80 * placement.height,
        ),
        (
            placement.x + 40 / 100 * placement.width,
            placement.y + placement.height - 50 / 80 * placement.height,
        ),
        (
            placement.x + 10 / 100 * placement.width,
            placement.y + placement.height - 50 / 80 * placement.height,
        ),
    ]
    actual = [(point.x, point.y) for point in annotation.pdf_corners.root]
    assert actual == pytest.approx(expected)


def test_make_pdf_sidecar_annotation_quads_do_not_overlap(tmp_path: Path) -> None:
    template = _template(tmp_path / "template.pdf", (612.0, 792.0))
    images = [
        PdfMakeImageInput.model_validate(
            _image_payload(_write_image(tmp_path / f"source_{index}.png"), index)
        )
        for index in range(3)
    ]
    texts = [
        PdfMakeTextInput.model_validate(_text_payload(index)) for index in range(3)
    ]

    artifacts = make_pdf_composition(
        template=template,
        images=images,
        texts=texts,
        output_dir=tmp_path / "output",
        seed=11,
    )

    annotations_by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    for annotation in artifacts.record.image_annotations:
        annotations_by_page.setdefault(annotation.placement.page_index, []).append(
            _bounds(annotation.pdf_corners.root)
        )
    for annotation in artifacts.record.text_annotations:
        annotations_by_page.setdefault(annotation.placement.page_index, []).append(
            _bounds(annotation.pdf_corners.root)
        )
    for quads in annotations_by_page.values():
        for first_index, first in enumerate(quads):
            for second in quads[first_index + 1 :]:
                assert not _overlap(first, second)


def test_make_pdf_same_seed_repeats_sidecar_layout_data(tmp_path: Path) -> None:
    template = _template(tmp_path / "template.pdf", (612.0, 792.0))
    images = [
        PdfMakeImageInput.model_validate(
            _image_payload(_write_image(tmp_path / f"seeded_{index}.png"), index)
        )
        for index in range(3)
    ]
    texts = [
        PdfMakeTextInput.model_validate(_text_payload(index)) for index in range(3)
    ]

    first = make_pdf_composition(
        template=template,
        images=images,
        texts=texts,
        output_dir=tmp_path / "same-output",
        seed=21,
    )
    first_payload = json.loads(first.annotation_json.read_text(encoding="utf-8"))
    second = make_pdf_composition(
        template=template,
        images=images,
        texts=texts,
        output_dir=tmp_path / "same-output",
        seed=21,
    )
    second_payload = json.loads(second.annotation_json.read_text(encoding="utf-8"))

    assert second_payload == first_payload


def test_make_pdf_seed_changes_layout_but_not_text_contents(tmp_path: Path) -> None:
    template = _template(tmp_path / "template.pdf", (612.0, 792.0))
    images = [
        PdfMakeImageInput.model_validate(
            _image_payload(_write_image(tmp_path / f"changed_{index}.png"), index)
        )
        for index in range(3)
    ]
    texts = [
        PdfMakeTextInput.model_validate(_text_payload(index)) for index in range(3)
    ]

    first = make_pdf_composition(
        template=template,
        images=images,
        texts=texts,
        output_dir=tmp_path / "seed-1",
        seed=1,
    )
    second = make_pdf_composition(
        template=template,
        images=images,
        texts=texts,
        output_dir=tmp_path / "seed-2",
        seed=2,
    )

    assert first.record.layout_decisions != second.record.layout_decisions
    assert [item.model_dump(mode="json") for item in first.record.texts] == [
        item.model_dump(mode="json") for item in second.record.texts
    ]
    assert [item.rendered_text for item in first.record.text_annotations] == [
        item.rendered_text for item in second.record.text_annotations
    ]


@pytest.mark.parametrize(
    ("image_count", "text_count", "message"),
    [
        (0, 1, "images must contain at least one item"),
        (1, 0, "texts must contain at least one item"),
    ],
)
def test_make_pdf_rejects_missing_required_sequences(
    tmp_path: Path,
    image_count: int,
    text_count: int,
    message: str,
) -> None:
    pdf, images, texts = _make_inputs(
        tmp_path,
        image_count=image_count,
        text_count=text_count,
    )

    with pytest.raises(ValueError, match=message):
        make_pdf(images, texts, pdf, tmp_path / "output", seed=4)


def test_make_pdf_rejects_missing_files(tmp_path: Path) -> None:
    pdf, images, texts = _make_inputs(tmp_path, image_count=1, text_count=1)
    images[0]["path"] = tmp_path / "missing.png"

    with pytest.raises(FileNotFoundError, match="images\\[0\\]\\.path does not exist"):
        make_pdf(images, texts, pdf, tmp_path / "output", seed=4)
    pdf, images, texts = _make_inputs(tmp_path, image_count=1, text_count=1)
    with pytest.raises(FileNotFoundError, match="pdf does not exist"):
        make_pdf(images, texts, tmp_path / "missing.pdf", tmp_path / "output", seed=4)


def test_make_pdf_rejects_template_output_alias_without_mutating_source(
    tmp_path: Path,
) -> None:
    pdf = _write_pdf(tmp_path / "pdf_make.pdf", (612.0, 792.0))
    image = _image_payload(_write_image(tmp_path / "source.png"), 0)
    source_bytes = pdf.read_bytes()

    with pytest.raises(ValueError, match="template and make_pdf output paths"):
        make_pdf([image], [_text_payload(0)], pdf, tmp_path, seed=4)

    assert pdf.read_bytes() == source_bytes
    assert not (tmp_path / "pdf_make_annotations.json").exists()


def test_make_pdf_writer_rejects_handwritten_without_asset_source(
    tmp_path: Path,
) -> None:
    template = _template(tmp_path / "template.pdf", (612.0, 792.0))
    image = PdfMakeImageInput.model_validate(
        _image_payload(_write_image(tmp_path / "source.png"), 0)
    )
    text = PdfMakeTextInput.model_validate(_text_payload(0, handwritten=True))

    with pytest.raises(ValueError, match="handwritten PDF text requires"):
        make_pdf_composition(
            template=template,
            images=[image],
            texts=[text],
            output_dir=tmp_path / "output",
            seed=4,
        )
