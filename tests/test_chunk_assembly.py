"""Tests for the chunk assembly engine — universal boundary rules R1-R8 and metadata."""

from __future__ import annotations

import pytest

from pipeline.chunk_assembly import (
    TOKEN_ESTIMATE_FACTOR,
    Chunk,
    apply_rule_r1_primary_unit,
    apply_rule_r2_size_targets,
    apply_rule_r3_never_split_steps,
    apply_rule_r4_safety_attachment,
    apply_rule_r5_table_integrity,
    apply_rule_r6_merge_small,
    apply_rule_r7_crossref_merge,
    apply_rule_r8_figure_continuity,
    assemble_chunks,
    compose_hierarchical_header,
    count_tokens,
    detect_safety_callouts,
    detect_step_sequences,
    detect_tables,
    tag_vehicle_applicability,
)
from pipeline.profile import load_profile
from pipeline.structural_parser import Manifest, ManifestEntry


# ── Token Counting Tests ──────────────────────────────────────────


class TestCountTokens:
    """Test token count estimation."""

    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_single_word(self):
        assert count_tokens("hello") == 1

    def test_sentence(self):
        count = count_tokens("The quick brown fox jumps over the lazy dog")
        assert count == 9

    def test_multiline_text(self):
        text = "Line one with words.\nLine two with more words."
        count = count_tokens(text)
        assert count >= 8

    def test_scaling_factor_applied(self, monkeypatch):
        """Verify TOKEN_ESTIMATE_FACTOR scales the count."""
        import pipeline.chunk_assembly as ca

        text = "one two three four five"
        baseline = count_tokens(text)
        assert baseline == 5

        monkeypatch.setattr(ca, "TOKEN_ESTIMATE_FACTOR", 2.0)
        scaled = count_tokens(text)
        assert scaled == baseline * 2

    def test_default_scaling_factor_is_one(self):
        assert TOKEN_ESTIMATE_FACTOR == 1.0


# ── Hierarchical Header Tests ─────────────────────────────────────


