# Improvement Recommendations

**Generated:** 2026-02-16
**Analyzed Project:** manual-chatbot (Smart Chunking Pipeline for Vehicle Service Manual RAG)
**Input:** End-to-end pipeline run on 1,948-page XJ service manual — output quality analysis

---

## Executive Summary

The pipeline successfully processes the 1,948-page 1999 Jeep Cherokee (XJ) service manual end-to-end, producing 25,130 chunks in 17 MB of JSONL — but output quality has four systemic problems that make the chunks unsuitable for production RAG retrieval.

**Problem 1 — Boundary over-detection:** The level 2 hierarchy pattern `^([A-Z][A-Z ]{3,})$` matches ANY all-caps line with 4+ characters. In OCR'd wiring diagrams, component labels like "SWITCH" (206 occurrences), "LAMP" (179), "POWER" (175), "RELAY" (159) each trigger a section boundary. Result: 24,473 boundaries from 1,948 pages — roughly 12.5 boundaries per page, when a real service manual has ~2-3 structural transitions per page.

**Problem 2 — Tiny isolated chunks:** 61.6% of chunks (15,477) contain 5 words or fewer. Median chunk length is 3 words. R6 (merge small) cannot fix this because it operates within a single manifest entry's text, not across entries. A 1-word boundary creates a 1-word entry that R6 can never merge.

**Problem 3 — Wiring diagram noise:** The 8W Wiring Diagrams group accounts for 11,516 chunks (46% of all output), of which 7,478 (65%) contain 3 words or fewer. These are OCR'd component labels and wire color codes, not prose suitable for RAG. The profile already declares `wiring_diagrams.section_id: "8W"` but the pipeline ignores it.

**Problem 4 — Empty metadata enrichment:** Every chunk has `has_safety_callouts: []`, `figure_references: []`, `cross_references: []` despite 997 chunks containing WARNING/CAUTION/NOTE text and 2,287 chunks referencing figures. The detection functions exist (`detect_safety_callouts()`, figure pattern matching) but their results are never stored in chunk metadata. `build_manifest()` hardcodes these fields to `[]` and `assemble_chunks()` copies the empty values through.

All four issues are fixable with targeted changes. The pipeline architecture is sound — no redesign needed.

---

## Recommendation Categories

### Category 1: Boundary Pattern Precision

#### Q1. Tighten Level 2 (Section) Pattern to Require Multi-Word Headings

**Priority:** Critical
**Effort:** M
**Impact:** Eliminates ~12,000 false-positive boundaries, reducing chunk count by ~50%

**Current State:**
Level 2 `id_pattern` and `title_pattern` are both `^([A-Z][A-Z ]{3,})$`. This matches any all-caps line 4+ characters wide. In the XJ manual's OCR output, this fires on:
- Component labels in wiring diagrams: SWITCH (206x), LAMP (179x), POWER (175x), RELAY (159x), SENSOR (90x), MOTOR (84x)
- Single-word artifact lines: POSITION, INCORRECT, VEHICLES, EQUIPPED, PASSIVE
- Shredded WARNING text: "REFER TO" (94x), "WITH AIR- BAGS," (93x), "GROUP 8M -" (93x), "DEPLOYMENT AND" (101x)

These are NOT section headings. Real section headings in the XJ manual are multi-word phrases: "GENERAL INFORMATION", "TORQUE SPECIFICATIONS", "REMOVAL AND INSTALLATION", "COOLING SYSTEM", "DIFFERENTIAL AND DRIVELINE".

**Recommendation:**
1. **Require minimum 2 words** in the section pattern. Single uppercase words are component labels, not section titles.
2. **Increase minimum character count** from 4 to 8+ to avoid matching short fragments.
3. Consider adding a **negative match list** for known false-positive words common in wiring diagram OCR.

**Proposed pattern:**
```yaml
# Level 2 section: at least 2 uppercase words, 8+ total chars
id_pattern: "^([A-Z][A-Z]+(?:\\s+[A-Z][A-Z]+)+)$"
title_pattern: "^([A-Z][A-Z]+(?:\\s+[A-Z][A-Z]+)+)$"
```

This matches "GENERAL INFORMATION" and "COOLING SYSTEM" but rejects "SWITCH", "LAMP", "RELAY".

