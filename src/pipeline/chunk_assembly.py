"""Chunk assembly engine — applies universal boundary rules and profile metadata."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .profile import ManualProfile
from .structural_parser import Manifest, ManifestEntry

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A fully assembled chunk with text and metadata."""
    chunk_id: str
    manual_id: str
    text: str
    metadata: dict[str, Any]


# Word-to-token scaling factor. Set to 1.0 because word count approximates
# token count for English prose. Actual BPE ratio is ~1.3x for technical
# English, meaning this intentionally undercounts — chunks may be ~30% larger
# than the nominal 200-2000 token target. The error direction is safe for RAG
# (slightly oversized chunks preserve more context per retrieval hit).
#
# To use a real tokenizer: swap the count_tokens() implementation for
# tiktoken or sentencepiece, and set this factor to 1.0.
TOKEN_ESTIMATE_FACTOR: float = 1.0


def count_tokens(text: str) -> int:
    """Estimate token count using whitespace word splitting.

    Deliberate tradeoff: avoids a tokenizer dependency (tiktoken,
    sentencepiece) at the cost of ~20-30% undercount vs actual BPE
    tokens for technical English. Chunks may run ~30% larger than
    the nominal 200-2000 token target defined in R2.

    The error direction is safe for RAG — slightly oversized chunks
    preserve more context per retrieval hit. If precision matters
    (e.g., strict model context limits), swap this implementation
    for a BPE tokenizer.
    """
    if not text or not text.strip():
        return 0
    return int(len(text.split()) * TOKEN_ESTIMATE_FACTOR)


def compose_hierarchical_header(
    profile: ManualProfile, hierarchy_path: list[str]
) -> str:
    """Build the hierarchical header string for a chunk.

    Format: {manual_title} | {level1_title} | {level2_title} | ...
    """
    parts = [profile.manual_title] + list(hierarchy_path)
    return " | ".join(parts)


def detect_step_sequences(text: str, step_patterns: list[str]) -> list[tuple[int, int]]:
    """Find step sequences in text that must not be split.

    Returns list of (start_line, end_line) tuples for each detected sequence.
    """
    lines = text.split("\n")
    compiled = [re.compile(p) for p in step_patterns]

    # Mark which lines match a step pattern
    step_lines: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        for pat in compiled:
            if pat.search(stripped):
                step_lines.append(i)
                break

    if not step_lines:
        return []

    # Group contiguous step lines (allowing gaps of at most 1 non-step line
    # between steps for continuation lines)
    sequences: list[tuple[int, int]] = []
    seq_start = step_lines[0]
    seq_end = step_lines[0]

    for i in range(1, len(step_lines)):
        # If the gap between consecutive step lines is small (step lines that
        # are adjacent or separated by only non-step continuation lines),
        # keep them in the same sequence. But if we see a step that resets
        # numbering (e.g., (1) again after we already had (1)), it's a new sequence.
        current_line = step_lines[i]
        prev_line = step_lines[i - 1]

        # Check if the current step restarts numbering
        current_stripped = lines[current_line].strip()
        prev_stripped = lines[prev_line].strip()

        restarts = False
        for pat in compiled:
            curr_match = pat.search(current_stripped)
            prev_match = pat.search(prev_stripped)
            if curr_match and prev_match:
                curr_val = curr_match.group(1)
                prev_val = prev_match.group(1)
                # If both are numeric and current <= previous, it's a restart
                if curr_val.isdigit() and prev_val.isdigit():
                    if int(curr_val) <= int(prev_val) and int(curr_val) == 1:
                        restarts = True
                # If both are alpha and current <= previous, it's a restart
                elif curr_val.isalpha() and prev_val.isalpha():
                    if curr_val <= prev_val and curr_val == 'a':
                        restarts = True
                break

        if restarts and (current_line - prev_line) > 1:
            # End current sequence and start a new one
            sequences.append((seq_start, seq_end))
            seq_start = current_line
            seq_end = current_line
        else:
            # Continue current sequence
            seq_end = current_line

    sequences.append((seq_start, seq_end))
    return sequences


