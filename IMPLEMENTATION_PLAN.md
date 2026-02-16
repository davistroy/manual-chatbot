# Implementation Plan: Production Output Quality

**Generated:** 2026-02-16
**Based On:** RECOMMENDATIONS.md (end-to-end XJ pipeline run analysis)
**Supersedes:** Previous IMPLEMENTATION_PLAN.md (REVIEW.md remediation — all 4 phases complete, 349 tests passing)
**Total Phases:** 3
**Estimated Total Effort:** ~180K tokens

---

## Plan Overview

This plan addresses the four production output quality issues identified by running the real 1,948-page XJ service manual through the pipeline. The previous plan (architectural remediation) is fully complete — 349 tests passing. This plan builds on that foundation.

**Strategy:** Fix the highest-impact, lowest-risk items first. Phase 1 handles the quick wins (skip list + metadata wiring + pattern tightening). Phase 2 adds the structural fix (cross-entry merge). Phase 3 adds the generalizable boundary filtering. Each phase is independently valuable and leaves the pipeline in a better state.

**Validation approach:** After each phase, re-run the full XJ pipeline and measure:
- Total chunk count (target: <5,000 from current 25,130)
- Tiny chunk percentage (target: <10% from current 61.6%)
- Metadata population rate (target: >90% of chunks with relevant safety/figure data populated)

### Phase Summary Table

| Phase | Focus Area | Key Deliverables | Est. Tokens | Dependencies |
|-------|------------|------------------|-------------|--------------|
| 1 | Quick Wins | Skip sections, metadata enrichment, pattern tightening | ~60K | None |
| 2 | Chunk Merging | Cross-entry merge pass, merge threshold tuning | ~60K | Phase 1 (pattern fix reduces noise before merging) |
| 3 | Boundary Intelligence | Post-detection filtering, schema extensions, contextual validation | ~60K | Phase 1 (patterns must be baselined first) |

---

## Phase 1: Quick Wins — Skip List, Metadata, Patterns

**Estimated Effort:** ~60,000 tokens (including testing/fixes)
**Dependencies:** None
**Parallelizable:** 1.1, 1.2, 1.3 are independent and can run concurrently

### Goals

- Eliminate wiring diagram noise (46% of junk chunks)
- Populate safety callout, figure reference, and cross-reference metadata
- Tighten hierarchy patterns to reject single-word false positives

### Work Items

#### 1.1 Add Section Skip List

**Recommendation Ref:** Q5
**Files Affected:**
- `src/pipeline/profile.py` (modify — add `skip_sections` field to `ManualProfile`, load from YAML)
- `src/pipeline/chunk_assembly.py` (modify — add skip filter in `assemble_chunks()`)
- `tests/fixtures/xj_1999_profile.yaml` (modify — add `skip_sections: ["8W"]`)
- `tests/test_chunk_assembly.py` (modify — add skip list tests)
- `tests/test_profile.py` (modify — add skip_sections loading test)
- `schema/manual_profile_v1.schema.json` (modify — add skip_sections property)

**Description:**
Add `skip_sections` field to `ManualProfile` that lists level-1 section IDs to exclude from chunk assembly. When processing manifest entries, skip any entry whose chunk_id starts with a skipped section prefix.

**Tasks:**
1. [ ] Add `skip_sections: list[str] = field(default_factory=list)` to `ManualProfile` dataclass
2. [ ] Update `load_profile()` to read `data.get("skip_sections", [])` and populate the field
3. [ ] Add `skip_sections` to schema JSON
4. [ ] In `assemble_chunks()`, add early `continue` for entries matching skip list:
   ```python
   skip_prefixes = [f"{manual_id}::{s}" for s in profile.skip_sections]
   # In the entry loop:
   if any(entry.chunk_id.startswith(p) for p in skip_prefixes):
       continue
   ```
5. [ ] Add `skip_sections: ["8W"]` to `tests/fixtures/xj_1999_profile.yaml`
6. [ ] Add test: profile with skip_sections, verify skipped entries produce zero chunks
7. [ ] Add test: profile without skip_sections, verify all entries processed (backward compat)
8. [ ] Run full test suite — all 349 tests must pass

**Acceptance Criteria:**
- [ ] `skip_sections` field loads from profile YAML
- [ ] Entries in skipped sections produce no chunks
- [ ] Existing profiles without `skip_sections` work unchanged
- [ ] All tests pass

---

#### 1.2 Add Metadata Enrichment Function

