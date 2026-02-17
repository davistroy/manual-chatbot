# Improvement Recommendations

**Generated:** 2026-02-17
**Analyzed Project:** manual-chatbot — Smart Chunking Pipeline for Vehicle Service Manual RAG
**Baseline:** Multi-manual validation — CJ (11 errors, 1,406 warnings), TM9-8014 (342 errors, 74 warnings), XJ (QA passing)
**Supersedes:** Previous RECOMMENDATIONS.md (XJ output quality — all 4 phases complete, 439 tests passing)
**Based On:** FINDINGS.md (2026-02-17)

---

## Executive Summary

The XJ-1999 pipeline is production-ready (QA passing, 2,137 chunks, 0 errors). However, extending the pipeline to the remaining two profiled manuals (CJ Universal, TM9-8014) reveals that the multi-manual architecture has three code-level gaps and significant profile authoring work ahead. The CJ manual produces 1,172 false L1 boundaries and 59.6% undersized chunks. TM9-8014 has 342 cross-reference errors (100% failure rate) and detects only 1 of 4 chapters.

The findings fall into two categories: (1) pipeline code fixes that affect all manuals (cross-ref partial-path matching, regex OCR substitutions, character-spacing collapse), and (2) per-manual profile authoring that requires complete known_ids lists, filtering configuration, and expanded OCR substitutions. Both categories must be addressed before any non-XJ manual can pass QA.

Beyond the immediate fixes, four additional PDFs in the data folder have been assessed: TM9-8015-2 (strongest candidate, 311 pages, fair OCR) and TM9-8015-1 (188 pages, poor OCR) are viable for pipeline processing. M38A1wiring (image-only) and ORD_SNL_G-758 (parts catalog) are not suitable for the current prose pipeline.

---

## Recommendation Categories

### Category 1: Output Quality Enhancements

#### Q1. Cross-Reference Partial-Path Matching

**Priority:** Critical
**Effort:** S
**Impact:** Eliminates 342 errors in TM9-8014 (100% cross-ref failure rate); affects all manuals with hierarchical chunk IDs

**Current State:**
Cross-references in military TMs use flat paragraph numbers: `par. 69`, `fig. 11`. The `enrich_chunk_metadata()` function at `chunk_assembly.py:745-753` constructs targets as `{manual_id}::{ref}` (e.g., `tm9-8014-m38a1::69`). But chunk IDs are hierarchical: `tm9-8014-m38a1::1::IV::69`. The QA validator at `qa.py:255-293` checks three strategies (exact ID, exact prefix, string-prefix), but `tm9-8014-m38a1::69` matches none of them because no prefix starts with `::69` — the `69` is buried at the end of the hierarchy path.

The XJ manual doesn't hit this because its cross-refs use group numbers (`Group 8A`) that match L1 prefixes directly. Military TMs use paragraph numbers that only appear at L3+ in the hierarchy.

**Recommendation:**
Add a fourth resolution strategy to `check_cross_ref_validity()`: **suffix-segment matching**. A reference like `tm9-8014-m38a1::69` should resolve if any chunk ID contains `::69` as a terminal segment (i.e., `::69::` or `::69` at end). Implementation: extract the ref suffix after the last `::`, then check if any chunk ID ends with `::` + that suffix or contains `::` + suffix + `::`.

**Implementation Notes:**
- Change is in `qa.py` only (resolution logic), not in chunk_assembly.py (target construction is correct)
- Must not over-match: `::69` should not match `::169` or `::690`
- The suffix must be a complete segment between `::` delimiters
- ~15 lines of code change + 4 new tests
- Independent of all other recommendations

---

#### Q2. Regex-Based OCR Substitution Support

**Priority:** High
**Effort:** S
**Impact:** Enables pattern-based OCR cleanup; handles entire error classes with single rules instead of one-by-one literal substitutions

**Current State:**
`apply_known_substitutions()` at `ocr_cleanup.py:38-50` uses only `str.replace()` — literal string matching. Both CJ and TM9-8014 need pattern-based substitutions:
- CJ: Collapse `H U R R I C A N E` → `HURRICANE` (single-char-space pattern)
- TM9-8014: Fix `InstaZZation`/`Znstaklation`/`Instuzlution` variants (common OCR Z/I confusion)
- Both: Normalize figure references (`F I G .` → `FIG.`)

The `OcrCleanupConfig` dataclass at `profile.py:80-85` has no `regex_substitutions` field. The JSON Schema also lacks it.