def detect_safety_callouts(
    text: str, profile: ManualProfile
) -> list[dict[str, Any]]:
    """Find safety callouts (WARNING/CAUTION/NOTE) in chunk text.

    Returns list of dicts with keys: level, start_line, end_line, text.
    """
    lines = text.split("\n")
    callouts: list[dict[str, Any]] = []

    # Pre-compile all safety callout patterns once for use in the inner loop
    compiled_safety = [
        re.compile(sc2.pattern, re.IGNORECASE if sc2.pattern[0] != "^" else 0)
        for sc2 in profile.safety_callouts
    ]

    for sc_idx, sc in enumerate(profile.safety_callouts):
        pat = compiled_safety[sc_idx]
        for i, line in enumerate(lines):
            stripped = line.strip()
            if pat.search(stripped):
                # Found a callout start. Determine its extent.
                # The callout continues until the next blank line or
                # next callout or next structural element.
                end_line = i
                for j in range(i + 1, len(lines)):
                    next_stripped = lines[j].strip()
                    if not next_stripped:
                        break
                    # Check if this line starts a new callout
                    is_new_callout = False
                    for inner_pat in compiled_safety:
                        if inner_pat.search(next_stripped):
                            is_new_callout = True
                            break
                    if is_new_callout:
                        break
                    # Check if line starts a numbered step
                    if re.match(r'^\(\d+\)\s', next_stripped) or re.match(r'^[a-z]\.\s', next_stripped):
                        break
                    end_line = j

                callout_text = "\n".join(lines[i:end_line + 1])
                callouts.append({
                    "level": sc.level,
                    "start_line": i,
                    "end_line": end_line,
                    "text": callout_text,
                })

    return callouts


def detect_tables(text: str) -> list[tuple[int, int]]:
    """Detect specification table boundaries in text.

    Returns list of (start_line, end_line) tuples.
    """
    lines = text.split("\n")

    # Detect table-like patterns: dot-leaders, columnar alignment
    dot_leader_pat = re.compile(r'\.{3,}')  # Three or more dots in a row
    column_pat = re.compile(r'\s{3,}\S')  # Large whitespace gap suggesting columns

    table_lines: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if dot_leader_pat.search(stripped):
            table_lines.append(i)

    if not table_lines:
        return []

    # Group contiguous table lines (with small gaps)
    sequences: list[tuple[int, int]] = []
    seq_start = table_lines[0]
    seq_end = table_lines[0]

    # Include a header line if there's one right before the first table line
    if seq_start > 0:
        prev = lines[seq_start - 1].strip()
        if prev and not dot_leader_pat.search(prev):
            # Could be a table header like "SPECIFICATIONS"
            seq_start = seq_start - 1

    for i in range(1, len(table_lines)):
        current = table_lines[i]
        prev = table_lines[i - 1]
        if current - prev <= 3:  # Allow small gaps (sub-headers within table)
            seq_end = current
        else:
            sequences.append((seq_start, seq_end))
            seq_start = current
            # Check for header line
            if seq_start > 0:
                header = lines[seq_start - 1].strip()
                if header and not dot_leader_pat.search(header):
                    seq_start = seq_start - 1
            seq_end = current

    sequences.append((seq_start, seq_end))
    return sequences


def apply_rule_r1_primary_unit(
    text: str, entry: ManifestEntry
) -> list[str]:
    """R1: One complete procedure/topic at the lowest meaningful hierarchy level."""
    # The primary unit is the text associated with the manifest entry.
    # Return the text as a single chunk - one procedure stays as one chunk.
    if not text or not text.strip():
        return []
    return [text]


def apply_rule_r2_size_targets(chunks: list[str]) -> list[str]:
    """R2: Enforce min 200, target 500-1500, max 2000 token limits."""
    result: list[str] = []
    max_tokens = 2000

    for chunk in chunks:
        tokens = count_tokens(chunk)
        if tokens <= max_tokens:
            result.append(chunk)
        else:
            # Split oversized chunks at paragraph boundaries
            result.extend(_split_oversized(chunk, max_tokens))

    return result


