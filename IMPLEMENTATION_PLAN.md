# Implementation Plan: Multi-Manual Pipeline

**Generated:** 2026-02-16 (Phases 1-4), 2026-02-17 (Phases 5-9)
**Based On:** RECOMMENDATIONS.md + FINDINGS.md
**Supersedes:** Previous IMPLEMENTATION_PLAN.md (Phase 1-3 remediation — complete, 349 tests passing)
**Total Phases:** 9
**Estimated Total Effort:** ~350K tokens

---

## Plan Overview

This plan has two eras. **Phases 1-4** (completed) addressed XJ output quality — the pipeline now processes the 1,948-page XJ service manual with QA passing (0 errors, 2,137 chunks, 439 tests). **Phases 5-9** (new) extend the pipeline to the CJ Universal and military TM manual families, fixing cross-cutting code issues discovered during multi-manual validation and creating production profiles for 4 additional manuals.

**Strategy:** Phase 5 fixes pipeline code bugs that affect all manuals (cross-ref resolution, regex substitutions, character-spacing collapse). Phases 6-7 create production profiles for the two existing test-fixture manuals (CJ, TM9-8014). Phase 8 onboards two new manuals (TM9-8015-2, TM9-8015-1). Phase 9 adds a multi-manual regression suite to prevent future regressions.

**Validation approach:** After each profile phase (6-8), run the full pipeline against the real PDF and confirm QA passes.

### Phase Summary Table

| Phase | Focus Area | Key Deliverables | Est. Tokens | Dependencies | Status |
|-------|------------|------------------|-------------|--------------|--------|
| 1 | Mandatory known_ids filter | Schema field, dataclass field, filter pass, 5 tests | ~25K | None | **Complete** |
| 2 | Production XJ profile | Complete profile YAML, L2/L3/L4 patterns, profile regression test | ~30K | Phase 1 | **Complete** |
| 3 | Cross-ref namespace fix | Qualify refs, downgrade skip_section refs, 5 tests | ~20K | None | **Complete** |
| 4 | End-to-end XJ validation | Pipeline run, metric comparison, iterative tuning | ~25K | Phases 1-3 | **Complete** |
| 5 | Pipeline code fixes | Cross-ref partial-path, regex subs, char-spacing collapse, logging | ~60K | None | **Complete** |
| 6 | Production CJ profile | Complete 25-section profile, validation, regression test | ~50K | Phase 5 | In Progress (6.1 complete) |
| 7 | Production TM9-8014 profile | Expanded subs, L4 removal, synthetic chapters, validation | ~50K | Phase 5 | In Progress (7.1 complete) |
| 8 | New manual profiles | TM9-8015-2 + TM9-8015-1 profiles, validation runs | ~60K | Phases 5, 7 | In Progress (8.1 complete) |
| 9 | Multi-manual regression suite | Profile regression tests, CLI report enhancement | ~30K | Phases 6-8 | Pending |

---

## Phase 1: Mandatory known_ids Filter [COMPLETE]

*Completed 2026-02-16. See PROGRESS.md for details. 5 new tests, 439 total passing.*

---

## Phase 2: Production XJ Profile [COMPLETE]

*Completed 2026-02-16. See PROGRESS.md for details. 6 new tests, 439 total passing.*

---

## Phase 3: Cross-Reference Namespace Fix [COMPLETE]

*Completed 2026-02-16. See PROGRESS.md for details. 5 new tests, 439 total passing.*

---

## Phase 4: End-to-End XJ Validation [COMPLETE]

*Completed 2026-02-16. XJ QA passes: 0 errors, 2,137 chunks, 5 cross-ref warnings (8W skipped). See PROGRESS.md.*

---

<!-- Appended on 2026-02-17 from /plan-improvements based on FINDINGS.md -->

## Phase 5: Pipeline Code Fixes for Multi-Manual Support [COMPLETE]

*Completed 2026-02-17. All 4 work items (5.1-5.4) ran in parallel with no merge conflicts. 465 tests passing. See PROGRESS.md for details.*