**Recommendation Ref:** Q6, Q7, Q8, Q9
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify — add `enrich_chunk_metadata()`, call in `assemble_chunks()`)
- `tests/test_chunk_assembly.py` (modify — add enrichment tests)

**Description:**
Create `enrich_chunk_metadata()` function that scans chunk text for safety callouts, figure references, and cross-references, then stores results in the metadata dict. Call this for each final chunk in `assemble_chunks()`.

**Tasks:**
1. [ ] Add `enrich_chunk_metadata(text, metadata, profile)` function:
   - Run `detect_safety_callouts(text, profile)` → extract unique levels → store in `metadata["has_safety_callouts"]`
   - Run `re.findall(profile.figure_reference_pattern, text)` → deduplicate → store in `metadata["figure_references"]`
   - Run `re.findall` for each `profile.cross_reference_patterns` → deduplicate → store in `metadata["cross_references"]`
2. [ ] Call `enrich_chunk_metadata(chunk_text, metadata, profile)` in the chunk building loop, after constructing the metadata dict (replacing the hardcoded empty lists from `entry.has_safety_callouts` etc.)
3. [ ] Add test: chunk with "WARNING: DO NOT..." → `has_safety_callouts: ["warning"]`
4. [ ] Add test: chunk with "(Fig. 12)" → `figure_references: ["12"]`
5. [ ] Add test: chunk with "Refer to Group 8A" → `cross_references: ["8A"]`
6. [ ] Add test: chunk with no matches → all three fields are empty lists (not missing)
7. [ ] Add test: chunk with multiple callout types → sorted list `["caution", "warning"]`
8. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] Safety callout levels detected and stored in metadata
- [ ] Figure reference numbers detected and stored in metadata
- [ ] Cross-reference targets detected and stored in metadata
- [ ] All three fields present even when empty (empty list, not missing key)
- [ ] All tests pass

---

#### 1.3 Tighten Hierarchy Patterns in XJ Profile

**Recommendation Ref:** Q1, Q2
**Files Affected:**
- `tests/fixtures/xj_1999_profile.yaml` (modify — update level 2 and 3 patterns)
- `tests/test_structural_parser.py` (modify — update or add pattern matching tests)

**Description:**
Update the XJ profile's level 2 (section) and level 3 (procedure) patterns to require multi-word headings, rejecting single-word OCR artifacts.

**Tasks:**
1. [ ] First, extract actual section and procedure headings from the XJ pipeline output to build a validation set:
   ```python
   # Run against current output to find real headings vs false positives
   # Real section headings: "GENERAL INFORMATION", "COOLING SYSTEM", etc.
   # False positives: "SWITCH", "LAMP", "RELAY", etc.
   ```
2. [ ] Update level 2 patterns to require 2+ uppercase words:
   ```yaml
   id_pattern: "^([A-Z][A-Z]+(?:\\s+[A-Z][A-Z]+)+)$"
   title_pattern: "^([A-Z][A-Z]+(?:\\s+[A-Z][A-Z]+)+)$"
   ```
3. [ ] Update level 3 pattern to require 2+ words or minimum 10 chars:
   ```yaml
   title_pattern: "^([A-Z][A-Z]+(?:\\s+[A-Z][A-Z \\-\\/\\(\\)]+)+)$"
   ```
4. [ ] Validate the new patterns against the extracted heading set — ensure zero false negatives for real headings
5. [ ] Update tests in `test_structural_parser.py` that use the XJ profile patterns
6. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] Level 2 pattern rejects single-word lines (SWITCH, RELAY, etc.)
- [ ] Level 2 pattern matches real section headings (GENERAL INFORMATION, COOLING SYSTEM, etc.)
- [ ] Level 3 pattern rejects short fragments
- [ ] Level 3 pattern matches real procedure headings (REMOVAL AND INSTALLATION, etc.)
- [ ] All tests pass

---

### Phase 1 Testing Requirements

- [ ] Skip list functionality tested (skip, no-skip, backward compat)
- [ ] Metadata enrichment tested for all three field types + edge cases
- [ ] Pattern changes validated against real headings
- [ ] All 349+ existing tests pass
- [ ] New tests added: ~12-15

### Phase 1 Validation

After all work items complete, re-run the XJ pipeline and measure:
```bash
pipeline -v process --profile tests/fixtures/xj_1999_profile.yaml \
  --pdf "data/99 XJ Service Manual.pdf" --output-dir output/
```