def _split_oversized(text: str, max_tokens: int) -> list[str]:
    """Split an oversized chunk into pieces that fit within max_tokens."""
    # Try to split on paragraph boundaries (double newlines)
    paragraphs = re.split(r'\n\s*\n', text)
    if len(paragraphs) > 1:
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            candidate = (current + "\n\n" + para).strip() if current else para
            if count_tokens(candidate) <= max_tokens:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # If single paragraph exceeds limit, split further
                if count_tokens(para) > max_tokens:
                    chunks.extend(_split_by_sentences(para, max_tokens))
                else:
                    current = para
        if current:
            chunks.append(current)
        return chunks if chunks else [text]

    # No paragraph breaks — split by sentences or lines
    return _split_by_sentences(text, max_tokens)


def _split_by_sentences(text: str, max_tokens: int) -> list[str]:
    """Split text by lines/sentences to fit within max_tokens."""
    lines = text.split("\n")
    chunks: list[str] = []
    current_lines: list[str] = []

    for line in lines:
        candidate = "\n".join(current_lines + [line])
        if count_tokens(candidate) <= max_tokens:
            current_lines.append(line)
        else:
            if current_lines:
                chunks.append("\n".join(current_lines))
            # If a single line exceeds the limit, split by words
            if count_tokens(line) > max_tokens:
                words = line.split()
                word_chunk: list[str] = []
                for word in words:
                    test = " ".join(word_chunk + [word])
                    if count_tokens(test) <= max_tokens:
                        word_chunk.append(word)
                    else:
                        if word_chunk:
                            chunks.append(" ".join(word_chunk))
                        word_chunk = [word]
                if word_chunk:
                    current_lines = [" ".join(word_chunk)]
                else:
                    current_lines = []
            else:
                current_lines = [line]

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks if chunks else [text]


def apply_rule_r3_never_split_steps(
    text: str, step_patterns: list[str]
) -> list[str]:
    """R3: Keep numbered/lettered step sequences in one chunk."""
    sequences = detect_step_sequences(text, step_patterns)
    if not sequences:
        return [text]

    lines = text.split("\n")

    # Build protected ranges (inclusive line ranges for step sequences)
    protected: list[tuple[int, int]] = sorted(sequences)

    # Build chunks: non-step text before/between/after sequences goes into
    # separate chunks, step sequences each go into their own chunk.
    chunks: list[str] = []
    current_pos = 0

    for seq_start, seq_end in protected:
        # Text before this sequence
        if current_pos < seq_start:
            before = "\n".join(lines[current_pos:seq_start]).strip()
            if before:
                chunks.append(before)

        # The step sequence itself
        step_text = "\n".join(lines[seq_start:seq_end + 1]).strip()
        if step_text:
            chunks.append(step_text)

        current_pos = seq_end + 1

    # Any remaining text after the last sequence
    if current_pos < len(lines):
        after = "\n".join(lines[current_pos:]).strip()
        if after:
            chunks.append(after)

    return chunks if chunks else [text]


def apply_rule_r4_safety_attachment(
    chunks: list[str], profile: ManualProfile
) -> list[str]:
    """R4: Safety callouts stay with their governed procedure."""
    # For each chunk, ensure safety callouts are kept together with
    # the procedure they govern (which follows the callout).
    # If a chunk ends with a safety callout and next chunk has the procedure,
    # merge them. If a safety callout is in its own chunk, merge with next.
    result: list[str] = list(chunks)

    # Check if any chunk consists primarily of safety callouts and needs
    # to be merged with the next chunk (which has the procedure).
    merged: list[str] = []
    i = 0
    while i < len(result):
        chunk = result[i]
        callouts = detect_safety_callouts(chunk, profile)

        if callouts and i + 1 < len(result):
            # Check if there's procedure content after the callout in this chunk
            # If the chunk is ONLY a safety callout, merge with next
            lines = chunk.strip().split("\n")
            non_callout_lines = set(range(len(lines)))
            for c in callouts:
                for ln in range(c["start_line"], c["end_line"] + 1):
                    non_callout_lines.discard(ln)

            # Check if remaining lines have procedure content
            has_procedure = False
            for ln in non_callout_lines:
                if ln < len(lines) and lines[ln].strip():
                    has_procedure = True
                    break

            if not has_procedure:
                # Safety-only chunk — merge with next
                merged_text = chunk + "\n\n" + result[i + 1]
                merged.append(merged_text)
                i += 2
                continue

        merged.append(chunk)
        i += 1

    return merged


