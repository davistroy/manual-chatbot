# Progress Log

**Started:** 2026-02-15
**Last Updated:** 2026-02-17

## Completed Work Items

| Date | Work Item | Files Changed | Tests |
|------|-----------|---------------|-------|
| 2026-02-15 | Phase 1: Profile System (1.1-1.3) | src/pipeline/profile.py | 48/48 pass |
| 2026-02-15 | Phase 2: OCR Cleanup (2.1-2.6) | src/pipeline/ocr_cleanup.py | 39/39 pass |
| 2026-02-15 | Phase 3: Structural Parsing (3.1-3.4) | src/pipeline/structural_parser.py | 28/28 pass |
| 2026-02-15 | Phase 4: Chunk Assembly (4.1-4.14) | src/pipeline/chunk_assembly.py | 41/41 pass |
| 2026-02-15 | Phase 5: Embedding and Retrieval (5.1-5.6) | src/pipeline/embeddings.py, src/pipeline/retrieval.py | 31/31 pass |
| 2026-02-15 | Phase 6: QA and CLI (6.1-6.9) | src/pipeline/qa.py, src/pipeline/cli.py | 42/42 pass |

| 2026-02-15 | Schema stability, typed profiles, architectural docs | src/pipeline/profile.py, chunk_assembly.py, ocr_cleanup.py, schema/ | 250/250 pass |

### REVIEW.md Remediation (Implementation Plan v2)

