# Implementation Plan

**Generated:** 2026-02-15
**Source Documents:**
- `PRD.pdf` — Product Requirements Document (30 pages, ~15,000 words)
- `README.md` — Project overview and architecture summary
- `CLAUDE.md` — Developer guide and conventions
- `tests/` — 233 TDD tests across 9 files defining all expected behavior
- `tests/fixtures/` — 4 YAML test profiles (xj_1999, cj_universal, tm9_8014, invalid)

**Total Phases:** 6
**Estimated Total Effort:** ~300,000 tokens

---

## Executive Summary

This project implements a Smart Chunking Pipeline for Vehicle Service Manual RAG. It processes OCR'd vehicle service manuals (PDF) into chunked, metadata-enriched vectors for a repair/troubleshooting chatbot. The pipeline is profile-driven: each manual gets a YAML profile that configures OCR cleanup, structural parsing, chunk assembly, and metadata tagging.

The codebase is in a TDD framework state — all 54 functions across 8 modules raise `NotImplementedError`. The 233 tests in `tests/` fully define expected behavior and serve as the implementation specification. The implementation strategy follows the pipeline's natural data flow: profile loading, OCR cleanup, structural parsing, chunk assembly, embedding/indexing, retrieval/QA/CLI.

Three target manuals drive all test fixtures: 1999 Jeep Cherokee XJ (modern, 4-level hierarchy), 1953-71 CJ Universal (classic, 3-level), and TM 9-8014 M38A1 (military, 3-level). Each has fundamentally different document conventions, making the profile-driven approach essential.

---

## Plan Overview

The implementation follows the pipeline's four-stage architecture plus the retrieval and quality layers. Each phase builds on the previous, and each phase leaves the codebase in a testable state with its corresponding tests passing.

The critical path is strictly sequential: Profile, OCR, Structural, Chunks, Embeddings, Retrieval, QA, CLI. However, within phases, many work items are parallelizable (e.g., individual chunk rules R1-R8 are independent).

### Phase Summary Table

| Phase | Focus Area | Key Deliverables | Est. Tokens | Dependencies |
|-------|------------|------------------|-------------|--------------|
| 1 | Profile System | YAML loader, validator, pattern compiler | ~40K | None |
| 2 | OCR Cleanup | Substitutions, header stripping, garbage detection, unicode | ~45K | Phase 1 |
| 3 | Structural Parsing | Boundary detection, manifest building, chunk IDs | ~50K | Phase 1 |
| 4 | Chunk Assembly Engine | Rules R1-R8, vehicle tagging, metadata composition | ~80K | Phases 1, 3 |
| 5 | Embedding and Retrieval | Embedding composition, SQLite index, query analysis, reranking | ~50K | Phases 1, 4 |
| 6 | QA Validation and CLI | 7-check validation suite, CLI argument parser, subcommands | ~35K | All previous |

---

## Phase 1: Profile System

**Estimated Effort:** ~40,000 tokens (including testing/fixes)
**Dependencies:** None
**Parallelizable:** Yes — work items 1.1, 1.2, 1.3 have some independence but share the ManualProfile dataclass

### Goals

- Load YAML manual profiles into typed `ManualProfile` dataclasses with nested vehicle, hierarchy, and safety structures
- Validate profiles for completeness and correctness
- Pre-compile regex patterns from profile strings for runtime performance

### Work Items

#### 1.1 Implement `load_profile()`

**Requirement Refs:** PRD 3.1 (Profile Schema), PRD 3.2-3.4 (Manual Profiles)
**Files Affected:**
- `src/pipeline/profile.py` (modify)

**Description:**
Load a YAML file from disk and map it into the `ManualProfile` dataclass. This involves parsing nested YAML structures into the already-defined dataclasses: `Vehicle`, `VehicleEngine`, `VehicleTransmission`, `HierarchyLevel`, `SafetyCallout`. The function must handle string and `Path` inputs, raise `FileNotFoundError` for missing files, and correctly extract all fields from the three different profile formats (XJ, CJ, TM9).

**Tasks:**
1. [ ] Read YAML file using `pyyaml` and parse into dict
2. [ ] Map `vehicles` list to `Vehicle` dataclasses with nested `VehicleEngine` and `VehicleTransmission`
3. [ ] Map `structure.hierarchy` list to `HierarchyLevel` dataclasses with `known_ids`
4. [ ] Map `safety_callouts` list to `SafetyCallout` dataclasses
5. [ ] Extract flat fields: `manual_id`, `manual_title`, `source_url`, `source_format`
6. [ ] Extract `page_number_pattern`, `step_patterns`, `figure_reference_pattern/scope`, `cross_reference_patterns`
7. [ ] Pass-through `content_types`, `ocr_cleanup`, `variants` as dicts
8. [ ] Handle `FileNotFoundError` for missing paths
9. [ ] Accept both `str` and `Path` arguments

**Acceptance Criteria:**
- [ ] All 8 tests in `TestLoadProfile` pass
- [ ] All 11 tests in `TestLoadProfileVehicles` pass
- [ ] All 7 tests in `TestLoadProfileHierarchy` pass
- [ ] All 4 tests in `TestLoadProfileSafetyCallouts` pass
- [ ] All 4 tests in `TestLoadProfileOCRCleanup` pass
- [ ] Profiles for all 3 manuals (XJ, CJ, TM9) load correctly
- [ ] Invalid/missing profiles raise appropriate errors

**Notes:**
- Dataclasses are already fully defined in `profile.py` — implementation is purely the loading/mapping logic
- YAML test fixtures in `tests/fixtures/` are simplified versions of the full PRD profiles
- Pay attention to field naming: YAML uses `snake_case` and nested dicts that must map to specific dataclass fields

---

#### 1.2 Implement `validate_profile()`

**Requirement Refs:** PRD 3.1 (Profile Schema validation)
**Files Affected:**
- `src/pipeline/profile.py` (modify)

**Description:**
Validate a loaded `ManualProfile` for required fields and structural correctness. Return a list of validation error strings (empty list = valid). Check for non-empty `manual_id`, non-empty `vehicles` list, non-empty `hierarchy`, and valid `source_format`.

