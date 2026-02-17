"""Tests for the chunk validation and QA suite."""

from __future__ import annotations

import pytest

from pipeline.chunk_assembly import Chunk
from pipeline.profile import load_profile
from pipeline.qa import (
    ValidationIssue,
    ValidationReport,
    check_cross_ref_validity,
    check_duplicate_content,
    check_metadata_completeness,
    check_orphaned_steps,
    check_profile_validation,
    check_size_outliers,
    check_split_safety_callouts,
    run_validation_suite,
)


def _make_chunk(
    chunk_id: str = "xj-1999::0::SP::JSP",
    text: str = "Default chunk text.",
    metadata: dict | None = None,
) -> Chunk:
    """Helper to create test chunks."""
    if metadata is None:
        metadata = {
            "manual_id": "xj-1999",
            "level1_id": "0",
            "content_type": "procedure",
        }
    return Chunk(
        chunk_id=chunk_id,
        manual_id="xj-1999",
        text=text,
        metadata=metadata,
    )


# ── Orphaned Steps Tests ──────────────────────────────────────────


class TestCheckOrphanedSteps:
    """Test detection of chunks starting mid-sequence."""

    def test_no_orphans_in_clean_chunks(self):
        chunks = [
            _make_chunk(text="(1) First step.\n(2) Second step.\n(3) Third step."),
        ]
        issues = check_orphaned_steps(chunks, [r"^\((\d+)\)\s"])
        assert issues == []

    def test_detects_chunk_starting_mid_sequence(self):
        chunks = [
            _make_chunk(
                chunk_id="xj-1999::0::SP::A",
                text="(3) Continue from previous chunk.\n(4) Next step.",
            ),
        ]
        issues = check_orphaned_steps(chunks, [r"^\((\d+)\)\s"])
        assert len(issues) >= 1
        assert issues[0].check == "orphaned_steps"

    def test_lettered_steps_orphan_detection(self):
        chunks = [
            _make_chunk(
                chunk_id="cj::B::B4",
                text="c. Continue from previous.\nd. Next step.",
            ),
        ]
        issues = check_orphaned_steps(chunks, [r"^([a-z])\.\s"])
        assert len(issues) >= 1

    def test_chunk_starting_with_step_1_not_orphaned(self):
        chunks = [
            _make_chunk(text="(1) First step.\n(2) Second step."),
        ]
        issues = check_orphaned_steps(chunks, [r"^\((\d+)\)\s"])
        assert issues == []

    def test_chunk_starting_with_step_a_not_orphaned(self):
        chunks = [
            _make_chunk(text="a. First step.\nb. Second step."),
        ]
        issues = check_orphaned_steps(chunks, [r"^([a-z])\.\s"])
        assert issues == []


# ── Split Safety Callout Tests ────────────────────────────────────