**Expected improvements:**
- Chunk count: ~25,130 → ~8,000-12,000 (8W elimination + fewer false boundaries)
- Tiny chunks (≤5 words): 61.6% → ~30-40% (pattern fix helps, but cross-entry merge needed for full fix)
- Metadata: 0 safety/figure/xref → populated on relevant chunks

### Phase 1 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing (`pytest -v --tb=short`)
- [ ] XJ pipeline re-run shows measurable improvement
- [ ] No regressions introduced

---

## Phase 2: Cross-Entry Chunk Merging

**Estimated Effort:** ~60,000 tokens (including testing/fixes)
**Dependencies:** Phase 1 (pattern tightening reduces noise — merging works better on cleaner boundaries)
**Parallelizable:** 2.1 and 2.2 are sequential (merge function first, then tuning)

### Goals

- Merge undersized chunks across manifest entry boundaries
- Reduce tiny chunk percentage to <10%
- Produce chunks in the 200-2000 word target range

### Work Items

#### 2.1 Implement Cross-Entry Merge Function

**Recommendation Ref:** Q4
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify — add `merge_small_across_entries()`, call in `assemble_chunks()`)
- `tests/test_chunk_assembly.py` (modify — add merge tests)

**Description:**
Add a post-assembly merge pass that iterates the full chunk list and merges any chunk below `min_tokens` into its next sibling within the same level-1 group. Run multiple passes until stable.

**Tasks:**
1. [ ] Add `merge_small_across_entries(chunks: list[Chunk], min_tokens: int = 200) -> list[Chunk]`:
   - Iterate chunks left to right
   - For each chunk with `count_tokens(text) < min_tokens`:
     - If next chunk exists and has same `level1_id`: prepend current text to next chunk's text
     - Otherwise: keep as-is (group boundary or last chunk)
   - Run until no merges occur (convergence loop, max 10 passes)
2. [ ] Handle metadata merge: when absorbing a small chunk, the absorbing chunk keeps its own metadata. Optionally concatenate `hierarchy_path` breadcrumbs.
3. [ ] Call `merge_small_across_entries(result_chunks)` at end of `assemble_chunks()` before return
4. [ ] Add logging: `logger.debug("Cross-entry merge: %d → %d chunks", before, after)`
5. [ ] Add test: 5 chunks of [10, 5, 300, 8, 400] words → merge produces [315, 408] (tiny chunks absorbed into next sibling)
6. [ ] Add test: chunks spanning level1 boundary → no merge across boundary
7. [ ] Add test: single tiny chunk at end of group → kept as-is (no next sibling to merge into)
8. [ ] Add test: convergence — chain of tiny chunks all merge in sequence
9. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] Chunks below `min_tokens` are merged into next sibling
- [ ] Level-1 group boundaries are respected
- [ ] Multiple passes converge (no infinite loop)
- [ ] Merged chunks maintain valid metadata
- [ ] All tests pass

---

#### 2.2 Tune Merge Thresholds and Validate

**Recommendation Ref:** Q4 (tuning)
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify — adjust thresholds if needed)
- `tests/test_chunk_assembly.py` (modify — add validation tests)

**Description:**
After implementing the merge function, run the full XJ pipeline and analyze the output to tune the `min_tokens` threshold. The goal is <10% tiny chunks while not creating oversized merged chunks.

**Tasks:**
1. [ ] Run XJ pipeline with `min_tokens=200`, measure chunk size distribution
2. [ ] If too many tiny chunks remain, try `min_tokens=100` (more aggressive merging)
3. [ ] If merged chunks are too large (>2000 tokens), add a max-merge-size guard:
   ```python
   merged_tokens = count_tokens(chunk.text + "\n\n" + next_chunk.text)
   if merged_tokens > 2000:
       result.append(chunk)  # Don't merge — would exceed size target
   ```
4. [ ] Document final threshold choice in code comment
5. [ ] Add test: merge doesn't create chunks exceeding 2000 tokens
6. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] Tiny chunk percentage <10%
- [ ] No merged chunks exceed 2000 tokens
- [ ] Threshold documented
- [ ] All tests pass

---

### Phase 2 Testing Requirements

- [ ] Cross-entry merge logic tested with various chunk size distributions
- [ ] Group boundary respect tested
- [ ] Convergence loop tested (no infinite loop)
- [ ] Max-merge-size guard tested
- [ ] All 349+ existing tests pass
- [ ] New tests added: ~8-10

### Phase 2 Validation