| Date | Work Item | Files Changed | Tests |
|------|-----------|---------------|-------|
| 2026-02-16 | Phase 1.1: Fix cross-page coordinate model | src/pipeline/structural_parser.py, tests/test_structural_parser.py, tests/conftest.py | 6 new tests |
| 2026-02-16 | Phase 1.2: Align metadata contract | src/pipeline/chunk_assembly.py, tests/test_chunk_assembly.py, tests/test_qa.py | 5 new tests |
| 2026-02-16 | Phase 1.3: Fix embedding composition contract | src/pipeline/embeddings.py, tests/test_embeddings.py | 4 new tests |
| 2026-02-16 | Phase 2.1: Add HTTP timeout and retry | src/pipeline/embeddings.py, tests/test_embeddings.py | 3 new tests |
| 2026-02-16 | Phase 2.2: Surface retrieval failures | src/pipeline/retrieval.py, tests/test_retrieval.py | 4 new tests |
| 2026-02-16 | Phase 2.3: Fix safety callout regex handling | src/pipeline/chunk_assembly.py, tests/test_chunk_assembly.py | 2 new tests |
| 2026-02-16 | Phase 2.4: Make bootstrap-profile fail fast | src/pipeline/cli.py, tests/test_cli.py | 1 new test |
| 2026-02-16 | Phase 2.5: Use deterministic Qdrant point IDs | src/pipeline/embeddings.py, tests/test_embeddings.py | 2 new tests |
| 2026-02-16 | Phase 3.1: Add chunk persistence (JSONL) | src/pipeline/chunk_assembly.py, src/pipeline/cli.py, tests/test_chunk_assembly.py, tests/test_cli.py | 14 new tests |
| 2026-02-16 | Phase 3.2: Add manifest persistence | src/pipeline/structural_parser.py, tests/test_structural_parser.py | 6 new tests |
| 2026-02-16 | Phase 3.3: Enable offline QA | src/pipeline/cli.py, tests/test_cli.py | 9 new tests |
| 2026-02-16 | Phase 3.4: Implement R5 and R8 rules | src/pipeline/chunk_assembly.py, tests/test_chunk_assembly.py | 12 new tests |
| 2026-02-16 | Phase 4.1: Add structured logging | src/pipeline/*.py, tests/test_cli.py | 5 new tests |
| 2026-02-16 | Phase 4.2: Type ManifestEntry ranges | src/pipeline/structural_parser.py, src/pipeline/chunk_assembly.py, tests/ | 0 new tests (refactoring) |
| 2026-02-16 | Phase 4.3: Multi-page test fixtures | tests/conftest.py, tests/test_structural_parser.py, tests/test_chunk_assembly.py | 22 new tests |

### Output Quality Implementation (Implementation Plan v3)

| Date | Work Item | Files Changed | Tests |
|------|-----------|---------------|-------|
| 2026-02-16 | Phase 1: Mandatory known_ids filter (1.1-1.4) | schema/manual_profile_v1.schema.json, src/pipeline/profile.py, src/pipeline/structural_parser.py, tests/test_structural_parser.py | 5 new tests |
| 2026-02-16 | Phase 3: Cross-ref namespace fix (3.1-3.3) | src/pipeline/chunk_assembly.py, src/pipeline/qa.py, tests/test_chunk_assembly.py, tests/test_qa.py | 5 new tests |
| 2026-02-16 | Phase 2: Production XJ profile (2.1-2.2) | profiles/xj-1999.yaml (new), tests/test_profile.py | 6 new tests |
| 2026-02-16 | Phase 4: End-to-end validation (4.1-4.5) | src/pipeline/qa.py | 0 new tests (validation + tuning) |

### Multi-Manual Pipeline Code Fixes (Implementation Plan v4, Phase 5)

| Date | Work Item | Files Changed | Tests |
|------|-----------|---------------|-------|
| 2026-02-17 | Phase 5.1: Cross-reference partial-path matching | src/pipeline/qa.py, tests/test_qa.py | 4 new tests |
| 2026-02-17 | Phase 5.2: Regex-based OCR substitution support | src/pipeline/profile.py, src/pipeline/ocr_cleanup.py, schema/manual_profile_v1.schema.json, tests/test_ocr_cleanup.py, tests/test_profile.py | 5 new tests |
| 2026-02-17 | Phase 5.3: Character-spacing collapse pre-processor | src/pipeline/profile.py, src/pipeline/ocr_cleanup.py, schema/manual_profile_v1.schema.json, tests/test_ocr_cleanup.py | 4 new tests |
| 2026-02-17 | Phase 5.4: Per-pass filter logging | src/pipeline/structural_parser.py, tests/test_structural_parser.py | 0 new tests (logging only) |

### Production Profile Creation (Implementation Plan v4, Phases 6-8)

| Date | Work Item | Files Changed | Tests |
|------|-----------|---------------|-------|
| 2026-02-17 | Phase 6.1: Create production CJ universal profile | profiles/cj-universal.yaml (new), tests/test_profile.py | 11 new tests (28 known_ids) |
| 2026-02-17 | Phase 7.1: Create production TM9-8014 profile | profiles/tm9-8014.yaml (new), tests/test_profile.py | 12 new tests (4 chapter known_ids, 42 OCR subs) |
| 2026-02-17 | Phase 8.1: Create TM9-8015-2 profile | profiles/tm9-8015-2.yaml (new), tests/test_profile.py | 14 new tests (58 L1 sections) |
| 2026-02-17 | Phase 6.2: Validate CJ pipeline against real PDF | profiles/cj-universal.yaml, src/pipeline/qa.py, tests/test_profile.py | 521 chunks, 0 errors, 0.4% undersized. L1 end-of-line anchor, min_gap_lines=500 |
| 2026-02-17 | Phase 7.2: Validate TM9-8014 pipeline against real PDF | src/pipeline/profile.py, src/pipeline/qa.py, schema/manual_profile_v1.schema.json, profiles/tm9-8014.yaml | 83 chunks, 0 errors. Added cross_ref_unresolved_severity field |
| 2026-02-17 | Phase 8.2: Create TM9-8015-1 profile and validate | profiles/tm9-8015-1.yaml (new), tests/test_profile.py | 64 chunks, 0 errors, 58 warnings. Poorest OCR, 35 OCR subs, 19 regression tests |

## Summary

All 6 original phases implemented, plus schema stability and documentation improvements, plus full REVIEW.md remediation (15 work items across 4 phases), plus output quality implementation (4 phases, 16 new tests), plus Phase 5 multi-manual code fixes (4 work items, 13 new tests), plus 5 production profiles created and validated (XJ-1999, CJ universal, TM9-8014, TM9-8015-2, TM9-8015-1). All 5 manuals QA-passing. Full test suite: **522 tests passing** (up from 250 baseline).

### Output Quality Results (XJ 1999 Service Manual)

| Metric | Before | Target | After |
|--------|--------|--------|-------|
| Total chunks | 2,408 | 1,500-2,500 | 2,137 |
| Cross-ref errors | 113 | 0 | 0 |
| Cross-ref warnings (8W) | 0 | ~3 | 5 |
| known_ids warnings | 1,716 | <20 | 4 |
| Undersized chunks (<100 words) | 637 (26%) | <10% | 249 (11.7%) |
| Mean words/chunk | — | — | 248 |
| QA passed | False | **True** | **True** |

No `NotImplementedError` remains in any source module.