**Implementation Notes:**
- Profile YAML change only — no code change needed in structural_parser.py
- Must validate against actual section headings from the XJ manual to ensure no false negatives
- The pattern must still work for single-word group names that ARE valid at level 1 (e.g., "ENGINE", "BRAKES") — these are level 1, not level 2, so this change is safe

---

#### Q2. Tighten Level 3 (Procedure) Pattern

**Priority:** High
**Effort:** S
**Impact:** Reduces false-positive procedure boundaries by ~3,000-5,000

**Current State:**
Level 3 pattern `^([A-Z][A-Z \-\/\(\)]{5,})$` matches any all-caps line 6+ chars including hyphens, slashes, and parens. Too broad — matches component descriptions, table column headers, and OCR noise fragments.

Real procedure headings follow predictable patterns: "REMOVAL AND INSTALLATION", "DISASSEMBLY AND ASSEMBLY", "DIAGNOSIS AND TESTING", "ADJUSTMENT", "INSPECTION".

**Recommendation:**
Require at least 2 words and increase minimum length. Procedure headings in Chrysler manuals are multi-word action phrases.

**Proposed pattern:**
```yaml
title_pattern: "^([A-Z][A-Z]+(?:\\s+(?:AND|OR|OF|THE|IN|FOR|TO)\\s+)?[A-Z][A-Z \\-\\/\\(\\)]{3,})$"
```

**Implementation Notes:**
- Profile YAML change only
- Test against procedure headings extracted from the pipeline run
- The conjunction words (AND, OR, OF) are included because "REMOVAL AND INSTALLATION" is a canonical procedure heading format

---

#### Q3. Add Post-Detection Boundary Filtering in `detect_boundaries()`

**Priority:** High
**Effort:** M
**Impact:** Prevents the structural fragmentation that creates 1-3 word chunks even when patterns are correct

**Current State:**
`detect_boundaries()` matches patterns line-by-line with zero contextual validation. A line matching a section pattern immediately becomes a boundary, regardless of:
- Whether the previous boundary was 0 lines ago (back-to-back boundaries = false positives)
- Whether there's any content between boundaries (empty boundaries = junk chunks)
- Whether the line is embedded in the middle of a paragraph or stands alone

**Recommendation:**
Add a **post-detection filter** pass after boundary detection that removes suspect boundaries:

1. **Minimum gap filter**: If two boundaries at the same level are fewer than N lines apart (configurable, default: 3), keep only the first one. Back-to-back boundaries indicate OCR noise matching.
2. **Minimum content filter**: If a boundary has fewer than N words of content before the next boundary (configurable, default: 5), suppress it as a false positive.
3. **Standalone line check**: Optionally require section-level boundaries to be preceded by a blank line or page boundary.

Add these as **profile-configurable fields** on the hierarchy level:
```yaml
- level: 2
  name: "section"
  id_pattern: "..."
  title_pattern: "..."
  min_gap_lines: 3        # NEW: minimum lines between same-level boundaries
  min_content_words: 5     # NEW: minimum words before next boundary
  require_blank_before: true  # NEW: boundary line must follow blank line
```

**Implementation Notes:**
- New optional fields on `HierarchyLevel` dataclass (defaults to disabled for backward compat)
- Applied as a post-filter after `detect_boundaries()` returns, before `build_manifest()`
- Alternatively, integrate into `detect_boundaries()` itself by tracking previous boundary position
- Test: create a fixture with back-to-back uppercase words and verify filtering removes false positives

---

### Category 2: Chunk Assembly Improvements

#### Q4. Add Cross-Entry Merge Pass After Chunk Assembly

**Priority:** Critical
**Effort:** L
**Impact:** Merges ~15,000 tiny chunks into meaningful units — transforms the median chunk from 3 words to 50+ words

**Current State:**
`assemble_chunks()` processes each manifest entry independently. For each entry, it extracts text between `line_range.start` and the next entry's start, applies R1-R8, and produces chunks. R6 (merge small) operates only on the `text_chunks` list within that single entry — it can only merge fragments within one entry's text span.

If a manifest entry has 1 word of text (because the next boundary starts immediately), R6 produces a 1-word chunk and moves on. There is no mechanism to merge across entry boundaries. This is why 15,477 chunks are ≤5 words — they are structurally isolated.

**Recommendation:**
Add a **post-assembly cross-entry merge pass** that runs after all chunks are built:

