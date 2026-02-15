"""Manual profile system — loads, validates, and provides access to YAML manual profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CURRENT_SCHEMA_VERSION = "1.0"


@dataclass
class HierarchyLevel:
    """A single level in the document hierarchy."""
    level: int
    name: str
    id_pattern: str | None
    title_pattern: str | None
    known_ids: list[dict[str, str]] = field(default_factory=list)


@dataclass
class SafetyCallout:
    """A safety callout pattern definition."""
    level: str
    pattern: str
    style: str


@dataclass
class VehicleEngine:
    """Engine specification for a vehicle."""
    name: str
    code: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class VehicleTransmission:
    """Transmission specification for a vehicle."""
    name: str
    code: str


@dataclass
class Vehicle:
    """Vehicle coverage definition."""
    model: str
    years: str
    drive_type: list[str]
    engines: list[VehicleEngine] = field(default_factory=list)
    transmissions: list[VehicleTransmission] = field(default_factory=list)


@dataclass
class ContentTypeConfig:
    """Content type metadata — sub-fields remain dicts because structure
    varies fundamentally across manual types (mileage-bands vs echelon-based
    vs interval-table)."""
    maintenance_schedule: dict[str, Any] = field(default_factory=dict)
    wiring_diagrams: dict[str, Any] = field(default_factory=dict)
    specification_tables: dict[str, Any] = field(default_factory=dict)


@dataclass
class GarbageDetectionConfig:
    """Garbage line detection parameters."""
    enabled: bool = False
    threshold: float = 0.5


@dataclass
class OcrCleanupConfig:
    """OCR cleanup configuration from manual profile."""
    quality_estimate: str = ""
    known_substitutions: list[dict[str, str]] = field(default_factory=list)
    header_footer_patterns: list[str] = field(default_factory=list)
    garbage_detection: GarbageDetectionConfig = field(default_factory=GarbageDetectionConfig)


@dataclass
class VariantConfig:
    """Market variant configuration."""
    has_market_variants: bool = False
    variant_indicator: str = "none"
    markets: list[str] = field(default_factory=list)


@dataclass
class ManualProfile:
    """Complete manual profile loaded from YAML."""
    schema_version: str
    manual_id: str
    manual_title: str
    source_url: str
    source_format: str
    vehicles: list[Vehicle]
    hierarchy: list[HierarchyLevel]
    page_number_pattern: str
    page_number_group_prefixed: bool
    step_patterns: list[str]
    figure_reference_pattern: str
    figure_reference_scope: str
    cross_reference_patterns: list[str]
    safety_callouts: list[SafetyCallout]
    content_types: ContentTypeConfig
    ocr_cleanup: OcrCleanupConfig
    variants: VariantConfig


def _parse_content_types(data: dict[str, Any]) -> ContentTypeConfig:
    return ContentTypeConfig(
        maintenance_schedule=data.get("maintenance_schedule", {}),
        wiring_diagrams=data.get("wiring_diagrams", {}),
        specification_tables=data.get("specification_tables", {}),
    )


def _parse_ocr_cleanup(data: dict[str, Any]) -> OcrCleanupConfig:
    gd = data.get("garbage_detection", {})
    return OcrCleanupConfig(
        quality_estimate=data.get("quality_estimate", ""),
        known_substitutions=data.get("known_substitutions", []),
        header_footer_patterns=data.get("header_footer_patterns", []),
        garbage_detection=GarbageDetectionConfig(
            enabled=gd.get("enabled", False),
            threshold=gd.get("threshold", 0.5),
        ),
    )


def _parse_variants(data: dict[str, Any]) -> VariantConfig:
    return VariantConfig(
        has_market_variants=data.get("has_market_variants", False),
        variant_indicator=data.get("variant_indicator", "none"),
        markets=data.get("markets", []),
    )


def load_profile(path: str | Path) -> ManualProfile:
    """Load a manual profile from a YAML file.

    Args:
        path: Path to the YAML profile file.

    Returns:
        A ManualProfile instance.

    Raises:
        FileNotFoundError: If the profile file does not exist.
        ValueError: If the profile is invalid or missing required fields.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Profile file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Profile YAML must be a mapping at the top level.")

    # Parse vehicles
    vehicles: list[Vehicle] = []
    for v in data.get("vehicles", []):
        engines = [
            VehicleEngine(
                name=e["name"],
                code=e["code"],
                aliases=e.get("aliases", []),
            )
            for e in v.get("engines", [])
        ]
        transmissions = [
            VehicleTransmission(name=t["name"], code=t["code"])
            for t in v.get("transmissions", [])
        ]
        vehicles.append(
            Vehicle(
                model=v["model"],
                years=v["years"],
                drive_type=v["drive_type"],
                engines=engines,
                transmissions=transmissions,
            )
        )

    # Parse structure
    structure = data.get("structure", {})

    hierarchy: list[HierarchyLevel] = []
    for h in structure.get("hierarchy", []):
        hierarchy.append(
            HierarchyLevel(
                level=h["level"],
                name=h["name"],
                id_pattern=h.get("id_pattern"),
                title_pattern=h.get("title_pattern"),
                known_ids=h.get("known_ids", []),
            )
        )

    page_number = structure.get("page_number", {})
    page_number_pattern = page_number.get("pattern", "")
    page_number_group_prefixed = page_number.get("group_prefixed", False)

    step_patterns = structure.get("step_patterns", [])

    figure_ref = structure.get("figure_reference", {})
    figure_reference_pattern = figure_ref.get("pattern", "")
    figure_reference_scope = figure_ref.get("scope", "")

    cross_ref = structure.get("cross_reference", {})
    cross_reference_patterns = cross_ref.get("patterns", [])

    # Parse safety callouts
    safety_callouts: list[SafetyCallout] = []
    for sc in data.get("safety_callouts", []):
        safety_callouts.append(
            SafetyCallout(
                level=sc["level"],
                pattern=sc["pattern"],
                style=sc["style"],
            )
        )

    return ManualProfile(
        schema_version=data.get("schema_version", ""),
        manual_id=data.get("manual_id", ""),
        manual_title=data.get("manual_title", ""),
        source_url=data.get("source_url", ""),
        source_format=data.get("source_format", ""),
        vehicles=vehicles,
        hierarchy=hierarchy,
        page_number_pattern=page_number_pattern,
        page_number_group_prefixed=page_number_group_prefixed,
        step_patterns=step_patterns,
        figure_reference_pattern=figure_reference_pattern,
        figure_reference_scope=figure_reference_scope,
        cross_reference_patterns=cross_reference_patterns,
        safety_callouts=safety_callouts,
        content_types=_parse_content_types(data.get("content_types", {})),
        ocr_cleanup=_parse_ocr_cleanup(data.get("ocr_cleanup", {})),
        variants=_parse_variants(data.get("variants", {})),
    )


