"""Profile-driven OCR cleanup engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .profile import ManualProfile


@dataclass
class CleanedPage:
    """Result of cleaning a single page."""
    page_number: int
    original_text: str
    cleaned_text: str
    extracted_page_id: str | None
    garbage_lines: list[int]
    substitutions_applied: int


@dataclass
class OCRQualityReport:
    """Quality assessment for a set of cleaned pages."""
    total_pages: int
    sampled_pages: int
    dictionary_match_rate: float
    garbage_line_rate: float
    suspected_errors: int
    needs_reocr: bool


def apply_known_substitutions(text: str, substitutions: list[dict[str, str]]) -> str:
    """Apply manual-specific OCR substitution rules.

    Args:
        text: The raw text to clean.
        substitutions: List of {from, to} substitution dicts.

    Returns:
        Text with substitutions applied.
    """
    raise NotImplementedError


def strip_headers_footers(text: str, patterns: list[str]) -> tuple[str, str | None]:
    """Remove header/footer lines matching profile patterns.

    Returns:
        Tuple of (cleaned text, extracted page number or None).
    """
    raise NotImplementedError


def detect_garbage_lines(text: str, threshold: float) -> list[int]:
    """Detect lines with excessive non-ASCII characters.

    Args:
        text: Text to analyze.
        threshold: Maximum ratio of non-ASCII characters before flagging.

    Returns:
        List of 0-indexed line numbers flagged as garbage.
    """
    raise NotImplementedError


def normalize_unicode(text: str) -> str:
    """Apply universal cleanup: smart quotes, ligatures, whitespace normalization."""
    raise NotImplementedError


def clean_page(page_text: str, page_number: int, profile: ManualProfile) -> CleanedPage:
    """Run the full cleanup pipeline on a single page.

    Applies in order:
    1. Known substitutions
    2. Header/footer stripping
    3. Garbage detection
    4. Universal normalization
    """
    raise NotImplementedError


def assess_quality(pages: list[CleanedPage], sample_size: int = 50) -> OCRQualityReport:
    """Run OCR quality assessment on a set of cleaned pages."""
    raise NotImplementedError
