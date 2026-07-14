"""CLI coverage for the first-class PDF injection command."""

import sys
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas

from injection_pipeline.runtime import cli
from tests.fixtures.synthetic_documents import (
    write_synthetic_dicom,
    write_synthetic_pdf_run,
)


def test_inject_pdf_cli_writes_composition_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    template_path = tmp_path / "template.pdf"
    canvas = Canvas(str(template_path), pagesize=(612.0, 792.0), invariant=1)
    canvas.drawString(36, 756, "SYNTHETIC TEMPLATE")
    canvas.save()
    run_dir = tmp_path / "run"
    annotation_path, _ = write_synthetic_pdf_run(run_dir)
    dicom_path = write_synthetic_dicom(run_dir / "injected.dcm")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "injection-pipeline",
            "inject-pdf",
            "--input-pdf",
            str(template_path),
            "--input-dicom",
            str(dicom_path),
            "--dicom-annotation",
            str(annotation_path),
            "--output-dir",
            str(tmp_path / "output"),
        ],
    )

    cli.main()

    output_dir = tmp_path / "output" / "pdf" / "synthetic-pdf-run"
    artifacts = list(output_dir.rglob("*"))
    assert any(path.name == "pdf_injected.pdf" for path in artifacts)
    assert any(path.name == "pdf_injected_annotated.pdf" for path in artifacts)
    assert any(path.name == "pdf_annotations.json" for path in artifacts)