def validate_profile(profile: ManualProfile) -> list[str]:
    """Validate a loaded profile for completeness and correctness.

    Returns a list of validation error messages. Empty list means valid.
    """
    errors: list[str] = []

    if not profile.schema_version:
        errors.append("schema_version is required and must not be empty.")
    elif profile.schema_version != CURRENT_SCHEMA_VERSION:
        errors.append(
            f"schema_version '{profile.schema_version}' is not supported. "
            f"Expected '{CURRENT_SCHEMA_VERSION}'."
        )

    if not profile.manual_id:
        errors.append("manual_id is required and must not be empty.")

    if not profile.manual_title:
        errors.append("manual_title is required and must not be empty.")

    if not profile.source_url:
        errors.append("source_url is required and must not be empty.")

    valid_formats = {"pdf-ocr", "pdf-native", "html", "epub"}
    if profile.source_format not in valid_formats:
        errors.append(
            f"source_format '{profile.source_format}' is not valid. "
            f"Must be one of: {', '.join(sorted(valid_formats))}."
        )

    if not profile.vehicles:
        errors.append("At least one vehicle must be defined.")

    if not profile.hierarchy:
        errors.append("At least one hierarchy level must be defined.")

    # Validate hierarchy levels are sequential (1, 2, 3...) with no gaps
    if profile.hierarchy:
        levels = [h.level for h in profile.hierarchy]
        expected = list(range(1, len(levels) + 1))
        if levels != expected:
            errors.append(
                f"Hierarchy levels must be sequential starting at 1. "
                f"Got: {levels}, expected: {expected}."
            )

    # Validate all regex patterns compile
    def _check_pattern(pattern: str | None, label: str) -> None:
        if pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(f"Invalid {label}: {e}")

    for h in profile.hierarchy:
        _check_pattern(h.id_pattern, f"id_pattern at hierarchy level {h.level}")
        _check_pattern(h.title_pattern, f"title_pattern at hierarchy level {h.level}")

    for i, sp in enumerate(profile.step_patterns):
        _check_pattern(sp, f"step_patterns[{i}]")

    for sc in profile.safety_callouts:
        _check_pattern(sc.pattern, f"safety callout pattern for '{sc.level}'")

    _check_pattern(profile.figure_reference_pattern, "figure_reference pattern")
    _check_pattern(profile.page_number_pattern, "page_number pattern")

    for i, p in enumerate(profile.cross_reference_patterns):
        _check_pattern(p, f"cross_reference_patterns[{i}]")

    # Validate OCR known_substitutions structure
    for i, sub in enumerate(profile.ocr_cleanup.known_substitutions):
        if "from" not in sub or "to" not in sub:
            errors.append(
                f"known_substitutions[{i}] must have 'from' and 'to' keys."
            )

    # Validate safety callout levels and styles
    valid_callout_levels = {"warning", "caution", "note"}
    valid_callout_styles = {"block", "inline"}
    for sc in profile.safety_callouts:
        if sc.level not in valid_callout_levels:
            errors.append(
                f"Safety callout level '{sc.level}' is not valid. "
                f"Must be one of: {', '.join(sorted(valid_callout_levels))}."
            )
        if sc.style not in valid_callout_styles:
            errors.append(
                f"Safety callout style '{sc.style}' is not valid. "
                f"Must be one of: {', '.join(sorted(valid_callout_styles))}."
            )

    return errors