**Tasks:**
1. [ ] Check `manual_id` is non-empty string
2. [ ] Check `manual_title` is non-empty string
3. [ ] Check `vehicles` list is non-empty
4. [ ] Check `hierarchy` list is non-empty
5. [ ] Check `source_format` is a recognized format
6. [ ] Return list of error message strings

**Acceptance Criteria:**
- [ ] Valid profiles (XJ, CJ, TM9) return empty list
- [ ] Invalid profile returns non-empty list with descriptive errors
- [ ] Each validation failure produces a clear error message

---

#### 1.3 Implement `compile_patterns()`

**Requirement Refs:** PRD 4.3.1 (Header Detection), PRD 3.1 (pattern fields)
**Files Affected:**
- `src/pipeline/profile.py` (modify)

**Description:**
Pre-compile all regex pattern strings from a `ManualProfile` into `re.Pattern` objects for runtime performance. Return a dict keyed by pattern category: `"hierarchy"`, `"step"`, `"safety"`, `"figure"`, `"cross_reference"`. Each value is a list of compiled `re.Pattern` objects.

**Tasks:**
1. [ ] Compile `hierarchy[].id_pattern` and `hierarchy[].title_pattern` for each level
2. [ ] Compile `step_patterns` list
3. [ ] Compile `safety_callouts[].pattern` for each callout level
4. [ ] Compile `figure_reference_pattern`
5. [ ] Compile `cross_reference_patterns` list
6. [ ] Return dict with categorized compiled patterns
7. [ ] Handle `None` patterns gracefully (skip compilation)

**Acceptance Criteria:**
- [ ] All 8 tests in `TestCompilePatterns` pass
- [ ] Step patterns match numbered `(1)` and lettered `a.` formats
- [ ] Safety patterns match `WARNING:`, `CAUTION:`, `NOTE:` formats
- [ ] Hierarchy patterns match chapter/section/group titles per manual format

---

### Phase 1 Testing Requirements

- [ ] `pytest tests/test_profile.py` — all 52 tests pass
- [ ] All 3 manual profiles load without errors
- [ ] Invalid profile correctly caught by validation
- [ ] Compiled patterns match expected text fragments from test fixtures

### Phase 1 Completion Checklist

- [ ] All work items complete
- [ ] All 52 profile tests passing
- [ ] No regressions introduced
- [ ] `ManualProfile` dataclass correctly populated for all 3 target manuals

---

## Phase 2: OCR Cleanup Pipeline

**Estimated Effort:** ~45,000 tokens (including testing/fixes)
**Dependencies:** Phase 1 (ManualProfile for profile-driven cleanup)
**Parallelizable:** Yes — work items 2.1-2.4 are independent utility functions; 2.5-2.6 integrate them

### Goals

- Apply profile-specific OCR substitutions to correct scan artifacts
- Strip headers/footers using profile regex patterns, extracting page numbers
- Detect garbage lines by non-ASCII density threshold
- Normalize unicode (smart quotes, ligatures, whitespace)
- Compose the full page cleanup pipeline and quality assessment

### Work Items

#### 2.1 Implement `apply_known_substitutions()`

**Requirement Refs:** PRD 4.2.2 (OCR Cleanup, step 1)
**Files Affected:**
- `src/pipeline/ocr_cleanup.py` (modify)

**Description:**
Apply a list of `{from, to}` substitution pairs to the input text. Each substitution is a simple string find-and-replace (case-sensitive). All occurrences of each `from` string are replaced with the `to` string. Substitutions are applied in order.

**Tasks:**
1. [ ] Iterate over substitution dicts, applying `text.replace(from, to)` for each
2. [ ] Handle empty substitution list (return text unchanged)
3. [ ] Handle special characters in substitution strings (smart quotes, split words)
4. [ ] Return the modified text

**Acceptance Criteria:**
- [ ] All 7 tests in `TestApplyKnownSubstitutions` pass
- [ ] Multiple occurrences of same pattern all replaced
- [ ] Case-sensitive replacement
- [ ] Substitutions with special chars work correctly

---

#### 2.2 Implement `strip_headers_footers()`

**Requirement Refs:** PRD 4.2.2 (OCR Cleanup, step 2)
**Files Affected:**
- `src/pipeline/ocr_cleanup.py` (modify)

**Description:**
Remove header and footer lines matching profile regex patterns. Extract page number/ID from headers before stripping. Return a tuple of `(cleaned_text, extracted_page_id)`. Also strip `(Continued)` markers.

**Tasks:**
1. [ ] Split text into lines
2. [ ] Match each line against header/footer regex patterns
3. [ ] Extract page number/ID from matching header lines (capture groups)
4. [ ] Remove matching lines from text
5. [ ] Strip `(Continued)` markers
6. [ ] Return `(cleaned_text, extracted_page_id_or_None)`

**Acceptance Criteria:**
- [ ] All 6 tests in `TestStripHeadersFooters` pass
- [ ] Headers removed, page numbers extracted
- [ ] Footer page numbers stripped
- [ ] Non-matching text preserved unchanged

---

#### 2.3 Implement `detect_garbage_lines()`

**Requirement Refs:** PRD 4.2.2 (OCR Cleanup, step 3)
**Files Affected:**
- `src/pipeline/ocr_cleanup.py` (modify)

**Description:**
Flag lines exceeding a non-ASCII character density threshold. Return a list of 0-based line indices where the ratio of non-ASCII characters to total characters exceeds the threshold (e.g., 0.3 = 30%).

**Tasks:**
1. [ ] Split text into lines
2. [ ] For each line, calculate ratio of non-ASCII characters
3. [ ] Flag lines exceeding the threshold
4. [ ] Return list of flagged line indices (0-based)
5. [ ] Handle empty lines gracefully

**Acceptance Criteria:**
- [ ] All 5 tests in `TestDetectGarbageLines` pass
- [ ] All-ASCII text returns empty list
- [ ] Lines with high non-ASCII density correctly flagged
- [ ] Threshold parameter respected

---

#### 2.4 Implement `normalize_unicode()`

**Requirement Refs:** PRD 4.2.2 (OCR Cleanup, step 4 — universal cleanup)
**Files Affected:**
- `src/pipeline/ocr_cleanup.py` (modify)

**Description:**
Apply universal unicode normalization: smart quotes to straight quotes, ligature decomposition, whitespace normalization (collapse multiple spaces, normalize line breaks while preserving paragraph structure).

