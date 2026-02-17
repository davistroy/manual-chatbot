"""Profile-driven structural parsing — detects document hierarchy and chunk boundaries."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .profile import ManualProfile

logger = logging.getLogger(__name__)


@dataclass
class Boundary:
    """A detected structural boundary in the document."""
    level: int
    level_name: str
    id: str | None
    title: str | None
    page_number: int
    line_number: int


@dataclass
class PageRange:
    """Typed page range for a manifest entry."""
    start: str
    end: str


@dataclass
class LineRange:
    """Typed line range for a manifest entry."""
    start: int
    end: int


@dataclass
class ManifestEntry:
    """A single entry in the hierarchical manifest."""
    chunk_id: str
    level: int
    level_name: str
    title: str
    hierarchy_path: list[str]
    content_type: str
    page_range: PageRange
    line_range: LineRange
    vehicle_applicability: list[str]
    engine_applicability: list[str]
    drivetrain_applicability: list[str]
    has_safety_callouts: list[str]
    figure_references: list[str]
    cross_references: list[str]
    parent_chunk_id: str | None
    children: list[str] = field(default_factory=list)


@dataclass
class Manifest:
    """Complete hierarchical manifest for a manual."""
    manual_id: str
    entries: list[ManifestEntry]


def detect_boundaries(
    pages: list[str], profile: ManualProfile
) -> list[Boundary]:
    """Scan cleaned text pages for structural boundaries using profile hierarchy patterns.

    Args:
        pages: List of cleaned text strings, one per page.
        profile: The manual profile with hierarchy definitions.

    Returns:
        Ordered list of detected boundaries, sorted by page_number then line_number.
    """
    boundaries: list[Boundary] = []
    logger.debug("Scanning %d pages for structural boundaries", len(pages))

    # Pre-compile patterns for each hierarchy level
    compiled_levels: list[
        tuple[int, str, re.Pattern | None, re.Pattern | None]
    ] = []
    for h in profile.hierarchy:
        id_pat = re.compile(h.id_pattern) if h.id_pattern else None
        title_pat = re.compile(h.title_pattern) if h.title_pattern else None
        compiled_levels.append((h.level, h.name, id_pat, title_pat))

    # Track the current deepest active level to resolve ambiguous matches.
    # When a line matches multiple hierarchy levels, we pick the shallowest
    # level that is deeper than any already-open level of the same pattern.
    current_level = 0  # deepest hierarchy level currently active

    # Running offset so that line_number is a global (absolute) index into the
    # concatenated page stream (i.e. "\n".join(pages).split("\n")).  Without
    # this, assemble_chunks() — which joins all pages and indexes by
    # line_number — would extract the wrong text for page 2+.
    global_line_offset = 0

    for page_idx, page_text in enumerate(pages):
        lines = page_text.split("\n")
        for line_idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # Collect all matching levels for this line
            matches: list[tuple[int, str, str | None, str | None]] = []
            for level_num, level_name, id_pat, title_pat in compiled_levels:
                id_match = id_pat.search(stripped) if id_pat else None
                title_match = title_pat.search(stripped) if title_pat else None

                if id_match or title_match:
                    boundary_id = id_match.group(1) if id_match else None
                    boundary_title = title_match.group(1) if title_match else None
                    matches.append((level_num, level_name, boundary_id, boundary_title))

            if not matches:
                continue

            # If only one level matches, use it directly.
            if len(matches) == 1:
                chosen = matches[0]
            else:
                # Multiple levels match. Use context to disambiguate:
                # - If a level <= current_level matches exclusively (unique pattern),
                #   it resets context (e.g., a new group heading).
                # - Otherwise, pick the deepest level that is > current_level
                #   to nest inside the current context. If none is deeper, pick
                #   the shallowest match (it's starting a new top-level section).
                deeper = [m for m in matches if m[0] > current_level]
                if deeper:
                    chosen = deeper[0]  # shallowest of the deeper matches
                else:
                    chosen = matches[0]  # shallowest overall (resets context)

            level_num, level_name, boundary_id, boundary_title = chosen

            # Update current context level
            current_level = level_num

            boundaries.append(
                Boundary(
                    level=level_num,
                    level_name=level_name,
                    id=boundary_id,
                    title=boundary_title,
                    page_number=page_idx,
                    line_number=global_line_offset + line_idx,
                )
            )

        # Advance the global offset by the number of lines in this page
        global_line_offset += len(lines)

    # Sort by page_number, then line_number
    boundaries.sort(key=lambda b: (b.page_number, b.line_number))
    logger.debug("Detected %d boundaries across %d pages", len(boundaries), len(pages))
    return boundaries


def filter_boundaries(
    boundaries: list[Boundary], profile: ManualProfile, pages: list[str]
) -> list[Boundary]:
    """Post-filter detected boundaries using per-level filter configuration.

    Applies three optional filters (configured per hierarchy level on the profile):
      - min_gap_lines: Remove a boundary if the gap (in lines) between it and the
        preceding same-level boundary is less than the threshold.
      - min_content_words: Remove a boundary if the word count between it and the
        next boundary (or end of document) is below the threshold.
      - require_blank_before: Remove a boundary whose line is not preceded by a
        blank line in the page text.

    Args:
        boundaries: Ordered list of detected boundaries (sorted by page/line).
        profile: The manual profile with hierarchy-level filter settings.
        pages: List of cleaned text strings, one per page.

    Returns:
        Filtered list of boundaries (may be smaller than input).
    """
    before = len(boundaries)
    if before == 0:
        return []

    # Build filter config lookup: level number -> HierarchyLevel
    level_config: dict[int, Any] = {}
    for h in profile.hierarchy:
        level_config[h.level] = h

    # Concatenate all pages into a single line list for word counting
    # and blank-line checking (mirrors how detect_boundaries computes
    # global line_number offsets).
    all_lines = "\n".join(pages).split("\n")
    total_lines = len(all_lines)

    # --- Pass 0: require_known_id ---
    known_id_sets: dict[int, set[str]] = {}
    for h in profile.hierarchy:
        if h.require_known_id and h.known_ids:
            known_id_sets[h.level] = {entry["id"] for entry in h.known_ids}

    if known_id_sets:
        before_pass0 = len(boundaries)
        filtered = []
        for b in boundaries:
            if b.level in known_id_sets:
                if b.id is None or b.id not in known_id_sets[b.level]:
                    continue  # rejected
            filtered.append(b)
        boundaries = filtered
        logger.info("Pass 0 (known_id): %d -> %d boundaries", before_pass0, len(boundaries))

    # --- Pass 1: require_blank_before ---
    # Remove boundaries whose line is not preceded by a blank line.
    before_pass1 = len(boundaries)
    filtered = []
    for b in boundaries:
        cfg = level_config.get(b.level)
        if cfg and cfg.require_blank_before:
            if b.line_number <= 0:
                # First line of document — no preceding line possible; remove.
                continue
            preceding_line = all_lines[b.line_number - 1] if b.line_number < total_lines else ""
            if preceding_line.strip() != "":
                continue
        filtered.append(b)
    boundaries = filtered
    logger.info("Pass 1 (blank_before): %d -> %d boundaries", before_pass1, len(boundaries))

    # --- Pass 2: min_gap_lines ---
    # For each hierarchy level with min_gap_lines > 0, iterate same-level
    # boundaries in order. If the gap to the preceding same-level boundary
    # is less than the threshold, drop the second boundary.
    levels_with_gap = {
        h.level for h in profile.hierarchy if h.min_gap_lines > 0
    }
    if levels_with_gap:
        before_pass2 = len(boundaries)
        # Track last-seen line_number per level
        last_line: dict[int, int] = {}
        filtered = []
        for b in boundaries:
            if b.level in levels_with_gap:
                cfg = level_config[b.level]
                if b.level in last_line:
                    gap = b.line_number - last_line[b.level]
                    if gap < cfg.min_gap_lines:
                        continue  # too close to previous same-level boundary
                last_line[b.level] = b.line_number
            filtered.append(b)
        boundaries = filtered
        logger.info("Pass 2 (min_gap): %d -> %d boundaries", before_pass2, len(boundaries))

    # --- Pass 3: min_content_words ---
    # For each boundary, count words between it and the next boundary
    # (or end of document). If below the level's min_content_words, remove it.
    levels_with_min_words = {
        h.level for h in profile.hierarchy if h.min_content_words > 0
    }
    if levels_with_min_words:
        before_pass3 = len(boundaries)
        filtered = []
        for i, b in enumerate(boundaries):
            if b.level in levels_with_min_words:
                cfg = level_config[b.level]
                start_line = b.line_number
                if i + 1 < len(boundaries):
                    end_line = boundaries[i + 1].line_number
                else:
                    end_line = total_lines
                span = all_lines[start_line:end_line]
                word_count = sum(len(line.split()) for line in span)
                if word_count < cfg.min_content_words:
                    continue
            filtered.append(b)
        boundaries = filtered
        logger.info("Pass 3 (min_words): %d -> %d boundaries", before_pass3, len(boundaries))

    after = len(boundaries)
    logger.info("Boundary filter: %d → %d boundaries", before, after)
    return boundaries


def validate_boundaries(
    boundaries: list[Boundary], profile: ManualProfile
) -> list[str]:
    """Validate detected boundaries against profile's known_ids.

    Returns list of warning messages for unrecognized IDs.
    """
    warnings: list[str] = []

    # Build a lookup: level_name -> set of known id strings
    known_ids_by_level: dict[int, set[str]] = {}
    for h in profile.hierarchy:
        if h.known_ids:
            known_ids_by_level[h.level] = {
                entry["id"] for entry in h.known_ids
            }

    for boundary in boundaries:
        if boundary.level not in known_ids_by_level:
            # No known_ids defined for this level — skip validation
            continue
        if boundary.id is None:
            # No ID extracted — skip validation
            continue
        known = known_ids_by_level[boundary.level]
        if boundary.id not in known:
            warnings.append(
                f"Unrecognized {boundary.level_name} ID '{boundary.id}' "
                f"at page {boundary.page_number}, line {boundary.line_number}. "
                f"Known IDs: {sorted(known)}"
            )

    return warnings


def build_manifest(
    boundaries: list[Boundary], profile: ManualProfile
) -> Manifest:
    """Build a hierarchical manifest from detected boundaries.

    Assigns chunk IDs in the format: {manual_id}::{level1_id}::{level2_id}::...
    Establishes parent-child relationships based on hierarchy levels.
    """
    manual_id = profile.manual_id
    entries: list[ManifestEntry] = []

    # Track current ancestors at each level for building hierarchy paths.
    # Key: level number, Value: (id_or_title, title, index into entries list)
    current_ancestors: dict[int, tuple[str, str, int]] = {}

    # Collect vehicle applicability from profile
    vehicle_names = [v.model for v in profile.vehicles]

    for boundary in boundaries:
        # Determine the ID string to use in chunk_id generation
        boundary_id_str = boundary.id if boundary.id is not None else (boundary.title or "")
        boundary_title_str = boundary.title or boundary.id or ""

        # Clear any deeper-level ancestors when encountering this level
        levels_to_remove = [
            lvl for lvl in current_ancestors if lvl >= boundary.level
        ]
        for lvl in levels_to_remove:
            del current_ancestors[lvl]

        # Build hierarchy_ids from ancestors + current
        hierarchy_ids: list[str] = []
        hierarchy_path: list[str] = []
        sorted_ancestor_levels = sorted(current_ancestors.keys())
        for lvl in sorted_ancestor_levels:
            anc_id, anc_title, _ = current_ancestors[lvl]
            hierarchy_ids.append(anc_id)
            hierarchy_path.append(anc_title)

        hierarchy_ids.append(boundary_id_str)
        hierarchy_path.append(boundary_title_str)

        chunk_id = generate_chunk_id(manual_id, hierarchy_ids)

        # Determine parent chunk_id
        parent_chunk_id: str | None = None
        if sorted_ancestor_levels:
            # Parent is the nearest ancestor (highest level number < current level)
            parent_level = sorted_ancestor_levels[-1]
            parent_ids: list[str] = []
            for lvl in sorted_ancestor_levels:
                anc_id, _, _ = current_ancestors[lvl]
                parent_ids.append(anc_id)
                if lvl == parent_level:
                    break
            parent_chunk_id = generate_chunk_id(manual_id, parent_ids)

        entry = ManifestEntry(
            chunk_id=chunk_id,
            level=boundary.level,
            level_name=boundary.level_name,
            title=boundary_title_str,
            hierarchy_path=hierarchy_path,
            content_type=boundary.level_name,
            page_range=PageRange(start=str(boundary.page_number), end=str(boundary.page_number)),
            line_range=LineRange(start=boundary.line_number, end=boundary.line_number),
            vehicle_applicability=vehicle_names,
            engine_applicability=["all"],
            drivetrain_applicability=["all"],
            has_safety_callouts=[],
            figure_references=[],
            cross_references=[],
            parent_chunk_id=parent_chunk_id,
            children=[],
        )

        entry_idx = len(entries)
        entries.append(entry)

        # Register as ancestor for child boundaries
        current_ancestors[boundary.level] = (boundary_id_str, boundary_title_str, entry_idx)

        # Add this entry as a child of its parent
        if parent_chunk_id is not None:
            for e in entries:
                if e.chunk_id == parent_chunk_id:
                    e.children.append(chunk_id)
                    break

    return Manifest(manual_id=manual_id, entries=entries)


def generate_chunk_id(manual_id: str, hierarchy_ids: list[str]) -> str:
    """Generate a namespaced chunk ID from hierarchy path.

    Format: {manual_id}::{level1_id}::{level2_id}::...
    """
    if not hierarchy_ids:
        return manual_id
    return "::".join([manual_id] + hierarchy_ids)


def save_manifest(manifest: Manifest, path: Path) -> None:
    """Serialize a Manifest to a JSON file.

    Uses dataclasses.asdict() for full recursive conversion, then writes
    indented JSON for readability and diffability.

    Args:
        manifest: The Manifest object to persist.
        path: Filesystem path for the output JSON file.
    """
    data = asdict(manifest)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.debug("Saved manifest with %d entries to %s", len(manifest.entries), path)


def load_manifest(path: Path) -> Manifest:
    """Deserialize a Manifest from a JSON file.

    Reconstructs fully-typed dataclass instances (Manifest, ManifestEntry,
    PageRange, LineRange) from the plain-dict JSON representation.

    Args:
        path: Filesystem path to a manifest JSON file.

    Returns:
        A Manifest with properly typed ManifestEntry objects.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    for entry_dict in data["entries"]:
        entry_dict["page_range"] = PageRange(**entry_dict["page_range"])
        entry_dict["line_range"] = LineRange(**entry_dict["line_range"])
        entries.append(ManifestEntry(**entry_dict))

    return Manifest(manual_id=data["manual_id"], entries=entries)
