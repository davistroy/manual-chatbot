# Pipeline Validation Findings

**Date:** 2026-02-17
**Scope:** Full pipeline validation of CJ Universal and TM9-8014 manuals against real PDFs, plus assessment of 4 remaining PDFs in `data/`
**Method:** End-to-end pipeline execution (OCR cleanup -> structural parsing -> chunk assembly -> QA validation) with automated analysis

---

## Executive Summary

Both existing non-XJ profiles (CJ Universal and TM9-8014) fail pipeline validation when run against their real PDFs. The XJ-1999 profile is the only production-ready profile. The two test fixture profiles were written for unit testing with minimal `known_ids` and no filtering configuration, and they produce unusable output when applied to actual manual content.

**Root causes are consistent across both manuals:**
1. Test fixture profiles lack the completeness needed for production use
2. No boundary filtering is configured on any hierarchy level
3. OCR substitution lists are too short for the actual OCR error density
4. Cross-reference namespace resolution is broken for hierarchical chunk IDs

Four additional PDFs were assessed. Two (TM9-8015-1, TM9-8015-2) are strong candidates for pipeline processing. Two (M38A1wiring, ORD_SNL_G-758) are not suitable for the current prose-chunking pipeline.

---

## CJ Universal Service Manual (SM-1046)

**PDF:** `data/53-71 CJ5 Service Manual.pdf` (376 pages, 11 empty)
**Profile:** `tests/fixtures/cj_universal_profile.yaml`
**QA Result:** FAILED (11 errors, 1,406 warnings)

### Pipeline Metrics

| Stage | Metric | Value |
|-------|--------|-------|
| OCR Quality | Dictionary match rate | 0.890 |
| OCR Quality | Garbage line rate | 0.054 |
| OCR Quality | Needs re-OCR | False |
| Structural Parsing | Raw boundaries | 1,745 |
| Structural Parsing | Filtered boundaries | 1,745 (0 removed) |
| Structural Parsing | L1 matches | 1,172 (expected ~25) |
| Chunk Assembly | Total chunks | 1,224 |
| Chunk Assembly | Undersized (<200 tokens) | 730 (59.6%) |
| Chunk Assembly | In range (200-2000) | 494 (40.4%) |
| Chunk Assembly | Mean tokens | 160 |
| Chunk Assembly | Vehicle tagged | 0/1,224 |
| QA | Errors | 11 |
| QA | Warnings | 1,406 |

### CJ-F1: L1 Pattern Generates 1,172 False Positives [CRITICAL]

**Pattern:** `^([A-Z])\s`
**Expected matches:** ~25 (actual section boundaries A through U)
**Actual matches:** 1,172

The pattern matches ANY line beginning with a capital letter followed by a space. The OCR has a characteristic failure mode where all-caps text is rendered with spaces between letters (e.g., `H U R R I C A N E` instead of `HURRICANE`). This makes the first character of every spaced-out word match the L1 pattern.

Worst offenders by letter:
- `F`: 476 matches (figure captions like `F I G . D-14...`)
- `A`: 86 matches (sentences starting with "A")
- `H`: 85 matches (`H U R R I C A N E F4 ENGINE`)
- `D`: 81 matches (`D A U N T L E S S V-6`)
- `P`: 70 matches (`P A R .` spaced text)
- `C`: 57 matches (spaced-out words)

**Fix options:**
1. Set `require_known_id: true` on L1 (reduces from 1,172 to ~25 immediately)
2. Change pattern to `^([A-Z])\s*$` (require standalone letter)
3. Add OCR cleanup rule to collapse single-character-space patterns before structural parsing

### CJ-F2: Known IDs List Covers Only 5 of 25 Sections [CRITICAL]

The profile lists 5 known section IDs (A, B, C, D, H). The actual manual TOC shows 25 sections:

| ID | Title | In Profile? |
|----|-------|:-----------:|
| A | General Data | Yes |
| B | Lubrication | Yes |
| C | Tune-Up | Yes |
| D | Hurricane F4 Engine | Yes |
| D1 | Dauntless V-6 Engine | No |
| E | Fuel System | No |
| F | Exhaust System | No |
| F1 | Exhaust Emission Control (F4) | No |
| F2 | Exhaust Emission Control (V6) | No |
| G | Cooling System | No |
| H | Electrical | Yes |
| I | Clutch | No |
| J | 3-Speed Transmission | No |
| J1 | 4-Speed Transmission | No |
| K | Transfer Case | No |
| L | Propeller Shafts | No |
| M | Front Axle | No |
| N | Rear Axle | No |
| O | Steering | No |
| P | Brakes | No |
| Q | Wheels | No |
| R | Frame | No |
| S | Springs/Shock Absorbers | No |
| T | Body | No |
| U | Miscellaneous | No |