**Recommendation:**
Add a `regex_substitutions` field to `OcrCleanupConfig` as a list of `{pattern: str, replacement: str}` dicts. Add a new function `apply_regex_substitutions()` that compiles patterns and calls `re.sub()`. Run regex substitutions AFTER literal substitutions in `clean_page()`. Update schema and profile validation to compile-check regex patterns during `load_profile()`.

**Implementation Notes:**
- 3 files changed: `profile.py` (dataclass + validation), `ocr_cleanup.py` (new function + call in clean_page), `schema/manual_profile_v1.schema.json`
- Regex substitutions run after literal subs to allow literal subs to "normalize" before patterns apply
- Pattern compilation should happen once during `load_profile()`, not per-page
- ~40 lines of code + 5 new tests
- The character-spacing collapse rule can then be written as a regex: `r'(?<![A-Za-z])([A-Z]) ([A-Z]) ([A-Z])(?: ([A-Z]))*'` → collapsed form

---

#### Q3. Character-Spacing Collapse Pre-Processor

**Priority:** High
**Effort:** S
**Impact:** Fixes CJ-F1 root cause (OCR renders `HURRICANE` as `H U R R I C A N E`); improves chunk text quality for embeddings; enables figure reference detection

**Current State:**
The CJ manual OCR systematically inserts spaces between characters in all-caps text. This causes: 476 false L1 `F` matches (from `F I G .`), undetectable figure references, degraded embedding quality, and overly broad header patterns. The profile has only 3 literal substitutions, far too few to cover all instances.

**Recommendation:**
Implement a dedicated character-spacing collapse function in `ocr_cleanup.py` that detects sequences of single uppercase characters separated by single spaces (e.g., `H U R R I C A N E`) and collapses them to the joined string (`HURRICANE`). This should run as a pre-processing step before other substitutions. Trigger it via a profile flag (`collapse_spaced_chars: true` on `OcrCleanupConfig`) so it's opt-in for manuals that exhibit this OCR artifact.

**Implementation Notes:**
- Regex: `r'\b([A-Z])(?: ([A-Z])){2,}\b'` — requires 3+ single-char sequences to avoid false positives on normal two-letter combinations
- Must preserve legitimate single-letter words and abbreviations
- Run BEFORE literal substitutions and regex substitutions (Q2) so downstream patterns see clean text
- Profile flag `collapse_spaced_chars: bool = False` on `OcrCleanupConfig`
- ~30 lines of code + 4 new tests
- Depends on Q2 only if implemented as a regex substitution; standalone function is independent

---

#### Q4. Vehicle Tagging for Universal Manuals

**Priority:** Low
**Effort:** XS
**Impact:** Adds specificity to vehicle tags when chunk text mentions specific models

**Current State:**
`tag_vehicle_applicability()` at `chunk_assembly.py:770-801` falls back to `["all"]` when no vehicle model string is found in chunk text. For universal manuals (CJ covers CJ-3B, CJ-5, DJ-5), every chunk gets `["all"]` because the text doesn't contain model strings — procedures apply universally. This is correct behavior but provides zero retrieval specificity.

**Recommendation:**
Accept the `["all"]` fallback as correct for universal manuals. Optionally, scan for model-specific callouts (e.g., "CJ-5 only", "DJ-5 equipped vehicles") and tag those chunks with the specific model in addition to the default. This is a minor enhancement — the existing fallback is acceptable.

**Implementation Notes:**
- Low priority — `["all"]` is functionally correct
- Could add model-specific regex scanning as an enhancement later
- No code change needed for current release

---

### Category 2: Profile Quality

#### P1. Production CJ Universal Profile

**Priority:** Critical
**Effort:** M
**Impact:** Enables pipeline processing of the 376-page CJ service manual (currently 11 errors, 1,406 warnings)

**Current State:**
`tests/fixtures/cj_universal_profile.yaml` has 5 known_ids (of 25 actual sections), no filtering, 3 literal substitutions, and a too-broad L1 pattern `^([A-Z])\s` that generates 1,172 false positives.

**Recommendation:**
Create `profiles/cj-universal.yaml` with:
1. Complete known_ids list (all 25 sections A through U, including compound IDs D1, F1, F2, J1)
2. Updated L1 `id_pattern`: `^([A-Z]\d?)\s` to capture compound section IDs
3. `require_known_id: true` on L1
4. Character-spacing collapse enabled (depends on Q3)
5. Expanded OCR substitutions and/or regex substitutions (depends on Q2)
6. Filtering: `min_content_words` and `require_blank_before` on L2
7. Page number pattern investigation and fix

