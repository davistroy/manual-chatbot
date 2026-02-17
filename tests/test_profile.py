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

    def test_regex_substitutions_defaults_to_empty_list(self, xj_profile_path: Path):
        """Profiles without regex_substitutions should default to empty list."""
        profile = load_profile(xj_profile_path)
        assert profile.ocr_cleanup.regex_substitutions == []

    def test_regex_substitutions_loaded_from_yaml(self, tmp_path: Path):
        """Regex substitutions are correctly loaded from YAML."""
        yaml_content = """\
schema_version: "1.0"
manual_id: "test-regex"
manual_title: "Test Regex Substitutions"
source_url: "https://example.com/test.pdf"
source_format: "pdf-ocr"
vehicles:
  - model: "Test"
    years: "2000"
    drive_type: ["2WD"]
structure:
  hierarchy:
    - level: 1
      name: "chapter"
      id_pattern: "^CHAPTER (\\\\d+)"
      title_pattern: null
safety_callouts: []
content_types: {}
ocr_cleanup:
  quality_estimate: "poor"
  regex_substitutions:
    - { pattern: "\\\\bZn", replacement: "In" }
    - { pattern: "CHAPTEa", replacement: "CHAPTER" }
variants: {}
"""
        p = tmp_path / "test_regex.yaml"
        p.write_text(yaml_content, encoding="utf-8")
        profile = load_profile(p)
        assert len(profile.ocr_cleanup.regex_substitutions) == 2
        assert profile.ocr_cleanup.regex_substitutions[0]["pattern"] == "\\bZn"
        assert profile.ocr_cleanup.regex_substitutions[0]["replacement"] == "In"


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

    def test_invalid_regex_substitution_pattern(self, xj_profile_path: Path):
        """Invalid regex in regex_substitutions raises validation error."""
        profile = load_profile(xj_profile_path)
        profile.ocr_cleanup.regex_substitutions = [
            {"pattern": "[invalid(", "replacement": "fixed"}
        ]
        errors = validate_profile(profile)
        assert any("regex_substitutions[0]" in e for e in errors)

    def test_regex_substitution_missing_pattern_key(self, xj_profile_path: Path):
        """regex_substitutions entry missing 'pattern' key raises validation error."""
        profile = load_profile(xj_profile_path)
        profile.ocr_cleanup.regex_substitutions = [
            {"replacement": "fixed"}
        ]
        errors = validate_profile(profile)
        assert any("regex_substitutions[0]" in e for e in errors)

    def test_regex_substitution_missing_replacement_key(self, xj_profile_path: Path):
        """regex_substitutions entry missing 'replacement' key raises validation error."""
        profile = load_profile(xj_profile_path)
        profile.ocr_cleanup.regex_substitutions = [
            {"pattern": r"\bZn"}
        ]
        errors = validate_profile(profile)
        assert any("regex_substitutions[0]" in e for e in errors)

    def test_valid_regex_substitutions_pass(self, xj_profile_path: Path):
        """Valid regex_substitutions produce no validation errors."""
        profile = load_profile(xj_profile_path)
        profile.ocr_cleanup.regex_substitutions = [
            {"pattern": r"\bZn", "replacement": "In"},
            {"pattern": r"CHAPTEa", "replacement": "CHAPTER"},
        ]
        errors = validate_profile(profile)
        assert not any("regex_substitutions" in e for e in errors)

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


# ── Production Profile Regression Tests ──────────────────────────


PRODUCTION_PROFILE_PATH = Path(__file__).parent.parent / "profiles" / "xj-1999.yaml"