**Additional complication:** Compound section IDs (D1, F1, F2, J1) follow the pattern `^([A-Z]\d)\s` which the current L1 `id_pattern` does not capture.

**Fix:** Complete the known_ids list and update the L1 id_pattern to `^([A-Z]\d?)\s` to handle compound IDs.

### CJ-F3: No Boundary Filtering Configured [HIGH]

All 1,745 raw boundaries survive filtering because no filtering parameters are set:
- `min_gap_lines`: 0 (disabled)
- `min_content_words`: 0 (disabled)
- `require_blank_before`: false
- `require_known_id`: false

**Fix:** At minimum, set `require_known_id: true` on L1. Additionally consider `min_content_words: 50` and `require_blank_before: true`.

### CJ-F4: OCR Character-Spacing Not Addressed [HIGH]

The OCR systematically spaces all-caps text: `H U R R I C A N E`, `G E N E R A L`, `P A R .`, `S E R I E S`, `F I G .`, etc. The profile has only 3 substitution rules. Without collapsing these patterns:
- False L1 boundaries are triggered
- Chunk text quality degrades for embedding
- Figure references become undetectable (`F I G . D-14` instead of `FIG. D-14`)

**Fix:** Add a general cleanup step that collapses `X Y Z` patterns where each segment is 1-2 characters back to `XYZ`. This may need a pipeline enhancement (regex-based substitution rather than literal string replacement).

### CJ-F5: 59.6% of Chunks Undersized [HIGH]

730 of 1,224 chunks are below 200 tokens. Median chunk size is 130 tokens. This is a direct cascade from the 1,172 false L1 boundaries fragmenting the document. The merge-small rule (R6) cannot compensate with this many false boundaries.

**Fix:** Resolving CJ-F1 through CJ-F3 will fix this. Not an independent problem.

### CJ-F6: Page Number Extraction Fails [MEDIUM]

Zero page IDs extracted from 376 pages. The pattern `^(\d+)$` expects standalone numbers on a line. In this OCR, page numbers may be embedded in header/footer lines or not appear as standalone lines.

**Fix:** Investigate page number format in the actual OCR output. May need a different pattern or page number extraction approach.

### CJ-F7: Header/Footer Pattern Too Broad [MEDIUM]

The second header pattern `^[A-Z]\s+[A-Z ]+$` is designed to catch spaced-out section headers but also matches any line of all-caps words. This likely strips legitimate content from specification tables and figure captions.

**Fix:** Make the pattern more specific or remove it in favor of known_ids-based section detection.

### CJ-F8: Cross-Reference Targets Unresolvable [LOW]

11 cross-reference targets not found (A-3, B-66, B-10, D-2, D-45, D-88, F2, F-3, M-14, N-3). Some (like F2) are compound section IDs. Others should exist but are mislocated due to false L1 boundaries.

**Fix:** Will partially resolve when L1 boundaries are fixed. Compound section IDs (F2) need the L1 pattern update from CJ-F2.

### CJ-F9: Vehicle Tagging Absent [MEDIUM]

Zero chunks have vehicle applicability tags despite all chunks having engine tags. The manual covers all models universally without explicit per-paragraph vehicle callouts. The tagging function may require explicit vehicle model mentions in chunk text.

**Fix:** Investigate whether the universal applicability should be tagged differently (e.g., default all-vehicle tag for universal manuals).

---

## TM 9-8014 (Operation and Organizational Maintenance)

**PDF:** `data/TM9-8014.pdf` (391 pages, 146 empty)
**Profile:** `tests/fixtures/tm9_8014_profile.yaml`
**QA Result:** FAILED (342 errors, 74 warnings)

### Pipeline Metrics

| Stage | Metric | Value |
|-------|--------|-------|
| OCR Quality | Dictionary match rate | 0.923 |
| OCR Quality | Garbage line rate | 0.007 |
| OCR Quality | Needs re-OCR | False |
| Structural Parsing | Raw boundaries | 412 |
| Structural Parsing | Filtered boundaries | 412 (0 removed) |
| Structural Parsing | L1 (Chapter) | 1 (expected 4) |
| Structural Parsing | L2 (Section) | 6 |
| Structural Parsing | L3 (Paragraph) | 71 |
| Structural Parsing | L4 (Sub-paragraph) | 334 |
| Chunk Assembly | Total chunks | 173 |
| Chunk Assembly | In range (200-2000) | 172 (99.4%) |
| Chunk Assembly | Mean tokens | 345 |
| QA | Errors | 342 |
| QA | Warnings | 74 |