**Implementation Notes:**
- Depends on Q2 (regex subs) and Q3 (character-spacing) for optimal results, but can be started with just `require_known_id` and expanded literal substitutions
- Keep test fixture unchanged for unit test isolation
- Compound IDs (D1, F1, F2, J1) need the L1 pattern update — test with real OCR to confirm OCR renders them as `D1`, `D 1`, or `D l` (lowercase L)

---

#### P2. Production TM9-8014 Profile

**Priority:** Critical
**Effort:** M
**Impact:** Enables pipeline processing of the 391-page military operator/maintenance manual (currently 342 errors, 74 warnings)

**Current State:**
`tests/fixtures/tm9_8014_profile.yaml` detects only 1 of 4 chapters (OCR garbles headings), has 4 literal substitutions (of which only 4 applied), and produces 342 cross-ref errors due to namespace mismatch (fixed by Q1).

**Recommendation:**
Create `profiles/tm9-8014.yaml` with:
1. Add OCR substitution `CHAPTEa → CHAPTER` (restores Chapter 4 detection)
2. Investigate Chapters 2 and 3 — add synthetic boundaries from known_ids if headings are image-only
3. Significantly expand substitution list (garbled headings, Z/I confusion, special chars)
4. Resolve L4/step collision: either remove L4 level entirely or add `require_blank_before: true` + `min_content_words: 20` to L4
5. Add `require_blank_before: true` and `min_content_words` to L3 to filter false paragraph matches
6. Keep `require_known_id: true` on L1 with known_ids for all 4 chapters

**Implementation Notes:**
- Cross-ref errors will be fixed by Q1 (partial-path matching), not by profile changes
- The L4/step collision (X-4) is a design decision: military TMs use `a.`, `b.`, `c.` for both sub-paragraph headings and procedural steps. Recommendation: remove L4 from TM profiles and treat sub-paragraphs as content within L3. This matches how the XJ profile handles it (no L4).
- 146 empty pages (37.3%) are image-only and cannot be fixed by profile changes
- Depends on Q1 for cross-ref fix, Q2 for regex substitutions (optional)

---

#### P3. L4/Step Pattern Collision Resolution

**Priority:** High
**Effort:** XS
**Impact:** Eliminates 334 false L4 boundaries and 74 orphaned-step warnings in TM9-8014; prevents same issue in future military TM profiles

**Current State:**
Both CJ and TM9-8014 profiles use `^([a-z])\.\s` as both the L4 sub-paragraph `id_pattern` AND a `step_pattern`. Every lettered step (`a.`, `b.`, `c.`) creates a structural boundary, fragmenting procedures into tiny L4 segments. The XJ profile avoids this by having no L4 level.

**Recommendation:**
For military TM profiles, remove the L4 hierarchy level entirely. Treat lettered sub-paragraphs as content within L3 paragraphs. The step_patterns configuration still recognizes `a.`, `b.`, `c.` for the "never split steps" rule (R3) without creating structural boundaries. This is consistent with how the XJ profile handles it.

For civilian manuals that genuinely have a 4th hierarchy level (e.g., section > subsection > procedure > sub-procedure), L4 can remain but must have strong filtering (`require_blank_before: true`, `min_content_words: 20`) to distinguish structural headings from procedural steps.

**Implementation Notes:**
- Profile-only change (remove L4 entries from TM profiles)
- No code change needed
- step_patterns remain unchanged — R3 still prevents splitting within step sequences

---

#### P4. TM9-8015-2 Profile (New Manual)

**Priority:** Medium
**Effort:** M
**Impact:** Adds 311-page power train/body/frame rebuild manual to the pipeline; strongest candidate among remaining PDFs

**Current State:**
No profile exists. PDF has fair OCR quality, 2 clean CHAPTER headers, 64 Section headers, 311 figure references. Same Chapter > Section > Paragraph hierarchy as TM9-8014. 12 chapters covering transmission, transfer case, axles, steering, brakes, springs, body, frame.

**Recommendation:**
Create `profiles/tm9-8015-2.yaml` based on the TM9-8014 profile template:
1. 12-chapter known_ids from TOC
2. `require_known_id: true` on L1
3. Section (Roman numeral) L2 pattern
4. Numbered paragraph L3 pattern with filtering
5. No L4 (per P3 decision)
6. OCR substitutions tuned to this manual's specific garbling patterns
7. Cross-references to TM9-8015-1 and TM9-8014 captured

