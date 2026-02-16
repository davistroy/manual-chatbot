"""Shared pytest fixtures for the manual-chatbot test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.structural_parser import LineRange, PageRange

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Profile Fixtures ──────────────────────────────────────────────


@pytest.fixture
def xj_profile_path() -> Path:
    return FIXTURES_DIR / "xj_1999_profile.yaml"


@pytest.fixture
def cj_profile_path() -> Path:
    return FIXTURES_DIR / "cj_universal_profile.yaml"


@pytest.fixture
def tm9_profile_path() -> Path:
    return FIXTURES_DIR / "tm9_8014_profile.yaml"


@pytest.fixture
def invalid_profile_path() -> Path:
    return FIXTURES_DIR / "invalid_profile.yaml"


@pytest.fixture
def nonexistent_profile_path(tmp_path: Path) -> Path:
    return tmp_path / "does_not_exist.yaml"


# ── Sample Text Fixtures ─────────────────────────────────────────


@pytest.fixture
def xj_sample_page_text() -> str:
    """Sample page from 1999 XJ manual with typical content."""
    return """\
XJ                    LUBRICATION AND MAINTENANCE               0 - 9

SERVICE PROCEDURES

JUMP STARTING PROCEDURE

WARNING: REVIEW COMPLETE JUMP STARTING PROCEDURE BEFORE
PROCEEDING. IMPROPER PROCEDURE COULD RESULT IN PERSONAL
INJURY OR PROPERTY DAMAGE FROM BATTERY EXPLOSION.

CAUTION: Do not jump start a vehicle if the battery fluid
is frozen. This could cause the battery to explode.

(1) Connect one end of the jumper cable to the positive
terminal of the booster battery.
(2) Connect the other end of the same cable to the positive
terminal of the discharged battery.
(3) Connect one end of the remaining cable to the negative
terminal of the booster battery.
(4) Connect the other end of the negative cable to the engine
ground of the vehicle with the discharged battery. Do not
connect directly to the negative terminal of the discharged
battery (Fig. 1).

Refer to Group 8A for battery testing and charging procedures.

0 - 9                LUBRICATION AND MAINTENANCE               XJ
"""


@pytest.fixture
def cj_sample_page_text() -> str:
    """Sample page from CJ Universal manual."""
    return """\
'Jeep' UNIVERSAL SERIES SERVICE MANUAL

B Lubrication and Periodic Services

B-1. General
The proper lubrication of all working parts is essential to
the satisfactory performance and long life of the vehicle.

B-4. Engine Lubrication System — Hurricane F4 Engine
a. The engine oil lubricates all internal moving parts of the
engine under pressure from the oil pump.
b. Check the oil level daily using the dipstick on the right
side of the engine.

Caution: Always use the grade of oil specified for the ambient
temperature range. Refer to Par. B-3 for specifications.

FIG. B-1 — Engine Lubrication System Diagram
"""


@pytest.fixture
def tm9_sample_page_text() -> str:
    """Sample page from TM 9-8014 military manual."""
    return """\
TM 9-8014

CHAPTER 2. OPERATING INSTRUCTIONS

Section III. Operation Under Usual Conditions

42. Starting the Engine
a. Set the parking brake.
b. Place the shift lever in neutral.
(1) Pull the choke control out fully if the engine is cold.
(2) Turn the ignition switch to the ON position.
(3) Depress the starter button with the right foot.

Caution: Do not operate the starter for more than 30 seconds
at a time. Allow the starter to cool for at least 2 minutes
between attempts.

Note. If the engine fails to start after three attempts,
refer to par. 81b for troubleshooting procedures.

43. Movement of Vehicle
a. Release the parking brake.
b. Depress the clutch pedal fully.
"""


@pytest.fixture
def sample_ocr_dirty_text() -> str:
    """Text with common OCR artifacts for cleanup testing."""
    return """\
XJ                    LUBRICATION AND MAINTENANCE               0 - 12

IJURY may result from improper procedures.
Use only genuine Mopart replacement parts.
The \u201csmart\u201d quotes should be normalized.
The \ufb01rst ligature should be decomposed.
Line with   multiple     spaces   needs   normalization.
\u00a7\u00b6\u2020\u2021 garbage line with special characters
(Continued)
"""


# ── Chunk Fixtures ────────────────────────────────────────────────


@pytest.fixture
def sample_step_sequence() -> str:
    """A numbered step sequence that must not be split."""
    return """\