**Tasks:**
1. [ ] Replace smart double quotes (U+201C, U+201D) with straight `"`
2. [ ] Replace smart single quotes (U+2018, U+2019) with straight `'`
3. [ ] Decompose ligatures: U+FB01 to `fi`, U+FB02 to `fl`
4. [ ] Collapse multiple spaces to single space
5. [ ] Collapse 3+ consecutive newlines to 2 newlines
6. [ ] Preserve single newlines

**Acceptance Criteria:**
- [ ] All 7 tests in `TestNormalizeUnicode` pass
- [ ] Smart quotes normalized
- [ ] Ligatures decomposed
- [ ] Whitespace collapsed without destroying paragraph breaks

---

#### 2.5 Implement `clean_page()`

**Requirement Refs:** PRD 4.2 (Stage 1 pipeline)
**Files Affected:**
- `src/pipeline/ocr_cleanup.py` (modify)

**Description:**
Full cleanup pipeline for a single page. Orchestrates: apply substitutions, strip headers/footers, detect garbage, normalize unicode. Returns a `CleanedPage` dataclass preserving the original text, cleaned text, extracted page ID, garbage line indices, and substitution count.

**Tasks:**
1. [ ] Store original text
2. [ ] Apply `apply_known_substitutions()` using `profile.ocr_cleanup["known_substitutions"]`
3. [ ] Count substitutions applied
4. [ ] Apply `strip_headers_footers()` using `profile.ocr_cleanup["header_footer_patterns"]`
5. [ ] Apply `detect_garbage_lines()` using `profile.ocr_cleanup["garbage_detection"]["threshold"]`
6. [ ] Apply `normalize_unicode()`
7. [ ] Return `CleanedPage` with all tracked metadata

**Acceptance Criteria:**
- [ ] All 10 tests in `TestCleanPage` pass (covering XJ, CJ, TM9 profiles)
- [ ] Original text preserved in output
- [ ] Substitution count tracked accurately
- [ ] Garbage lines detected and reported
- [ ] Page number extracted from headers

---

#### 2.6 Implement `assess_quality()`

**Requirement Refs:** PRD 4.2.3 (OCR Quality Assessment)
**Files Affected:**
- `src/pipeline/ocr_cleanup.py` (modify)

**Description:**
Run quality assessment on a list of `CleanedPage` objects. Sample up to `sample_size` pages (default 50), calculate dictionary match rate, garbage line rate, and determine if re-OCR is needed (dictionary match rate below 0.85).

**Tasks:**
1. [ ] Sample pages (up to `sample_size` from total)
2. [ ] Calculate dictionary match rate (percentage of words matching English dictionary)
3. [ ] Calculate garbage line rate
4. [ ] Count suspected remaining OCR errors
5. [ ] Set `needs_reocr` flag based on threshold
6. [ ] Return `OCRQualityReport` dataclass

**Acceptance Criteria:**
- [ ] All 4 tests in `TestAssessQuality` pass
- [ ] Dictionary match rate calculated correctly
- [ ] `needs_reocr` flag set when quality is poor
- [ ] Total and sampled page counts reported

---

### Phase 2 Testing Requirements

- [ ] `pytest tests/test_ocr_cleanup.py` — all 28 tests pass
- [ ] All 3 manual sample texts cleaned correctly
- [ ] Dirty OCR text fixture normalized properly

### Phase 2 Completion Checklist

- [ ] All work items complete
- [ ] All 28 OCR cleanup tests passing
- [ ] All Phase 1 tests still passing (no regressions)
- [ ] CleanedPage objects preserve full audit trail

---

## Phase 3: Structural Parsing

**Estimated Effort:** ~50,000 tokens (including testing/fixes)
**Dependencies:** Phase 1 (ManualProfile, compiled patterns)
**Parallelizable:** Partially — 3.1 is independent; 3.2-3.4 are sequential

### Goals

- Generate namespaced chunk IDs in the format `{manual_id}::{level1}::{level2}::...`
- Detect structural boundaries (chapters, sections, procedures) using profile regex patterns
- Validate detected boundaries against known IDs from the profile
- Build hierarchical manifest with parent-child relationships and chunk boundaries

### Work Items

#### 3.1 Implement `generate_chunk_id()`

**Requirement Refs:** PRD 4.3.3 (Chunk ID format)
**Files Affected:**
- `src/pipeline/structural_parser.py` (modify)

**Description:**
Generate a chunk ID by joining the manual_id with hierarchy level IDs using `::` as delimiter. Format: `{manual_id}::{level1_id}::{level2_id}::...`. Empty hierarchy list returns just the manual_id.

**Tasks:**
1. [ ] Join `manual_id` with `hierarchy_ids` using `::` separator
2. [ ] Handle empty hierarchy list returning just `manual_id`
3. [ ] Support alphanumeric IDs (e.g., `8A`, `B-4`, `III`, `42`)

**Acceptance Criteria:**
- [ ] All 6 tests in `TestGenerateChunkId` pass
- [ ] `generate_chunk_id("xj-1999", ["0", "SP", "JSP"])` returns `"xj-1999::0::SP::JSP"`
- [ ] `generate_chunk_id("xj-1999", [])` returns `"xj-1999"`

---

#### 3.2 Implement `detect_boundaries()`

**Requirement Refs:** PRD 4.3.1 (Header Detection)
**Files Affected:**
- `src/pipeline/structural_parser.py` (modify)

**Description:**
Scan cleaned text pages for structural boundaries using profile hierarchy patterns. For each hierarchy level, match lines against the level's `id_pattern` and `title_pattern`. Return a list of `Boundary` objects with level, level_name, extracted ID, title, page number, and line number.

**Tasks:**
1. [ ] Iterate over pages with page index tracking
2. [ ] For each line, test against each hierarchy level's compiled `id_pattern`
3. [ ] Extract ID using regex capture groups
4. [ ] Extract title using `title_pattern` if available
5. [ ] Create `Boundary` object with level, level_name, id, title, page_number, line_number
6. [ ] Return boundaries sorted by page and line number
7. [ ] Handle empty pages and no-match pages returning `[]`

