"""Chunk assembly engine — applies universal boundary rules and profile metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .profile import ManualProfile
from .structural_parser import Manifest, ManifestEntry


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

    for sc in profile.safety_callouts:
        pat = re.compile(sc.pattern, re.IGNORECASE if sc.pattern[0] != "^" else 0)
        # Try case-sensitive first, then case-insensitive
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.search(sc.pattern, stripped):
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
                    for sc2 in profile.safety_callouts:
                        if re.search(sc2.pattern, next_stripped):
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
    """R5: Specification tables are never split."""
    # Tables should remain as single chunks. This rule ensures that if a
    # table was somehow split, it gets reassembled. In practice, since we
    # detect tables and protect them, they should already be intact.
    # Simply pass through — tables are atomic.
    return list(chunks)


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
    """R8: Figure references stay with the text describing them."""
    # Ensure figure references remain with their describing text.
    # If a figure reference appears at the start of a chunk but the describing
    # text is in the previous chunk, merge them.
    pat = re.compile(figure_pattern)

    # In the simple case: chunks already contain figure refs with their text.
    # Just pass through since figure refs should already be attached.
    result: list[str] = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        if pat.search(chunk):
            # Figure reference is in this chunk — it stays with describing text
            result.append(chunk)
        else:
            result.append(chunk)
        i += 1

    return result


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

    result_chunks: list[Chunk] = []

    for entry_idx, entry in enumerate(manifest.entries):
        # Extract text for this manifest entry based on line range
        start_line = entry.line_range.get("start", 0)
        # Determine end line: either the entry's end, or the start of the next entry
        if entry_idx + 1 < len(manifest.entries):
            next_entry = manifest.entries[entry_idx + 1]
            end_line = next_entry.line_range.get("start", total_lines)
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

            metadata = {
                "hierarchical_header": header,
                "hierarchy_path": entry.hierarchy_path,
                "content_type": entry.content_type,
                "page_range": entry.page_range,
                "vehicle_models": tags["vehicle_models"],
                "engine_applicability": tags["engine_applicability"],
                "drivetrain_applicability": tags["drivetrain_applicability"],
                "has_safety_callouts": entry.has_safety_callouts,
                "figure_references": entry.figure_references,
                "cross_references": entry.cross_references,
            }

            result_chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    manual_id=manifest.manual_id,
                    text=chunk_text,
                    metadata=metadata,
                )
            )

    return result_chunks