**Implementation Notes:**
- Best OCR quality of all remaining manuals — good for proving the pipeline generalizes
- Depends on Q1 (cross-ref fix) for clean QA results
- Depends on P2 completion for lessons learned on military TM profile authoring
- Only 8 empty pages (vs. 146 in TM9-8014) — much better text coverage

---

#### P5. TM9-8015-1 Profile (New Manual)

**Priority:** Medium
**Effort:** M
**Impact:** Adds 188-page engine/clutch rebuild manual; completes the M38A1 service manual set

**Current State:**
No profile exists. OCR quality is poor — zero clean CHAPTER markers, only 4 Section headers survived. Body text reads reasonably well. Same hierarchy as TM9-8014 and TM9-8015-2.

**Recommendation:**
Create `profiles/tm9-8015-1.yaml`, but defer until after TM9-8015-2 is working. This manual will require:
1. Heavy reliance on known_ids (regex cannot match garbled chapter headings)
2. Aggressive OCR substitutions (more than TM9-8014)
3. Possibly supplemental OCR or manual annotation for image-only pages (14% empty)

**Implementation Notes:**
- Depends on P2 and P4 for lessons learned
- May expose the need for fuzzy heading matching or LLM-assisted boundary detection
- If OCR is too degraded, may need re-OCR before pipeline can produce usable output

---

### Category 3: Architecture Improvements

#### A1. Separate Test Fixtures from Production Profiles

**Priority:** Medium
**Effort:** XS
**Impact:** Prevents confusion between minimal test fixtures and complete production profiles; establishes clear workflow

**Current State:**
Test fixtures in `tests/fixtures/` are minimal (5 known_ids for CJ, 4 known_ids for TM9-8014). Production profiles live in `profiles/`. The XJ already follows this pattern (test fixture + separate production profile). CJ and TM9-8014 need the same treatment.

**Recommendation:**
Formalize the pattern: test fixtures stay minimal for unit test isolation, production profiles in `profiles/` are complete. Update CLAUDE.md to document this convention. Test fixtures should never be used for real PDF processing.

**Implementation Notes:**
- Already partially in place (XJ has both)
- P1 and P2 create the production profiles; this recommendation just formalizes the convention
- No code change needed

---

#### A2. Per-Pass Filter Logging

**Priority:** Low
**Effort:** XS
**Impact:** Faster debugging when filter passes produce unexpected boundary counts

**Current State:**
`filter_boundaries()` logs total before/after counts but not per-pass. When 1,745 boundaries become 1,745 (zero removed), there's no way to see that Pass 0 was disabled (no filtering config).

**Recommendation:**
Add per-pass INFO-level logging: `"Pass 0 (known_id): %d -> %d"`, `"Pass 1 (blank_before): %d -> %d"`, etc. This was recommended in the previous RECOMMENDATIONS.md and is still relevant.

**Implementation Notes:**
- 4-5 `logger.info()` calls in `filter_boundaries()`
- Zero behavioral change

---

### Category 4: Developer Experience

#### D1. Multi-Manual Regression Test Suite

**Priority:** High
**Effort:** M
**Impact:** Catches multi-manual issues before they reach production; the CJ/TM9-8014 failures were only discovered by running real PDFs manually

**Current State:**
439 unit tests cover individual modules. The XJ production profile has a regression test. But there is no test that validates CJ or TM9-8014 profiles against expected boundary/chunk counts, and no test that runs multiple profiles to verify cross-manual consistency.

**Recommendation:**
Create integration tests (marked `@pytest.mark.integration`) that:
1. Load each production profile and verify it passes schema validation
2. Verify known_ids completeness (count, compound ID presence)
3. Verify filtering is configured (require_known_id: true on L1)
4. Optionally run a small synthetic fixture through each profile and assert boundary counts

**Implementation Notes:**
- Does NOT require the real 50MB+ PDFs in the test suite
- Profile-level tests are lightweight (load + validate + compile patterns)
- Add a conftest fixture that discovers all YAML files in `profiles/`
- ~30 lines of test code per profile

---

#### D2. CLI Validation Report Enhancement

**Priority:** Low
**Effort:** S
**Impact:** Makes CLI output actionable when running validate on real manuals with hundreds of issues