**Acceptance Criteria:**
- [ ] All 9 tests in `TestDetectBoundaries` pass
- [ ] XJ boundaries: groups (0, 9), sections (SP), procedures (JSP) detected
- [ ] CJ boundaries: sections (B), paragraphs (B-1) detected
- [ ] TM9 boundaries: chapters (2), sections (III), paragraphs (42) detected
- [ ] Empty input returns empty list

---

#### 3.3 Implement `validate_boundaries()`

**Requirement Refs:** PRD 4.3.1 (known_ids validation)
**Files Affected:**
- `src/pipeline/structural_parser.py` (modify)

**Description:**
Cross-check detected boundary IDs against the profile's `known_ids` lists for each hierarchy level. Generate warning strings for unrecognized IDs. Levels without `known_ids` skip validation.

**Tasks:**
1. [ ] For each boundary, find its hierarchy level in the profile
2. [ ] If that level has `known_ids`, check if the boundary's ID matches
3. [ ] Generate warning string for unrecognized IDs
4. [ ] Skip validation for levels without `known_ids`
5. [ ] Return list of warning strings

**Acceptance Criteria:**
- [ ] All 4 tests in `TestValidateBoundaries` pass
- [ ] Known IDs pass validation (empty warnings)
- [ ] Unknown IDs generate descriptive warnings
- [ ] Levels without known_ids silently pass

---

#### 3.4 Implement `build_manifest()`

**Requirement Refs:** PRD 4.3.3 (Manifest Output Format)
**Files Affected:**
- `src/pipeline/structural_parser.py` (modify)

**Description:**
Construct a hierarchical `Manifest` from detected boundaries. Each boundary becomes a `ManifestEntry` with a generated chunk_id, hierarchy_path, parent_chunk_id, and children list. Establish parent-child relationships based on hierarchy levels.

**Tasks:**
1. [ ] Create `ManifestEntry` for each boundary using `generate_chunk_id()`
2. [ ] Build hierarchy path from ancestor boundaries
3. [ ] Set `parent_chunk_id` based on nearest ancestor at a higher level
4. [ ] Populate `children` lists for parent entries
5. [ ] Set `page_range` and `line_range` from boundary positions
6. [ ] Set `manual_id` from profile
7. [ ] Handle empty boundaries producing manifest with empty entries

**Acceptance Criteria:**
- [ ] All 6 tests in `TestBuildManifest` pass
- [ ] Manifest `manual_id` matches profile
- [ ] Parent-child relationships correctly established
- [ ] Chunk IDs follow `{manual_id}::{hierarchy}` format
- [ ] Empty boundaries produce empty manifest

---

### Phase 3 Testing Requirements

- [ ] `pytest tests/test_structural_parser.py` — all 24 tests pass
- [ ] Chunk IDs generated in correct format for all 3 manuals
- [ ] Boundaries detected from all 3 manual sample texts
- [ ] Manifest hierarchy correctly built

### Phase 3 Completion Checklist

- [ ] All work items complete
- [ ] All 24 structural parser tests passing
- [ ] All Phase 1-2 tests still passing (no regressions)
- [ ] Manifest correctly represents document hierarchy

---

## Phase 4: Chunk Assembly Engine

**Estimated Effort:** ~80,000 tokens (including testing/fixes)
**Dependencies:** Phases 1, 3 (ManualProfile, Manifest, compiled patterns)
**Parallelizable:** Yes — rules R1-R8 are largely independent; detection functions are independent

### Goals

- Count tokens using simple word-split approximation
- Compose hierarchical headers for chunk context
- Detect step sequences, safety callouts, and tables in text
- Implement all 8 universal chunk boundary rules (R1-R8)
- Tag chunks with vehicle/engine/drivetrain applicability
- Orchestrate the full chunk assembly pipeline

### Work Items

#### 4.1 Implement `count_tokens()`

**Requirement Refs:** PRD 4.4.1 R2 (Size targets)
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Estimate token count using whitespace-split word count. Empty string returns 0.

**Tasks:**
1. [ ] Split text on whitespace, return count of non-empty segments
2. [ ] Handle empty string returning 0

**Acceptance Criteria:**
- [ ] All 4 tests in `TestCountTokens` pass

---

#### 4.2 Implement `compose_hierarchical_header()`

**Requirement Refs:** PRD 4.4.4 (Chunk Text Composition)
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Build a hierarchical header string: `{manual_title} | {level1} | {level2} | {level3}`.

**Tasks:**
1. [ ] Get `manual_title` from profile
2. [ ] Join with hierarchy_path elements using ` | ` separator
3. [ ] Return the composed header string

**Acceptance Criteria:**
- [ ] All 4 tests in `TestComposeHierarchicalHeader` pass
- [ ] All 3 manuals produce correctly formatted headers

---

#### 4.3 Implement `detect_step_sequences()`

**Requirement Refs:** PRD 4.4.1 R3 (Never split steps)
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Find contiguous numbered `(1), (2)` and lettered `a., b.` step sequences using profile step patterns. Return list of `(start_line, end_line)` tuples.

**Tasks:**
1. [ ] Split text into lines
2. [ ] Match each line against step patterns
3. [ ] Group consecutive matching lines into sequences
4. [ ] Return list of `(start_line, end_line)` tuples

**Acceptance Criteria:**
- [ ] All 4 tests in `TestDetectStepSequences` pass
- [ ] Both numbered and lettered patterns supported

---

#### 4.4 Implement `detect_safety_callouts()`

**Requirement Refs:** PRD 4.4.1 R4 (Safety attachment)
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Find WARNING/CAUTION/NOTE callouts using profile safety patterns. Return list of dicts with `level`, `text`, and `line_range` keys.

**Tasks:**
1. [ ] Split text into lines, match against safety callout patterns
2. [ ] Determine callout extent (single line or block)
3. [ ] Return list of dicts with level, text, line_range

**Acceptance Criteria:**
- [ ] All 5 tests in `TestDetectSafetyCallouts` pass

---

#### 4.5 Implement `detect_tables()`

**Requirement Refs:** PRD 4.4.1 R5 (Table integrity)
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Identify specification tables by formatting patterns (dot-leaders, columnar alignment). Return list of `(start_line, end_line)` tuples.

