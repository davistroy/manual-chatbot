"""Manual profile system — loads, validates, and provides access to YAML manual profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


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
class ManualProfile:
    """Complete manual profile loaded from YAML."""
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
    content_types: dict[str, Any]
    ocr_cleanup: dict[str, Any]
    variants: dict[str, Any]


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
        content_types=data.get("content_types", {}),
        ocr_cleanup=data.get("ocr_cleanup", {}),
        variants=data.get("variants", {}),
    )


def validate_profile(profile: ManualProfile) -> list[str]:
    """Validate a loaded profile for completeness and correctness.

    Returns a list of validation error messages. Empty list means valid.
    """
    errors: list[str] = []

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