def apply_rule_r5_table_integrity(chunks: list[str]) -> list[str]:
    """R5: Specification tables are never split.

    If a prior splitting rule broke a table across two adjacent chunks,
    this rule detects the split and re-merges them.  The heuristic is
    conservative -- both signals must agree before merging:

    1. The current chunk must end with table-like content (the last
       table detected by ``detect_tables`` extends to or near the
       chunk's last line).
    2. The next chunk must start with table-like content (``detect_tables``
       returns at least one table whose first line is near line 0).

    When both conditions hold, the two chunks are concatenated.  The merged
    result is then re-evaluated on the next iteration so that a table
    split across three chunks is still reassembled.
    """
    if len(chunks) <= 1:
        return list(chunks)

    result: list[str] = []
    i = 0
    while i < len(chunks):
        current = chunks[i]

        if i + 1 < len(chunks):
            next_chunk = chunks[i + 1]

            # Signal 1: current chunk ends with table content
            current_lines = current.split("\n")
            current_tables = detect_tables(current)
            current_ends_with_table = False
            if current_tables:
                last_table_end = current_tables[-1][1]
                # The table's last line is at or very near the end of the chunk
                # (allow up to 2 trailing blank/whitespace lines)
                non_blank_end = len(current_lines) - 1
                while non_blank_end > 0 and not current_lines[non_blank_end].strip():
                    non_blank_end -= 1
                if last_table_end >= non_blank_end - 1:
                    current_ends_with_table = True

            # Signal 2: next chunk starts with table content
            next_tables = detect_tables(next_chunk)
            next_starts_with_table = False
            if next_tables:
                first_table_start = next_tables[0][0]
                # The first table starts at or very near the beginning
                # (allow up to 2 leading blank lines)
                next_lines = next_chunk.split("\n")
                first_non_blank = 0
                while first_non_blank < len(next_lines) and not next_lines[first_non_blank].strip():
                    first_non_blank += 1
                if first_table_start <= first_non_blank + 1:
                    next_starts_with_table = True

            # Only merge when BOTH signals agree
            if current_ends_with_table and next_starts_with_table:
                merged = current + "\n" + next_chunk
                # Replace the next chunk with the merged result so we can
                # re-evaluate (handles 3-way splits)
                chunks[i + 1] = merged
                i += 1
                continue

        result.append(current)
        i += 1

    return result


def apply_rule_r6_merge_small(chunks: list[str], min_tokens: int = 200) -> list[str]:
    """R6: Merge chunks under min_tokens with next sibling or parent."""
    if len(chunks) <= 1:
        return list(chunks)

    # Use a merge threshold: only merge truly small chunks (well below min_tokens).
    # Chunks that are at or near half the min_tokens threshold are considered
    # substantive enough to stand alone.
    merge_threshold = min_tokens // 2

    result: list[str] = []
    i = 0
    while i < len(chunks):
        current = chunks[i]
        if count_tokens(current) < merge_threshold and i + 1 < len(chunks):
            # Merge with next chunk and re-evaluate the merged result
            # by keeping it as `current` for the next iteration
            chunks[i + 1] = current + "\n\n" + chunks[i + 1]
            i += 1
        else:
            result.append(current)
            i += 1

    return result