class TestCheckSplitSafetyCallouts:
    """Test detection of orphaned safety callouts at chunk boundaries."""

    def test_no_issues_with_attached_callout(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [
            _make_chunk(
                text="WARNING: Do not proceed without safety equipment.\n"
                     "(1) First step.\n(2) Second step.",
            ),
        ]
        issues = check_split_safety_callouts(chunks, profile)
        assert issues == []

    def test_detects_callout_at_chunk_start_without_context(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [
            _make_chunk(
                text="WARNING: THIS IS A CRITICAL SAFETY WARNING.",
            ),
        ]
        issues = check_split_safety_callouts(chunks, profile)
        # A chunk that's ONLY a warning with no procedure is suspicious
        assert len(issues) >= 1

    def test_note_at_start_is_less_severe(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [
            _make_chunk(text="NOTE: Some informational note.\n\nContent follows."),
        ]
        issues = check_split_safety_callouts(chunks, profile)
        # Notes are less critical than warnings
        if issues:
            assert all(i.severity == "warning" for i in issues)


# ── Size Outlier Tests ────────────────────────────────────────────


class TestCheckSizeOutliers:
    """Test chunk size outlier detection."""

    def test_normal_size_no_issues(self):
        text = "Word " * 500
        chunks = [_make_chunk(text=text)]
        issues = check_size_outliers(chunks, min_tokens=100, max_tokens=3000)
        assert issues == []

    def test_too_small_flagged(self):
        chunks = [_make_chunk(text="Tiny chunk.")]
        issues = check_size_outliers(chunks, min_tokens=100, max_tokens=3000)
        assert len(issues) >= 1
        assert issues[0].check == "size_outliers"

    def test_too_large_flagged(self):
        text = "Word " * 5000
        chunks = [_make_chunk(text=text)]
        issues = check_size_outliers(chunks, min_tokens=100, max_tokens=3000)
        assert len(issues) >= 1

    def test_severity_is_warning(self):
        chunks = [_make_chunk(text="Small.")]
        issues = check_size_outliers(chunks, min_tokens=100, max_tokens=3000)
        if issues:
            assert issues[0].severity == "warning"


# ── Metadata Completeness Tests ───────────────────────────────────


class TestCheckMetadataCompleteness:
    """Test that all required metadata fields are present."""

    def test_complete_metadata_no_issues(self):
        chunks = [
            _make_chunk(
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                },
            )
        ]
        issues = check_metadata_completeness(chunks)
        assert issues == []

    def test_missing_manual_id_flagged(self):
        chunks = [
            _make_chunk(metadata={"level1_id": "0", "content_type": "procedure"})
        ]
        issues = check_metadata_completeness(chunks)
        assert len(issues) >= 1

    def test_missing_level1_id_flagged(self):
        chunks = [
            _make_chunk(metadata={"manual_id": "xj-1999", "content_type": "procedure"})
        ]
        issues = check_metadata_completeness(chunks)
        assert len(issues) >= 1

    def test_missing_content_type_flagged(self):
        chunks = [
            _make_chunk(metadata={"manual_id": "xj-1999", "level1_id": "0"})
        ]
        issues = check_metadata_completeness(chunks)
        assert len(issues) >= 1

    def test_severity_is_error(self):
        chunks = [_make_chunk(metadata={})]
        issues = check_metadata_completeness(chunks)
        assert all(i.severity == "error" for i in issues)


# ── Duplicate Content Tests ───────────────────────────────────────


class TestCheckDuplicateContent:
    """Test near-duplicate chunk detection."""

    def test_no_duplicates(self):
        chunks = [
            _make_chunk(chunk_id="a", text="Completely different content A."),
            _make_chunk(chunk_id="b", text="Completely different content B."),
        ]
        issues = check_duplicate_content(chunks, similarity_threshold=0.95)
        assert issues == []

    def test_identical_chunks_flagged(self):
        text = "This exact text appears in two chunks."
        chunks = [
            _make_chunk(chunk_id="a", text=text),
            _make_chunk(chunk_id="b", text=text),
        ]
        issues = check_duplicate_content(chunks, similarity_threshold=0.95)
        assert len(issues) >= 1

    def test_similar_but_different_not_flagged(self):
        chunks = [
            _make_chunk(
                chunk_id="a",
                text="Remove the oil filter using a wrench. Install the new filter.",
            ),
            _make_chunk(
                chunk_id="b",
                text="Remove the air filter housing. Install the new air filter element.",
            ),
        ]
        issues = check_duplicate_content(chunks, similarity_threshold=0.95)
        assert issues == []


# ── Cross-Reference Validity Tests ────────────────────────────────


class TestCheckCrossRefValidity:
    """Test cross-reference target resolution."""

    def test_valid_refs_no_issues(self):
        chunks = [
            _make_chunk(
                chunk_id="xj-1999::0::SP",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": ["xj-1999::8A"],
                },
            ),
            _make_chunk(
                chunk_id="xj-1999::8A",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "8A",
                    "content_type": "procedure",
                    "cross_references": [],
                },
            ),
        ]
        issues = check_cross_ref_validity(chunks)
        assert issues == []

    def test_broken_ref_flagged(self):
        chunks = [
            _make_chunk(
                chunk_id="xj-1999::0::SP",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": ["xj-1999::99::NONEXISTENT"],
                },
            ),
        ]
        issues = check_cross_ref_validity(chunks)
        assert len(issues) >= 1

    def test_no_cross_refs_no_issues(self):
        chunks = [
            _make_chunk(
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": [],
                },
            )
        ]
        issues = check_cross_ref_validity(chunks)
        assert issues == []