---

## Phase 6: Production CJ Universal Profile

**Estimated Effort:** ~50,000 tokens (including validation and tuning)
**Dependencies:** Phase 5 (needs regex subs and char-spacing collapse)
**Parallelizable:** Yes — can run concurrently with Phase 7

### Goals
- Create `profiles/cj-universal.yaml` with complete known_ids and filtering
- Achieve QA-passing pipeline output for the 376-page CJ service manual
- Add profile regression test

### Work Items

#### 6.1 Create Production CJ Profile [COMPLETE — 2026-02-17]

*Completed 2026-02-17. Files: profiles/cj-universal.yaml, tests/test_profile.py. 28 known_ids, 11 regression tests.*

**Recommendation Ref:** P1, P3
**Files Affected:** `profiles/cj-universal.yaml` (new)

**Acceptance Criteria:**
- [x] Profile passes schema validation
- [x] All regex patterns compile
- [x] known_ids count = 28
- [x] `require_known_id: true` on L1
- [x] `collapse_spaced_chars: true`

---

#### 6.2 Validate Against Real PDF

**Recommendation Ref:** P1
**Files Affected:** None (validation only)

**Description:**
Run pipeline against `data/53-71 CJ5 Service Manual.pdf`. Compare metrics against FINDINGS.md baseline.

| Metric | Baseline (FINDINGS.md) | Target |
|--------|----------------------|--------|
| L1 boundaries | 1,172 | ~25 |
| Total chunks | 1,224 | 400-800 |
| Undersized (<200 tokens) | 730 (59.6%) | <15% |
| Cross-ref errors | 11 | 0 |
| QA warnings | 1,406 | <50 |
| QA passed | False | True |

**Acceptance Criteria:**
- [ ] QA passes (zero errors)
- [ ] L1 boundaries within expected range
- [ ] Chunk sizes improved significantly

---

#### 6.3 Add Profile Regression Test

**Recommendation Ref:** D1
**Files Affected:** `tests/test_profile.py`

**Description:**
Add integration test that loads `profiles/cj-universal.yaml`, validates it, compiles patterns, asserts invariants (25 known_ids, require_known_id on L1, collapse_spaced_chars enabled).

**Acceptance Criteria:**
- [ ] Profile loads and validates
- [ ] known_ids count = 25
- [ ] Compound IDs (D1, F1, F2, J1) present
- [ ] All patterns compile

---

### Phase 6 Completion Checklist
- [ ] `profiles/cj-universal.yaml` created and validates
- [ ] Pipeline produces QA-passing output for CJ manual
- [ ] Regression test added
- [ ] All tests passing

---

## Phase 7: Production TM9-8014 Profile

**Estimated Effort:** ~50,000 tokens (including validation and tuning)
**Dependencies:** Phase 5 (needs cross-ref partial-path matching and regex subs)
**Parallelizable:** Yes — can run concurrently with Phase 6

### Goals
- Create `profiles/tm9-8014.yaml` with expanded OCR substitutions and filtering
- Resolve the L4/step pattern collision
- Achieve QA-passing pipeline output for the 391-page military operator manual

### Work Items

#### 7.1 Create Production TM9-8014 Profile [COMPLETE — 2026-02-17]

*Completed 2026-02-17. Files: profiles/tm9-8014.yaml, tests/test_profile.py. 4 chapter known_ids, 42 OCR subs, 12 regression tests.*

**Recommendation Ref:** P2, P3
**Files Affected:** `profiles/tm9-8014.yaml` (new)

**Acceptance Criteria:**
- [x] Profile passes schema validation
- [x] All regex patterns compile
- [x] 4 chapter known_ids
- [x] No L4 hierarchy level
- [x] `require_known_id: true` on L1

---

#### 7.2 Validate Against Real PDF

**Recommendation Ref:** P2
**Files Affected:** None (validation only)

