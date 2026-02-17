"""Tests for the profile-driven structural parser."""

from __future__ import annotations

import json
import re

import pytest

from pipeline.profile import load_profile
from pipeline.structural_parser import (
    Boundary,
    LineRange,
    Manifest,
    ManifestEntry,
    PageRange,
    build_manifest,
    detect_boundaries,
    filter_boundaries,
    generate_chunk_id,
    load_manifest,
    save_manifest,
    validate_boundaries,
)


# ── Chunk ID Generation Tests ─────────────────────────────────────


class TestGenerateChunkId:
    """Test namespaced chunk ID generation."""

    def test_single_level(self):
        result = generate_chunk_id("xj-1999", ["0"])
        assert result == "xj-1999::0"

    def test_multi_level(self):
        result = generate_chunk_id("xj-1999", ["0", "SP", "JSP"])
        assert result == "xj-1999::0::SP::JSP"

    def test_different_manual_prefix(self):
        result = generate_chunk_id("cj-universal-53-71", ["B", "B-4"])
        assert result == "cj-universal-53-71::B::B-4"

    def test_tm9_id_format(self):
        result = generate_chunk_id("tm9-8014-m38a1", ["2", "III", "42"])
        assert result == "tm9-8014-m38a1::2::III::42"

    def test_empty_hierarchy_returns_manual_id_only(self):
        result = generate_chunk_id("xj-1999", [])
        assert result == "xj-1999"

    def test_ids_with_letters(self):
        result = generate_chunk_id("xj-1999", ["8A"])
        assert result == "xj-1999::8A"


# ── Boundary Detection Tests ──────────────────────────────────────