**Tasks:**
1. [ ] Analyze line patterns for table indicators
2. [ ] Group consecutive table lines
3. [ ] Return `(start_line, end_line)` tuples

**Acceptance Criteria:**
- [ ] All 2 tests in `TestDetectTables` pass

---

#### 4.6 Implement `apply_rule_r1_primary_unit()`

**Requirement Refs:** PRD 4.4.1 R1
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
One complete procedure/topic at the lowest meaningful hierarchy level stays as a single chunk.

**Tasks:**
1. [ ] Keep text as single chunk when it represents one procedure
2. [ ] Split only at sub-boundaries if manifest entry indicates multiple children

**Acceptance Criteria:**
- [ ] Test in `TestRuleR1PrimaryUnit` passes

---

#### 4.7 Implement `apply_rule_r2_size_targets()`

**Requirement Refs:** PRD 4.4.1 R2
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Enforce size constraints: min 200 tokens, target 500-1500, max 2000 (hard ceiling). Split oversized chunks; leave others unchanged.

**Tasks:**
1. [ ] Check each chunk's token count
2. [ ] Split chunks exceeding 2000 tokens at natural boundaries
3. [ ] Leave normal/undersized chunks unchanged

**Acceptance Criteria:**
- [ ] All 3 tests in `TestRuleR2SizeTargets` pass

---

#### 4.8 Implement `apply_rule_r3_never_split_steps()`

**Requirement Refs:** PRD 4.4.1 R3
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Ensure step sequences are never split across chunks. Adjust split points to keep sequences together.

**Tasks:**
1. [ ] Detect step sequences using step patterns
2. [ ] Ensure no chunk boundary falls within a step sequence

**Acceptance Criteria:**
- [ ] All 2 tests in `TestRuleR3NeverSplitSteps` pass

---

#### 4.9 Implement `apply_rule_r4_safety_attachment()`

**Requirement Refs:** PRD 4.4.1 R4
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Keep safety callouts (WARNING/CAUTION/NOTE) with their governed procedure.

**Tasks:**
1. [ ] Detect safety callouts in each chunk
2. [ ] Merge isolated callouts with adjacent procedure chunks

**Acceptance Criteria:**
- [ ] All 2 tests in `TestRuleR4SafetyAttachment` pass

---

#### 4.10 Implement `apply_rule_r5_table_integrity()`

**Requirement Refs:** PRD 4.4.1 R5
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Specification tables are never split, even if they exceed the 2000-token ceiling.

**Tasks:**
1. [ ] Detect tables in chunks
2. [ ] Prevent splits within table boundaries

**Acceptance Criteria:**
- [ ] All 2 tests in `TestRuleR5TableIntegrity` pass

---

#### 4.11 Implement `apply_rule_r6_merge_small()`

**Requirement Refs:** PRD 4.4.1 R6
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Merge chunks smaller than `min_tokens` (default 200) with their next sibling.

**Tasks:**
1. [ ] Check each chunk's token count against `min_tokens`
2. [ ] Merge small chunks with next sibling
3. [ ] Handle edge cases: single chunk, last chunk

**Acceptance Criteria:**
- [ ] All 3 tests in `TestRuleR6MergeSmall` pass

---

#### 4.12 Implement `apply_rule_r7_crossref_merge()` and `apply_rule_r8_figure_continuity()`

**Requirement Refs:** PRD 4.4.1 R7-R8
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
R7: Cross-reference-only sections merge into parent chunk. R8: Figure references stay with describing text.

**Tasks:**
1. [ ] R7: Detect chunks that are exclusively cross-reference text, merge into preceding chunk
2. [ ] R8: Detect figure references, ensure they stay with describing paragraph

**Acceptance Criteria:**
- [ ] All 2 tests in `TestRuleR7CrossRefMerge` pass
- [ ] Test in `TestRuleR8FigureContinuity` passes

---

#### 4.13 Implement `tag_vehicle_applicability()`

**Requirement Refs:** PRD 4.4.3 (Vehicle Applicability Tagging)
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Scan chunk text for vehicle model names, engine aliases, and drivetrain keywords from the profile. Default to `["all"]` if no specific mentions found.

**Tasks:**
1. [ ] Match text against `profile.vehicles[].model` names and aliases
2. [ ] Match against `profile.vehicles[].engines[].aliases`
3. [ ] Match drivetrain keywords: "4WD", "2WD", "4x4"
4. [ ] Default to `["all"]` for each category if no matches
5. [ ] Return dict with `vehicle_models`, `engines`, `drivetrains` keys

**Acceptance Criteria:**
- [ ] All 7 tests in `TestTagVehicleApplicability` pass

---

#### 4.14 Implement `assemble_chunks()`

**Requirement Refs:** PRD 4.4 (Stage 3 full pipeline)
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify)

**Description:**
Orchestrate the full chunk assembly pipeline: extract text per manifest entry, apply rules R1-R8 in sequence, compose hierarchical headers, tag vehicle applicability, build metadata dict, return list of `Chunk` objects.

**Tasks:**
1. [ ] Extract text for each manifest entry using page/line ranges
2. [ ] Apply R1 through R8 in sequence
3. [ ] Compose hierarchical header for each chunk
4. [ ] Tag vehicle applicability
5. [ ] Build metadata dict per PRD 4.4.5 schema
6. [ ] Return list of `Chunk` objects

**Acceptance Criteria:**
- [ ] Full pipeline produces valid `Chunk` objects with populated metadata
- [ ] Metadata includes: `hierarchy_path`, `level1_id`, `content_type`, `vehicle_models`, etc.

---

### Phase 4 Testing Requirements

- [ ] `pytest tests/test_chunk_assembly.py` — all 47 tests pass
- [ ] All 8 rules tested independently and in pipeline
- [ ] Vehicle tagging works for all 3 manual types

### Phase 4 Completion Checklist

- [ ] All work items complete
- [ ] All 47 chunk assembly tests passing
- [ ] All Phase 1-3 tests still passing (no regressions)

---

## Phase 5: Embedding and Retrieval

**Estimated Effort:** ~50,000 tokens (including testing/fixes)
**Dependencies:** Phases 1, 4 (ManualProfile, Chunk objects)
**Parallelizable:** Yes — embedding (5.1-5.3) and retrieval (5.4-5.6) are independent work streams