**Description:**
Run pipeline against `data/TM9-8014.pdf`. Compare against FINDINGS.md baseline.

| Metric | Baseline (FINDINGS.md) | Target |
|--------|----------------------|--------|
| L1 (Chapter) | 1 | 2-4 |
| L4 (Sub-paragraph) | 334 | 0 (removed) |
| Cross-ref errors | 342 | 0 (fixed by Phase 5.1) |
| Orphaned step warnings | 74 | <10 |
| Total chunks | 173 | 150-300 |
| QA passed | False | True |

**Acceptance Criteria:**
- [ ] QA passes (zero errors)
- [ ] Cross-ref errors eliminated
- [ ] Orphaned step warnings dramatically reduced

---

#### 7.3 Add Profile Regression Test

**Recommendation Ref:** D1
**Files Affected:** `tests/test_profile.py`

**Description:**
Integration test for `profiles/tm9-8014.yaml` — validates, compiles, asserts invariants (4 chapter known_ids, no L4, require_known_id on L1).

**Acceptance Criteria:**
- [ ] Profile loads and validates
- [ ] No L4 hierarchy level
- [ ] 4 chapter known_ids present

---

### Phase 7 Completion Checklist
- [ ] `profiles/tm9-8014.yaml` created and validates
- [ ] Pipeline produces QA-passing output for TM9-8014
- [ ] Regression test added
- [ ] All tests passing

---

## Phase 8: New Manual Profiles (TM9-8015 Series)

**Estimated Effort:** ~60,000 tokens (including validation and tuning)
**Dependencies:** Phase 5 (code fixes), Phase 7 (military TM profile patterns)
**Parallelizable:** 8.1 and 8.2 are sequential (8.1 first, lessons applied to 8.2)

### Goals
- Create production profiles for two new manuals: TM9-8015-2 (strongest candidate) and TM9-8015-1
- Validate both against real PDFs
- Complete the M38A1 service manual set (3 of 3 TMs profiled)

### Work Items

#### 8.1 Create TM9-8015-2 Profile (Power Train/Body/Frame) [COMPLETE — 2026-02-17]

*Completed 2026-02-17. Files: profiles/tm9-8015-2.yaml, tests/test_profile.py. 58 L1 sections, 14 regression tests.*

**Recommendation Ref:** P4
**Files Affected:** `profiles/tm9-8015-2.yaml` (new)

**Acceptance Criteria:**
- [x] Profile passes schema validation
- [x] Pipeline produces QA-passing output
- [x] 58 L1 sections
- [x] Profile regression test added

---

#### 8.2 Create TM9-8015-1 Profile (Engine/Clutch)

**Recommendation Ref:** P5
**Files Affected:** `profiles/tm9-8015-1.yaml` (new)

**Description:**
Poorest OCR quality. 188 pages, zero clean CHAPTER markers. Requires:
- Heavy reliance on known_ids (chapter headings too garbled for regex)
- Aggressive OCR substitutions (multiple patterns from TM9-8015-2 experience)
- No L4 level
- May need fallback strategy if chapters are undetectable

**Acceptance Criteria:**
- [ ] Profile passes schema validation
- [ ] Pipeline completes without errors
- [ ] QA passes or failures are documented with justification
- [ ] Profile regression test added

---

### Phase 8 Completion Checklist
- [ ] `profiles/tm9-8015-2.yaml` created, validated, QA passes
- [ ] `profiles/tm9-8015-1.yaml` created, validated, best-effort QA
- [ ] Both regression tests added
- [ ] All tests passing
- [ ] M38A1 manual set complete (TM9-8014 + TM9-8015-1 + TM9-8015-2)

---

## Phase 9: Multi-Manual Regression Suite

**Estimated Effort:** ~30,000 tokens
**Dependencies:** Phases 6-8 (all production profiles must exist)
**Parallelizable:** No — final integration phase

### Goals
- Create a comprehensive profile regression test that validates all production profiles
- Add CLI validation report grouping for better UX
- Update documentation

