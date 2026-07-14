"""Loader for PDF templates used by the PDF injection workflow."""

from pathlib import Path

from pypdf import PdfReader

from injection_pipeline.pdf.models import PdfTemplate


class PdfLoader:
    """Read PDF page geometry without changing the source document."""

    format_id = "pdf"
    extensions = (".pdf",)

    # Input: `path` mit dem PDF-Template.
    # Output: `PdfTemplate` mit Seitenanzahl und Seitengroessen in Punkten.
    # Die Methode validiert Lesbarkeit und Dateityp, ohne das Quelldokument zu
    # mutieren.
    def load(self, path: Path) -> PdfTemplate:
        if not path.is_file():
            raise FileNotFoundError(f"PDF input does not exist: {path}")
        try:
            reader = PdfReader(str(path))
            pages = reader.pages
            if not pages:
                raise ValueError("PDF input has no pages.")
            page_sizes = [
                (float(page.mediabox.width), float(page.mediabox.height))
                for page in pages
            ]
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError(f"Unable to read PDF input: {path}") from exc
        return PdfTemplate(
            source_file=path,
            page_count=len(pages),
            page_sizes=page_sizes,
        )