### Goals

- Compose embedding input from hierarchical header plus first 150 body words
- Build SQLite secondary index for metadata-based lookups
- Analyze natural language queries to extract vehicle/system/type scope
- Implement result enrichment (parent, sibling, cross-reference) and reranking

### Work Items

#### 5.1 Implement `get_first_n_words()` and `compose_embedding_input()`

**Requirement Refs:** PRD 4.5.1 (Embedding Input)
**Files Affected:**
- `src/pipeline/embeddings.py` (modify)

**Description:**
`get_first_n_words()`: Extract the first N words (default 150) from text. `compose_embedding_input()`: Combine hierarchical header with first 150 body words into an `EmbeddingInput` object.

**Tasks:**
1. [ ] `get_first_n_words()`: Split text on whitespace, return first N words joined
2. [ ] Handle fewer than N words (return all available) and empty text
3. [ ] `compose_embedding_input()`: Extract header from chunk, get first 150 body words
4. [ ] Combine into `EmbeddingInput(chunk_id, text)`

**Acceptance Criteria:**
- [ ] All 5 tests in `TestGetFirstNWords` pass
- [ ] All 4 tests in `TestComposeEmbeddingInput` pass

---

#### 5.2 Implement `generate_embedding()`, `create_qdrant_collection()`, `index_chunks()`

**Requirement Refs:** PRD 4.5.2-4.5.3 (Embedding Model, Vector Store)
**Files Affected:**
- `src/pipeline/embeddings.py` (modify)

**Description:**
`generate_embedding()`: Call Ollama API with nomic-embed-text model. `create_qdrant_collection()`: Create a Qdrant collection. `index_chunks()`: Index chunks into Qdrant with metadata.

**Tasks:**
1. [ ] `generate_embedding()`: POST to Ollama `/api/embeddings` endpoint, return vector
2. [ ] `create_qdrant_collection()`: Use qdrant_client to create collection
3. [ ] `index_chunks()`: Compose embeddings, upsert to Qdrant with metadata payload

**Acceptance Criteria:**
- [ ] Functions implement correct API calls with proper data marshaling
- [ ] Metadata payload includes all filterable fields from PRD 4.5.3

**Notes:**
- Tests likely mock external service calls (Ollama, Qdrant). Focus on correct API signatures.

---

#### 5.3 Implement `build_sqlite_index()`

**Requirement Refs:** PRD 4.5.4 (Secondary Metadata Index)
**Files Affected:**
- `src/pipeline/embeddings.py` (modify)

**Description:**
Build SQLite database with lookup tables: procedure_name, vehicle_model, figure_ref, cross_ref_target — each mapping to chunk_ids.

**Tasks:**
1. [ ] Create SQLite database at specified path
2. [ ] Create tables: `procedure_lookup`, `vehicle_model_lookup`, `figure_lookup`, `cross_ref_lookup`
3. [ ] Populate from chunk metadata
4. [ ] Create indexes for fast lookups

**Acceptance Criteria:**
- [ ] All 5 tests in `TestBuildSQLiteIndex` pass
- [ ] Lookups return correct chunk IDs

---

#### 5.4 Implement `analyze_query()`

**Requirement Refs:** PRD 5.1 (Query Understanding)
**Files Affected:**
- `src/pipeline/retrieval.py` (modify)

**Description:**
Parse a natural language query to extract structured scope: vehicle, engine, drivetrain, system, and query type (procedure/specification/diagnostic).

**Tasks:**
1. [ ] Extract vehicle scope by matching known vehicle names/aliases
2. [ ] Extract engine scope by matching engine codes/aliases
3. [ ] Extract drivetrain scope by matching drivetrain keywords
4. [ ] Extract system scope by matching system/group keywords
5. [ ] Classify query type based on intent keywords
6. [ ] Return `QueryAnalysis` dataclass

**Acceptance Criteria:**
- [ ] All 15 tests in `TestAnalyzeQuery` pass
- [ ] Vehicle, engine, drivetrain, system extraction works correctly
- [ ] Query type classification accurate

---

#### 5.5 Implement `enrich_with_parent()`, `enrich_with_siblings()`, `resolve_cross_references()`

**Requirement Refs:** PRD 5.2 (Retrieval Flow steps 2-4)
**Files Affected:**
- `src/pipeline/retrieval.py` (modify)

**Description:**
Enrich retrieval results with contextual chunks: parent for section overview, siblings for adjacent procedures, cross-references for related content.

**Tasks:**
1. [ ] `enrich_with_parent()`: Look up parent chunk, add with `source="parent"`
2. [ ] `enrich_with_siblings()`: Look up sibling chunks, add with `source="sibling"`
3. [ ] `resolve_cross_references()`: Resolve cross-ref targets, add with `source="cross_ref"`
4. [ ] Handle missing parents/siblings/refs gracefully

**Acceptance Criteria:**
- [ ] All 2 tests in `TestEnrichWithParent` pass
- [ ] Test in `TestEnrichWithSiblings` passes
- [ ] Test in `TestResolveCrossReferences` passes

---

#### 5.6 Implement `rerank()` and `retrieve()`

**Requirement Refs:** PRD 5.2 (Retrieval Flow step 5)
**Files Affected:**
- `src/pipeline/retrieval.py` (modify)

**Description:**
`rerank()`: Sort results by score descending, return top N. `retrieve()`: Full retrieval pipeline.

**Tasks:**
1. [ ] `rerank()`: Sort by `score` descending, return first `top_n` results
2. [ ] Handle fewer results than `top_n`
3. [ ] `retrieve()`: Compose full retrieval flow (embed, search, enrich, rerank)

**Acceptance Criteria:**
- [ ] All 3 tests in `TestRerank` pass

---

### Phase 5 Testing Requirements

- [ ] `pytest tests/test_embeddings.py` — all 14 tests pass
- [ ] `pytest tests/test_retrieval.py` — all 18 tests pass

### Phase 5 Completion Checklist

- [ ] All work items complete
- [ ] All 32 embedding + retrieval tests passing
- [ ] All Phase 1-4 tests still passing (no regressions)

---

## Phase 6: QA Validation and CLI

**Estimated Effort:** ~35,000 tokens (including testing/fixes)
**Dependencies:** All previous phases
**Parallelizable:** Yes — QA checks (6.1-6.7) are fully independent; CLI (6.9) is independent of QA internals