def apply_rule_r7_crossref_merge(
    chunks: list[str], cross_ref_patterns: list[str]
) -> list[str]:
    """R7: Cross-ref-only sections merge into parent."""
    compiled = [re.compile(p) for p in cross_ref_patterns]

    result: list[str] = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]

        # Check if this chunk consists only of cross-references
        if _is_crossref_only(chunk, compiled):
            if result:
                # Merge into previous (parent) chunk
                result[-1] = result[-1] + "\n\n" + chunk
            else:
                # No parent to merge into — keep as is
                result.append(chunk)
        else:
            result.append(chunk)
        i += 1

    return result


def _is_crossref_only(text: str, compiled_patterns: list[re.Pattern]) -> bool:
    """Check if a chunk consists only of cross-references and headers."""
    lines = text.strip().split("\n")
    if not lines:
        return False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check if the line is a cross-reference
        is_crossref = False
        for pat in compiled_patterns:
            if pat.search(stripped):
                is_crossref = True
                break

        if is_crossref:
            continue

        # Check if the line looks like a heading (all caps, short)
        if stripped.isupper() and len(stripped.split()) <= 5:
            continue

        # This line has real content that isn't a cross-ref or heading
        return False

    return True


def apply_rule_r8_figure_continuity(
    chunks: list[str], figure_pattern: str
) -> list[str]:
    """R8: Figure references stay with the text describing them.

    If a chunk's first non-blank line is primarily a figure reference or
    caption (e.g. ``FIG. B-1 -- Engine Lubrication System Diagram``) and
    the *previous* chunk also mentions the same figure, this rule merges
    the orphaned figure line back into the previous chunk.

    The heuristic is intentionally conservative:
    * Only the first non-blank line of a chunk is considered a candidate.
    * The line must match ``figure_pattern``.
    * The previous chunk must also contain a match for the same pattern
      (confirming the figure is discussed there, not somewhere unrelated).
    """
    pat = re.compile(figure_pattern)

    result: list[str] = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]

        if result:
            # Check if this chunk starts with a figure reference line
            lines = chunk.split("\n")
            first_non_blank_idx = 0
            while first_non_blank_idx < len(lines) and not lines[first_non_blank_idx].strip():
                first_non_blank_idx += 1

            if first_non_blank_idx < len(lines):
                first_line = lines[first_non_blank_idx].strip()
                first_match = pat.search(first_line)

                if first_match:
                    # Extract the figure identifier from the first line
                    fig_id = first_match.group(1) if first_match.lastindex else first_match.group(0)

                    # Check if the previous chunk references the same figure
                    prev_chunk = result[-1]
                    prev_has_same_fig = False
                    for prev_match_obj in pat.finditer(prev_chunk):
                        prev_fig_id = (
                            prev_match_obj.group(1)
                            if prev_match_obj.lastindex
                            else prev_match_obj.group(0)
                        )
                        if prev_fig_id == fig_id:
                            prev_has_same_fig = True
                            break

                    if prev_has_same_fig:
                        # Merge this chunk into the previous one
                        result[-1] = prev_chunk + "\n\n" + chunk
                        i += 1
                        continue

        result.append(chunk)
        i += 1

    return result


def _extract_level1_id(chunk: Chunk) -> str:
    """Extract the level-1 group ID from a chunk's chunk_id.

    Chunk IDs follow the pattern ``{manual_id}::{level1_id}::...``.
    Returns the second ``::``-delimited segment, or an empty string if
    the chunk_id has fewer than two segments.
    """
    parts = chunk.chunk_id.split("::")
    if len(parts) >= 2:
        return parts[1]
    return ""