(1) Remove the drain plug from the oil pan.
(2) Allow the oil to drain completely into a suitable container.
(3) Install the drain plug and tighten to 25 ft-lbs torque.
(4) Remove the oil filter using an oil filter wrench.
(5) Apply a thin coat of clean engine oil to the gasket of the new filter.
(6) Install the new filter. Hand tighten only.
(7) Fill the engine with the specified amount of oil.
(8) Start the engine and check for leaks.
"""


@pytest.fixture
def sample_spec_table() -> str:
    """A specification table that must be kept atomic."""
    return """\
SPECIFICATIONS
Engine Oil Capacity:
  2.5L I4 .............. 4 quarts (with filter change)
  4.0L I6 .............. 6 quarts (with filter change)
  2.5L Diesel .......... 5.5 quarts (with filter change)
Coolant Capacity:
  2.5L I4 .............. 9.0 quarts
  4.0L I6 .............. 10.0 quarts
Oil Pressure (hot idle): 13 psi minimum
Oil Pressure (3000 RPM): 37-75 psi
"""


@pytest.fixture
def sample_safety_callout_text() -> str:
    """Text with safety callouts that must stay with their procedure."""
    return """\
WARNING: THE COOLING SYSTEM IS PRESSURIZED. NEVER REMOVE THE
RADIATOR CAP WHILE THE ENGINE IS HOT. SCALDING COOLANT AND
STEAM CAN CAUSE SERIOUS BURNS.

CAUTION: Use only the specified coolant mixture. Using the
wrong coolant can damage the engine.

(1) Allow the engine to cool completely before servicing.
(2) Slowly remove the radiator cap.
(3) Drain the coolant by opening the petcock valve at the
bottom of the radiator.
"""


@pytest.fixture
def sample_small_chunk() -> str:
    """A chunk that's too small and should be merged (< 200 tokens)."""
    return "Refer to Group 9 for engine specifications."


@pytest.fixture
def sample_crossref_only_section() -> str:
    """A section consisting only of cross-references."""
    return """\
RELATED PROCEDURES
Refer to Group 5 for brake system procedures.
Refer to Group 2 for suspension procedures.
Refer to Group 19 for steering procedures.
"""


# ── Manifest Fixtures ─────────────────────────────────────────────


@pytest.fixture
def xj_multipage_pages() -> list[str]:
    """Two-page XJ manual content with boundaries on each page.

    Page 0 has a group boundary ('0 Lubrication and Maintenance') at line 0
    and a section boundary ('SERVICE PROCEDURES') at line 4.
    Page 1 has a procedure boundary ('JUMP STARTING PROCEDURE') at line 2.

    Used to verify that detect_boundaries records global line offsets
    rather than per-page offsets, so that assemble_chunks extracts the
    correct text from the concatenated page stream.
    """
    page0 = (
        "0 Lubrication and Maintenance\n"
        "\n"
        "Introduction to maintenance procedures for all models.\n"
        "\n"
        "SERVICE PROCEDURES\n"
        "\n"
        "Overview of service procedures follows."
    )
    page1 = (
        "Additional overview text from page 2.\n"
        "\n"
        "JUMP STARTING PROCEDURE\n"
        "\n"
        "WARNING: REVIEW COMPLETE JUMP STARTING PROCEDURE BEFORE\n"
        "PROCEEDING. IMPROPER PROCEDURE COULD RESULT IN PERSONAL\n"
        "INJURY OR PROPERTY DAMAGE FROM BATTERY EXPLOSION.\n"
        "\n"
        "(1) Connect positive cable to booster battery.\n"
        "(2) Connect other end to discharged battery positive.\n"
        "(3) Connect negative cable to booster battery.\n"
        "(4) Connect other negative end to engine ground."
    )
    return [page0, page1]


@pytest.fixture
def sample_manifest_entry() -> dict:
    """A sample manifest entry dict for chunk assembly testing."""
    return {
        "chunk_id": "xj-1999::0::SP::JSP",
        "level": 3,
        "level_name": "procedure",
        "title": "Jump Starting Procedure",
        "hierarchy_path": [
            "0 Lubrication and Maintenance",
            "SERVICE PROCEDURES",
            "Jump Starting Procedure",
        ],
        "content_type": "procedure",
        "page_range": PageRange(start="0-9", end="0-10"),
        "line_range": LineRange(start=1842, end=1923),
        "vehicle_applicability": ["Cherokee XJ"],
        "engine_applicability": ["all"],
        "drivetrain_applicability": ["all"],
        "has_safety_callouts": ["warning", "caution"],
        "figure_references": ["Fig. 1"],
        "cross_references": ["Group 8A"],
        "parent_chunk_id": "xj-1999::0::SP",
        "children": [],
    }