### TM-F1: Only 1 of 4 Chapters Detected [CRITICAL]

The L1 pattern `^CHAPTER\s+(\d+)` requires exact spelling. The OCR renders chapter headings as:
- Page 1: `CHAPTEIR 1.` -- Substitution `CHAPTEIR -> CHAPTER` exists and works. **Chapter 1 detected.**
- Page 2: `CHAPTEa 4.` -- No substitution exists. **Chapter 4 NOT detected.**
- Chapters 2 and 3: **Completely absent from extracted text** (likely image-only pages)

The entire 391-page manual gets filed under Chapter 1. The hierarchy is flat and poorly structured.

**Fix:** Add substitution `CHAPTEa -> CHAPTER`. For missing chapters 2 and 3, consider adding synthetic boundaries via `known_ids` with `require_known_id` if page ranges can be determined from the TOC.

### TM-F2: OCR Substitution Coverage Insufficient [HIGH]

Only 4 substitutions configured, only 4 applied across 3 pages out of 391. Garbled headings found in actual text:
- `c)p c!r~trfi#le.` (detected as paragraph title)
- `AIR CWiiiER` (should be "AIR CLEANER")
- `InstaZZation.` / `Znstaklation.` / `Instuzlution.` / `InstuZlufio/x.` / `InsuZation.` (multiple variants of "Installation")
- `Znterference` (should be "Interference")
- `CHAPTEa` (should be "CHAPTER")

These garbled strings become boundary titles and chunk metadata, degrading retrieval quality.

**Fix:** Expand the substitution list significantly. Consider patterns-based substitution for common OCR error classes (Z/I confusion, special characters in place of letters).

### TM-F3: 342 Cross-Reference Errors (100% Failure) [CRITICAL]

Every cross-reference in the document is unresolved. The cross-ref pattern `par\.?\s+(\d+[a-z]?)` extracts paragraph numbers (e.g., `69`, `11`, `13`). These get constructed as `tm9-8014-m38a1::69`, but actual chunk IDs are hierarchical: `tm9-8014-m38a1::1::IV::69`.

This is a **systematic namespace mismatch** -- not a profile configuration issue but a pipeline logic issue. The cross-reference validator expects flat IDs but the manifest builds hierarchical IDs.

Most frequently referenced unresolved targets:
- `tm9-8014-m38a1::69` (16 references)
- `tm9-8014-m38a1::11` (13 references)
- `tm9-8014-m38a1::13` (7 references)

**Fix:** The cross-reference resolution logic needs to support partial-path matching. A reference to "par. 69" should resolve to any chunk ID containing `::69` in the hierarchy path. This is a **code change** in the pipeline, not just a profile fix.

### TM-F4: L3 Paragraph Pattern Captures Garbage [HIGH]

The L3 pattern `^(\d+)\.\s` matches any line starting with a number and period. This picks up:
- `6. c)p c!r~trfi#le.` (garbage OCR)
- `6. Engaging` (mid-procedure step)
- `6. Data.` / `6. Installation.` / `6. Removal` (numbered sub-steps within paragraphs)

There are 17 boundaries detected as "paragraph 6" -- the ID is massively over-matched because step 6 in various procedures also triggers the pattern.

**Fix:** Add `require_blank_before: true` and `min_content_words` filtering to L3. Real paragraph headings are preceded by blank lines; mid-procedure steps are not.

### TM-F5: L4 Sub-Paragraph / Step Ambiguity [HIGH]

The L4 pattern `^([a-z])\.\s` matches both sub-paragraph headings AND procedural steps (`a.`, `b.`, `c.`). This creates 334 L4 boundaries, many of which are procedure steps rather than structural sub-paragraphs. Result: 74 orphaned-step warnings where chunks start mid-sequence.

**Fix:** Add `min_content_words: 20` or `require_blank_before: true` to L4. The step_patterns configuration already lists `^([a-z])\.\s` -- the same pattern should not be both a hierarchy boundary AND a step pattern.

### TM-F6: No Boundary Filtering Configured [HIGH]

All 412 raw boundaries survive filtering. No filtering parameters set on any level. Same problem as CJ-F3.

**Fix:** Configure filtering on all hierarchy levels, especially L3 and L4 which have the most false positives.

### TM-F7: 146 Empty Pages (37.3%) [MEDIUM]

