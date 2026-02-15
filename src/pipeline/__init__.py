"""Smart Chunking Pipeline for Vehicle Service Manual RAG."""

from __future__ import annotations

from pathlib import Path


def extract_pages(pdf_path: str | Path) -> list[str]:
    """Extract text from each page of a PDF using pymupdf.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of strings, one per page.

    Raises:
        FileNotFoundError: If the PDF file does not exist.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    import pymupdf

    pages: list[str] = []
    with pymupdf.open(str(pdf_path)) as doc:
        for page in doc:
            pages.append(page.get_text())
    return pages
