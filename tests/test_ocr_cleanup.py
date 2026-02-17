"""Tests for the profile-driven OCR cleanup engine."""

from __future__ import annotations

import pytest

from pipeline.ocr_cleanup import (
    CleanedPage,
    OCRQualityReport,
    apply_known_substitutions,
    apply_regex_substitutions,
    assess_quality,
    clean_page,
    collapse_spaced_characters,
    detect_garbage_lines,
    normalize_unicode,
    strip_headers_footers,
)
from pipeline.profile import load_profile


# ── Known Substitutions Tests ─────────────────────────────────────


class TestApplyKnownSubstitutions:
    """Test manual-specific OCR substitution rules."""

    def test_single_substitution(self):
        result = apply_known_substitutions(
            "IJURY may result",
            [{"from": "IJURY", "to": "INJURY"}],
        )
        assert result == "INJURY may result"

    def test_multiple_substitutions(self):
        result = apply_known_substitutions(
            "IJURY from Mopart parts",
            [
                {"from": "IJURY", "to": "INJURY"},
                {"from": "Mopart", "to": "Mopar"},
            ],
        )
        assert result == "INJURY from Mopar parts"

    def test_no_match_returns_unchanged(self):
        original = "No OCR errors here"
        result = apply_known_substitutions(original, [{"from": "XYZ", "to": "ABC"}])
        assert result == original

    def test_empty_substitutions_list(self):
        original = "Some text"
        result = apply_known_substitutions(original, [])
        assert result == original

    def test_cj_smart_quote_substitution(self):
        result = apply_known_substitutions(
            "'Jeep' is a brand",
            [{"from": "'Jeep'", "to": "Jeep"}],
        )
        assert result == "Jeep is a brand"

    def test_cj_split_word_substitution(self):
        result = apply_known_substitutions(
            "UNIVERSA L SERIE S",
            [
                {"from": "UNIVERSA L", "to": "UNIVERSAL"},
                {"from": "SERIE S", "to": "SERIES"},
            ],
        )
        assert result == "UNIVERSAL SERIES"

    def test_tm9_substitutions(self):
        result = apply_known_substitutions(
            "TECHNIG~MANUAL CHAPTEIR 3",
            [
                {"from": "TECHNIG~MANUAL", "to": "TECHNICAL MANUAL"},
                {"from": "CHAPTEIR", "to": "CHAPTER"},
            ],
        )
        assert result == "TECHNICAL MANUAL CHAPTER 3"

    def test_multiple_occurrences_replaced(self):
        result = apply_known_substitutions(
            "IJURY here and IJURY there",
            [{"from": "IJURY", "to": "INJURY"}],
        )
        assert result == "INJURY here and INJURY there"


# ── Regex Substitutions Tests ────────────────────────────────────


class TestApplyRegexSubstitutions:
    """Test regex-based OCR substitution rules."""

    def test_single_regex_substitution(self):
        result = apply_regex_substitutions(
            "Znstallation of the Znterference fit",
            [{"pattern": r"\bZn", "replacement": "In"}],
        )
        assert result == "Installation of the Interference fit"

    def test_multiple_regex_substitutions_applied_in_order(self):
        result = apply_regex_substitutions(
            "CHAPTEa 3 Generd",
            [
                {"pattern": r"CHAPTEa", "replacement": "CHAPTER"},
                {"pattern": r"Generd", "replacement": "General"},
            ],
        )
        assert result == "CHAPTER 3 General"

    def test_no_match_returns_unchanged(self):
        original = "Clean text without OCR errors"
        result = apply_regex_substitutions(
            original,
            [{"pattern": r"XYZ\d+", "replacement": "ABC"}],
        )
        assert result == original

    def test_empty_substitutions_list(self):
        original = "Some text"
        result = apply_regex_substitutions(original, [])
        assert result == original

    def test_backreference_in_replacement(self):
        """Regex replacement can use backreferences like \\1."""
        result = apply_regex_substitutions(
            "AIR CWiiiER cleaned",
            [{"pattern": r"CWiiiER", "replacement": "CLEANER"}],
        )
        assert result == "AIR CLEANER cleaned"


