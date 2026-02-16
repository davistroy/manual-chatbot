"""Tests for the profile-driven structural parser."""

from __future__ import annotations

import pytest

from pipeline.profile import load_profile
from pipeline.structural_parser import (
    Boundary,
    Manifest,
    ManifestEntry,
    build_manifest,
    detect_boundaries,
    generate_chunk_id,
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