Nearly 40% of pages extract as empty. These are image-only pages (diagrams, wiring schematics, exploded views) where pymupdf cannot extract text. Expected for a scanned 1950s military manual, but means significant content is inaccessible to the pipeline.

**Fix:** No profile fix available. Could consider supplemental OCR (Tesseract) on image-only pages, or manual annotation of key diagrams.

### TM-F8: Section Hierarchy Duplication [MEDIUM]

Because Chapters 2 and 3 are missing, Sections from different chapters all nest under Chapter 1. Section `I` appears multiple times (once for each chapter's "Section I"), creating duplicate/ambiguous hierarchy paths like `tm9-8014-m38a1::1::I`.

**Fix:** Will resolve when Chapter detection (TM-F1) is fixed. If chapters remain undetectable, use synthetic boundaries from known_ids.

---

## Remaining PDF Assessment

### TM9-8015-1: Engine and Clutch Manual

**File:** `data/TM9-8015-1.pdf`

| Metric | Value |
|--------|-------|
| Pages | 188 (27 empty = 14%) |
| Total characters | 198,700 |
| OCR quality | Poor (garbled headers) |
| Hierarchy | Chapter > Section > Paragraph (same as TM9-8014) |

**Content:** Ordnance Maintenance manual for the Hurricane F-head I4 engine and clutch assembly. Companion to TM9-8014 (operator maintenance) and TM9-8015-2 (power train/body/frame). Covers field and depot maintenance including rebuild procedures.

**Assessment:** CANDIDATE for pipeline processing. OCR quality is worse than TM9-8014 -- zero clean CHAPTER markers detected, only 4 Section headers survived OCR. Body text reads reasonably well. 200 figure references, 213 part numbers.

**Action needed:** Create profile `tm9-8015-1-m38a1` based on TM9-8014 template. Will require aggressive OCR substitutions and known_ids-based boundary detection since regex cannot reliably match the garbled headers.

### TM9-8015-2: Power Train, Body, and Frame Manual

**File:** `data/TM9-8015-2.pdf`

| Metric | Value |
|--------|-------|
| Pages | 311 (8 empty = 2.6%) |
| Total characters | 333,057 |
| OCR quality | Fair (mostly readable headers) |
| Hierarchy | Chapter > Section > Paragraph (same as TM9-8014) |

**Content:** Ordnance Maintenance manual covering transmission (T-90), transfer case (Dana 18), propeller shafts, front axle (Dana 25), rear axle (Dana 44), steering, brakes, springs, body, and frame. Organized into 12 chapters.

**Assessment:** STRONGEST CANDIDATE for pipeline processing. Better OCR than either TM9-8014 or TM9-8015-1. 2 clean CHAPTER headers detected, 64 Section headers. Rich paragraph structure with numbered paragraphs. 311 figure references, 261 part numbers.

**Action needed:** Create profile `tm9-8015-2-m38a1`. Leverage existing TM9-8014 profile as template. This manual should be prioritized first among the new profiles due to best OCR quality.

### M38A1wiring: Wiring Diagram

**File:** `data/M38A1wiring.pdf`

| Metric | Value |
|--------|-------|
| Pages | 1 |
| Total characters | 0 |
| OCR quality | N/A (no text layer) |

**Assessment:** NOT a pipeline candidate. Single-page scanned wiring diagram with zero text content. This is a visual reference supplement to the M38A1 manual set.

**Options:** Manual annotation as a metadata-only chunk, vision model description, or link as referenced figure from TM9-8014 electrical section.

### ORD_SNL_G-758: Illustrated Parts Catalog

**File:** `data/ORD_SNL_G-758.pdf`

| Metric | Value |
|--------|-------|
| Pages | 447 (62 empty = 13.9%) |
| Total characters | 1,172,777 |
| OCR quality | Fair (tabular noise) |
| Structure | Group > Subgroup (not Chapter > Section) |

**Assessment:** CONDITIONAL CANDIDATE. This is a tabular parts catalog (8,602 part/NSN numbers, organized by standard government grouping), not a prose service manual. The current R1-R8 chunk rules are designed for prose maintenance procedures and will not work on tabular parts listings.

**Recommendation:** Defer. Least valuable for repair/troubleshooting chatbot use case. If processed later, needs table-extraction approach rather than prose chunking, or a specialized profile with Group > Subgroup hierarchy and parts-group-based chunking.

---

## Cross-Cutting Issues

These problems appear in both CJ and TM9-8014 validation and likely affect any new profile:

### X-1: Test Fixture Profiles Are Not Production-Ready

Both non-XJ profiles in `tests/fixtures/` were written with minimal known_ids for unit testing. They lack:
- Complete known_ids lists
- Any filtering configuration
- Sufficient OCR substitutions
- Production-tuned patterns

**Recommendation:** Create production profiles in `profiles/` directory (alongside existing `xj-1999.yaml`) separate from test fixtures. Test fixtures should remain minimal for unit test isolation.

### X-2: Boundary Filtering Is Never Configured

Neither profile uses `min_gap_lines`, `min_content_words`, `require_blank_before`, or `require_known_id`. The XJ-1999 production profile demonstrates that `require_known_id: true` is essential for L1 boundary accuracy. Both other profiles need it.

### X-3: Cross-Reference Resolution Assumes Flat Namespace

The cross-reference validator constructs targets as `{manual_id}::{ref}` but chunk IDs are hierarchical (`{manual_id}::{L1}::{L2}::{L3}`). This is a **pipeline code bug**, not a profile issue. Every cross-reference in TM9-8014 fails (342 errors). The CJ manual has fewer failures only because it has fewer detected cross-references.

**Fix required in:** `src/pipeline/qa.py` (cross-ref validity check) and/or `src/pipeline/chunk_assembly.py` (cross-ref target construction). The resolver needs partial-path matching: "par. 69" should match any chunk ID ending in `::69`.

### X-4: L4/Step Pattern Collision

Both profiles use `^([a-z])\.\s` as both the L4 sub-paragraph `id_pattern` AND a `step_pattern`. This creates structural boundaries at every lettered step in a procedure, fragmenting procedures into tiny L4 segments. The XJ profile avoids this because its hierarchy doesn't have an L4 level.

**Fix:** Either remove L4 from these profiles (treat sub-paragraphs as content within L3) or add strong filtering to L4 to distinguish headings from steps.

### X-5: OCR Cleanup Lacks Regex-Based Substitution

Both manuals need pattern-based OCR cleanup (e.g., collapse `H U R R I C A N E` to `HURRICANE`). The current `known_substitutions` only supports literal string replacement. A regex-based substitution capability would handle entire classes of OCR errors with single rules.

**Pipeline enhancement needed in:** `src/pipeline/ocr_cleanup.py`. Add support for regex patterns in the substitution list, or add a separate pre-processing step for character-spacing collapse.

---

## Priority Ranking

| Priority | Finding | Type | Impact |
|:--------:|---------|------|--------|
| 1 | X-3: Cross-ref namespace mismatch | Code bug | 342 errors in TM9-8014, affects all manuals |
| 2 | CJ-F1/CJ-F2: L1 pattern + incomplete known_ids | Profile | 1,172 false boundaries, 59.6% undersized chunks |
| 3 | TM-F1/TM-F2: Missing chapters + insufficient substitutions | Profile | 75% of chapters undetected |
| 4 | X-4: L4/step pattern collision | Design | 334 false L4 boundaries, 74 orphaned steps |
| 5 | X-2: No filtering configured | Profile | Zero false positives removed |
| 6 | X-5: No regex-based OCR substitution | Enhancement | Entire classes of OCR errors uncorrectable |
| 7 | CJ-F4: Character-spacing not addressed | Profile + Enhancement | Degrades embedding quality and pattern matching |
| 8 | X-1: Create production profiles | Workflow | Test fixtures should not be production profiles |
| 9 | New profiles for TM9-8015-1, TM9-8015-2 | New work | Complete the M38A1 manual set |
| 10 | ORD_SNL_G-758 table extraction | New work | Requires pipeline enhancement for tabular content |

---

## Recommended Next Steps

1. **Fix X-3 (cross-ref namespace)** -- This is the only finding that requires a code change rather than profile work. Fix the cross-reference resolver to support partial-path matching for hierarchical chunk IDs.

2. **Create production CJ profile** (`profiles/cj-universal.yaml`) with complete known_ids, `require_known_id: true`, and L1 pattern updated for compound section IDs.

3. **Create production TM9-8014 profile** (`profiles/tm9-8014.yaml`) with additional OCR substitutions, filtering on L3/L4, and (if possible) synthetic chapter boundaries.

4. **Resolve X-4 (L4/step collision)** -- Design decision needed: should L4 exist in military TM profiles, or should sub-paragraphs be treated as content within L3?

5. **Create TM9-8015-2 profile** -- Best OCR quality among the remaining manuals. Use as proof that the pipeline generalizes beyond the XJ.

6. **Consider X-5 (regex substitutions)** -- Would dramatically simplify OCR cleanup for the CJ character-spacing problem and military TM garbling patterns.