# ── Profile Validation Tests ──────────────────────────────────────


class TestCheckProfileValidation:
    """Test Level 1 ID validation against profile known_ids."""

    def test_known_ids_no_issues(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [
            _make_chunk(
                chunk_id="xj-1999::0::SP",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                },
            ),
        ]
        issues = check_profile_validation(chunks, profile)
        assert issues == []

    def test_unknown_level1_id_flagged(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [
            _make_chunk(
                chunk_id="xj-1999::99::SP",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "99",
                    "content_type": "procedure",
                },
            ),
        ]
        issues = check_profile_validation(chunks, profile)
        assert len(issues) >= 1


# ── Full Validation Suite Tests ───────────────────────────────────


class TestRunValidationSuite:
    """Test the complete validation suite."""

    def test_returns_validation_report(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [
            _make_chunk(
                text="(1) First step.\n(2) Second step.",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": [],
                },
            ),
        ]
        report = run_validation_suite(chunks, profile)
        assert isinstance(report, ValidationReport)

    def test_report_has_total_chunks(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [_make_chunk() for _ in range(5)]
        report = run_validation_suite(chunks, profile)
        assert report.total_chunks == 5

    def test_report_lists_checks_run(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [_make_chunk()]
        report = run_validation_suite(chunks, profile)
        assert len(report.checks_run) >= 7  # All 7 checks

    def test_clean_chunks_pass(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        text = "Word " * 500
        chunks = [
            _make_chunk(
                text=text,
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": [],
                },
            ),
        ]
        report = run_validation_suite(chunks, profile)
        assert report.error_count == 0

    def test_report_error_count(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [_make_chunk(metadata={})]  # Missing all required metadata
        report = run_validation_suite(chunks, profile)
        assert report.error_count > 0

    def test_report_passed_property(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        chunks = [_make_chunk(metadata={})]
        report = run_validation_suite(chunks, profile)
        assert report.passed is False


# ── Qualified Cross-Reference Tests ──────────────────────────────


class TestQualifiedCrossRefs:
    """Test namespace-qualified cross-reference validation."""

    def test_cross_ref_qualified_resolves(self):
        """A qualified cross-reference that matches a chunk ID prefix produces no error."""
        chunks = [
            _make_chunk(
                chunk_id="xj-1999::0::SP",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": ["xj-1999::7"],
                },
            ),
            _make_chunk(
                chunk_id="xj-1999::7::cooling",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "7",
                    "content_type": "section",
                    "cross_references": [],
                },
            ),
        ]
        issues = check_cross_ref_validity(chunks)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], f"Qualified ref 'xj-1999::7' should resolve via prefix: {errors}"

    def test_cross_ref_bare_id_fails(self):
        """A bare (unqualified) cross-reference that doesn't match any chunk ID produces an error."""
        chunks = [
            _make_chunk(
                chunk_id="xj-1999::0::SP",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": ["7"],
                },
            ),
        ]
        issues = check_cross_ref_validity(chunks)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1, "Bare ref '7' should NOT resolve and should produce an error"

    def test_cross_ref_suffix_segment_resolves(self):
        """A partial-path ref resolves via suffix-segment when the suffix
        appears as a complete segment in a hierarchical chunk ID."""
        chunks = [
            _make_chunk(
                chunk_id="tm9-8014-m38a1::0::SP",
                text="See paragraph 69.",
                metadata={
                    "manual_id": "tm9-8014-m38a1",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": ["tm9-8014-m38a1::69"],
                },
            ),
            _make_chunk(
                chunk_id="tm9-8014-m38a1::1::IV::69",
                text="Paragraph 69 content here.",
                metadata={
                    "manual_id": "tm9-8014-m38a1",
                    "level1_id": "1",
                    "content_type": "procedure",
                    "cross_references": [],
                },
            ),
        ]
        issues = check_cross_ref_validity(chunks)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], (
            f"Ref 'tm9-8014-m38a1::69' should resolve via suffix-segment to "
            f"'tm9-8014-m38a1::1::IV::69': {errors}"
        )

    def test_cross_ref_suffix_segment_no_partial_digit_match(self):
        """Suffix-segment matching must not match partial digits —
        '::69' must NOT match '::169' (only full segment boundaries)."""
        chunks = [
            _make_chunk(
                chunk_id="tm9-8014-m38a1::0::SP",
                text="See paragraph 69.",
                metadata={
                    "manual_id": "tm9-8014-m38a1",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": ["tm9-8014-m38a1::69"],
                },
            ),
            # Chunk ID ends with ::169, NOT ::69 — should NOT match
            _make_chunk(
                chunk_id="tm9-8014-m38a1::1::IV::169",
                text="Paragraph 169 content here.",
                metadata={
                    "manual_id": "tm9-8014-m38a1",
                    "level1_id": "1",
                    "content_type": "procedure",
                    "cross_references": [],
                },
            ),
        ]
        issues = check_cross_ref_validity(chunks)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1, (
            "Ref 'tm9-8014-m38a1::69' must NOT match chunk '::169' (partial digit)"
        )

    def test_cross_ref_suffix_segment_no_prefix_digit_match(self):
        """Suffix-segment matching must not match when the suffix is a prefix
        of another segment — '::69' must NOT match '::690'."""
        chunks = [
            _make_chunk(
                chunk_id="tm9-8014-m38a1::0::SP",
                text="See paragraph 69.",
                metadata={
                    "manual_id": "tm9-8014-m38a1",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": ["tm9-8014-m38a1::69"],
                },
            ),
            # Chunk ID ends with ::690, NOT ::69 — should NOT match
            _make_chunk(
                chunk_id="tm9-8014-m38a1::1::IV::690",
                text="Paragraph 690 content here.",
                metadata={
                    "manual_id": "tm9-8014-m38a1",
                    "level1_id": "1",
                    "content_type": "procedure",
                    "cross_references": [],
                },
            ),
        ]
        issues = check_cross_ref_validity(chunks)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 1, (
            "Ref 'tm9-8014-m38a1::69' must NOT match chunk '::690' (prefix digit)"
        )

    def test_cross_ref_existing_strategies_no_regression(self):
        """XJ cross-refs that resolve via existing strategies (exact, prefix,
        string-prefix) must still work after adding suffix-segment matching."""
        chunks = [
            # Chunk with refs that resolve via strategies 1-3
            _make_chunk(
                chunk_id="xj-1999::0::SP",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": [
                        "xj-1999::8A",         # strategy 1: exact chunk ID
                        "xj-1999::8",           # strategy 2/3: prefix match
                    ],
                },
            ),
            _make_chunk(
                chunk_id="xj-1999::8A",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "8A",
                    "content_type": "procedure",
                    "cross_references": [],
                },
            ),
            _make_chunk(
                chunk_id="xj-1999::8A::cooling",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "8A",
                    "content_type": "section",
                    "cross_references": [],
                },
            ),
        ]
        issues = check_cross_ref_validity(chunks)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == [], (
            f"Existing XJ cross-ref resolution strategies must not regress: {errors}"
        )

    def test_cross_ref_skipped_section_is_warning(self, xj_profile_path):
        """A cross-reference to a skipped section produces a warning, not an error."""
        profile = load_profile(xj_profile_path)
        # xj profile has skip_sections: ["8W"]
        chunks = [
            _make_chunk(
                chunk_id="xj-1999::0::SP",
                metadata={
                    "manual_id": "xj-1999",
                    "level1_id": "0",
                    "content_type": "procedure",
                    "cross_references": ["xj-1999::8W"],
                },
            ),
        ]
        issues = check_cross_ref_validity(chunks, profile)
        assert len(issues) >= 1, "Should produce at least one issue for unresolved ref"
        for issue in issues:
            assert issue.severity == "warning", (
                f"Skipped-section ref should be warning, not {issue.severity}"
            )
            assert "skipped section" in issue.message
            assert issue.details["skipped"] is True