**Current State:**
`cmd_validate()` logs every individual issue. With 1,406 CJ warnings, the output is unusable. This was recommended in the previous RECOMMENDATIONS.md (D3) and is still relevant — even more so now with multiple manuals.

**Recommendation:**
Group issues by `(check, severity)`, show count and a single example per group. Keep full detail behind `--verbose`.

**Implementation Notes:**
- Change in `cli.py` only
- Low priority but becomes important as more manuals are onboarded

---

### Category 5: New Capabilities

#### N1. Profile Bootstrapping from PDF

**Priority:** Medium
**Effort:** L
**Impact:** Reduces manual profile authoring from hours to minutes; critical for scaling beyond 5 manuals

**Current State:**
`cmd_bootstrap_profile()` is a stub. Profile authoring is manual — examine PDF, identify patterns, build known_ids, tune regex. The FINDINGS.md validation process demonstrated this takes significant effort.

**Recommendation:**
Defer to after current profiles are production-ready. Implementation should extract TOC pages, identify hierarchy patterns, and generate a draft YAML profile. The production XJ, CJ, and TM9-8014 profiles serve as few-shot examples.

**Implementation Notes:**
- Deferred — same recommendation as previous RECOMMENDATIONS.md
- The validation agents' approach (extract pages, analyze patterns, count matches) is essentially what bootstrap-profile should automate

---

#### N2. Image-Only Page Handling

**Priority:** Low
**Effort:** L
**Impact:** Recovers content from 146 empty pages in TM9-8014 (37.3% of the manual)

**Current State:**
pymupdf's `get_text()` returns empty strings for scanned image-only pages. These pages often contain critical diagrams, wiring schematics, and exploded views.

**Recommendation:**
Defer. Options for future work:
1. Supplemental OCR (Tesseract) on image-only pages
2. Vision model annotation (describe diagram contents for indexing)
3. Manual metadata chunks linking to page numbers

**Implementation Notes:**
- Significant effort with uncertain ROI
- The M38A1wiring.pdf (single-page, zero text) is the extreme case
- Vision model approach is most promising but requires API integration

---

## Quick Wins

| # | Recommendation | Effort | Impact |
|---|---------------|--------|--------|
| Q1 | Cross-ref partial-path matching | S | Eliminates 342 errors (code fix) |
| P3 | Remove L4 from military TM profiles | XS | Eliminates 334 false boundaries + 74 warnings |
| A1 | Formalize test fixture vs production profile convention | XS | Documentation clarity |
| A2 | Per-pass filter logging | XS | Better debugging |

These four can be completed in a single session and immediately improve multi-manual support.

---

## Strategic Initiatives

| # | Recommendation | Effort | Impact |
|---|---------------|--------|--------|
| Q2+Q3 | Regex subs + character-spacing collapse | S+S | Unlocks CJ and military TM OCR cleanup |
| P1+P2 | Production CJ + TM9-8014 profiles | M+M | Two more manuals through the pipeline |
| P4+P5 | TM9-8015-2 + TM9-8015-1 profiles | M+M | Complete the M38A1 manual set |
| D1 | Multi-manual regression suite | M | Prevents future regressions |
| N1 | Profile bootstrapping | L | Scaling enabler |

These require phased implementation and are covered in the Implementation Plan.

---

## Not Recommended

| Idea | Rationale |
|------|-----------|
| Fuzzy heading matching for OCR-damaged text | `require_known_id` with complete known_ids lists is more reliable and debuggable. Fuzzy matching introduces unpredictable behavior. If OCR is too damaged for regex, re-OCR is the right answer. |
| ML-based boundary classification | Same rationale as previous round — deterministic, closed-vocabulary patterns work for this corpus. Military TMs and Chrysler manuals both have standardized heading formats. |
| Processing ORD_SNL_G-758 (parts catalog) | Tabular parts listings need table-extraction, not prose chunking. The current R1-R8 rules are designed for maintenance procedures. Defer until a table-extraction pipeline exists. |
| Processing M38A1wiring.pdf | Single-page image with zero text. Not a pipeline candidate. Handle as supplemental visual reference. |
| Redesigning disambiguation algorithm | Q1 (known_ids filter) and Q3 (character-spacing) eliminate the inputs that cause cascade failures. The algorithm works correctly with clean inputs. |
| Adding Pydantic or changing to dataclass alternatives | 439 tests validate the current type system. Migration cost exceeds benefit. |

---

*Recommendations generated by Claude on 2026-02-17*
*Baseline: Multi-manual validation from FINDINGS.md*