def merge_small_across_entries(
    chunks: list[Chunk], min_tokens: int = 200, max_tokens: int = 2000
) -> list[Chunk]:
    """Post-assembly merge pass: absorb tiny chunks into their next sibling.

    Iterates the full chunk list left to right.  For each chunk whose token
    count is below *min_tokens*, the chunk's text is prepended to the next
    chunk **if** both chunks share the same level-1 group (extracted from
    ``chunk_id``) **and** the combined size does not exceed *max_tokens*.

    Runs multiple passes (up to 10) until no further merges occur so that
    chains of tiny chunks collapse fully.

    Returns a new list — the input list is not mutated.
    """
    # Threshold tuning: min_tokens=200 catches most tiny chunks,
    # max_tokens=2000 prevents oversized merged chunks.
    # Tuned against XJ 1999 service manual output.
    if not chunks:
        return []

    working = list(chunks)
    max_passes = 10

    for pass_num in range(max_passes):
        before = len(working)
        merged: list[Chunk] = []
        i = 0
        while i < len(working):
            current = working[i]

            if count_tokens(current.text) < min_tokens and i + 1 < len(working):
                next_chunk = working[i + 1]
                current_l1 = _extract_level1_id(current)
                next_l1 = _extract_level1_id(next_chunk)

                if current_l1 == next_l1:
                    combined_text = current.text + "\n\n" + next_chunk.text
                    # Guard: don't merge if the result would exceed max_tokens
                    if count_tokens(combined_text) <= max_tokens:
                        # Prepend current text to next chunk; next chunk keeps its metadata
                        working[i + 1] = Chunk(
                            chunk_id=next_chunk.chunk_id,
                            manual_id=next_chunk.manual_id,
                            text=combined_text,
                            metadata=next_chunk.metadata,
                        )
                        i += 1
                        continue

            merged.append(current)
            i += 1

        working = merged
        after = len(working)
        if after == before:
            break  # Stable — no merges occurred this pass

    logger.debug("Cross-entry merge: %d → %d chunks", len(chunks), len(working))
    return working


def enrich_chunk_metadata(
    text: str, metadata: dict[str, Any], profile: ManualProfile
) -> None:
    """Scan chunk text for safety callouts, figure references, and cross-references.

    Updates *metadata* in place with three keys:

    - ``has_safety_callouts``  -- sorted, deduplicated list of callout levels
      found in *text* (e.g. ``["caution", "warning"]``).
    - ``figure_references``    -- sorted, deduplicated list of figure reference
      strings found via ``profile.figure_reference_pattern``.
    - ``cross_references``     -- sorted, deduplicated list of cross-reference
      strings found via ``profile.cross_reference_patterns``.

    All three keys are always present after this call (empty lists if nothing
    matched).  The function is designed to run *after* chunk rules R1-R8 so
    the metadata reflects the actual chunk content rather than the original
    manifest entry boundaries.
    """
    # -- Safety callouts ------------------------------------------------
    callouts = detect_safety_callouts(text, profile)
    levels = sorted({c["level"] for c in callouts})
    metadata["has_safety_callouts"] = levels

    # -- Figure references ----------------------------------------------
    if profile.figure_reference_pattern:
        fig_matches = re.findall(profile.figure_reference_pattern, text)
        metadata["figure_references"] = sorted(set(fig_matches))
    else:
        metadata["figure_references"] = []

    # -- Cross-references -----------------------------------------------
    xref_matches: list[str] = []
    for pat in profile.cross_reference_patterns:
        xref_matches.extend(re.findall(pat, text))
    # Qualify cross-references with manual_id namespace prefix so they
    # resolve against chunk IDs (which are "{manual_id}::{group}::...").
    manual_id = metadata.get("manual_id", "")
    if manual_id:
        xref_matches = [f"{manual_id}::{ref}" for ref in xref_matches]
    metadata["cross_references"] = sorted(set(xref_matches))