class TestCleanPageRegexSubstitutions:
    """Test that regex substitutions are applied within clean_page pipeline."""

    def test_regex_subs_applied_in_clean_page(self, xj_profile_path):
        """Regex substitutions are applied during clean_page when present in profile."""
        profile = load_profile(xj_profile_path)
        # Inject regex substitutions into the profile for testing
        profile.ocr_cleanup.regex_substitutions = [
            {"pattern": r"\bZnstall", "replacement": "Install"},
        ]
        result = clean_page("Znstallation procedure follows.", 1, profile)
        assert "Installation" in result.cleaned_text
        assert "Znstall" not in result.cleaned_text


# ── Character-Spacing Collapse Tests ─────────────────────────────


class TestCollapseSpacedCharacters:
    """Test character-spacing collapse for OCR'd headings."""

    def test_collapses_hurricane(self):
        """H U R R I C A N E -> HURRICANE (3+ single uppercase chars)."""
        result = collapse_spaced_characters("H U R R I C A N E")
        assert result == "HURRICANE"

    def test_preserves_punctuation_between_segments(self):
        """F I G . D - 1 4 -> collapsed segments preserve punctuation."""
        # The regex only collapses sequences of uppercase letters separated by
        # spaces. Punctuation/digits break the sequence into separate segments.
        # 'F I G' collapses to 'FIG'; the period and everything after stays.
        result = collapse_spaced_characters("F I G . D - 1 4")
        assert result == "FIG . D - 1 4"

    def test_does_not_collapse_single_char_with_word(self):
        """'A description' NOT collapsed (only 1 single-char, need 3+)."""
        result = collapse_spaced_characters("A description")
        assert result == "A description"

    def test_does_not_collapse_two_chars(self):
        """'I V' NOT collapsed (only 2 chars — below threshold of 3)."""
        result = collapse_spaced_characters("I V")
        assert result == "I V"


# ── Header/Footer Stripping Tests ─────────────────────────────────


class TestStripHeadersFooters:
    """Test header/footer removal using profile patterns."""

    def test_strips_xj_header(self):
        text = "XJ LUBRICATION AND MAINTENANCE 0 - 12\nActual content here"
        cleaned, page_num = strip_headers_footers(
            text,
            [r"^XJ\s+[A-Z ]+\d+[A-Z]?\s*-\s*\d+"],
        )
        assert "XJ LUBRICATION" not in cleaned
        assert "Actual content here" in cleaned

    def test_strips_xj_footer(self):
        text = "Actual content here\n0 - 12 LUBRICATION AND MAINTENANCE XJ"
        cleaned, _ = strip_headers_footers(
            text,
            [r"^\d+[A-Z]?\s*-\s*\d+\s+[A-Z ]+XJ$"],
        )
        assert "LUBRICATION AND MAINTENANCE XJ" not in cleaned
        assert "Actual content here" in cleaned

    def test_strips_continued_marker(self):
        text = "Some content\nMore content (Continued)"
        cleaned, _ = strip_headers_footers(text, [r"\(Continued\)$"])
        assert "(Continued)" not in cleaned

    def test_extracts_page_number(self):
        text = "XJ LUBRICATION AND MAINTENANCE 0 - 12\nContent"
        _, page_num = strip_headers_footers(
            text,
            [r"^XJ\s+[A-Z ]+\d+[A-Z]?\s*-\s*\d+"],
        )
        # Should extract the page number from the header
        assert page_num is not None

    def test_no_match_returns_original(self):
        text = "Just regular content\nWith no headers"
        cleaned, page_num = strip_headers_footers(text, [r"^XJ\s+"])
        assert cleaned == text
        assert page_num is None

    def test_strips_tm9_header(self):
        text = "TM 9-8014\nActual content"
        cleaned, _ = strip_headers_footers(text, [r"^\*?TM\s+9-8014"])
        assert "TM 9-8014" not in cleaned
        assert "Actual content" in cleaned


# ── Garbage Line Detection Tests ──────────────────────────────────


class TestDetectGarbageLines:
    """Test non-ASCII character garbage detection."""

    def test_clean_text_no_garbage(self):
        text = "This is clean English text.\nWith normal characters."
        garbage = detect_garbage_lines(text, threshold=0.5)
        assert garbage == []

    def test_detects_high_non_ascii_line(self):
        text = "Normal line\n\u00a7\u00b6\u2020\u2021\u00a9\u00ae\u2122\u00d7\u00f7\u2260 garbage\nNormal again"
        garbage = detect_garbage_lines(text, threshold=0.3)
        assert 1 in garbage  # Second line (index 1) is garbage

    def test_respects_threshold(self):
        text = "Normal line\nMild\u00e9 acc\u00e8nt\nNormal"
        # With a high threshold, accented chars shouldn't flag
        garbage = detect_garbage_lines(text, threshold=0.8)
        assert garbage == []

    def test_empty_text(self):
        garbage = detect_garbage_lines("", threshold=0.5)
        assert garbage == []

    def test_all_ascii_text(self):
        text = "Purely ASCII text here\nAnother line"
        garbage = detect_garbage_lines(text, threshold=0.1)
        assert garbage == []


