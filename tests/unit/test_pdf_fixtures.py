from pathlib import Path

from PIL import Image

from injection_pipeline.models import load_run_record
from tests.fixtures.synthetic_documents import write_synthetic_pdf_run


def test_synthetic_pdf_run_fixture_has_non_square_preview_and_three_boxes(
    tmp_path: Path,
) -> None:
    ground_truth_path, preview_path = write_synthetic_pdf_run(tmp_path / "run")

    record = load_run_record(ground_truth_path)
    with Image.open(preview_path) as preview:
        assert preview.size == (320, 180)

    assert len(record.box_annotations) == 3
    assert record.box_annotations[2].rotation_degrees == 20
    assert record.preview_file == Path("preview.png")