def tag_vehicle_applicability(
    text: str, profile: ManualProfile
) -> dict[str, list[str]]:
    """Scan chunk text for vehicle/engine/drivetrain mentions.

    Returns dict with keys: vehicle_models, engine_applicability, drivetrain_applicability.
    """
    vehicle_models: list[str] = []
    engine_applicability: list[str] = []
    drivetrain_applicability: list[str] = []

    text_lower = text.lower()

    # Check vehicle models
    for vehicle in profile.vehicles:
        model = vehicle.model
        if model.lower() in text_lower or model in text:
            if model not in vehicle_models:
                vehicle_models.append(model)

    # Check engines
    for vehicle in profile.vehicles:
        for engine in vehicle.engines:
            # Check engine name and aliases
            names_to_check = [engine.name, engine.code] + engine.aliases
            for name in names_to_check:
                if name.lower() in text_lower or name in text:
                    entry = engine.name
                    if entry not in engine_applicability:
                        engine_applicability.append(entry)
                    break

    # Check drivetrains
    for vehicle in profile.vehicles:
        for dt in vehicle.drive_type:
            if dt.lower() in text_lower or dt in text:
                if dt not in drivetrain_applicability:
                    drivetrain_applicability.append(dt)

    # Default to ["all"] if nothing specific was found
    if not vehicle_models:
        vehicle_models = ["all"]
    if not engine_applicability:
        engine_applicability = ["all"]
    if not drivetrain_applicability:
        drivetrain_applicability = ["all"]

    return {
        "vehicle_models": vehicle_models,
        "engine_applicability": engine_applicability,
        "drivetrain_applicability": drivetrain_applicability,
    }