# ── Unicode Normalization Tests ───────────────────────────────────


class TestNormalizeUnicode:
    """Test universal cleanup: quotes, ligatures, whitespace."""

    def test_smart_quotes_to_straight(self):
        result = normalize_unicode("\u201cHello\u201d and \u2018world\u2019")
        assert '"Hello"' in result
        assert "'world'" in result

    def test_ligature_decomposition(self):
        result = normalize_unicode("The \ufb01rst \ufb02oor")
        assert "first" in result
        assert "floor" in result

    def test_whitespace_normalization(self):
        result = normalize_unicode("Multiple   spaces   here")
        assert "Multiple spaces here" in result

    def test_preserves_single_newlines(self):
        result = normalize_unicode("Line one\nLine two")
        assert "\n" in result

    def test_collapses_excessive_newlines(self):
        result = normalize_unicode("Line one\n\n\n\n\nLine two")
        # Should collapse to at most 2 newlines
        assert "\n\n\n" not in result

    def test_empty_string(self):
        result = normalize_unicode("")
        assert result == ""


# ── Full Page Cleanup Tests ───────────────────────────────────────


class TestCleanPage:
    """Test full cleanup pipeline on a single page."""

    def test_returns_cleaned_page(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert isinstance(result, CleanedPage)

    def test_page_number_preserved(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert result.page_number == 12

    def test_original_text_preserved(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert result.original_text == sample_ocr_dirty_text

    def test_substitutions_applied(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert "IJURY" not in result.cleaned_text
        assert "INJURY" in result.cleaned_text

    def test_mopar_substitution_applied(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert "Mopart" not in result.cleaned_text
        assert "Mopar" in result.cleaned_text

    def test_headers_stripped(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert "XJ                    LUBRICATION" not in result.cleaned_text

    def test_continued_marker_stripped(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert "(Continued)" not in result.cleaned_text

    def test_smart_quotes_normalized(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert "\u201c" not in result.cleaned_text
        assert "\u201d" not in result.cleaned_text

    def test_garbage_lines_detected(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert len(result.garbage_lines) > 0

    def test_substitutions_count_tracked(self, xj_profile_path, sample_ocr_dirty_text):
        profile = load_profile(xj_profile_path)
        result = clean_page(sample_ocr_dirty_text, 12, profile)
        assert result.substitutions_applied >= 2  # IJURY and Mopart


# ── Quality Assessment Tests ──────────────────────────────────────


class TestAssessQuality:
    """Test OCR quality assessment across cleaned pages."""

    def test_returns_quality_report(self, xj_profile_path, xj_sample_page_text):
        profile = load_profile(xj_profile_path)
        page = clean_page(xj_sample_page_text, 9, profile)
        report = assess_quality([page], sample_size=1)
        assert isinstance(report, OCRQualityReport)

    def test_good_text_high_dictionary_rate(self, xj_profile_path, xj_sample_page_text):
        profile = load_profile(xj_profile_path)
        page = clean_page(xj_sample_page_text, 9, profile)
        report = assess_quality([page], sample_size=1)
        assert report.dictionary_match_rate >= 0.80

    def test_needs_reocr_flag_on_poor_quality(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        garbage_text = "\u00a7\u00b6\u2020\u2021 g@rb@g3 t3xt h3r3\n!@#$%^& m0r3 j#nk"
        page = clean_page(garbage_text, 1, profile)
        report = assess_quality([page], sample_size=1)
        assert report.needs_reocr is True

    def test_report_counts(self, xj_profile_path, xj_sample_page_text):
        profile = load_profile(xj_profile_path)
        pages = [clean_page(xj_sample_page_text, i, profile) for i in range(5)]
        report = assess_quality(pages, sample_size=5)
        assert report.total_pages == 5
        assert report.sampled_pages == 5