### Goals

- Implement the 7-check validation suite for chunk quality assurance
- Build the CLI argument parser with 4 subcommands
- Wire up CLI subcommands to pipeline functions

### Work Items

#### 6.1 Implement `check_orphaned_steps()`

**Requirement Refs:** PRD 6.1 (Check 1)
**Files Affected:**
- `src/pipeline/qa.py` (modify)

**Description:**
Detect chunks that start mid-sequence (e.g., `(3)` without preceding `(1)(2)`). A chunk starting with `(1)` or `a.` is valid.

**Tasks:**
1. [ ] Check first step in each chunk against step patterns
2. [ ] Flag chunks starting mid-sequence
3. [ ] Return list of `ValidationIssue` with `check="orphaned_steps"`

**Acceptance Criteria:**
- [ ] All 5 tests in `TestCheckOrphanedSteps` pass

---

#### 6.2 Implement `check_split_safety_callouts()`

**Requirement Refs:** PRD 6.1 (Check 2)
**Files Affected:**
- `src/pipeline/qa.py` (modify)

**Description:**
Detect safety callouts at chunk boundaries without their governed procedure.

**Tasks:**
1. [ ] Check if chunk starts with a safety callout without following procedure text
2. [ ] Return `ValidationIssue` list

**Acceptance Criteria:**
- [ ] All 3 tests in `TestCheckSplitSafetyCallouts` pass

---

#### 6.3 Implement `check_size_outliers()`

**Requirement Refs:** PRD 6.1 (Check 3)
**Files Affected:**
- `src/pipeline/qa.py` (modify)

**Description:**
Flag chunks below `min_tokens` (default 100) or above `max_tokens` (default 3000).

**Tasks:**
1. [ ] Count tokens for each chunk
2. [ ] Flag chunks outside range with severity "warning"

**Acceptance Criteria:**
- [ ] All 3 tests in `TestCheckSizeOutliers` pass

---

#### 6.4 Implement `check_metadata_completeness()`

**Requirement Refs:** PRD 6.1 (Check 4)
**Files Affected:**
- `src/pipeline/qa.py` (modify)

**Description:**
Verify every chunk has required metadata fields: `manual_id`, `level1_id`, `content_type`.

**Tasks:**
1. [ ] Check each chunk's metadata dict for required keys
2. [ ] Flag missing fields with severity "error"

**Acceptance Criteria:**
- [ ] All 4 tests in `TestCheckMetadataCompleteness` pass

---

#### 6.5 Implement `check_duplicate_content()`

**Requirement Refs:** PRD 6.1 (Check 5)
**Files Affected:**
- `src/pipeline/qa.py` (modify)

**Description:**
Detect near-duplicate chunks using text similarity above threshold (default 0.95).

**Tasks:**
1. [ ] Compare chunk texts pairwise
2. [ ] Calculate similarity (token overlap or ratio)
3. [ ] Flag pairs exceeding threshold

**Acceptance Criteria:**
- [ ] All 3 tests in `TestCheckDuplicateContent` pass

---

#### 6.6 Implement `check_cross_ref_validity()`

**Requirement Refs:** PRD 6.1 (Check 6)
**Files Affected:**
- `src/pipeline/qa.py` (modify)

**Description:**
Verify that cross-reference targets resolve to existing chunk IDs.

**Tasks:**
1. [ ] Collect all chunk IDs into a set
2. [ ] Flag references to non-existent chunk IDs

**Acceptance Criteria:**
- [ ] All 3 tests in `TestCheckCrossRefValidity` pass

---

#### 6.7 Implement `check_profile_validation()`

**Requirement Refs:** PRD 6.1 (Check 7)
**Files Affected:**
- `src/pipeline/qa.py` (modify)

**Description:**
Verify that level1 IDs in chunks match the profile's `known_ids` list.

**Tasks:**
1. [ ] Extract `level1_id` from each chunk's metadata
2. [ ] Compare against `profile.hierarchy[0].known_ids`
3. [ ] Flag unrecognized IDs

**Acceptance Criteria:**
- [ ] All 2 tests in `TestCheckProfileValidation` pass

---

#### 6.8 Implement `run_validation_suite()`

**Requirement Refs:** PRD 6.1 (Full validation suite)
**Files Affected:**
- `src/pipeline/qa.py` (modify)

**Description:**
Run all 7 checks and aggregate into a `ValidationReport`.

**Tasks:**
1. [ ] Call all 7 check functions
2. [ ] Aggregate issues, count errors and warnings
3. [ ] Set `passed = (error_count == 0)`
4. [ ] Return `ValidationReport`

**Acceptance Criteria:**
- [ ] All 7 tests in `TestRunValidationSuite` pass
- [ ] `passed` is `True` only when `error_count == 0`

---

#### 6.9 Implement CLI (`build_parser()` and subcommands)

**Requirement Refs:** PRD 7.1 (CLI Interface)
**Files Affected:**
- `src/pipeline/cli.py` (modify)

**Description:**
Build `ArgumentParser` with 4 subcommands: `process`, `bootstrap-profile`, `validate`, `qa`. Implement `main()` entry point.

**Tasks:**
1. [ ] `build_parser()`: Create parser with subcommands
   - `process --profile <path> --pdf <path>`
   - `bootstrap-profile --pdf <path> --output <path>`
   - `validate --profile <path> --pdf <path>`
   - `qa --manual-id <id> --test-set <path>`
2. [ ] `cmd_process()`: Wire up full pipeline
3. [ ] `cmd_bootstrap_profile()`: Stub for LLM-based profile generation
4. [ ] `cmd_validate()`: Wire up to validation
5. [ ] `cmd_qa()`: Wire up to QA suite
6. [ ] `main()`: Parse args, dispatch to handler, return exit code
7. [ ] Handle errors gracefully (nonexistent files produce non-zero exit code)

**Acceptance Criteria:**
- [ ] All 8 tests in `TestBuildParser` pass
- [ ] All 3 tests in `TestMain` pass
- [ ] Subcommands accept required arguments
- [ ] Missing subcommand raises SystemExit

---

### Phase 6 Testing Requirements