After completion, re-run XJ pipeline and measure:
- Chunk count: should drop to ~3,000-5,000
- Tiny chunks (≤5 words): should drop to <10%
- Average chunk size: should be 50-200 words
- Max chunk size: should stay ≤2,000 words

### Phase 2 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing
- [ ] XJ pipeline produces <10% tiny chunks
- [ ] Chunk size distribution in target range
- [ ] No regressions introduced

---

## Phase 3: Boundary Intelligence

**Estimated Effort:** ~60,000 tokens (including testing/fixes)
**Dependencies:** Phase 1 (patterns must be baselined before adding filtering logic)
**Parallelizable:** 3.1 and 3.2 are sequential; 3.3 is independent

### Goals

- Add configurable boundary post-filtering to catch remaining false positives
- Make the filtering generalizable to other manual profiles (CJ, TM9)
- Add boundary validation diagnostics for profile tuning

### Work Items

#### 3.1 Add Boundary Filter Configuration to Schema

**Recommendation Ref:** Q3
**Files Affected:**
- `src/pipeline/profile.py` (modify — add filter fields to `HierarchyLevel`)
- `schema/manual_profile_v1.schema.json` (modify — add filter properties)
- `tests/test_profile.py` (modify — add loading tests for new fields)

**Description:**
Add optional boundary filtering fields to the `HierarchyLevel` dataclass: `min_gap_lines`, `min_content_words`, `require_blank_before`. These configure the post-detection filter in 3.2.

**Tasks:**
1. [ ] Add fields to `HierarchyLevel`:
   ```python
   min_gap_lines: int = 0          # 0 = disabled
   min_content_words: int = 0      # 0 = disabled
   require_blank_before: bool = False
   ```
2. [ ] Update `load_profile()` to read these fields from YAML
3. [ ] Add to schema JSON with default values
4. [ ] Add test: profile with filter fields loads correctly
5. [ ] Add test: profile without filter fields loads with defaults (backward compat)
6. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] Filter fields load from YAML
- [ ] Defaults are disabled (no change to existing behavior)
- [ ] Schema validates
- [ ] All tests pass

---

#### 3.2 Implement Boundary Post-Filter

**Recommendation Ref:** Q3
**Files Affected:**
- `src/pipeline/structural_parser.py` (modify — add `filter_boundaries()` function)
- `src/pipeline/cli.py` (modify — call filter after detect_boundaries)
- `tests/test_structural_parser.py` (modify — add filter tests)

**Description:**
Add `filter_boundaries()` that takes detected boundaries, the profile, and cleaned page text, and removes boundaries that fail the configured filters.

**Tasks:**
1. [ ] Add `filter_boundaries(boundaries, profile, pages) -> list[Boundary]`:
   - **min_gap_lines**: For each level with `min_gap_lines > 0`, iterate boundaries at that level. If the gap (in lines) between consecutive same-level boundaries is less than `min_gap_lines`, remove the second one.
   - **min_content_words**: For each boundary, count words between it and the next boundary. If below `min_content_words`, remove the boundary.
   - **require_blank_before**: For each level with `require_blank_before = True`, check if the boundary line is preceded by a blank line (in the page text). If not, remove the boundary.
2. [ ] Call `filter_boundaries()` in `cmd_process()` and `cmd_validate()` between `detect_boundaries()` and `build_manifest()`
3. [ ] Add logging: `logger.info("Boundary filter: %d → %d boundaries", before, after)`
4. [ ] Add test: back-to-back boundaries with `min_gap_lines=3` → second removed
5. [ ] Add test: boundary with 2 words content and `min_content_words=5` → removed
6. [ ] Add test: boundary without preceding blank line and `require_blank_before=True` → removed
7. [ ] Add test: all filters disabled → boundaries unchanged (backward compat)
8. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] Minimum gap filter removes back-to-back boundaries
- [ ] Minimum content filter removes empty/trivial boundaries
- [ ] Blank-line-before filter removes mid-paragraph matches
- [ ] All filters disabled by default
- [ ] All tests pass

---

#### 3.3 Add Boundary Diagnostics Command

**Recommendation Ref:** Q3 (tooling)
**Files Affected:**
- `src/pipeline/cli.py` (modify — add `diagnose` subcommand or enhance `validate`)

**Description:**
Add diagnostic output to help tune boundary patterns and filters. When running `pipeline validate`, output a boundary quality summary: total boundaries, boundaries per page, content size distribution between boundaries, suspected false positives.