class TestProductionXjProfile:
    """Integration tests for the production XJ profile (profiles/xj-1999.yaml).

    These tests ensure the production profile remains loadable, valid, and
    structurally correct across code changes.
    """

    def test_production_profile_loads(self):
        profile = load_profile(PRODUCTION_PROFILE_PATH)
        assert isinstance(profile, ManualProfile)
        assert profile.manual_id == "xj-1999"

    def test_production_profile_validates_no_errors(self):
        profile = load_profile(PRODUCTION_PROFILE_PATH)
        errors = validate_profile(profile)
        assert errors == [], f"Validation errors: {errors}"

    def test_production_profile_all_patterns_compile(self):
        profile = load_profile(PRODUCTION_PROFILE_PATH)
        patterns = compile_patterns(profile)
        # Every category should contain compiled re.Pattern objects
        for category, pattern_list in patterns.items():
            for p in pattern_list:
                assert isinstance(p, re.Pattern), (
                    f"Pattern in {category} is not compiled: {p}"
                )

    def test_production_profile_known_ids_count(self):
        profile = load_profile(PRODUCTION_PROFILE_PATH)
        known_ids = profile.hierarchy[0].known_ids
        assert len(known_ids) >= 35, (
            f"Expected >= 35 known_ids, got {len(known_ids)}"
        )

    def test_production_profile_l1_require_known_id(self):
        profile = load_profile(PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[0].require_known_id is True

    def test_production_profile_l3_title_pattern_contains_removal(self):
        profile = load_profile(PRODUCTION_PROFILE_PATH)
        l3 = profile.hierarchy[2]
        assert "REMOVAL" in l3.title_pattern


CJ_PRODUCTION_PROFILE_PATH = Path(__file__).parent.parent / "profiles" / "cj-universal.yaml"


class TestProductionCjProfile:
    """Integration tests for the production CJ profile (profiles/cj-universal.yaml).

    These tests ensure the production profile remains loadable, valid, and
    structurally correct across code changes.
    """

    def test_production_profile_loads(self):
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        assert isinstance(profile, ManualProfile)
        assert profile.manual_id == "cj-universal-53-71"

    def test_production_profile_validates_no_errors(self):
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        errors = validate_profile(profile)
        assert errors == [], f"Validation errors: {errors}"

    def test_production_profile_all_patterns_compile(self):
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        patterns = compile_patterns(profile)
        for category, pattern_list in patterns.items():
            for p in pattern_list:
                assert isinstance(p, re.Pattern), (
                    f"Pattern in {category} is not compiled: {p}"
                )

    def test_production_profile_known_ids_count(self):
        """25 canonical sections plus OCR variant duplicates (D1/Dl, F1/Fl, J1/Jl)."""
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        known_ids = profile.hierarchy[0].known_ids
        # 25 canonical sections + 3 OCR variants = 28
        assert len(known_ids) >= 25, (
            f"Expected >= 25 known_ids, got {len(known_ids)}"
        )

    def test_production_profile_compound_ids_present(self):
        """Compound section IDs (D1, F1, F2, J1) and their OCR variants are present."""
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        ids = {k["id"] for k in profile.hierarchy[0].known_ids}
        # Canonical compound IDs
        assert "D1" in ids or "Dl" in ids, "D1/Dl missing from known_ids"
        assert "F1" in ids or "Fl" in ids, "F1/Fl missing from known_ids"
        assert "F2" in ids, "F2 missing from known_ids"
        assert "J1" in ids or "Jl" in ids, "J1/Jl missing from known_ids"

    def test_production_profile_all_canonical_sections(self):
        """All 25 canonical sections A through U are present."""
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        ids = {k["id"] for k in profile.hierarchy[0].known_ids}
        expected_single = set("ABCDEFGHIJKLMNOPQRSTU")
        missing = expected_single - ids
        assert not missing, f"Missing single-letter sections: {missing}"

    def test_production_profile_l1_require_known_id(self):
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[0].require_known_id is True

    def test_production_profile_collapse_spaced_chars(self):
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        assert profile.ocr_cleanup.collapse_spaced_chars is True

    def test_production_profile_has_regex_substitutions(self):
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        assert len(profile.ocr_cleanup.regex_substitutions) > 0

    def test_production_profile_no_l4_level(self):
        """CJ profile should have no L4 (per plan: step_patterns handle sub-steps)."""
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        assert len(profile.hierarchy) == 3, (
            f"Expected 3 hierarchy levels, got {len(profile.hierarchy)}"
        )

    def test_production_profile_l2_has_filtering(self):
        """L2 should have min_content_words for filtering.

        Note: require_blank_before is false on L2 because the CJ manual
        does not consistently have blank lines before paragraph IDs
        (e.g., "B-66." appears on its own line without preceding blank).
        L1 uses require_blank_before instead to filter running headers.
        """
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        l2 = profile.hierarchy[1]
        assert l2.min_content_words > 0, "L2 should have min_content_words > 0"

    def test_production_profile_l1_has_blank_before_and_gap(self):
        """L1 should use require_blank_before and min_gap_lines to filter running headers."""
        profile = load_profile(CJ_PRODUCTION_PROFILE_PATH)
        l1 = profile.hierarchy[0]
        assert l1.require_blank_before is True, "L1 should require blank before"
        assert l1.min_gap_lines > 0, "L1 should have min_gap_lines > 0"


TM9_8014_PRODUCTION_PROFILE_PATH = Path(__file__).parent.parent / "profiles" / "tm9-8014.yaml"


class TestProductionTm98014Profile:
    """Integration tests for the production TM9-8014 profile (profiles/tm9-8014.yaml).

    These tests ensure the production profile remains loadable, valid, and
    structurally correct across code changes.
    """

    def test_production_profile_loads(self):
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        assert isinstance(profile, ManualProfile)
        assert profile.manual_id == "tm9-8014-m38a1"

    def test_production_profile_validates_no_errors(self):
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        errors = validate_profile(profile)
        assert errors == [], f"Validation errors: {errors}"

    def test_production_profile_all_patterns_compile(self):
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        patterns = compile_patterns(profile)
        for category, pattern_list in patterns.items():
            for p in pattern_list:
                assert isinstance(p, re.Pattern), (
                    f"Pattern in {category} is not compiled: {p}"
                )

    def test_production_profile_known_ids_count(self):
        """4 chapter known_ids matching the manual's TOC."""
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        known_ids = profile.hierarchy[0].known_ids
        assert len(known_ids) == 4, (
            f"Expected 4 known_ids, got {len(known_ids)}"
        )

    def test_production_profile_chapter_ids_present(self):
        """All 4 chapter IDs (1-4) are present."""
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        ids = {k["id"] for k in profile.hierarchy[0].known_ids}
        expected = {"1", "2", "3", "4"}
        missing = expected - ids
        assert not missing, f"Missing chapter IDs: {missing}"

    def test_production_profile_l1_require_known_id(self):
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[0].require_known_id is True

    def test_production_profile_no_l4_level(self):
        """TM9-8014 profile should have no L4 (per plan: step_patterns handle sub-steps)."""
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        assert len(profile.hierarchy) == 3, (
            f"Expected 3 hierarchy levels (chapter/section/paragraph), got {len(profile.hierarchy)}"
        )

    def test_production_profile_l3_has_filtering(self):
        """L3 (paragraph) should have require_blank_before and min_content_words."""
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        l3 = profile.hierarchy[2]
        assert l3.require_blank_before is True, "L3 should require blank before"
        assert l3.min_content_words > 0, "L3 should have min_content_words > 0"

    def test_production_profile_expanded_ocr_substitutions(self):
        """Profile should have substantially more OCR substitutions than the test fixture."""
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        assert len(profile.ocr_cleanup.known_substitutions) >= 20, (
            f"Expected >= 20 OCR substitutions, got {len(profile.ocr_cleanup.known_substitutions)}"
        )

    def test_production_profile_has_regex_substitutions(self):
        """Profile should have regex substitutions for Z/I confusion patterns."""
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        assert len(profile.ocr_cleanup.regex_substitutions) > 0, (
            "Expected regex substitutions for Z/I confusion patterns"
        )

    def test_production_profile_ocr_quality_poor(self):
        """OCR quality should be marked as poor for this 1950s military manual."""
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        assert profile.ocr_cleanup.quality_estimate == "poor"

    def test_production_profile_two_vehicles(self):
        """Profile covers both M38A1 and M170."""
        profile = load_profile(TM9_8014_PRODUCTION_PROFILE_PATH)
        models = {v.model for v in profile.vehicles}
        assert "M38A1" in models, "M38A1 should be in vehicles"
        assert "M170" in models, "M170 should be in vehicles"


TM9_8015_2_PRODUCTION_PROFILE_PATH = Path(__file__).parent.parent / "profiles" / "tm9-8015-2.yaml"


class TestProductionTm980152Profile:
    """Integration tests for the production TM9-8015-2 profile (profiles/tm9-8015-2.yaml).

    TM9-8015-2 covers Power Train, Body, and Frame for the M38A1.
    The manual has 17 chapters but chapter boundaries are not detectable in OCR text
    (only in the TOC). L1 uses Section (Roman numeral) boundaries instead, with
    require_known_id filtering for Roman numerals I-X plus the numeric "1" variant.
    """

    def test_production_profile_loads(self):
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert isinstance(profile, ManualProfile)
        assert profile.manual_id == "tm9-8015-2"

    def test_production_profile_validates_no_errors(self):
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        errors = validate_profile(profile)
        assert errors == [], f"Validation errors: {errors}"

    def test_production_profile_all_patterns_compile(self):
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        patterns = compile_patterns(profile)
        for category, pattern_list in patterns.items():
            for p in pattern_list:
                assert isinstance(p, re.Pattern), (
                    f"Pattern in {category} is not compiled: {p}"
                )

    def test_production_profile_known_ids_count(self):
        """11 known section IDs (Roman numerals I-X plus numeric '1' variant)."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        known_ids = profile.hierarchy[0].known_ids
        assert len(known_ids) == 11, (
            f"Expected 11 known_ids, got {len(known_ids)}"
        )

    def test_production_profile_section_ids_present(self):
        """All Roman numeral section IDs I through X are present."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        ids = {k["id"] for k in profile.hierarchy[0].known_ids}
        expected = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
        missing = expected - ids
        assert not missing, f"Missing section IDs: {missing}"

    def test_production_profile_l1_require_known_id(self):
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[0].require_known_id is True

    def test_production_profile_two_hierarchy_levels(self):
        """TM9-8015-2 uses 2 levels: section (L1) and paragraph (L2). No L4."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert len(profile.hierarchy) == 2, (
            f"Expected 2 hierarchy levels (section/paragraph), got {len(profile.hierarchy)}"
        )

    def test_production_profile_l1_is_section(self):
        """L1 is 'section' (not 'chapter') because chapter markers are undetectable."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[0].name == "section"

    def test_production_profile_l2_is_paragraph(self):
        """L2 is numbered paragraph."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[1].name == "paragraph"

    def test_production_profile_l1_has_gap_filter(self):
        """L1 should have min_gap_lines to filter TOC false positives."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[0].min_gap_lines >= 10

    def test_production_profile_ocr_quality_good(self):
        """OCR quality should be 'good' (best of remaining TM manuals)."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert profile.ocr_cleanup.quality_estimate == "good"

    def test_production_profile_one_vehicle(self):
        """Profile covers M38A1 only (TM9-8015-2 is power train/body/frame)."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert len(profile.vehicles) == 1
        assert profile.vehicles[0].model == "M38A1"

    def test_production_profile_has_cross_reference_patterns(self):
        """Cross-reference patterns for paragraph refs and companion TM refs."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert len(profile.cross_reference_patterns) >= 2

    def test_production_profile_no_wiring_diagrams(self):
        """TM9-8015-2 (power train/body/frame) has no wiring diagrams."""
        profile = load_profile(TM9_8015_2_PRODUCTION_PROFILE_PATH)
        assert profile.content_types.wiring_diagrams.get("present") is False


TM9_8015_1_PRODUCTION_PROFILE_PATH = Path(__file__).parent.parent / "profiles" / "tm9-8015-1.yaml"


class TestProductionTm980151Profile:
    """Integration tests for the production TM9-8015-1 profile (profiles/tm9-8015-1.yaml).

    TM9-8015-1 covers Engine (Willys-Overland Model MD) and Clutch for the M38A1.
    This is the poorest OCR quality manual in the M38A1 set. Chapter markers are
    completely garbled in the TOC and absent from body text. L1 uses Section (Roman
    numeral) boundaries with require_known_id. Only ~12 of ~25 sections survive OCR
    (many section title pages are image-only). Profile uses aggressive OCR substitutions
    and cross_ref_unresolved_severity: "warning" to handle the degraded quality.
    """

    def test_production_profile_loads(self):
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert isinstance(profile, ManualProfile)
        assert profile.manual_id == "tm9-8015-1"

    def test_production_profile_validates_no_errors(self):
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        errors = validate_profile(profile)
        assert errors == [], f"Validation errors: {errors}"

    def test_production_profile_all_patterns_compile(self):
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        patterns = compile_patterns(profile)
        for category, pattern_list in patterns.items():
            for p in pattern_list:
                assert isinstance(p, re.Pattern), (
                    f"Pattern in {category} is not compiled: {p}"
                )

    def test_production_profile_known_ids_count(self):
        """21 known section IDs (Roman I-XIX plus Xl OCR variant and numeric '1')."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        known_ids = profile.hierarchy[0].known_ids
        assert len(known_ids) == 21, (
            f"Expected 21 known_ids, got {len(known_ids)}"
        )

    def test_production_profile_section_ids_present(self):
        """Key Roman numeral section IDs are present."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        ids = {k["id"] for k in profile.hierarchy[0].known_ids}
        expected = {"I", "II", "III", "IV", "IX", "X", "XI", "XIV", "XVII", "XIX"}
        missing = expected - ids
        assert not missing, f"Missing section IDs: {missing}"

    def test_production_profile_xl_ocr_variant_present(self):
        """The 'Xl' OCR variant for Section XI is included."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        ids = {k["id"] for k in profile.hierarchy[0].known_ids}
        assert "Xl" in ids, "Xl (OCR variant of XI) missing from known_ids"

    def test_production_profile_l1_require_known_id(self):
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[0].require_known_id is True

    def test_production_profile_two_hierarchy_levels(self):
        """TM9-8015-1 uses 2 levels: section (L1) and paragraph (L2). No L3/L4."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert len(profile.hierarchy) == 2, (
            f"Expected 2 hierarchy levels (section/paragraph), got {len(profile.hierarchy)}"
        )

    def test_production_profile_l1_is_section(self):
        """L1 is 'section' (not 'chapter') because chapter markers are undetectable."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[0].name == "section"

    def test_production_profile_l2_is_paragraph(self):
        """L2 is numbered paragraph."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[1].name == "paragraph"

    def test_production_profile_l1_has_gap_filter(self):
        """L1 should have min_gap_lines to filter TOC false positives."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert profile.hierarchy[0].min_gap_lines >= 10

    def test_production_profile_l2_has_content_filter(self):
        """L2 should have min_content_words >= 15 to filter spec table numbers."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        l2 = profile.hierarchy[1]
        assert l2.min_content_words >= 15, (
            f"Expected L2 min_content_words >= 15, got {l2.min_content_words}"
        )

    def test_production_profile_ocr_quality_poor(self):
        """OCR quality should be 'poor' (worst of the M38A1 TM set)."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert profile.ocr_cleanup.quality_estimate == "poor"

    def test_production_profile_heavy_ocr_substitutions(self):
        """Profile should have substantial OCR substitutions for garbled text."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert len(profile.ocr_cleanup.known_substitutions) >= 30, (
            f"Expected >= 30 known_substitutions, got {len(profile.ocr_cleanup.known_substitutions)}"
        )

    def test_production_profile_has_regex_substitutions(self):
        """Profile should have regex substitutions for Z/I confusion patterns."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert len(profile.ocr_cleanup.regex_substitutions) > 0

    def test_production_profile_two_vehicles(self):
        """Profile covers both M38A1 and M170."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        models = {v.model for v in profile.vehicles}
        assert "M38A1" in models, "M38A1 should be in vehicles"
        assert "M170" in models, "M170 should be in vehicles"

    def test_production_profile_cross_ref_severity_warning(self):
        """Cross-ref unresolved severity should be 'warning' for this degraded manual."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert profile.cross_ref_unresolved_severity == "warning"

    def test_production_profile_has_cross_reference_patterns(self):
        """Cross-reference patterns for paragraph refs and companion TM refs."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert len(profile.cross_reference_patterns) >= 2

    def test_production_profile_no_wiring_diagrams(self):
        """TM9-8015-1 (engine/clutch) has no wiring diagrams."""
        profile = load_profile(TM9_8015_1_PRODUCTION_PROFILE_PATH)
        assert profile.content_types.wiring_diagrams.get("present") is False


# ── Profile Discovery Tests (9.1) ───────────────────────────────


_PROFILES_DIR = Path(__file__).parent.parent / "profiles"
_DISCOVERED_PROFILES = sorted(_PROFILES_DIR.glob("*.yaml"))


class TestProfileDiscoveryInvariants:
    """Parametrized tests that auto-discover all profiles/*.yaml files and
    assert common invariants.

    Adding a new YAML file to profiles/ automatically includes it in this
    test suite — no manual registration required.
    """

    @pytest.fixture(params=_DISCOVERED_PROFILES, ids=lambda p: p.stem)
    def production_profile_path(self, request: pytest.FixtureRequest) -> Path:
        return request.param

    def test_profile_loads_successfully(self, production_profile_path: Path):
        """Every production profile must load without errors."""
        profile = load_profile(production_profile_path)
        assert isinstance(profile, ManualProfile)

    def test_profile_validates_with_zero_errors(self, production_profile_path: Path):
        """Every production profile must pass validation with no errors."""
        profile = load_profile(production_profile_path)
        errors = validate_profile(profile)
        assert errors == [], (
            f"Validation errors in {production_profile_path.name}: {errors}"
        )

    def test_profile_all_patterns_compile(self, production_profile_path: Path):
        """Every regex pattern in the profile must compile successfully."""
        profile = load_profile(production_profile_path)
        patterns = compile_patterns(profile)
        for category, pattern_list in patterns.items():
            for p in pattern_list:
                assert isinstance(p, re.Pattern), (
                    f"Pattern in {category} is not compiled in "
                    f"{production_profile_path.name}: {p}"
                )

    def test_profile_has_at_least_one_hierarchy_level(self, production_profile_path: Path):
        """Every production profile must define at least one hierarchy level."""
        profile = load_profile(production_profile_path)
        assert len(profile.hierarchy) >= 1, (
            f"{production_profile_path.name} has no hierarchy levels"
        )

    def test_profile_has_manual_id(self, production_profile_path: Path):
        """Every production profile must have a non-empty manual_id."""
        profile = load_profile(production_profile_path)
        assert profile.manual_id, (
            f"{production_profile_path.name} has empty manual_id"
        )

    def test_profile_has_vehicle_info(self, production_profile_path: Path):
        """Every production profile must define at least one vehicle."""
        profile = load_profile(production_profile_path)
        assert len(profile.vehicles) >= 1, (
            f"{production_profile_path.name} has no vehicles"
        )
        # Each vehicle must have a model and years
        for v in profile.vehicles:
            assert v.model, f"Vehicle in {production_profile_path.name} has empty model"
            assert v.years, f"Vehicle in {production_profile_path.name} has empty years"

    def test_profile_l1_has_require_known_id(self, production_profile_path: Path):
        """L1 must have require_known_id: true to prevent false-positive boundaries."""
        profile = load_profile(production_profile_path)
        assert profile.hierarchy[0].require_known_id is True, (
            f"{production_profile_path.name} L1 does not have require_known_id=true"
        )

    def test_profile_l1_has_nonempty_known_ids(self, production_profile_path: Path):
        """L1 must have at least one known_id entry."""
        profile = load_profile(production_profile_path)
        assert len(profile.hierarchy[0].known_ids) > 0, (
            f"{production_profile_path.name} L1 has no known_ids"
        )

    def test_profile_no_duplicate_known_ids_within_level(self, production_profile_path: Path):
        """No hierarchy level should have duplicate known_ids."""
        profile = load_profile(production_profile_path)
        for level in profile.hierarchy:
            if not level.known_ids:
                continue
            ids = [k["id"] for k in level.known_ids]
            duplicates = [id_ for id_ in ids if ids.count(id_) > 1]
            assert not duplicates, (
                f"{production_profile_path.name} level {level.level} ({level.name}) "
                f"has duplicate known_ids: {set(duplicates)}"
            )
