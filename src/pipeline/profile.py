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
    raise NotImplementedError


def validate_profile(profile: ManualProfile) -> list[str]:
    """Validate a loaded profile for completeness and correctness.

    Returns a list of validation error messages. Empty list means valid.
    """
    raise NotImplementedError


def compile_patterns(profile: ManualProfile) -> dict[str, list[re.Pattern]]:
    """Pre-compile all regex patterns from a profile for runtime use.

    Returns a dict mapping pattern category names to compiled patterns.
    """
    raise NotImplementedError