**Tasks:**
1. [ ] Add boundary diagnostics section to `cmd_validate()` output:
   ```
   Boundary diagnostics:
     Total boundaries: 24,473
     Boundaries per page: 12.5 avg
     Content between boundaries: min=0, median=3, avg=25, max=2000 words
     Suspected false positives (≤3 words between): 15,200 (62%)
     Level distribution: group=2873, section=13109, procedure=9095, sub-procedure=53
   ```
2. [ ] Add `--diagnostics` flag to `validate` subcommand for verbose boundary analysis
3. [ ] Optionally: dump suspected false-positive boundaries to a TSV file for manual review
4. [ ] Add test: diagnostics output is generated without errors
5. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] `pipeline validate --diagnostics` shows boundary quality metrics
- [ ] False-positive rate is calculated and displayed
- [ ] Level distribution is shown
- [ ] All tests pass

---

### Phase 3 Testing Requirements

- [ ] Filter configuration loads and defaults correctly
- [ ] Each filter type tested independently
- [ ] Combined filters tested
- [ ] Backward compatibility verified (all filters disabled)
- [ ] Diagnostics output tested
- [ ] All 349+ existing tests pass
- [ ] New tests added: ~10-15

### Phase 3 Validation

After completion, re-run XJ pipeline with tuned filters and measure:
- Expected boundary count: ~3,000-5,000 (from 24,473)
- Expected chunk count: ~2,000-4,000
- Expected tiny chunks: <5%

### Phase 3 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing
- [ ] XJ pipeline produces high-quality chunks suitable for RAG
- [ ] Boundary diagnostics help with profile tuning
- [ ] CLAUDE.md updated with new profile fields and CLI flags
- [ ] No regressions introduced

---

## Parallel Work Opportunities

Phase 1 work items are fully independent — all three can execute concurrently:

| Work Item | Can Run With | Notes |
|-----------|--------------|-------|
| 1.1 (skip list) | 1.2, 1.3 | Different files: profile.py + assembly vs. assembly metadata vs. YAML |
| 1.2 (metadata enrichment) | 1.1, 1.3 | Only touches chunk_assembly.py metadata section |
| 1.3 (patterns) | 1.1, 1.2 | Only touches YAML profile + parser tests |
| 2.1 (merge function) | — | Must complete before 2.2 |
| 2.2 (tuning) | — | Depends on 2.1 |
| 3.1 (schema) | — | Must complete before 3.2 |
| 3.2 (filter) | 3.3 | Filter implementation is independent from diagnostics |
| 3.3 (diagnostics) | 3.2 | Can develop diagnostics while filter is being built |

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pattern changes cause false negatives (real headings missed) | Medium | High | Extract real headings from current output as validation set before changing patterns. Test against this set. |
| Cross-entry merge creates oversized chunks | Medium | Medium | Add max-merge-size guard (2000 token cap). Test with real pipeline output. |
| Skip list removes content that has RAG value | Low | Medium | The 8W group is genuinely non-prose. Can always remove sections from skip list later. |
| Boundary filter is too aggressive | Medium | Medium | All filters disabled by default. Enable incrementally with conservative thresholds. |
| Metadata enrichment is slow on large chunks | Low | Low | Safety detection is O(lines × patterns). With ~5 patterns and chunks ≤2000 words, this is negligible. |
| Existing tests break from pattern changes | Medium | Low | Pattern changes affect test fixtures that use the old patterns. Update fixtures alongside patterns. |

---

## Success Metrics

| Metric | Current (Baseline) | Phase 1 Target | Phase 2 Target | Phase 3 Target |
|--------|-------------------|----------------|----------------|----------------|
| Total chunks | 25,130 | ~12,000 | ~4,000 | ~3,000 |
| Tiny chunks (≤5 words) | 61.6% | ~35% | <10% | <5% |
| Median chunk words | 3 | ~15 | ~80 | ~100 |
| Safety callouts populated | 0 | ~900+ | ~900+ | ~900+ |
| Figure refs populated | 0 | ~2,000+ | ~2,000+ | ~2,000+ |
| Cross-refs populated | 0 | ~200+ | ~200+ | ~200+ |
| 8W junk chunks | 11,516 | 0 | 0 | 0 |
| All tests passing | 349 | 360+ | 370+ | 385+ |

---

*Implementation plan generated by Claude on 2026-02-16*
*Source: RECOMMENDATIONS.md (XJ pipeline output quality analysis)*