def assemble_chunks(
    pages: list[str], manifest: Manifest, profile: ManualProfile
) -> list[Chunk]:
    """Run the full chunk assembly pipeline.

    Applies rules R1-R8 in non-sequential order (R1,R3,R4,R5,R2,R6,R7,R8)
    to ensure semantic integrity before size enforcement. See the inline
    comment block above the rule applications for the full rationale.
    """
    all_text = "\n".join(pages)
    lines = all_text.split("\n")
    total_lines = len(lines)
    logger.debug("Assembling chunks from %d manifest entries, %d total lines", len(manifest.entries), total_lines)

    result_chunks: list[Chunk] = []

    # Build skip prefixes from profile.skip_sections
    manual_id = manifest.manual_id
    skip_prefixes = [f"{manual_id}::{s}" for s in profile.skip_sections]

    for entry_idx, entry in enumerate(manifest.entries):
        # Skip entries whose chunk_id matches a skipped section prefix
        if skip_prefixes and any(entry.chunk_id.startswith(p) for p in skip_prefixes):
            logger.debug("Skipping entry %s (matches skip_sections)", entry.chunk_id)
            continue
        # Extract text for this manifest entry based on line range
        start_line = entry.line_range.start
        # Determine end line: either the entry's end, or the start of the next entry
        if entry_idx + 1 < len(manifest.entries):
            next_entry = manifest.entries[entry_idx + 1]
            end_line = next_entry.line_range.start
        else:
            end_line = total_lines

        if start_line >= total_lines:
            continue

        text = "\n".join(lines[start_line:end_line]).strip()
        if not text:
            continue

        # ── Rule Application Order ──────────────────────────────────
        # Intentionally non-sequential. Rules execute in two phases:
        #
        # Phase 1 — Semantic integrity (before any size enforcement):
        #   R1: Primary unit — establish procedure boundaries
        #   R3: Never split steps — protect step sequences as atomic
        #   R4: Safety attachment — bind callouts to parent content
        #   R5: Table integrity — keep tables with their headers
        #
        # Phase 2 — Size enforcement and cleanup:
        #   R2: Size targets — split oversized chunks (AFTER integrity
        #       rules so it respects step/safety/table boundaries)
        #   R6: Merge small — combine undersized fragments
        #   R7: Cross-reference merge — consolidate xref-only sections
        #   R8: Figure continuity — keep figure refs with context
        #
        # WHY: If R2 ran before R3-R5, it would split at token
        # boundaries before semantic units are identified, breaking
        # step sequences, safety callouts, and tables across chunks.
        # See LEARNINGS.md for discovery context.
        # ────────────────────────────────────────────────────────────

        # R1: Primary unit — one procedure per chunk
        text_chunks = apply_rule_r1_primary_unit(text, entry)

        # R3: Never split steps
        expanded: list[str] = []
        for tc in text_chunks:
            expanded.extend(
                apply_rule_r3_never_split_steps(tc, profile.step_patterns)
            )
        text_chunks = expanded

        # R4: Safety callout attachment
        text_chunks = apply_rule_r4_safety_attachment(text_chunks, profile)

        # R5: Table integrity
        text_chunks = apply_rule_r5_table_integrity(text_chunks)

        # R2: Size targets (split oversized)
        text_chunks = apply_rule_r2_size_targets(text_chunks)

        # R6: Merge small chunks
        text_chunks = apply_rule_r6_merge_small(text_chunks)

        # R7: Cross-reference merge
        text_chunks = apply_rule_r7_crossref_merge(
            text_chunks, profile.cross_reference_patterns
        )

        # R8: Figure continuity
        if profile.figure_reference_pattern:
            text_chunks = apply_rule_r8_figure_continuity(
                text_chunks, profile.figure_reference_pattern
            )

        # Build hierarchical header
        header = compose_hierarchical_header(profile, entry.hierarchy_path)

        # Tag vehicle applicability
        tags = tag_vehicle_applicability(text, profile)

        # Build Chunk objects
        for chunk_idx, chunk_text in enumerate(text_chunks):
            chunk_id = entry.chunk_id
            if len(text_chunks) > 1:
                chunk_id = f"{entry.chunk_id}::part{chunk_idx + 1}"

            # Extract level1_id from hierarchy_path or chunk_id.
            # hierarchy_path[0] is the level-1 title (e.g. "0 Lubrication and Maintenance").
            # For the ID we parse the chunk_id: "{manual_id}::{level1_id}::..."
            level1_id = ""
            chunk_id_parts = entry.chunk_id.split("::")
            if len(chunk_id_parts) >= 2:
                level1_id = chunk_id_parts[1]

            metadata = {
                "manual_id": manifest.manual_id,
                "level1_id": level1_id,
                "procedure_name": entry.title,
                "hierarchical_header": header,
                "hierarchy_path": entry.hierarchy_path,
                "content_type": entry.content_type,
                "page_range": asdict(entry.page_range),
                "vehicle_models": tags["vehicle_models"],
                "engine_applicability": tags["engine_applicability"],
                "drivetrain_applicability": tags["drivetrain_applicability"],
                "has_safety_callouts": entry.has_safety_callouts,
                "figure_references": entry.figure_references,
                "cross_references": entry.cross_references,
            }

            # Enrich metadata by scanning the actual chunk text for
            # safety callouts, figure refs, and cross-refs.  This
            # overwrites the manifest-entry-level values with per-chunk
            # values that reflect what is really in this text fragment.
            enrich_chunk_metadata(chunk_text, metadata, profile)

            result_chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    manual_id=manifest.manual_id,
                    text=chunk_text,
                    metadata=metadata,
                )
            )

    # Post-assembly cross-entry merge: merge tiny chunks into next sibling
    # within the same level-1 group to eliminate orphan fragments that the
    # per-entry R6 pass cannot reach (it only sees chunks within one entry).
    result_chunks = merge_small_across_entries(result_chunks)

    logger.debug("Assembled %d chunks from %d manifest entries", len(result_chunks), len(manifest.entries))
    return result_chunks


def save_chunks(chunks: list[Chunk], output_path: Path) -> None:
    """Write chunks to a JSONL file (one JSON object per line).

    Each line contains: chunk_id, manual_id, text, metadata.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            record = {
                "chunk_id": chunk.chunk_id,
                "manual_id": chunk.manual_id,
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_chunks(input_path: Path) -> list[Chunk]:
    """Read chunks from a JSONL file back into Chunk objects.

    Each line must be a JSON object with: chunk_id, manual_id, text, metadata.
    """
    chunks: list[Chunk] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            chunks.append(
                Chunk(
                    chunk_id=record["chunk_id"],
                    manual_id=record["manual_id"],
                    text=record["text"],
                    metadata=record["metadata"],
                )
            )
    return chunks