- [ ] `pytest tests/test_qa.py` — all 39 tests pass
- [ ] `pytest tests/test_cli.py` — all 11 tests pass

### Phase 6 Completion Checklist

- [ ] All work items complete
- [ ] All 50 QA + CLI tests passing
- [ ] Full test suite passes: `pytest` — all 233 tests green
- [ ] No regressions across any phase

---

## Parallel Work Opportunities

| Work Item | Can Run With | Notes |
|-----------|--------------|-------|
| Phase 2 (OCR) | Phase 3 (Structural) | Both depend only on Phase 1; no inter-dependency |
| 4.1 count_tokens | 4.2 compose_header | Independent utility functions |
| 4.3 detect_steps | 4.4 detect_safety | Independent detection functions |
| 4.6-4.12 Rules R1-R8 | Each other | Rules are independent transforms |
| 5.1-5.3 Embedding | 5.4-5.6 Retrieval | Different modules, linked only through data types |
| 6.1-6.7 QA checks | Each other | All 7 checks are fully independent |
| 6.1-6.8 QA suite | 6.9 CLI | QA logic vs argument parsing are independent |

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation Strategy |
|------|------------|--------|---------------------|
| Profile YAML structure does not match test expectations | Medium | High | Read test fixtures carefully; match YAML key paths exactly to dataclass fields |
| OCR garbage detection threshold logic unclear | Low | Medium | Study test cases for exact threshold comparison behavior |
| Step pattern detection edge cases (military numbering vs hierarchy) | Medium | Medium | Check hierarchy patterns in level order, disambiguate by context |
| Chunk rule interaction order matters | Medium | High | Apply rules in strict R1 to R8 order; test each independently first |
| SQLite index schema not fully specified | Low | Medium | Derive schema from test assertions in TestBuildSQLiteIndex |
| External service mocking (Ollama, Qdrant) in tests | Medium | Medium | Implement correct API signatures so mocks work |
| Vehicle tagging ambiguity for multi-vehicle manuals | High | Medium | Default to ["all"] when no specific model mentioned |

---

## Success Metrics

- [ ] All 6 phases completed
- [ ] All 233 tests passing (`pytest` exits with code 0)
- [ ] All acceptance criteria met for every work item
- [ ] No `NotImplementedError` remains in any source module
- [ ] Pipeline processes all 3 target manuals (XJ, CJ, TM9) through full chain
- [ ] Chunk validation suite reports no errors on well-formed chunks
- [ ] CLI accepts and dispatches all 4 subcommands correctly

---

## Appendix: Requirement Traceability

| Requirement | Source | Phase | Work Item |
|-------------|--------|-------|-----------|
| YAML profile loading with nested dataclasses | PRD 3.1, 3.2-3.4 | 1 | 1.1 |
| Profile validation | PRD 3.1 | 1 | 1.2 |
| Pattern pre-compilation | PRD 4.3.1 | 1 | 1.3 |
| OCR known substitutions | PRD 4.2.2 step 1 | 2 | 2.1 |
| Header/footer stripping | PRD 4.2.2 step 2 | 2 | 2.2 |
| Garbage line detection | PRD 4.2.2 step 3 | 2 | 2.3 |
| Unicode normalization | PRD 4.2.2 step 4 | 2 | 2.4 |
| Full page cleanup pipeline | PRD 4.2 | 2 | 2.5 |
| OCR quality assessment | PRD 4.2.3 | 2 | 2.6 |
| Chunk ID generation | PRD 4.3.3 | 3 | 3.1 |
| Boundary detection | PRD 4.3.1 | 3 | 3.2 |
| Boundary validation against known_ids | PRD 4.3.1 | 3 | 3.3 |
| Hierarchical manifest building | PRD 4.3.3 | 3 | 3.4 |
| Token counting | PRD 4.4.1 R2 | 4 | 4.1 |
| Hierarchical header composition | PRD 4.4.4 | 4 | 4.2 |
| Step sequence detection | PRD 4.4.1 R3 | 4 | 4.3 |
| Safety callout detection | PRD 4.4.1 R4 | 4 | 4.4 |
| Table detection | PRD 4.4.1 R5 | 4 | 4.5 |
| Rule R1: Primary unit | PRD 4.4.1 | 4 | 4.6 |
| Rule R2: Size targets | PRD 4.4.1 | 4 | 4.7 |
| Rule R3: Never split steps | PRD 4.4.1 | 4 | 4.8 |
| Rule R4: Safety attachment | PRD 4.4.1 | 4 | 4.9 |
| Rule R5: Table integrity | PRD 4.4.1 | 4 | 4.10 |
| Rule R6: Merge small chunks | PRD 4.4.1 | 4 | 4.11 |
| Rules R7-R8: Cross-ref merge, Figure continuity | PRD 4.4.1 | 4 | 4.12 |
| Vehicle applicability tagging | PRD 4.4.3 | 4 | 4.13 |
| Full chunk assembly pipeline | PRD 4.4 | 4 | 4.14 |
| Embedding input composition | PRD 4.5.1 | 5 | 5.1 |
| Qdrant vector indexing | PRD 4.5.3 | 5 | 5.2 |
| SQLite secondary index | PRD 4.5.4 | 5 | 5.3 |
| Query analysis / understanding | PRD 5.1 | 5 | 5.4 |
| Parent/sibling/cross-ref enrichment | PRD 5.2 | 5 | 5.5 |
| Reranking and full retrieval | PRD 5.2 | 5 | 5.6 |
| Check: Orphaned steps | PRD 6.1 | 6 | 6.1 |
| Check: Split safety callouts | PRD 6.1 | 6 | 6.2 |
| Check: Size outliers | PRD 6.1 | 6 | 6.3 |
| Check: Metadata completeness | PRD 6.1 | 6 | 6.4 |
| Check: Duplicate content | PRD 6.1 | 6 | 6.5 |
| Check: Cross-ref validity | PRD 6.1 | 6 | 6.6 |
| Check: Profile validation | PRD 6.1 | 6 | 6.7 |
| Full validation suite | PRD 6.1 | 6 | 6.8 |
| CLI with 4 subcommands | PRD 7.1 | 6 | 6.9 |

---

*Implementation plan generated by Claude on 2026-02-15*
*Source: /create-plan command*
