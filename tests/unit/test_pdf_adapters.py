from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from injection_pipeline.loaders.pdf import PdfLoader
from injection_pipeline.pdf.models import PdfAnnotationRecord
from injection_pipeline.writers.pdf import PdfWriterAdapter
from tests.fixtures.synthetic_documents import (
    write_synthetic_dicom,
    write_synthetic_pdf_run,
)


def _write_template(path: Path) -> Path:
    canvas = Canvas(str(path), pagesize=(612.0, 792.0), invariant=1)
    canvas.drawString(36, 756, "SYNTHETIC REPORT TEMPLATE")
    canvas.showPage()
    canvas.drawString(36, 756, "SECOND SYNTHETIC PAGE")
    canvas.save()
    return path


def test_pdf_loader_reads_page_count_and_sizes(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path / "template.pdf")

    template = PdfLoader().load(template_path)

    assert template.source_file == template_path
    assert template.page_count == 2
    assert template.page_sizes == [(612.0, 792.0), (612.0, 792.0)]


def test_pdf_writer_emits_clean_annotated_pdf_and_sidecar(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path / "template.pdf")
    run_dir = tmp_path / "run"
    annotation_path, _ = write_synthetic_pdf_run(run_dir)
    dicom_path = write_synthetic_dicom(run_dir / "injected.dcm")
    template = PdfLoader().load(template_path)

    artifacts = PdfWriterAdapter().write(
        template,
        dicom_path,
        annotation_path,
        tmp_path / "output",
        slot="top_right",
    )

    assert artifacts.clean_pdf.is_file()
    assert artifacts.annotated_pdf.is_file()
    assert artifacts.annotation_json.is_file()
    assert artifacts.record.placement.slot == "top_right"
    assert len(artifacts.record.annotations) == 3
    rotated_corners = artifacts.record.annotations[2].pdf_corners.root
    assert rotated_corners[0].x != rotated_corners[1].x
    clean_reader = PdfReader(str(artifacts.clean_pdf))
    annotated_reader = PdfReader(str(artifacts.annotated_pdf))
    assert len(clean_reader.pages) == 2
    assert len(annotated_reader.pages) == 2
    assert "SYNTHETIC REPORT TEMPLATE" in clean_reader.pages[0].extract_text()
    assert "SECOND SYNTHETIC PAGE" in clean_reader.pages[1].extract_text()

    loaded_sidecar = PdfAnnotationRecord.model_validate_json(
        artifacts.annotation_json.read_text(encoding="utf-8")
    )
    assert loaded_sidecar.record_type == "pdf_injection_run"
    assert loaded_sidecar.source_run_id == "synthetic-pdf-run"


def test_pdf_writer_is_reproducible_for_identical_inputs(tmp_path: Path) -> None:
    template_path = _write_template(tmp_path / "template.pdf")
    run_dir = tmp_path / "run"
    annotation_path, _ = write_synthetic_pdf_run(run_dir)
    dicom_path = write_synthetic_dicom(run_dir / "injected.dcm")
    template = PdfLoader().load(template_path)

    first = PdfWriterAdapter().write(
        template, dicom_path, annotation_path, tmp_path / "output"
    )
    first_clean = first.clean_pdf.read_bytes()
    first_annotated = first.annotated_pdf.read_bytes()
    second = PdfWriterAdapter().write(
        template, dicom_path, annotation_path, tmp_path / "output"
    )

    assert second.clean_pdf.read_bytes() == first_clean
    assert second.annotated_pdf.read_bytes() == first_annotated
