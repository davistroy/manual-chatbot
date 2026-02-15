"""Tests for the manual profile system — loading, validation, and pattern compilation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.profile import (
    HierarchyLevel,
    ManualProfile,
    SafetyCallout,
    Vehicle,
    VehicleEngine,
    compile_patterns,
    load_profile,
    validate_profile,
)


# ── Loading Tests ─────────────────────────────────────────────────


class TestLoadProfile:
    """Test profile loading from YAML files."""

    def test_load_xj_profile_returns_manual_profile(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert isinstance(profile, ManualProfile)

    def test_load_xj_profile_manual_id(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.manual_id == "xj-1999"

    def test_load_xj_profile_title(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.manual_title == "1999 Jeep Cherokee (XJ) Factory Service Manual"

    def test_load_xj_profile_source_format(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.source_format == "pdf-ocr"

    def test_load_cj_profile_manual_id(self, cj_profile_path: Path):
        profile = load_profile(cj_profile_path)
        assert profile.manual_id == "cj-universal-53-71"

    def test_load_tm9_profile_manual_id(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        assert profile.manual_id == "tm9-8014-m38a1"

    def test_load_nonexistent_raises_file_not_found(self, nonexistent_profile_path: Path):
        with pytest.raises(FileNotFoundError):
            load_profile(nonexistent_profile_path)

    def test_load_accepts_string_path(self, xj_profile_path: Path):
        profile = load_profile(str(xj_profile_path))
        assert profile.manual_id == "xj-1999"


class TestLoadProfileVehicles:
    """Test vehicle data loading from profiles."""

    def test_xj_has_one_vehicle(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert len(profile.vehicles) == 1

    def test_xj_vehicle_model(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.vehicles[0].model == "Cherokee XJ"

    def test_xj_vehicle_years(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.vehicles[0].years == "1999"

    def test_xj_vehicle_drive_types(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.vehicles[0].drive_type == ["2WD", "4WD"]

    def test_xj_has_three_engines(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert len(profile.vehicles[0].engines) == 3

    def test_xj_engine_aliases(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        engine = profile.vehicles[0].engines[1]  # 4.0L I6
        assert "4.0L" in engine.aliases
        assert "inline 6" in engine.aliases

    def test_xj_has_two_transmissions(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert len(profile.vehicles[0].transmissions) == 2

    def test_cj_has_multiple_vehicles(self, cj_profile_path: Path):
        profile = load_profile(cj_profile_path)
        assert len(profile.vehicles) == 3  # CJ-3B, CJ-5, DJ-5

    def test_cj_vehicle_models(self, cj_profile_path: Path):
        profile = load_profile(cj_profile_path)
        models = [v.model for v in profile.vehicles]
        assert "CJ-3B" in models
        assert "CJ-5" in models
        assert "DJ-5" in models

    def test_tm9_has_two_vehicles(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        assert len(profile.vehicles) == 2

    def test_tm9_vehicle_models(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        models = [v.model for v in profile.vehicles]
        assert "M38A1" in models
        assert "M170" in models


class TestLoadProfileHierarchy:
    """Test hierarchy structure loading from profiles."""

    def test_xj_has_four_hierarchy_levels(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert len(profile.hierarchy) == 4

    def test_xj_level1_is_group(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.hierarchy[0].name == "group"
        assert profile.hierarchy[0].level == 1

    def test_xj_level1_has_known_ids(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        known_ids = profile.hierarchy[0].known_ids
        assert len(known_ids) > 0
        ids = [k["id"] for k in known_ids]
        assert "0" in ids
        assert "9" in ids

    def test_cj_level1_is_section(self, cj_profile_path: Path):
        profile = load_profile(cj_profile_path)
        assert profile.hierarchy[0].name == "section"

    def test_tm9_level1_is_chapter(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        assert profile.hierarchy[0].name == "chapter"

    def test_xj_hierarchy_id_patterns_are_strings(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        for level in profile.hierarchy:
            if level.id_pattern is not None:
                assert isinstance(level.id_pattern, str)


class TestLoadProfileSafetyCallouts:
    """Test safety callout loading from profiles."""

    def test_xj_has_three_callout_levels(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert len(profile.safety_callouts) == 3

    def test_xj_warning_pattern(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        warning = next(c for c in profile.safety_callouts if c.level == "warning")
        assert warning.pattern == "^WARNING:"
        assert warning.style == "block"

    def test_cj_has_no_warning_level(self, cj_profile_path: Path):
        profile = load_profile(cj_profile_path)
        levels = [c.level for c in profile.safety_callouts]
        assert "warning" not in levels

    def test_tm9_has_all_three_levels(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        levels = [c.level for c in profile.safety_callouts]
        assert "warning" in levels
        assert "caution" in levels
        assert "note" in levels


class TestLoadProfileOCRCleanup:
    """Test OCR cleanup config loading from profiles."""

    def test_xj_ocr_quality_estimate(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.ocr_cleanup["quality_estimate"] == "fair"

    def test_xj_known_substitutions(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        subs = profile.ocr_cleanup["known_substitutions"]
        assert len(subs) == 2
        assert subs[0]["from"] == "IJURY"
        assert subs[0]["to"] == "INJURY"

    def test_tm9_poor_quality(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        assert profile.ocr_cleanup["quality_estimate"] == "poor"

    def test_tm9_garbage_threshold(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        assert profile.ocr_cleanup["garbage_detection"]["threshold"] == 0.3


# ── Validation Tests ──────────────────────────────────────────────


class TestValidateProfile:
    """Test profile validation for completeness and correctness."""

    def test_valid_xj_profile_passes(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        errors = validate_profile(profile)
        assert errors == []

    def test_valid_cj_profile_passes(self, cj_profile_path: Path):
        profile = load_profile(cj_profile_path)
        errors = validate_profile(profile)
        assert errors == []

    def test_valid_tm9_profile_passes(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        errors = validate_profile(profile)
        assert errors == []

    def test_empty_manual_id_is_error(self, invalid_profile_path: Path):
        profile = load_profile(invalid_profile_path)
        errors = validate_profile(profile)
        assert any("manual_id" in e or "manual_title" in e for e in errors)

    def test_empty_vehicles_is_error(self, invalid_profile_path: Path):
        profile = load_profile(invalid_profile_path)
        errors = validate_profile(profile)
        assert any("vehicle" in e.lower() for e in errors)

    def test_empty_hierarchy_is_error(self, invalid_profile_path: Path):
        profile = load_profile(invalid_profile_path)
        errors = validate_profile(profile)
        assert any("hierarchy" in e.lower() for e in errors)

    def test_invalid_source_format_is_error(self, invalid_profile_path: Path):
        profile = load_profile(invalid_profile_path)
        errors = validate_profile(profile)
        assert any("source_format" in e or "format" in e.lower() for e in errors)


# ── Pattern Compilation Tests ─────────────────────────────────────


class TestCompilePatterns:
    """Test regex pattern pre-compilation from profiles."""

    def test_compiles_hierarchy_patterns(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        patterns = compile_patterns(profile)
        assert "hierarchy" in patterns

    def test_compiles_step_patterns(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        patterns = compile_patterns(profile)
        assert "step_patterns" in patterns

    def test_compiles_safety_patterns(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        patterns = compile_patterns(profile)
        assert "safety_callouts" in patterns

    def test_compiled_patterns_are_regex(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        patterns = compile_patterns(profile)
        for category, pattern_list in patterns.items():
            for p in pattern_list:
                assert isinstance(p, re.Pattern), (
                    f"Pattern in {category} is not compiled: {p}"
                )

    def test_xj_step_pattern_matches_numbered_steps(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        patterns = compile_patterns(profile)
        step_patterns = patterns["step_patterns"]
        assert any(p.match("(1) First step") for p in step_patterns)
        assert any(p.match("(2) Second step") for p in step_patterns)

    def test_cj_step_pattern_matches_lettered_steps(self, cj_profile_path: Path):
        profile = load_profile(cj_profile_path)
        patterns = compile_patterns(profile)
        step_patterns = patterns["step_patterns"]
        assert any(p.match("a. First step") for p in step_patterns)
        assert any(p.match("b. Second step") for p in step_patterns)

    def test_xj_safety_pattern_matches_warning(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        patterns = compile_patterns(profile)
        safety_patterns = patterns["safety_callouts"]
        assert any(p.match("WARNING: Do not proceed") for p in safety_patterns)

    def test_tm9_hierarchy_pattern_matches_chapter(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        patterns = compile_patterns(profile)
        hierarchy_patterns = patterns["hierarchy"]
        assert any(p.match("CHAPTER 3") for p in hierarchy_patterns)