class TestComposeHierarchicalHeader:
    """Test hierarchical header string composition."""

    def test_xj_header(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        header = compose_hierarchical_header(
            profile,
            ["Lubrication and Maintenance", "Service Procedures", "Jump Starting Procedure"],
        )
        assert "1999 Jeep Cherokee" in header
        assert "Lubrication and Maintenance" in header
        assert "Jump Starting Procedure" in header

    def test_header_uses_pipe_separator(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        header = compose_hierarchical_header(
            profile,
            ["Lubrication and Maintenance", "Service Procedures"],
        )
        assert " | " in header

    def test_cj_header(self, cj_profile_path):
        profile = load_profile(cj_profile_path)
        header = compose_hierarchical_header(
            profile,
            ["Lubrication", "B-4. Engine Lubrication"],
        )
        assert "Jeep Universal" in header or "1953-71" in header

    def test_tm9_header(self, tm9_profile_path):
        profile = load_profile(tm9_profile_path)
        header = compose_hierarchical_header(
            profile,
            ["Operating Instructions", "Section III", "42. Starting the Engine"],
        )
        assert "TM 9-8014" in header or "M38A1" in header


# ── Step Sequence Detection Tests ─────────────────────────────────


class TestDetectStepSequences:
    """Test detection of numbered/lettered step sequences."""

    def test_detects_numbered_steps(self):
        text = "Intro text.\n(1) First step.\n(2) Second step.\n(3) Third step.\nEnd."
        sequences = detect_step_sequences(text, [r"^\((\d+)\)\s"])
        assert len(sequences) >= 1
        start, end = sequences[0]
        assert start >= 1  # After intro
        assert end >= 3  # Covers all three steps

    def test_detects_lettered_steps(self):
        text = "Intro text.\na. First step.\nb. Second step.\nc. Third step.\nEnd."
        sequences = detect_step_sequences(text, [r"^([a-z])\.\s"])
        assert len(sequences) >= 1

    def test_no_steps_returns_empty(self):
        text = "Just regular text.\nNo steps here."
        sequences = detect_step_sequences(text, [r"^\((\d+)\)\s"])
        assert sequences == []

    def test_multiple_step_sequences(self):
        text = (
            "Procedure A:\n(1) Step.\n(2) Step.\n"
            "Procedure B:\n(1) Step.\n(2) Step.\n"
        )
        sequences = detect_step_sequences(text, [r"^\((\d+)\)\s"])
        assert len(sequences) >= 2


# ── Safety Callout Detection Tests ────────────────────────────────


class TestDetectSafetyCallouts:
    """Test safety callout detection using profile patterns."""

    def test_detects_xj_warning(self, xj_profile_path, sample_safety_callout_text):
        profile = load_profile(xj_profile_path)
        callouts = detect_safety_callouts(sample_safety_callout_text, profile)
        levels = [c["level"] for c in callouts]
        assert "warning" in levels

    def test_detects_xj_caution(self, xj_profile_path, sample_safety_callout_text):
        profile = load_profile(xj_profile_path)
        callouts = detect_safety_callouts(sample_safety_callout_text, profile)
        levels = [c["level"] for c in callouts]
        assert "caution" in levels

    def test_no_callouts_in_plain_text(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        callouts = detect_safety_callouts("Just regular text here.", profile)
        assert callouts == []

    def test_tm9_caution_detection(self, tm9_profile_path, tm9_sample_page_text):
        profile = load_profile(tm9_profile_path)
        callouts = detect_safety_callouts(tm9_sample_page_text, profile)
        levels = [c["level"] for c in callouts]
        assert "caution" in levels

    def test_tm9_note_detection(self, tm9_profile_path, tm9_sample_page_text):
        profile = load_profile(tm9_profile_path)
        callouts = detect_safety_callouts(tm9_sample_page_text, profile)
        levels = [c["level"] for c in callouts]
        assert "note" in levels


# ── Table Detection Tests ─────────────────────────────────────────


class TestDetectTables:
    """Test specification table boundary detection."""

    def test_detects_spec_table(self, sample_spec_table):
        tables = detect_tables(sample_spec_table)
        assert len(tables) >= 1

    def test_no_table_in_prose(self):
        text = "Regular paragraph text without any table structure."
        tables = detect_tables(text)
        assert tables == []


# ── Rule R1: Primary Chunk Unit ───────────────────────────────────


class TestRuleR1PrimaryUnit:
    """R1: One complete procedure/topic at the lowest meaningful hierarchy level."""

    def test_single_procedure_stays_whole(self, sample_manifest_entry, xj_sample_page_text):
        from pipeline.structural_parser import ManifestEntry

        entry = ManifestEntry(**sample_manifest_entry)
        chunks = apply_rule_r1_primary_unit(xj_sample_page_text, entry)
        assert len(chunks) >= 1


# ── Rule R2: Size Targets ─────────────────────────────────────────


class TestRuleR2SizeTargets:
    """R2: Min 200, target 500-1500, max 2000 tokens."""

    def test_small_chunk_unchanged(self):
        chunks = ["A small chunk with about fifty words. " * 10]
        result = apply_rule_r2_size_targets(chunks)
        assert len(result) >= 1

    def test_oversized_chunk_gets_split(self):
        huge_text = "Word " * 2500  # Way over 2000 tokens
        result = apply_rule_r2_size_targets([huge_text])
        assert len(result) > 1
        for chunk in result:
            assert count_tokens(chunk) <= 2000

    def test_normal_sized_chunk_unchanged(self):
        normal_text = "Word " * 800  # Within target range
        result = apply_rule_r2_size_targets([normal_text])
        assert len(result) == 1


# ── Rule R3: Never Split Steps ────────────────────────────────────


class TestRuleR3NeverSplitSteps:
    """R3: Numbered/lettered step sequences stay in one chunk."""

    def test_step_sequence_stays_together(self, sample_step_sequence):
        result = apply_rule_r3_never_split_steps(
            sample_step_sequence, [r"^\((\d+)\)\s"]
        )
        # All 8 steps should be in one chunk
        for chunk in result:
            if "(1)" in chunk:
                assert "(8)" in chunk

    def test_long_step_sequence_not_split(self):
        steps = "\n".join(f"({i}) Step {i} with some extra text." for i in range(1, 21))
        result = apply_rule_r3_never_split_steps(steps, [r"^\((\d+)\)\s"])
        # Even if long, steps stay together
        step_chunks = [c for c in result if "(1)" in c]
        assert len(step_chunks) == 1
        assert "(20)" in step_chunks[0]


# ── Rule R4: Safety Callout Attachment ────────────────────────────


class TestRuleR4SafetyAttachment:
    """R4: Safety callouts stay with their governed procedure."""

    def test_warning_stays_with_procedure(
        self, xj_profile_path, sample_safety_callout_text
    ):
        profile = load_profile(xj_profile_path)
        chunks = [sample_safety_callout_text]
        result = apply_rule_r4_safety_attachment(chunks, profile)
        # WARNING and the steps should be in the same chunk
        for chunk in result:
            if "WARNING:" in chunk:
                assert "(1)" in chunk or "(2)" in chunk

    def test_caution_stays_with_procedure(
        self, xj_profile_path, sample_safety_callout_text
    ):
        profile = load_profile(xj_profile_path)
        chunks = [sample_safety_callout_text]
        result = apply_rule_r4_safety_attachment(chunks, profile)
        for chunk in result:
            if "CAUTION:" in chunk:
                assert "(1)" in chunk or "(2)" in chunk


# ── Rule R5: Table Integrity ──────────────────────────────────────


class TestRuleR5TableIntegrity:
    """R5: Specification tables are never split."""

    def test_spec_table_stays_whole(self, sample_spec_table):
        result = apply_rule_r5_table_integrity([sample_spec_table])
        # Table should be in a single chunk
        assert len(result) == 1
        assert "2.5L I4" in result[0]
        assert "4.0L I6" in result[0]

    def test_oversized_table_overrides_size_ceiling(self):
        big_table = "SPECIFICATIONS\n" + "\n".join(
            f"Item {i} .............. Value {i}" for i in range(200)
        )
        result = apply_rule_r5_table_integrity([big_table])
        # Even if over 2000 tokens, table stays whole
        assert len(result) == 1


# ── Rule R6: Merge Small Chunks ───────────────────────────────────


class TestRuleR6MergeSmall:
    """R6: Chunks under min_tokens merge with next sibling or parent."""

    def test_small_chunks_merged(self):
        chunks = ["Short.", "Also short.", "A longer chunk with sufficient content. " * 20]
        result = apply_rule_r6_merge_small(chunks, min_tokens=200)
        assert len(result) < len(chunks)

    def test_normal_chunks_unchanged(self):
        chunks = ["Sufficient content. " * 50, "More content. " * 50]
        result = apply_rule_r6_merge_small(chunks, min_tokens=200)
        assert len(result) == 2

    def test_single_small_chunk_stays(self):
        result = apply_rule_r6_merge_small(["Tiny."], min_tokens=200)
        assert len(result) == 1


# ── Rule R7: Cross-Ref Merge ──────────────────────────────────────


class TestRuleR7CrossRefMerge:
    """R7: Cross-ref-only sections merge into parent."""

    def test_crossref_only_section_merged(self, sample_crossref_only_section):
        chunks = ["Parent content with procedures.", sample_crossref_only_section]
        result = apply_rule_r7_crossref_merge(
            chunks, [r"Refer to Group \d+", r"Refer to Group \d+"]
        )
        assert len(result) < len(chunks)

    def test_section_with_real_content_not_merged(self):
        chunks = [
            "Parent content.",
            "Real procedures here.\n(1) Do something.\nRefer to Group 5.",
        ]
        result = apply_rule_r7_crossref_merge(chunks, [r"Refer to Group \d+"])
        # The second chunk has real content, should not be merged
        assert len(result) == 2


# ── Rule R8: Figure Reference Continuity ──────────────────────────


class TestRuleR8FigureContinuity:
    """R8: Figure references stay with the text describing them."""

    def test_figure_ref_stays_with_text(self):
        chunks = [
            "Remove the bolt as shown (Fig. 1).",
            "Install the new gasket.",
        ]
        result = apply_rule_r8_figure_continuity(chunks, r"\(Fig\.\s+\d+\)")
        # Fig. 1 reference should stay with its describing text
        for chunk in result:
            if "(Fig. 1)" in chunk:
                assert "bolt" in chunk


# ── Vehicle Applicability Tagging Tests ───────────────────────────


class TestTagVehicleApplicability:
    """Test vehicle/engine/drivetrain applicability tagging."""

    def test_xj_all_applicability(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        tags = tag_vehicle_applicability(
            "General maintenance procedure for all models.", profile
        )
        assert tags["vehicle_models"] == ["all"] or "Cherokee XJ" in tags["vehicle_models"]

    def test_cj5_specific_mention(self, cj_profile_path):
        profile = load_profile(cj_profile_path)
        tags = tag_vehicle_applicability(
            "On CJ-5 models, the carburetor is located differently.", profile
        )
        assert "CJ-5" in tags["vehicle_models"]

    def test_engine_specific_mention(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        tags = tag_vehicle_applicability(
            "The 4.0L I6 engine requires 6 quarts of oil.", profile
        )
        assert any("4.0" in e for e in tags["engine_applicability"])

    def test_drivetrain_mention(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        tags = tag_vehicle_applicability(
            "For 4WD models, check the transfer case fluid.", profile
        )
        assert "4WD" in tags["drivetrain_applicability"]

    def test_no_specific_mention_defaults_to_all(self, xj_profile_path):
        profile = load_profile(xj_profile_path)
        tags = tag_vehicle_applicability(
            "Check the tire pressure regularly.", profile
        )
        assert "all" in tags["engine_applicability"]

    def test_tm9_dual_vehicle_detection(self, tm9_profile_path):
        profile = load_profile(tm9_profile_path)
        tags = tag_vehicle_applicability(
            "The M38A1 utility truck and M170 ambulance share this procedure.", profile
        )
        assert "M38A1" in tags["vehicle_models"]
        assert "M170" in tags["vehicle_models"]


# ── Rule Ordering Guard Tests ────────────────────────────────────


class TestRuleOrdering:
    """Guard tests verifying that rule ordering preserves semantic integrity.

    These tests exercise assemble_chunks() end-to-end to confirm that
    semantic rules (R3, R4) run before size enforcement (R2), keeping
    step sequences and safety callouts attached to their procedures.
    """

    def _make_manifest(self, manual_id: str, num_lines: int) -> Manifest:
        """Build a minimal single-entry Manifest spanning all lines."""
        entry = ManifestEntry(
            chunk_id=f"{manual_id}::proc",
            level=3,
            level_name="procedure",
            title="Test Procedure",
            hierarchy_path=["Test Group", "Test Section", "Test Procedure"],
            content_type="procedure",
            page_range={"start": "1", "end": "1"},
            line_range={"start": 0, "end": num_lines},
            vehicle_applicability=["all"],
            engine_applicability=["all"],
            drivetrain_applicability=["all"],
            has_safety_callouts=[],
            figure_references=[],
            cross_references=[],
            parent_chunk_id=None,
            children=[],
        )
        return Manifest(manual_id=manual_id, entries=[entry])

    def test_safety_callout_not_split_from_procedure(self, xj_profile_path):
        """A WARNING callout must remain in the same chunk as its procedure.

        If R2 ran before R4, the size splitter could place the WARNING
        in one chunk and the procedure steps in another.
        """
        profile = load_profile(xj_profile_path)

        page_text = (
            "WARNING: DO NOT REMOVE THE RADIATOR CAP WHILE THE\n"
            "ENGINE IS HOT. SCALDING COOLANT AND STEAM CAN CAUSE\n"
            "SERIOUS BURNS TO THE SKIN AND EYES.\n"
            "\n"
            "(1) Allow the engine to cool completely.\n"
            "(2) Place a rag over the radiator cap.\n"
            "(3) Slowly rotate the cap to the first stop.\n"
            "(4) Allow residual pressure to escape.\n"
            "(5) Press down and rotate the cap to remove."
        )

        pages = [page_text]
        num_lines = len(page_text.split("\n"))
        manifest = self._make_manifest("xj-1999", num_lines)

        chunks = assemble_chunks(pages, manifest, profile)
        assert len(chunks) >= 1

        # Find the chunk(s) containing the WARNING text
        warning_chunks = [c for c in chunks if "WARNING:" in c.text]
        assert len(warning_chunks) >= 1, "WARNING callout must appear in output"

        # The WARNING and procedure steps must co-exist in the same chunk
        for wc in warning_chunks:
            assert "(1)" in wc.text, (
                "WARNING callout was split from its procedure steps — "
                "R4 (safety attachment) must run before R2 (size targets)"
            )

    def test_step_sequence_preserved_before_size_split(self, xj_profile_path):
        """A numbered step sequence under the size ceiling stays in one chunk.

        If R2 ran before R3, it could split at an arbitrary token boundary
        inside a step sequence, breaking the procedure's logical continuity.
        """
        profile = load_profile(xj_profile_path)

        # Build a 10-step sequence. Each step is ~10 words, so the whole
        # sequence is ~100 words — well under the 2000-token ceiling.
        steps = "\n".join(
            f"({i}) Perform step {i} of the oil change procedure carefully."
            for i in range(1, 11)
        )
        page_text = f"OIL CHANGE PROCEDURE\n\n{steps}"

        pages = [page_text]
        num_lines = len(page_text.split("\n"))
        manifest = self._make_manifest("xj-1999", num_lines)

        chunks = assemble_chunks(pages, manifest, profile)
        assert len(chunks) >= 1

        # Find the chunk that contains step (1)
        step_chunks = [c for c in chunks if "(1)" in c.text]
        assert len(step_chunks) == 1, "Step (1) should appear in exactly one chunk"

        # All 10 steps must be in that same chunk
        the_chunk = step_chunks[0]
        for i in range(1, 11):
            assert f"({i})" in the_chunk.text, (
                f"Step ({i}) was split from the sequence — "
                "R3 (never split steps) must run before R2 (size targets)"
            )
