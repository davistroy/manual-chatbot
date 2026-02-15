"""Profile-driven OCR cleanup engine."""

from __future__ import annotations

import re
import unicodedata
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
    for sub in substitutions:
        text = text.replace(sub["from"], sub["to"])
    return text


def strip_headers_footers(text: str, patterns: list[str]) -> tuple[str, str | None]:
    """Remove header/footer lines matching profile patterns.

    Returns:
        Tuple of (cleaned text, extracted page number or None).
    """
    compiled = [re.compile(p) for p in patterns]
    lines = text.split("\n")
    kept_lines: list[str] = []
    page_number: str | None = None

    for line in lines:
        matched = False
        for pattern in compiled:
            if pattern.search(line):
                matched = True
                # Try to extract a page number from the matched line
                if page_number is None:
                    # Look for digit patterns like "0 - 12" or standalone numbers
                    num_match = re.search(r"(\d+)\s*-\s*(\d+)", line)
                    if num_match:
                        page_number = f"{num_match.group(1)}-{num_match.group(2)}"
                    else:
                        num_match = re.search(r"(\d+)", line)
                        if num_match:
                            page_number = num_match.group(1)
                break
        if not matched:
            kept_lines.append(line)

    cleaned = "\n".join(kept_lines)
    return cleaned, page_number


def detect_garbage_lines(text: str, threshold: float) -> list[int]:
    """Detect lines with excessive non-ASCII characters.

    Args:
        text: Text to analyze.
        threshold: Maximum ratio of non-ASCII characters before flagging.

    Returns:
        List of 0-indexed line numbers flagged as garbage.
    """
    if not text:
        return []

    garbage: list[int] = []
    lines = text.split("\n")

    for i, line in enumerate(lines):
        if not line.strip():
            continue
        # Check each word (whitespace-delimited token) for non-ASCII density.
        # A line is flagged as garbage if any token exceeds the threshold.
        words = line.split()
        for word in words:
            non_ascii_count = sum(1 for ch in word if ord(ch) > 127)
            total = len(word)
            if total > 0 and non_ascii_count / total > threshold:
                garbage.append(i)
                break

    return garbage


def normalize_unicode(text: str) -> str:
    """Apply universal cleanup: smart quotes, ligatures, whitespace normalization."""
    if not text:
        return text

    # Smart quotes to straight quotes
    text = text.replace("\u201c", '"')   # left double curly quote
    text = text.replace("\u201d", '"')   # right double curly quote
    text = text.replace("\u2018", "'")   # left single curly quote
    text = text.replace("\u2019", "'")   # right single curly quote

    # Common ligature decomposition
    text = text.replace("\ufb01", "fi")  # fi ligature
    text = text.replace("\ufb02", "fl")  # fl ligature
    text = text.replace("\ufb03", "ffi") # ffi ligature
    text = text.replace("\ufb04", "ffl") # ffl ligature

    # Normalize other unicode characters (NFC normalization)
    text = unicodedata.normalize("NFC", text)

    # Normalize horizontal whitespace (spaces/tabs) within each line, preserving newlines
    lines = text.split("\n")
    normalized_lines: list[str] = []
    for line in lines:
        # Collapse multiple spaces/tabs to single space
        line = re.sub(r"[ \t]+", " ", line)
        line = line.strip()
        normalized_lines.append(line)
    text = "\n".join(normalized_lines)

    # Collapse excessive newlines (more than 2) to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def clean_page(page_text: str, page_number: int, profile: ManualProfile) -> CleanedPage:
    """Run the full cleanup pipeline on a single page.

    Applies in order:
    1. Known substitutions
    2. Header/footer stripping
    3. Garbage detection
    4. Universal normalization
    """
    ocr_config = profile.ocr_cleanup

    # 1. Apply known substitutions
    substitutions = ocr_config.known_substitutions
    text = apply_known_substitutions(page_text, substitutions)

    # Count how many substitutions were actually applied
    sub_count = 0
    for sub in substitutions:
        count = page_text.count(sub["from"])
        sub_count += count

    # 2. Strip headers/footers
    header_footer_patterns = ocr_config.header_footer_patterns
    text, extracted_page_id = strip_headers_footers(text, header_footer_patterns)

    # 3. Detect garbage lines
    garbage_detection = ocr_config.garbage_detection

    if garbage_detection.enabled:
        garbage_lines = detect_garbage_lines(text, garbage_detection.threshold)
    else:
        garbage_lines = []

    # 4. Universal normalization
    text = normalize_unicode(text)

    return CleanedPage(
        page_number=page_number,
        original_text=page_text,
        cleaned_text=text,
        extracted_page_id=extracted_page_id,
        garbage_lines=garbage_lines,
        substitutions_applied=sub_count,
    )


def assess_quality(pages: list[CleanedPage], sample_size: int = 50) -> OCRQualityReport:
    """Run OCR quality assessment on a set of cleaned pages."""
    total_pages = len(pages)
    sampled = pages[:sample_size]
    sampled_pages = len(sampled)

    if sampled_pages == 0:
        return OCRQualityReport(
            total_pages=0,
            sampled_pages=0,
            dictionary_match_rate=0.0,
            garbage_line_rate=0.0,
            suspected_errors=0,
            needs_reocr=True,
        )

    # Calculate dictionary match rate by checking if words look like
    # valid English words (alphabetic characters only after stripping
    # edge punctuation)
    total_words = 0
    dict_words = 0
    total_lines = 0
    total_garbage_lines = 0
    suspected_errors = 0

    for page in sampled:
        text = page.cleaned_text
        words = re.findall(r"\S+", text)
        total_words += len(words)

        for word in words:
            # Strip punctuation from word edges for checking
            clean_word = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", word)
            if not clean_word:
                continue
            # A word looks "dictionary-like" if it is entirely alphabetic
            # (possibly with internal hyphens)
            inner = clean_word.replace("-", "")
            if inner and inner.isalpha():
                dict_words += 1
            else:
                suspected_errors += 1

        # Count garbage lines
        lines = text.split("\n")
        total_lines += len(lines)
        total_garbage_lines += len(page.garbage_lines)

    dictionary_match_rate = dict_words / total_words if total_words > 0 else 0.0
    garbage_line_rate = total_garbage_lines / total_lines if total_lines > 0 else 0.0

    # Determine if re-OCR is needed
    needs_reocr = dictionary_match_rate < 0.7 or garbage_line_rate > 0.3

    return OCRQualityReport(
        total_pages=total_pages,
        sampled_pages=sampled_pages,
        dictionary_match_rate=dictionary_match_rate,
        garbage_line_rate=garbage_line_rate,
        suspected_errors=suspected_errors,
        needs_reocr=needs_reocr,
    )