class TestDetectBoundaries:
    """Test structural boundary detection using profile patterns."""

    def test_detects_xj_group_boundary(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        pages = ["0 Lubrication and Maintenance\n\nSome content here."]
        boundaries = detect_boundaries(pages, profile)
        assert len(boundaries) >= 1
        assert boundaries[0].level == 1
        assert boundaries[0].id == "0"

    def test_detects_xj_section_boundary(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        pages = ["0 Lubrication and Maintenance\n\nSERVICE PROCEDURES\n\nSome content."]
        boundaries = detect_boundaries(pages, profile)
        section_bounds = [b for b in boundaries if b.level == 2]
        assert len(section_bounds) >= 1

    def test_detects_xj_procedure_boundary(self, xj_profile_path, xj_sample_page_text):
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries([xj_sample_page_text], profile)
        proc_bounds = [b for b in boundaries if b.level == 3]
        assert len(proc_bounds) >= 1
        assert any("JUMP STARTING" in (b.title or "") for b in proc_bounds)

    def test_detects_cj_section_boundary(self, cj_profile_path):
        profile = load_profile(cj_profile_path)
        pages = ["B Lubrication and Periodic Services\n\nB-1. General\nContent here."]
        boundaries = detect_boundaries(pages, profile)
        assert len(boundaries) >= 1
        assert boundaries[0].level == 1
        assert boundaries[0].id == "B"

    def test_detects_cj_paragraph_boundary(self, cj_profile_path, cj_sample_page_text):
        profile = load_profile(cj_profile_path)
        boundaries = detect_boundaries([cj_sample_page_text], profile)
        para_bounds = [b for b in boundaries if b.level == 2]
        assert len(para_bounds) >= 1

    def test_detects_tm9_chapter_boundary(self, tm9_profile_path):
        profile = load_profile(tm9_profile_path)
        pages = ["CHAPTER 2. OPERATING INSTRUCTIONS\n\nContent here."]
        boundaries = detect_boundaries(pages, profile)
        assert len(boundaries) >= 1
        assert boundaries[0].level == 1
        assert boundaries[0].id == "2"

    def test_detects_tm9_section_boundary(self, tm9_profile_path, tm9_sample_page_text):
        profile = load_profile(tm9_profile_path)
        boundaries = detect_boundaries([tm9_sample_page_text], profile)
        section_bounds = [b for b in boundaries if b.level == 2]
        assert len(section_bounds) >= 1

    def test_detects_tm9_paragraph_boundary(self, tm9_profile_path, tm9_sample_page_text):
        profile = load_profile(tm9_profile_path)
        boundaries = detect_boundaries([tm9_sample_page_text], profile)
        para_bounds = [b for b in boundaries if b.level == 3]
        assert len(para_bounds) >= 1
        assert any(b.id == "42" for b in para_bounds)

    def test_records_page_number(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        pages = ["", "0 Lubrication and Maintenance\nContent"]
        boundaries = detect_boundaries(pages, profile)
        # Boundary detected on page index 1
        if boundaries:
            assert boundaries[0].page_number == 1

    def test_records_line_number_as_global_offset(self, xj_profile_path):
        """line_number must be a global offset into the concatenated page stream."""
        profile = load_profile(xj_profile_path)
        pages = ["Some preceding text\n\n0 Lubrication and Maintenance\nContent"]
        boundaries = detect_boundaries(pages, profile)
        if boundaries:
            # "0 Lubrication..." is on line index 2 within page 0 (and globally)
            assert boundaries[0].line_number == 2

    def test_multipage_line_numbers_are_global(
        self, xj_profile_path, xj_multipage_pages
    ):
        """Boundaries on page 2+ must have global (absolute) line offsets.

        Page 0 has 7 lines (indices 0-6). Page 1 has 12 lines (indices 0-11).
        After concatenation, page 1's lines start at global index 7.
        The procedure boundary 'JUMP STARTING PROCEDURE' is at page-local
        line 2, so its global offset must be 7 + 2 = 9.
        """
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(xj_multipage_pages, profile)

        # Should detect at least: group on page 0, section on page 0,
        # procedure on page 1
        assert len(boundaries) >= 3

        proc_bounds = [b for b in boundaries if b.level == 3]
        assert len(proc_bounds) >= 1, "Must detect procedure boundary on page 1"

        # The procedure is at page-local line 2 of page 1.
        # Page 0 has 7 lines, so global offset = 7 + 2 = 9.
        proc = proc_bounds[0]
        assert proc.page_number == 1
        page0_line_count = len(xj_multipage_pages[0].split("\n"))
        expected_global = page0_line_count + 2  # 7 + 2 = 9
        assert proc.line_number == expected_global, (
            f"Expected global line {expected_global}, got {proc.line_number}. "
            f"line_number must be a global offset, not per-page."
        )

    def test_multipage_group_boundary_on_first_page(
        self, xj_profile_path, xj_multipage_pages
    ):
        """Group boundary on page 0 should have line_number == 0 (global == local)."""
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(xj_multipage_pages, profile)

        group_bounds = [b for b in boundaries if b.level == 1]
        assert len(group_bounds) >= 1
        assert group_bounds[0].line_number == 0, (
            "Group boundary on page 0, line 0 should have global offset 0"
        )

    def test_empty_pages_returns_empty(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries([], profile)
        assert boundaries == []

    def test_no_matches_returns_empty(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        pages = ["Just some regular text with no structural markers."]
        boundaries = detect_boundaries(pages, profile)
        assert boundaries == []


# ── XJ Hierarchy Pattern Tightening Tests ────────────────────────


class TestXjLevel2PatternSelectivity:
    """Level 2 (section) pattern must require 2+ uppercase words, rejecting single-word OCR artifacts."""

    @pytest.fixture
    def level2_pattern(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        level2 = [h for h in profile.hierarchy if h.level == 2][0]
        return re.compile(level2.title_pattern)

    @pytest.mark.parametrize("heading", [
        "GENERAL INFORMATION",
        "COOLING SYSTEM",
        "FUEL INJECTION",
        "SERVICE PROCEDURES",
    ])
    def test_matches_multi_word_section_headings(self, level2_pattern, heading):
        assert level2_pattern.match(heading), (
            f"Level 2 pattern should match multi-word heading '{heading}'"
        )

    @pytest.mark.parametrize("artifact", [
        "SWITCH",
        "RELAY",
        "LAMP",
        "A",
    ])
    def test_rejects_single_word_ocr_artifacts(self, level2_pattern, artifact):
        assert level2_pattern.match(artifact) is None, (
            f"Level 2 pattern must reject single-word artifact '{artifact}'"
        )


class TestXjLevel3PatternSelectivity:
    """Level 3 (procedure) pattern must require 2+ words, rejecting single-word OCR artifacts."""

    @pytest.fixture
    def level3_pattern(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        level3 = [h for h in profile.hierarchy if h.level == 3][0]
        return re.compile(level3.title_pattern)

    @pytest.mark.parametrize("heading", [
        "REMOVAL AND INSTALLATION",
        "DIAGNOSIS AND TESTING",
        "JUMP STARTING PROCEDURE",
        "THERMOSTAT - REMOVAL AND INSTALLATION",
        "RADIATOR DRAINING AND REFILLING",
    ])
    def test_matches_multi_word_procedure_headings(self, level3_pattern, heading):
        assert level3_pattern.match(heading), (
            f"Level 3 pattern should match multi-word heading '{heading}'"
        )

    @pytest.mark.parametrize("artifact", [
        "SWITCH",
        "CHECK",
        "LAMP",
        "RELAY",
    ])
    def test_rejects_single_word_ocr_artifacts(self, level3_pattern, artifact):
        assert level3_pattern.match(artifact) is None, (
            f"Level 3 pattern must reject single-word artifact '{artifact}'"
        )


# ── Boundary Validation Tests ─────────────────────────────────────


class TestValidateBoundaries:
    """Test boundary validation against profile known_ids."""

    def test_valid_xj_boundaries(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        boundaries = [
            Boundary(level=1, level_name="group", id="0",
                     title="Lubrication and Maintenance", page_number=0, line_number=0),
            Boundary(level=1, level_name="group", id="9",
                     title="Engine", page_number=100, line_number=0),
        ]
        warnings = validate_boundaries(boundaries, profile)
        assert warnings == []

    def test_unrecognized_id_generates_warning(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        boundaries = [
            Boundary(level=1, level_name="group", id="99",
                     title="Unknown Group", page_number=0, line_number=0),
        ]
        warnings = validate_boundaries(boundaries, profile)
        assert len(warnings) >= 1
        assert any("99" in w for w in warnings)

    def test_level_without_known_ids_skips_validation(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        boundaries = [
            Boundary(level=3, level_name="procedure", id=None,
                     title="SOME PROCEDURE", page_number=0, line_number=0),
        ]
        warnings = validate_boundaries(boundaries, profile)
        assert warnings == []

    def test_empty_boundaries_returns_empty(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        warnings = validate_boundaries([], profile)
        assert warnings == []


# ── Boundary Post-Filter Tests ────────────────────────────────────


class TestFilterBoundaries:
    """Test filter_boundaries() post-filter logic."""

    @pytest.fixture
    def _make_profile(self, xj_profile_path):
        """Return a helper that loads the XJ profile and patches hierarchy filter fields."""
        from pipeline.profile import load_profile

        def _inner(
            min_gap_lines: int = 0,
            min_content_words: int = 0,
            require_blank_before: bool = False,
            target_level: int = 3,
        ):
            profile = load_profile(xj_profile_path)
            for h in profile.hierarchy:
                if h.level == target_level:
                    h.min_gap_lines = min_gap_lines
                    h.min_content_words = min_content_words
                    h.require_blank_before = require_blank_before
            return profile

        return _inner

    # ── min_gap_lines ────────────────────────────────────

    def test_min_gap_lines_removes_close_boundary(self, _make_profile):
        """Back-to-back level-3 boundaries with gap < min_gap_lines: second removed."""
        profile = _make_profile(min_gap_lines=3)
        # Page with two procedure headings only 1 line apart (lines 2 and 3)
        pages = [
            "7 Cooling System\n"
            "\n"
            "FIRST HEADING PROCEDURE\n"
            "SECOND HEADING PROCEDURE\n"
            "some content words here to pad things out\n"
            "more filler content here"
        ]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling System", page_number=0, line_number=0),
            Boundary(level=3, level_name="procedure", id=None, title="FIRST HEADING PROCEDURE", page_number=0, line_number=2),
            Boundary(level=3, level_name="procedure", id=None, title="SECOND HEADING PROCEDURE", page_number=0, line_number=3),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        level3 = [b for b in filtered if b.level == 3]
        assert len(level3) == 1
        assert level3[0].title == "FIRST HEADING PROCEDURE"

    def test_min_gap_lines_keeps_distant_boundary(self, _make_profile):
        """Level-3 boundaries with gap >= min_gap_lines: both kept."""
        profile = _make_profile(min_gap_lines=3)
        pages = [
            "7 Cooling System\n"
            "\n"
            "FIRST HEADING PROCEDURE\n"
            "filler line\n"
            "filler line\n"
            "\n"
            "SECOND HEADING PROCEDURE\n"
            "some content words here to pad things out"
        ]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling System", page_number=0, line_number=0),
            Boundary(level=3, level_name="procedure", id=None, title="FIRST HEADING PROCEDURE", page_number=0, line_number=2),
            Boundary(level=3, level_name="procedure", id=None, title="SECOND HEADING PROCEDURE", page_number=0, line_number=6),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        level3 = [b for b in filtered if b.level == 3]
        assert len(level3) == 2

    # ── min_content_words ────────────────────────────────

    def test_min_content_words_removes_below_threshold(self, _make_profile):
        """Boundary with fewer content words than threshold is removed."""
        profile = _make_profile(min_content_words=5)
        # Lines: 0="7 Cooling System", 1="", 2="SPARSE HEADING HERE",
        #        3="ok", 4="", 5="REAL HEADING PROCEDURE",
        #        6="lots of words to make this section clearly large enough"
        pages = [
            "7 Cooling System\n"
            "\n"
            "SPARSE HEADING HERE\n"
            "ok\n"
            "\n"
            "REAL HEADING PROCEDURE\n"
            "lots of words to make this section clearly large enough"
        ]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling System", page_number=0, line_number=0),
            Boundary(level=3, level_name="procedure", id=None, title="SPARSE HEADING HERE", page_number=0, line_number=2),
            Boundary(level=3, level_name="procedure", id=None, title="REAL HEADING PROCEDURE", page_number=0, line_number=5),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        level3 = [b for b in filtered if b.level == 3]
        # SPARSE boundary covers lines 2..4: "SPARSE HEADING HERE" (3) + "ok" (1) + "" (0) = 4 words < 5
        assert len(level3) == 1
        assert level3[0].title == "REAL HEADING PROCEDURE"

    def test_min_content_words_keeps_above_threshold(self, _make_profile):
        """Boundary with enough content words is kept."""
        profile = _make_profile(min_content_words=5)
        pages = [
            "7 Cooling System\n"
            "\n"
            "GOOD HEADING PROCEDURE\n"
            "this line has plenty of words to exceed the threshold\n"
            "even more content here for good measure"
        ]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling System", page_number=0, line_number=0),
            Boundary(level=3, level_name="procedure", id=None, title="GOOD HEADING PROCEDURE", page_number=0, line_number=2),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        level3 = [b for b in filtered if b.level == 3]
        assert len(level3) == 1

    # ── require_blank_before ─────────────────────────────

    def test_require_blank_before_removes_without_blank(self, _make_profile):
        """Boundary without a preceding blank line is removed when required."""
        profile = _make_profile(require_blank_before=True)
        # Line 2 is the boundary; line 1 is "content" (not blank)
        pages = [
            "7 Cooling System\n"
            "content right before heading\n"
            "HEADING WITHOUT BLANK BEFORE\n"
            "some content words here to pad things out more and more"
        ]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling System", page_number=0, line_number=0),
            Boundary(level=3, level_name="procedure", id=None, title="HEADING WITHOUT BLANK BEFORE", page_number=0, line_number=2),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        level3 = [b for b in filtered if b.level == 3]
        assert len(level3) == 0

    def test_require_blank_before_keeps_with_blank(self, _make_profile):
        """Boundary preceded by a blank line is kept."""
        profile = _make_profile(require_blank_before=True)
        # Line 1 is blank, line 2 is the boundary
        pages = [
            "7 Cooling System\n"
            "\n"
            "HEADING WITH BLANK BEFORE\n"
            "some content words here to pad things out more and more"
        ]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling System", page_number=0, line_number=0),
            Boundary(level=3, level_name="procedure", id=None, title="HEADING WITH BLANK BEFORE", page_number=0, line_number=2),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        level3 = [b for b in filtered if b.level == 3]
        assert len(level3) == 1

    def test_require_blank_before_removes_at_line_zero(self, _make_profile):
        """Boundary at line 0 (no preceding line) is removed when require_blank_before=True."""
        profile = _make_profile(require_blank_before=True, target_level=1)
        pages = ["HEADING AT LINE ZERO\nsome content words here"]
        boundaries = [
            Boundary(level=1, level_name="group", id="0", title="HEADING AT LINE ZERO", page_number=0, line_number=0),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        assert len(filtered) == 0

    # ── All filters disabled (backward compat) ───────────

    def test_all_filters_disabled_passes_through(self, _make_profile):
        """With all filter fields at defaults (0/False), boundaries are unchanged."""
        profile = _make_profile(min_gap_lines=0, min_content_words=0, require_blank_before=False)
        pages = [
            "7 Cooling System\n"
            "content\n"
            "HEADING ONE PROCEDURE\n"
            "HEADING TWO PROCEDURE\n"
            "some content"
        ]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling System", page_number=0, line_number=0),
            Boundary(level=3, level_name="procedure", id=None, title="HEADING ONE PROCEDURE", page_number=0, line_number=2),
            Boundary(level=3, level_name="procedure", id=None, title="HEADING TWO PROCEDURE", page_number=0, line_number=3),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        assert len(filtered) == len(boundaries)

    # ── Multiple filters combined ────────────────────────

    def test_multiple_filters_applied_together(self, _make_profile):
        """Combining min_gap_lines, min_content_words, and require_blank_before."""
        profile = _make_profile(min_gap_lines=3, min_content_words=5, require_blank_before=True)
        # Lines:
        # 0: "7 Cooling System"
        # 1: ""
        # 2: "GOOD HEADING PROCEDURE"  -- blank before, enough words after, first at level 3
        # 3: "word1 word2 word3 word4 word5 word6"
        # 4: ""
        # 5: "BAD GAP HEADING HERE"    -- blank before, but gap from line 2 is only 3 (exactly min)
        # 6: "word1 word2 word3 word4 word5 word6"
        # 7: ""
        # 8: "NO BLANK BEFORE HEADING" -- NOT preceded by blank (line 7 is blank... wait)
        # Need to construct carefully.
        pages = [
            "7 Cooling System\n"       # line 0
            "\n"                         # line 1
            "GOOD HEADING PROCEDURE\n"   # line 2  -- blank before (line 1), enough words, first lvl3
            "word1 word2 word3 word4 word5 word6\n"  # line 3
            "BAD NO BLANK HEADING\n"     # line 4  -- NOT blank before (line 3 has content) => removed by require_blank_before
            "word1 word2 word3 word4 word5 word6\n"  # line 5
            "\n"                         # line 6
            "CLOSE GAP HEADING HERE\n"   # line 7  -- blank before (line 6), but if GOOD at 2 survived, gap=5 >= 3 ✓
            "ok\n"                       # line 8  -- only 1 word + heading = few words
            "\n"                         # line 9
            "SPARSE CONTENT HEADING\n"   # line 10 -- blank before, gap from 7 = 3, but content < 5 words
            "hi"                         # line 11
        ]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling System", page_number=0, line_number=0),
            Boundary(level=3, level_name="procedure", id=None, title="GOOD HEADING PROCEDURE", page_number=0, line_number=2),
            Boundary(level=3, level_name="procedure", id=None, title="BAD NO BLANK HEADING", page_number=0, line_number=4),
            Boundary(level=3, level_name="procedure", id=None, title="CLOSE GAP HEADING HERE", page_number=0, line_number=7),
            Boundary(level=3, level_name="procedure", id=None, title="SPARSE CONTENT HEADING", page_number=0, line_number=10),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        level3 = [b for b in filtered if b.level == 3]
        # GOOD (line 2): blank before ✓, first at level ✓, words >= 5 ✓ => KEPT
        # BAD NO BLANK (line 4): no blank before (line 3 has content) => REMOVED by require_blank_before
        # CLOSE GAP (line 7): blank before (line 6) ✓, gap from 2 = 5 >= 3 ✓
        #   content lines 7..9 = "CLOSE GAP HEADING HERE" (4) + "ok" (1) + "" (0) = 5 words (not < 5) => KEPT
        # SPARSE (line 10): blank before ✓, gap from 7 = 3 >= 3 ✓
        #   content lines 10..11 = "SPARSE CONTENT HEADING" (3) + "hi" (1) = 4 words < 5 => REMOVED
        assert len(level3) == 2
        titles = [b.title for b in level3]
        assert "GOOD HEADING PROCEDURE" in titles
        assert "CLOSE GAP HEADING HERE" in titles

    def test_empty_boundaries_returns_empty(self, _make_profile):
        """Filtering an empty list returns an empty list."""
        profile = _make_profile(min_gap_lines=3, min_content_words=5, require_blank_before=True)
        filtered = filter_boundaries([], profile, ["some text"])
        assert filtered == []

    def test_filter_does_not_affect_other_levels(self, _make_profile):
        """Filters on level 3 do not remove level 1 or level 2 boundaries."""
        profile = _make_profile(min_gap_lines=10, min_content_words=100, require_blank_before=True)
        pages = [
            "7 Cooling System\n"
            "content here\n"
            "SERVICE PROCEDURES\n"
            "more content"
        ]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling System", page_number=0, line_number=0),
            Boundary(level=2, level_name="section", id=None, title="SERVICE PROCEDURES", page_number=0, line_number=2),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        # Level 1 and 2 have default filter settings (0/False), so all pass
        assert len(filtered) == 2


# ── Require Known ID Filter Tests ─────────────────────────────────


class TestRequireKnownId:
    """Test Pass 0 require_known_id filtering in filter_boundaries()."""

    @pytest.fixture
    def _make_profile_with_require(self, xj_profile_path):
        """Return a helper that loads the XJ profile and configures require_known_id."""
        from pipeline.profile import load_profile as _load

        def _inner(
            require_known_id: bool = False,
            known_ids: list[dict[str, str]] | None = None,
            target_level: int = 1,
        ):
            profile = _load(xj_profile_path)
            for h in profile.hierarchy:
                if h.level == target_level:
                    h.require_known_id = require_known_id
                    if known_ids is not None:
                        h.known_ids = known_ids
            return profile

        return _inner

    def test_require_known_id_rejects_unknown(self, _make_profile_with_require):
        """Boundaries with IDs not in known_ids are rejected when require_known_id is True."""
        profile = _make_profile_with_require(
            require_known_id=True,
            known_ids=[{"id": "7", "title": "Cooling"}, {"id": "9", "title": "Engine"}],
            target_level=1,
        )
        pages = ["dummy content with enough words for everyone"]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling", page_number=0, line_number=0),
            Boundary(level=1, level_name="group", id="9", title="Engine", page_number=0, line_number=5),
            Boundary(level=1, level_name="group", id="42", title="Unknown", page_number=0, line_number=10),
            Boundary(level=1, level_name="group", id="1999", title="Also Unknown", page_number=0, line_number=15),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        surviving_ids = [b.id for b in filtered]
        assert "7" in surviving_ids
        assert "9" in surviving_ids
        assert "42" not in surviving_ids
        assert "1999" not in surviving_ids
        assert len(filtered) == 2

    def test_require_known_id_false_passes_all(self, _make_profile_with_require):
        """When require_known_id is False, all boundaries pass regardless of known_ids."""
        profile = _make_profile_with_require(
            require_known_id=False,
            known_ids=[{"id": "7", "title": "Cooling"}, {"id": "9", "title": "Engine"}],
            target_level=1,
        )
        pages = ["dummy content with enough words for everyone"]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling", page_number=0, line_number=0),
            Boundary(level=1, level_name="group", id="9", title="Engine", page_number=0, line_number=5),
            Boundary(level=1, level_name="group", id="42", title="Unknown", page_number=0, line_number=10),
            Boundary(level=1, level_name="group", id="1999", title="Also Unknown", page_number=0, line_number=15),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        assert len(filtered) == 4

    def test_require_known_id_empty_known_ids_passes_all(self, _make_profile_with_require):
        """When require_known_id is True but known_ids is empty, all boundaries pass (guard clause)."""
        profile = _make_profile_with_require(
            require_known_id=True,
            known_ids=[],
            target_level=1,
        )
        pages = ["dummy content with enough words for everyone"]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling", page_number=0, line_number=0),
            Boundary(level=1, level_name="group", id="42", title="Unknown", page_number=0, line_number=10),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        assert len(filtered) == 2

    def test_require_known_id_none_id_rejected(self, _make_profile_with_require):
        """Boundary with id=None is rejected when require_known_id is True."""
        profile = _make_profile_with_require(
            require_known_id=True,
            known_ids=[{"id": "7", "title": "Cooling"}],
            target_level=1,
        )
        pages = ["dummy content with enough words for everyone"]
        boundaries = [
            Boundary(level=1, level_name="group", id=None, title="No ID", page_number=0, line_number=0),
            Boundary(level=1, level_name="group", id="7", title="Cooling", page_number=0, line_number=5),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        assert len(filtered) == 1
        assert filtered[0].id == "7"

    def test_require_known_id_only_affects_configured_level(self, _make_profile_with_require):
        """require_known_id on L1 does not filter L2 boundaries."""
        profile = _make_profile_with_require(
            require_known_id=True,
            known_ids=[{"id": "7", "title": "Cooling"}],
            target_level=1,
        )
        pages = ["dummy content with enough words for everyone"]
        boundaries = [
            Boundary(level=1, level_name="group", id="7", title="Cooling", page_number=0, line_number=0),
            Boundary(level=1, level_name="group", id="42", title="Unknown Group", page_number=0, line_number=5),
            Boundary(level=2, level_name="section", id="UNKNOWN_SECTION", title="UNKNOWN SECTION", page_number=0, line_number=10),
            Boundary(level=2, level_name="section", id="ANOTHER", title="ANOTHER SECTION", page_number=0, line_number=15),
        ]
        filtered = filter_boundaries(boundaries, profile, pages)
        # L1: only "7" survives (42 rejected). L2: both pass (not configured).
        level1 = [b for b in filtered if b.level == 1]
        level2 = [b for b in filtered if b.level == 2]
        assert len(level1) == 1
        assert level1[0].id == "7"
        assert len(level2) == 2


# ── Manifest Building Tests ───────────────────────────────────────


class TestBuildManifest:
    """Test hierarchical manifest construction from boundaries."""

    def test_returns_manifest(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        boundaries = [
            Boundary(level=1, level_name="group", id="0",
                     title="Lubrication and Maintenance", page_number=0, line_number=0),
        ]
        manifest = build_manifest(boundaries, profile)
        assert isinstance(manifest, Manifest)

    def test_manifest_manual_id(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        boundaries = [
            Boundary(level=1, level_name="group", id="0",
                     title="Lubrication and Maintenance", page_number=0, line_number=0),
        ]
        manifest = build_manifest(boundaries, profile)
        assert manifest.manual_id == "xj-1999"

    def test_manifest_entries_have_chunk_ids(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        boundaries = [
            Boundary(level=1, level_name="group", id="0",
                     title="Lubrication and Maintenance", page_number=0, line_number=0),
            Boundary(level=2, level_name="section", id="SERVICE PROCEDURES",
                     title="SERVICE PROCEDURES", page_number=5, line_number=100),
        ]
        manifest = build_manifest(boundaries, profile)
        assert len(manifest.entries) >= 1
        assert all(e.chunk_id.startswith("xj-1999::") for e in manifest.entries)

    def test_manifest_hierarchy_path(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        boundaries = [
            Boundary(level=1, level_name="group", id="0",
                     title="Lubrication and Maintenance", page_number=0, line_number=0),
            Boundary(level=2, level_name="section", id="SP",
                     title="SERVICE PROCEDURES", page_number=5, line_number=100),
            Boundary(level=3, level_name="procedure", id="JSP",
                     title="JUMP STARTING PROCEDURE", page_number=8, line_number=200),
        ]
        manifest = build_manifest(boundaries, profile)
        proc_entry = [e for e in manifest.entries if e.level == 3]
        if proc_entry:
            assert len(proc_entry[0].hierarchy_path) == 3

    def test_parent_child_relationships(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        boundaries = [
            Boundary(level=1, level_name="group", id="0",
                     title="Lubrication and Maintenance", page_number=0, line_number=0),
            Boundary(level=2, level_name="section", id="SP",
                     title="SERVICE PROCEDURES", page_number=5, line_number=100),
        ]
        manifest = build_manifest(boundaries, profile)
        child_entries = [e for e in manifest.entries if e.parent_chunk_id is not None]
        if child_entries:
            assert child_entries[0].parent_chunk_id.startswith("xj-1999::")

    def test_empty_boundaries_returns_empty_manifest(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        manifest = build_manifest([], profile)
        assert manifest.entries == []


# ── Three-Page Multi-Page Boundary Detection Tests ──────────────


class TestThreePageBoundaryDetection:
    """Verify boundary detection across 3-page manual content.

    These tests use the ``three_page_manual_pages`` fixture which has:
    - Page 0 (10 lines): group '7 Cooling System' + section 'SERVICE PROCEDURES'
    - Page 1 (16 lines): procedure 'RADIATOR DRAINING AND REFILLING'
    - Page 2 (14 lines): procedure 'THERMOSTAT - REMOVAL AND INSTALLATION'
    """

    def test_detects_all_boundary_levels(
        self, xj_profile_path, three_page_manual_pages
    ):
        """Should detect group, section, and two procedure boundaries."""
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)

        group_bounds = [b for b in boundaries if b.level == 1]
        section_bounds = [b for b in boundaries if b.level == 2]
        proc_bounds = [b for b in boundaries if b.level == 3]

        assert len(group_bounds) >= 1, "Must detect group boundary on page 0"
        assert len(section_bounds) >= 1, "Must detect section boundary on page 0"
        assert len(proc_bounds) >= 2, "Must detect procedure boundaries on pages 1 and 2"

    def test_group_boundary_has_global_line_zero(
        self, xj_profile_path, three_page_manual_pages
    ):
        """Group '7 Cooling System' is on page 0, line 0 => global offset 0."""
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)

        group_bounds = [b for b in boundaries if b.level == 1]
        assert len(group_bounds) >= 1
        assert group_bounds[0].page_number == 0
        assert group_bounds[0].line_number == 0
        assert group_bounds[0].id == "7"

    def test_section_boundary_global_offset_page0(
        self, xj_profile_path, three_page_manual_pages
    ):
        """'SERVICE PROCEDURES' is on page 0, line 4 => global offset 4."""
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)

        section_bounds = [b for b in boundaries if b.level == 2]
        assert len(section_bounds) >= 1
        assert section_bounds[0].page_number == 0
        assert section_bounds[0].line_number == 4

    def test_page1_procedure_global_line_offset(
        self, xj_profile_path, three_page_manual_pages
    ):
        """'RADIATOR DRAINING AND REFILLING' is at page-local line 2 of page 1.

        Page 0 has 10 lines, so global offset = 10 + 2 = 12.
        """
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)

        proc_bounds = [b for b in boundaries if b.level == 3]
        assert len(proc_bounds) >= 1

        radiator_proc = proc_bounds[0]
        assert radiator_proc.page_number == 1

        page0_lines = len(three_page_manual_pages[0].split("\n"))
        expected_global = page0_lines + 2  # 10 + 2 = 12
        assert radiator_proc.line_number == expected_global, (
            f"Expected global line {expected_global}, got {radiator_proc.line_number}. "
            f"Page 0 has {page0_lines} lines, procedure is at page-local line 2."
        )

    def test_page2_procedure_global_line_offset(
        self, xj_profile_path, three_page_manual_pages
    ):
        """'THERMOSTAT - REMOVAL AND INSTALLATION' is at page-local line 0 of page 2.

        Page 0 has 10 lines, page 1 has 16 lines.
        Global offset = 10 + 16 + 0 = 26.
        """
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)

        proc_bounds = [b for b in boundaries if b.level == 3]
        assert len(proc_bounds) >= 2, "Must detect procedures on both page 1 and page 2"

        thermostat_proc = proc_bounds[1]
        assert thermostat_proc.page_number == 2

        page0_lines = len(three_page_manual_pages[0].split("\n"))
        page1_lines = len(three_page_manual_pages[1].split("\n"))
        expected_global = page0_lines + page1_lines + 0  # 10 + 16 + 0 = 26
        assert thermostat_proc.line_number == expected_global, (
            f"Expected global line {expected_global}, got {thermostat_proc.line_number}. "
            f"Page 0: {page0_lines} lines, Page 1: {page1_lines} lines."
        )

    def test_boundaries_sorted_by_page_then_line(
        self, xj_profile_path, three_page_manual_pages
    ):
        """All boundaries must be sorted by (page_number, line_number)."""
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)

        for i in range(1, len(boundaries)):
            prev = boundaries[i - 1]
            curr = boundaries[i]
            assert (curr.page_number, curr.line_number) >= (prev.page_number, prev.line_number), (
                f"Boundary at index {i} ({curr.page_number}:{curr.line_number}) "
                f"precedes boundary at index {i-1} ({prev.page_number}:{prev.line_number})"
            )


class TestThreePageManifest:
    """Verify manifest built from 3-page boundaries has correct page ranges."""

    def test_manifest_has_entries_for_all_boundaries(
        self, xj_profile_path, three_page_manual_pages
    ):
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)
        manifest = build_manifest(boundaries, profile)

        assert len(manifest.entries) == len(boundaries), (
            f"Manifest should have one entry per boundary: "
            f"expected {len(boundaries)}, got {len(manifest.entries)}"
        )

    def test_manifest_entries_have_correct_page_numbers(
        self, xj_profile_path, three_page_manual_pages
    ):
        """Each manifest entry's page_range.start should match its boundary's page."""
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)
        manifest = build_manifest(boundaries, profile)

        for entry, boundary in zip(manifest.entries, boundaries):
            assert entry.page_range.start == str(boundary.page_number), (
                f"Entry '{entry.title}' page_range.start={entry.page_range.start} "
                f"but boundary page_number={boundary.page_number}"
            )

    def test_manifest_hierarchy_path_depth(
        self, xj_profile_path, three_page_manual_pages
    ):
        """Procedure entries should have 3-level hierarchy paths (group > section > procedure)."""
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)
        manifest = build_manifest(boundaries, profile)

        proc_entries = [e for e in manifest.entries if e.level == 3]
        for entry in proc_entries:
            assert len(entry.hierarchy_path) == 3, (
                f"Procedure '{entry.title}' hierarchy_path has "
                f"{len(entry.hierarchy_path)} levels, expected 3: {entry.hierarchy_path}"
            )

    def test_procedure_entries_have_parent(
        self, xj_profile_path, three_page_manual_pages
    ):
        """Procedure entries should have a parent_chunk_id pointing to the section."""
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(three_page_manual_pages, profile)
        manifest = build_manifest(boundaries, profile)

        proc_entries = [e for e in manifest.entries if e.level == 3]
        for entry in proc_entries:
            assert entry.parent_chunk_id is not None, (
                f"Procedure '{entry.title}' should have a parent_chunk_id"
            )
            assert entry.parent_chunk_id.startswith("xj-1999::"), (
                f"Parent chunk_id should start with 'xj-1999::'"
            )


class TestPageBoundaryEdgeCases:
    """Test boundary detection when boundaries fall on page edges."""

    def test_section_at_last_line_of_page(
        self, xj_profile_path, page_boundary_edge_case_pages
    ):
        """A section boundary at the very last line of page 0 should be detected.

        Page 0 has 5 lines (indices 0-4). 'SERVICE PROCEDURES' is at line 4.
        """
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(page_boundary_edge_case_pages, profile)

        section_bounds = [b for b in boundaries if b.level == 2]
        assert len(section_bounds) >= 1, (
            "Must detect section boundary even at last line of page"
        )
        assert section_bounds[0].page_number == 0
        assert section_bounds[0].line_number == 4

    def test_section_at_last_line_global_offset_correct(
        self, xj_profile_path, page_boundary_edge_case_pages
    ):
        """Boundary at last line of page 0 should have global offset = local offset."""
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(page_boundary_edge_case_pages, profile)

        section_bounds = [b for b in boundaries if b.level == 2]
        assert len(section_bounds) >= 1
        # On page 0, global == local since there are no preceding pages
        assert section_bounds[0].line_number == 4

    def test_content_after_page_boundary_section(
        self, xj_profile_path, page_boundary_edge_case_pages
    ):
        """Content on page 1 follows the section started at the end of page 0.

        Build a manifest and verify the section entry's line range starts at
        the correct global offset.
        """
        profile = load_profile(xj_profile_path)
        boundaries = detect_boundaries(page_boundary_edge_case_pages, profile)
        manifest = build_manifest(boundaries, profile)

        section_entries = [e for e in manifest.entries if e.level == 2]
        assert len(section_entries) >= 1

        # The section's line_range.start should be 4 (last line of page 0)
        assert section_entries[0].line_range.start == 4


# ── Manifest Persistence Tests ────────────────────────────────────


class TestManifestPersistence:
    """Test JSON serialization and deserialization of manifests."""

    @pytest.fixture
    def sample_manifest(self) -> Manifest:
        """A manifest with representative entries for persistence testing."""
        return Manifest(
            manual_id="xj-1999",
            entries=[
                ManifestEntry(
                    chunk_id="xj-1999::0",
                    level=1,
                    level_name="group",
                    title="Lubrication and Maintenance",
                    hierarchy_path=["Lubrication and Maintenance"],
                    content_type="group",
                    page_range=PageRange(start="0", end="12"),
                    line_range=LineRange(start=0, end=450),
                    vehicle_applicability=["Cherokee XJ"],
                    engine_applicability=["all"],
                    drivetrain_applicability=["all"],
                    has_safety_callouts=["warning"],
                    figure_references=["Fig. 1"],
                    cross_references=["Group 8A"],
                    parent_chunk_id=None,
                    children=["xj-1999::0::SP"],
                ),
                ManifestEntry(
                    chunk_id="xj-1999::0::SP",
                    level=2,
                    level_name="section",
                    title="SERVICE PROCEDURES",
                    hierarchy_path=["Lubrication and Maintenance", "SERVICE PROCEDURES"],
                    content_type="section",
                    page_range=PageRange(start="5", end="12"),
                    line_range=LineRange(start=100, end=450),
                    vehicle_applicability=["Cherokee XJ"],
                    engine_applicability=["all"],
                    drivetrain_applicability=["all"],
                    has_safety_callouts=[],
                    figure_references=[],
                    cross_references=[],
                    parent_chunk_id="xj-1999::0",
                    children=[],
                ),
            ],
        )

    def test_save_creates_valid_json_file(self, tmp_path, sample_manifest):
        out = tmp_path / "manifest.json"
        save_manifest(sample_manifest, out)

        assert out.exists()
        # Must be parseable JSON
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "manual_id" in data
        assert "entries" in data
        assert len(data["entries"]) == 2

    def test_load_reconstructs_manifest_with_correct_types(self, tmp_path, sample_manifest):
        out = tmp_path / "manifest.json"
        save_manifest(sample_manifest, out)

        loaded = load_manifest(out)
        assert isinstance(loaded, Manifest)
        assert isinstance(loaded.entries[0], ManifestEntry)
        assert isinstance(loaded.entries[0].page_range, PageRange)
        assert isinstance(loaded.entries[0].line_range, LineRange)

    def test_round_trip_preserves_all_fields(self, tmp_path, sample_manifest):
        out = tmp_path / "manifest.json"
        save_manifest(sample_manifest, out)
        loaded = load_manifest(out)

        assert loaded.manual_id == sample_manifest.manual_id
        assert len(loaded.entries) == len(sample_manifest.entries)

        for orig, restored in zip(sample_manifest.entries, loaded.entries):
            assert restored.chunk_id == orig.chunk_id
            assert restored.level == orig.level
            assert restored.level_name == orig.level_name
            assert restored.title == orig.title
            assert restored.hierarchy_path == orig.hierarchy_path
            assert restored.content_type == orig.content_type
            assert restored.page_range.start == orig.page_range.start
            assert restored.page_range.end == orig.page_range.end
            assert restored.line_range.start == orig.line_range.start
            assert restored.line_range.end == orig.line_range.end
            assert restored.vehicle_applicability == orig.vehicle_applicability
            assert restored.engine_applicability == orig.engine_applicability
            assert restored.drivetrain_applicability == orig.drivetrain_applicability
            assert restored.has_safety_callouts == orig.has_safety_callouts
            assert restored.figure_references == orig.figure_references
            assert restored.cross_references == orig.cross_references
            assert restored.parent_chunk_id == orig.parent_chunk_id
            assert restored.children == orig.children

    def test_loaded_page_range_has_correct_types(self, tmp_path, sample_manifest):
        out = tmp_path / "manifest.json"
        save_manifest(sample_manifest, out)
        loaded = load_manifest(out)

        for entry in loaded.entries:
            assert isinstance(entry.page_range, PageRange)
            assert isinstance(entry.page_range.start, str)
            assert isinstance(entry.page_range.end, str)

    def test_loaded_line_range_has_correct_types(self, tmp_path, sample_manifest):
        out = tmp_path / "manifest.json"
        save_manifest(sample_manifest, out)
        loaded = load_manifest(out)

        for entry in loaded.entries:
            assert isinstance(entry.line_range, LineRange)
            assert isinstance(entry.line_range.start, int)
            assert isinstance(entry.line_range.end, int)

    def test_empty_manifest_round_trip(self, tmp_path):
        manifest = Manifest(manual_id="empty-test", entries=[])
        out = tmp_path / "empty.json"
        save_manifest(manifest, out)
        loaded = load_manifest(out)

        assert loaded.manual_id == "empty-test"
        assert loaded.entries == []