def compile_patterns(profile: ManualProfile) -> dict[str, list[re.Pattern]]:
    """Pre-compile all regex patterns from a profile for runtime use.

    Returns a dict mapping pattern category names to compiled patterns.
    """
    result: dict[str, list[re.Pattern]] = {}

    # Compile hierarchy patterns (id_pattern and title_pattern for each level)
    hierarchy_patterns: list[re.Pattern] = []
    for level in profile.hierarchy:
        if level.id_pattern:
            hierarchy_patterns.append(re.compile(level.id_pattern))
        if level.title_pattern:
            hierarchy_patterns.append(re.compile(level.title_pattern))
    result["hierarchy"] = hierarchy_patterns

    # Compile step patterns
    result["step_patterns"] = [re.compile(p) for p in profile.step_patterns]

    # Compile safety callout patterns
    result["safety_callouts"] = [
        re.compile(sc.pattern) for sc in profile.safety_callouts
    ]

    # Compile figure reference pattern
    if profile.figure_reference_pattern:
        result["figure_reference"] = [re.compile(profile.figure_reference_pattern)]
    else:
        result["figure_reference"] = []

    # Compile cross reference patterns
    result["cross_reference"] = [
        re.compile(p) for p in profile.cross_reference_patterns
    ]

    # Compile page number pattern
    if profile.page_number_pattern:
        result["page_number"] = [re.compile(profile.page_number_pattern)]
    else:
        result["page_number"] = []

    return result