### Work Items

#### 9.1 Profile Discovery Test

**Recommendation Ref:** D1
**Files Affected:** `tests/test_profile.py`, `tests/conftest.py`

**Description:**
Add a conftest fixture that discovers all YAML files in `profiles/`. Create a parametrized test that loads each profile, validates it, compiles patterns, and asserts common invariants:
- Schema valid
- All regex patterns compile
- L1 has `require_known_id: true`
- known_ids is non-empty on L1
- No duplicate known_ids within a level

**Acceptance Criteria:**
- [ ] Test automatically discovers all profiles in `profiles/`
- [ ] Each profile passes all common invariants
- [ ] Adding a new profile automatically includes it in the test

---

#### 9.2 CLI Validation Report Grouping

**Recommendation Ref:** D2
**Files Affected:** `src/pipeline/cli.py`, `tests/test_cli.py`

**Description:**
After logging all issues, add a summary grouping:
```
=== Validation Summary ===
cross_ref_validity: 0 errors, 5 warnings
size_outlier: 0 errors, 12 warnings
orphaned_steps: 0 errors, 3 warnings
...
Total: 0 errors, 20 warnings
Result: PASSED
```

Keep full detail in normal mode; add `--summary-only` flag to suppress per-issue output.

**Acceptance Criteria:**
- [ ] Summary appears after individual issues
- [ ] Groups by (check, severity)
- [ ] Shows total counts
- [ ] 2 new tests

---

#### 9.3 Update Documentation

**Recommendation Ref:** A1
**Files Affected:** `CLAUDE.md`, `PROGRESS.md`, `LEARNINGS.md`

**Description:**
- Update CLAUDE.md code layout with all production profiles
- Update PROGRESS.md with Phase 5-9 completion records
- Update LEARNINGS.md with multi-manual findings
- Formalize test fixture vs production profile convention in CLAUDE.md

**Acceptance Criteria:**
- [ ] CLAUDE.md reflects current state
- [ ] Convention documented: test fixtures are minimal, production profiles are complete

---

### Phase 9 Completion Checklist
- [ ] Profile discovery test covers all production profiles
- [ ] CLI validation report is usable for multi-manual workflows
- [ ] Documentation updated
- [ ] All tests passing

---

## Parallel Work Opportunities

Phases 1 and 3 are fully independent and can execute concurrently (completed):

| Work Item | Can Run With | Notes |
|-----------|--------------|-------|
| Phase 1 (known_ids filter) | Phase 3 (cross-ref fix) | Complete |
| Phase 5.1 (partial-path) | Phase 5.2 (regex subs) | Different files: qa.py vs. ocr_cleanup.py + profile.py |
| Phase 5.1 (partial-path) | Phase 5.3 (char-spacing) | Different files entirely |
| Phase 5.2 (regex subs) | Phase 5.3 (char-spacing) | Both in ocr_cleanup.py but different functions |
| Phase 6 (CJ profile) | Phase 7 (TM9-8014 profile) | Different profiles, different manuals |
| Phase 8.1 (TM9-8015-2) | — | Sequential: lessons feed into 8.2 |
| Phase 9 (regression suite) | — | Depends on all profiles existing |

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| L4 pattern too broad, creates false positives | Medium | Medium | Resolved: Remove L4 from military TM profiles entirely (P3). |
| `a`-suffixed group variants rejected by known_ids filter | Medium | Low | Phase 4.4 handled iteratively (complete for XJ). |
| L3 closed vocabulary misses non-standard procedure names | Low | Medium | Start with Chrysler standard keywords. Expand during tuning. |
| Test fixture changes break existing tests | Zero | — | Test fixtures are NOT modified. Production profiles are separate. |
| Cross-ref partial-path over-matches | Low | Medium | Segment-boundary matching (`::69` not `::169`) prevents false positives. Test with edge cases. |
| Character-spacing collapse changes meaning | Low | Low | Requires 3+ single-char sequences. Two-letter combos preserved. Opt-in flag. |
| Regex substitution performance | Low | Low | Patterns are compiled once during profile load, not per-page. Small pattern count. |
| CJ compound IDs (D1, F1) not detectable in OCR | Medium | Medium | OCR may render as `D 1` or `D l` (lowercase L). Test with real data; add literal substitutions if needed. |
| TM9-8014 Chapters 2 and 3 are image-only | High | Medium | Accept 2-chapter coverage or add synthetic boundaries at known page ranges from TOC. |
| TM9-8015-1 OCR too degraded for pipeline | Medium | Medium | If QA fails despite best-effort profile, document as needing re-OCR. Pipeline correctness > coverage. |

