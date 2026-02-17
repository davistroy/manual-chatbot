"""Tests for the manual profile system — loading, validation, and pattern compilation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.profile import (
    CURRENT_SCHEMA_VERSION,
    GarbageDetectionConfig,
    HierarchyLevel,
    ManualProfile,
    OcrCleanupConfig,
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

    def test_load_xj_profile_schema_version(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.schema_version == "1.0"

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


class TestLoadProfileBoundaryFilters:
    """Test boundary filter configuration loading from profiles."""

    def test_xj_level3_has_min_gap_lines(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        level3 = profile.hierarchy[2]  # level 3 = procedure
        assert level3.min_gap_lines == 2

    def test_xj_level3_has_min_content_words(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        level3 = profile.hierarchy[2]
        assert level3.min_content_words == 5

    def test_xj_level3_has_require_blank_before(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        level3 = profile.hierarchy[2]
        assert level3.require_blank_before is True

    def test_level_without_filters_defaults_min_gap_lines(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        level1 = profile.hierarchy[0]  # level 1 = group, no filter fields in YAML
        assert level1.min_gap_lines == 0

    def test_level_without_filters_defaults_min_content_words(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        level1 = profile.hierarchy[0]
        assert level1.min_content_words == 0

    def test_level_without_filters_defaults_require_blank_before(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        level1 = profile.hierarchy[0]
        assert level1.require_blank_before is False

    def test_cj_levels_all_default_filters(self, cj_profile_path: Path):
        """CJ profile has no filter fields — all levels should use defaults."""
        profile = load_profile(cj_profile_path)
        for level in profile.hierarchy:
            assert level.min_gap_lines == 0
            assert level.min_content_words == 0
            assert level.require_blank_before is False

    def test_tm9_levels_all_default_filters(self, tm9_profile_path: Path):
        """TM9 profile has no filter fields — all levels should use defaults."""
        profile = load_profile(tm9_profile_path)
        for level in profile.hierarchy:
            assert level.min_gap_lines == 0
            assert level.min_content_words == 0
            assert level.require_blank_before is False

    def test_profile_with_filters_still_validates(self, xj_profile_path: Path):
        """Profile with boundary filter fields should pass validation."""
        profile = load_profile(xj_profile_path)
        errors = validate_profile(profile)
        assert errors == []


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
        assert profile.ocr_cleanup.quality_estimate == "fair"

    def test_xj_known_substitutions(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        subs = profile.ocr_cleanup.known_substitutions
        assert len(subs) == 2
        assert subs[0]["from"] == "IJURY"
        assert subs[0]["to"] == "INJURY"

    def test_tm9_poor_quality(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        assert profile.ocr_cleanup.quality_estimate == "poor"

    def test_tm9_garbage_threshold(self, tm9_profile_path: Path):
        profile = load_profile(tm9_profile_path)
        assert profile.ocr_cleanup.garbage_detection.threshold == 0.3


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


class TestSchemaVersion:
    """Test schema version validation."""

    def test_missing_schema_version_is_error(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.schema_version = ""
        errors = validate_profile(profile)
        assert any("schema_version" in e for e in errors)

    def test_wrong_schema_version_is_error(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.schema_version = "2.0"
        errors = validate_profile(profile)
        assert any("schema_version" in e for e in errors)
        assert any("2.0" in e for e in errors)

    def test_correct_schema_version_passes(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.schema_version == CURRENT_SCHEMA_VERSION
        errors = validate_profile(profile)
        assert not any("schema_version" in e for e in errors)

    def test_all_fixtures_have_schema_version(
        self, xj_profile_path: Path, cj_profile_path: Path, tm9_profile_path: Path
    ):
        for path in [xj_profile_path, cj_profile_path, tm9_profile_path]:
            profile = load_profile(path)
            assert profile.schema_version == CURRENT_SCHEMA_VERSION


class TestExpandedValidation:
    """Test expanded validation checks (regex, substitutions, hierarchy, callouts)."""

    def test_invalid_regex_in_hierarchy_id_pattern(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.hierarchy[0].id_pattern = "[invalid("
        errors = validate_profile(profile)
        assert any("id_pattern at hierarchy level 1" in e for e in errors)

    def test_invalid_regex_in_step_pattern(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.step_patterns = ["[bad("]
        errors = validate_profile(profile)
        assert any("step_patterns[0]" in e for e in errors)

    def test_invalid_regex_in_safety_callout(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.safety_callouts[0].pattern = "[bad("
        errors = validate_profile(profile)
        assert any("safety callout pattern" in e for e in errors)

    def test_valid_patterns_pass(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        errors = validate_profile(profile)
        assert not any("Invalid" in e for e in errors)

    def test_malformed_substitution_missing_from(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.ocr_cleanup.known_substitutions = [{"to": "INJURY"}]
        errors = validate_profile(profile)
        assert any("known_substitutions[0]" in e for e in errors)

    def test_malformed_substitution_missing_to(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.ocr_cleanup.known_substitutions = [{"from": "IJURY"}]
        errors = validate_profile(profile)
        assert any("known_substitutions[0]" in e for e in errors)

    def test_valid_substitutions_pass(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        errors = validate_profile(profile)
        assert not any("known_substitutions" in e for e in errors)

    def test_non_sequential_hierarchy_levels(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.hierarchy[1].level = 5  # gap: 1, 5, 3, 4
        errors = validate_profile(profile)
        assert any("sequential" in e.lower() for e in errors)

    def test_sequential_hierarchy_passes(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        errors = validate_profile(profile)
        assert not any("sequential" in e.lower() for e in errors)

    def test_invalid_safety_callout_level(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.safety_callouts.append(SafetyCallout(level="danger", pattern="^DANGER:", style="block"))
        errors = validate_profile(profile)
        assert any("callout level 'danger'" in e for e in errors)

    def test_invalid_safety_callout_style(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        profile.safety_callouts.append(SafetyCallout(level="warning", pattern="^WARNING:", style="floating"))
        errors = validate_profile(profile)
        assert any("callout style 'floating'" in e for e in errors)

    def test_valid_callout_levels_and_styles_pass(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        errors = validate_profile(profile)
        assert not any("callout level" in e for e in errors)
        assert not any("callout style" in e for e in errors)


# ── Skip Sections Tests ───────────────────────────────────────────


class TestLoadProfileSkipSections:
    """Test skip_sections loading from YAML profiles."""

    def test_xj_skip_sections_loaded(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert profile.skip_sections == ["8W"]

    def test_skip_sections_defaults_to_empty_list(self, cj_profile_path: Path):
        profile = load_profile(cj_profile_path)
        assert profile.skip_sections == []

    def test_skip_sections_is_list_of_strings(self, xj_profile_path: Path):
        profile = load_profile(xj_profile_path)
        assert isinstance(profile.skip_sections, list)
        for item in profile.skip_sections:
            assert isinstance(item, str)


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