```python
def merge_small_across_entries(chunks: list[Chunk], min_tokens: int = 200) -> list[Chunk]:
    """Merge undersized chunks into their next sibling within the same level-1 group."""
    result = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        tokens = count_tokens(chunk.text)
        if tokens < min_tokens and i + 1 < len(chunks):
            next_chunk = chunks[i + 1]
            # Only merge within the same level-1 group
            if chunk.metadata["level1_id"] == next_chunk.metadata["level1_id"]:
                # Absorb into next chunk
                next_chunk.text = chunk.text + "\n\n" + next_chunk.text
                i += 1
                continue
        result.append(chunk)
        i += 1
    return result
```

Call at the end of `assemble_chunks()` before returning.

**Implementation Notes:**
- New function in `chunk_assembly.py`
- Must respect level-1 group boundaries (don't merge across groups)
- The absorbing chunk keeps its own chunk_id and metadata (the small chunk's identity is lost, which is correct — it was too small to be a standalone retrieval unit)
- May need multiple passes until no chunk is below threshold
- Test: create manifest entries that produce tiny chunks, verify post-merge sizes

---

### Category 3: Special Content Handling

#### Q5. Add Section Skip List for Wiring Diagrams and Similar Non-Prose Content

**Priority:** Critical
**Effort:** S
**Impact:** Eliminates 11,516 junk chunks (46% of output) instantly

**Current State:**
The profile declares `content_types.wiring_diagrams.present: true` and `section_id: "8W"` but the pipeline never reads these fields. Every page in Group 8W is processed identically to prose pages — boundary detection fires on component labels, chunk assembly creates thousands of 1-3 word chunks, and the result is noise.

8W pages are wiring diagrams — the OCR text is wire colors, pin numbers, connector IDs, and component labels. This is not natural language and has zero RAG value as individual chunks.

**Recommendation:**
Add a `skip_sections` list to the profile schema and filter in `assemble_chunks()`:

```yaml
# In profile YAML
skip_sections:
  - "8W"  # Wiring diagrams — OCR produces non-prose noise
```

In `assemble_chunks()`, check `entry.chunk_id` against skip_sections. For entries in skipped sections, either:
- **Option A (recommended):** Skip entirely — produce no chunks
- **Option B:** Produce one summary chunk per group with `content_type: "wiring_diagram"` and metadata tag for filtering

**Implementation Notes:**
- Add `skip_sections: list[str]` field to `ManualProfile` (loaded from YAML)
- 5-line filter in `assemble_chunks()`: `if any(entry.chunk_id.startswith(f"{manual_id}::{skip}") for skip in profile.skip_sections): continue`
- Alternative: use existing `content_types.wiring_diagrams.section_id` instead of a new field
- Test: profile with `skip_sections: ["8W"]` produces zero chunks for 8W entries

---

### Category 4: Metadata Enrichment

#### Q6. Populate `has_safety_callouts` from Chunk Text

**Priority:** High
**Effort:** S
**Impact:** Enables safety-aware retrieval for 997 chunks containing WARNING/CAUTION/NOTE text

**Current State:**
Every chunk has `has_safety_callouts: []`. The detection function `detect_safety_callouts()` exists and works — R4 calls it to decide merging. But its results are never stored in metadata. `build_manifest()` hardcodes `has_safety_callouts=[]` and `assemble_chunks()` copies `entry.has_safety_callouts` (always `[]`) into the metadata dict at line 812.

The safety patterns (`^WARNING:`, `^CAUTION:`, `^NOTE:`) would match. The OCR text contains 997 chunks with these patterns. The wiring is just missing.

**Recommendation:**
In `assemble_chunks()`, after the rule pipeline produces final `text_chunks`, run `detect_safety_callouts()` on each chunk's text and store the detected callout levels in metadata:

```python
# After rule pipeline, for each final chunk_text:
callouts = detect_safety_callouts(chunk_text, profile)
safety_levels = sorted(set(c["level"] for c in callouts))
# Store in metadata:
metadata["has_safety_callouts"] = safety_levels
```

**Implementation Notes:**
- ~5 lines added to the chunk building loop in `assemble_chunks()`
- `detect_safety_callouts()` already handles pattern matching and extent finding
- Should scan the final chunk text (after all rules applied), not the raw manifest entry text
- Test: chunk containing "WARNING: DO NOT..." should have `["warning"]` in metadata

---

#### Q7. Populate `figure_references` from Chunk Text

**Priority:** High
**Effort:** S
**Impact:** Enables figure-aware retrieval for 2,287 chunks referencing figures

**Current State:**
Same wiring problem as Q6. The profile defines `figure_reference.pattern: "\\(Fig\\.\\s+(\\d+)\\)"`. R8 uses it for merge decisions. But detected figure numbers are never stored in metadata. Every chunk has `figure_references: []`.

**Recommendation:**
In `assemble_chunks()`, scan each final chunk text with the figure reference pattern and populate `figure_references`:

```python
if profile.figure_reference_pattern:
    fig_matches = re.findall(profile.figure_reference_pattern, chunk_text)
    metadata["figure_references"] = sorted(set(fig_matches))
```

**Implementation Notes:**
- 3 lines added to chunk building loop
- `re.findall` with the profile pattern extracts all figure numbers
- Deduplicate and sort for consistency

---

#### Q8. Populate `cross_references` from Chunk Text

**Priority:** Medium
**Effort:** S
**Impact:** Enables cross-reference navigation in retrieval

**Current State:**
`cross_references: []` for all chunks. Profile defines patterns `"Refer to Group (\\d+[A-Z]?)"` and `"Refer to (Section \\d+)"`. R7 uses these for merge decisions but never stores matches.

**Recommendation:**
In `assemble_chunks()`, scan each final chunk text with all cross-reference patterns:

```python
xrefs = []
for pattern in profile.cross_reference_patterns:
    xrefs.extend(re.findall(pattern, chunk_text))
metadata["cross_references"] = sorted(set(xrefs))
```

**Implementation Notes:**
- 4 lines added to chunk building loop
- Combine with Q6 and Q7 into a single "metadata enrichment" block after rule application
- Test: chunk containing "Refer to Group 8A" should have `["8A"]` in metadata

---

#### Q9. Combine Q6-Q8 into a Single Metadata Enrichment Pass

**Priority:** High (efficiency)
**Effort:** S
**Impact:** Clean code organization — one function handles all metadata population

**Recommendation:**
Create a `enrich_chunk_metadata()` function that takes the final chunk text, profile, and existing metadata dict, and populates all three fields:

```python
def enrich_chunk_metadata(
    text: str, metadata: dict, profile: ManualProfile
) -> None:
    """Populate safety callouts, figure refs, and cross-refs from chunk text."""
    # Safety callouts
    callouts = detect_safety_callouts(text, profile)
    metadata["has_safety_callouts"] = sorted(set(c["level"] for c in callouts))

    # Figure references
    if profile.figure_reference_pattern:
        metadata["figure_references"] = sorted(set(
            re.findall(profile.figure_reference_pattern, text)
        ))

    # Cross references
    xrefs = []
    for pattern in profile.cross_reference_patterns:
        xrefs.extend(re.findall(pattern, text))
    metadata["cross_references"] = sorted(set(xrefs))
```

---

## Quick Wins

1. **Q5: Skip wiring diagrams** — Add `skip_sections` field + 5-line filter. Eliminates 46% of junk chunks.
2. **Q6+Q7+Q8 (via Q9): Metadata enrichment** — ~15 lines of new code. Wires existing detection logic into output. No new algorithms.
3. **Q1+Q2: Tighten patterns** — Profile YAML changes only, no code. Requires validation against real headings.

## Strategic Initiatives

1. **Q4: Cross-entry merge** — New function with hierarchy-aware merge logic. Highest structural impact on chunk quality.
2. **Q3: Boundary post-filtering** — New schema fields + filter logic. Generalizable to all manual profiles.

## Not Recommended

| Item | Rationale |
|------|-----------|
| **LLM-based boundary detection** | Overkill. Regex patterns work perfectly for Chrysler manuals' highly regular structure — the problem is pattern specificity, not approach. |
| **Real tokenizer (tiktoken)** | Word-count approximation is fine for merge/split decisions. Whether a 3-word chunk has 3 or 4 BPE tokens doesn't change that it's too small. |
| **OCR re-processing of wiring diagrams** | Better OCR won't help — wiring diagram content is inherently non-prose. Skip or tag is the right approach. |
| **ML section classifier** | The hierarchical structure of Chrysler manuals is deterministic, not probabilistic. Regex is the right tool. |

---

*Recommendations generated by Claude on 2026-02-16*
*Source: End-to-end pipeline run on 1999 XJ Service Manual (1,948 pages → 25,130 chunks)*