---

## Success Metrics

| Metric | Current (Baseline) | Target | Measurement |
|--------|-------------------|--------|-------------|
| XJ QA passed | True | True (maintain) | `pipeline validate` exit code 0 |
| CJ QA passed | False (11 errors) | True | `pipeline validate` exit code 0 |
| TM9-8014 QA passed | False (342 errors) | True | `pipeline validate` exit code 0 |
| TM9-8015-2 QA passed | N/A (no profile) | True | `pipeline validate` exit code 0 |
| TM9-8015-1 QA passed | N/A (no profile) | True or documented | `pipeline validate` |
| Production profiles | 1 (XJ) | 5 (XJ, CJ, TM9-8014, 8015-1, 8015-2) | `ls profiles/*.yaml` |
| Total tests | 439 | 470+ | `pytest` summary |
| Manuals with QA passing | 1/3 profiled | 4-5/5 profiled | Pipeline validation runs |

---

## Files Changed (Phases 5-9)

| File | Phase | Change |
|------|-------|--------|
| `src/pipeline/qa.py` | 5.1 | Add suffix-segment matching to cross-ref resolution |
| `tests/test_qa.py` | 5.1 | Add 4 partial-path matching tests |
| `src/pipeline/profile.py` | 5.2, 5.3 | Add `regex_substitutions`, `collapse_spaced_chars` to `OcrCleanupConfig` |
| `src/pipeline/ocr_cleanup.py` | 5.2, 5.3 | Add `apply_regex_substitutions()`, `collapse_spaced_characters()` |
| `schema/manual_profile_v1.schema.json` | 5.2, 5.3 | Add `regex_substitutions`, `collapse_spaced_chars` properties |
| `tests/test_ocr_cleanup.py` | 5.2, 5.3 | Add 9 new tests (5 regex + 4 spacing) |
| `tests/test_profile.py` | 5.2 | Add regex validation test |
| `src/pipeline/structural_parser.py` | 5.4 | Add per-pass INFO logging |
| `profiles/cj-universal.yaml` | 6.1 | New production CJ profile |
| `tests/test_profile.py` | 6.3 | Add CJ profile regression test |
| `profiles/tm9-8014.yaml` | 7.1 | New production TM9-8014 profile |
| `tests/test_profile.py` | 7.3 | Add TM9-8014 profile regression test |
| `profiles/tm9-8015-2.yaml` | 8.1 | New TM9-8015-2 profile |
| `profiles/tm9-8015-1.yaml` | 8.2 | New TM9-8015-1 profile |
| `tests/test_profile.py` | 8.1, 8.2 | Add regression tests for both new profiles |
| `tests/conftest.py` | 9.1 | Add profile discovery fixture |
| `src/pipeline/cli.py` | 9.2 | Add validation report grouping |
| `tests/test_cli.py` | 9.2 | Add 2 report grouping tests |
| `CLAUDE.md` | 9.3 | Update documentation |
| `PROGRESS.md` | 9.3 | Update completion records |
| `LEARNINGS.md` | 9.3 | Add multi-manual findings |

---

*Implementation plan generated by Claude on 2026-02-16 (Phases 1-4), 2026-02-17 (Phases 5-9)*
*Based on: RECOMMENDATIONS.md + FINDINGS.md*
