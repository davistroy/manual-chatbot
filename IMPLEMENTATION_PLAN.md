# Implementation Plan: REVIEW.md Remediation

**Generated:** 2026-02-16
**Based On:** RECOMMENDATIONS.md (derived from REVIEW.md architectural audit + codebase analysis)
**Supersedes:** Previous IMPLEMENTATION_PLAN.md (2026-02-15, completed — schema stability/documentation)
**Total Phases:** 4
**Estimated Total Effort:** ~200,000 tokens

---

## Plan Overview

This plan addresses the remediation roadmap from the architectural review (REVIEW.md) plus additional findings from deep codebase analysis. The previous implementation plan (schema stability, typed profiles, documentation) is complete — all 250 tests pass.

The strategy is: **fix data integrity first** (Phase 1), **then reliability** (Phase 2), **then output quality and persistence** (Phase 3), **then developer experience** (Phase 4). Each phase leaves the codebase in a working state with all tests passing.

### Phase Summary Table

| Phase | Focus Area | Key Deliverables | Est. Tokens | Dependencies |
|-------|------------|------------------|-------------|--------------|
| 1 | Data Integrity | Cross-page slicing fix, metadata alignment, embedding contract fix | ~60K | None |
| 2 | Reliability | HTTP timeouts, error surfacing, regex fix, deterministic IDs, bootstrap-profile | ~40K | None |
| 3 | Output & Persistence | JSONL chunk export, manifest export, offline QA, content-type detection | ~60K | Phase 1 (metadata alignment) |
| 4 | Developer Experience | Structured logging, typed ranges, multi-page tests, mypy | ~40K | None |

---

## Phase 1: Data Integrity

**Estimated Effort:** ~60,000 tokens (including testing/fixes)
**Dependencies:** None
**Parallelizable:** 1.1 is independent; 1.2 and 1.3 can run in parallel after 1.1

### Goals

- Fix the cross-page chunk slicing coordinate model (REVIEW #1 — Critical)
- Align metadata contract between assembler, QA, and embeddings (REVIEW #2 — Must Fix)
- Fix embedding composition to use metadata header (REVIEW #3 — Must Fix)

### Work Items

#### 1.1 Fix cross-page coordinate model

**Recommendation Ref:** D1
**Files Affected:**
- `src/pipeline/structural_parser.py` (modify — `detect_boundaries()`, `build_manifest()`)
- `tests/test_structural_parser.py` (modify — update line_number assertions, add multi-page tests)
- `tests/test_chunk_assembly.py` (modify — add multi-page assembly test)
- `tests/conftest.py` (modify — add multi-page fixture)

**Description:**
`detect_boundaries()` records `line_number` as the offset within the current page, but `assemble_chunks()` joins all pages and treats `line_number` as a global offset. For any manual with more than one page, chunk text extraction is wrong.

Fix: track a running `global_line_offset` in `detect_boundaries()`. Before iterating each page's lines, compute `global_offset = sum(len(pages[p].split("\n")) for p in range(page_idx))` (or accumulate incrementally). Store `boundary.line_number = global_offset + line_idx`.

**Tasks:**
1. [ ] Add multi-page test fixtures to `conftest.py` — at least 2 pages with boundaries on each page
2. [ ] Write failing test: process 2 pages through `detect_boundaries` → `build_manifest` → `assemble_chunks`, assert chunk text matches expected content from the correct page
3. [ ] Fix `detect_boundaries()` in `structural_parser.py` to use global line offsets
4. [ ] Update `build_manifest()` if needed (it passes through boundary.line_number — should work once boundaries are correct)
5. [ ] Update existing tests in `test_structural_parser.py` that assert per-page line numbers — these should now assert global offsets
6. [ ] Run full test suite — all 250+ tests must pass

**Acceptance Criteria:**
- [ ] Multi-page test demonstrates correct chunk text extraction from page 2+
- [ ] Boundary line numbers are global (absolute) offsets, not per-page
- [ ] `assemble_chunks()` produces correct text for multi-page manuals without any changes to its own code
- [ ] All existing tests pass (with updated line number expectations)

---

#### 1.2 Align metadata contract

**Recommendation Ref:** D2
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify — metadata dict in `assemble_chunks()`)
- `tests/test_chunk_assembly.py` (modify — assert new metadata fields)
- `tests/test_qa.py` (modify — metadata_completeness tests should now pass cleanly)

**Description:**
Add `manual_id`, `level1_id`, and `procedure_name` to the chunk metadata dict in `assemble_chunks()`. Currently QA's `check_metadata_completeness` always flags missing `manual_id` and `level1_id`, and the SQLite index writes empty strings for `procedure_name` and `level1_id`.

**Tasks:**
1. [ ] Add `"manual_id": manifest.manual_id` to the metadata dict at `chunk_assembly.py:682`
2. [ ] Extract `level1_id` from `entry.hierarchy_path[0]` if available, else from chunk_id parsing. Add to metadata.
3. [ ] Add `"procedure_name": entry.title` to metadata
4. [ ] Update `test_chunk_assembly.py` tests that assert metadata keys
5. [ ] Verify `test_qa.py` metadata_completeness tests pass without false errors
6. [ ] Verify `embeddings.py` SQLite index now gets real values for `level1_id` and `procedure_name`

**Acceptance Criteria:**
- [ ] `chunk.metadata` contains `manual_id`, `level1_id`, `content_type`, `procedure_name`
- [ ] QA `check_metadata_completeness` passes for correctly formed chunks
- [ ] SQLite `procedure_lookup` gets meaningful data
- [ ] All tests pass

---

#### 1.3 Fix embedding composition contract

**Recommendation Ref:** D3
**Files Affected:**
- `src/pipeline/embeddings.py` (modify — `compose_embedding_input()`)
- `tests/test_embeddings.py` (modify — update composition tests)

**Description:**
`compose_embedding_input()` splits `chunk.text` on the first `\n\n` thinking the header is baked into the text. It's not — the header is in `chunk.metadata["hierarchical_header"]`. The function should use the metadata header + body text.

**Tasks:**
1. [ ] Rewrite `compose_embedding_input()` to read header from `chunk.metadata["hierarchical_header"]`
2. [ ] Build embedding text as `f"{header}\n\n{get_first_n_words(chunk.text, 150)}"`
3. [ ] Remove the `\n\n` split logic (dead code after fix)
4. [ ] Handle missing `hierarchical_header` key gracefully (fallback to text-only)
5. [ ] Update tests in `test_embeddings.py` — construct chunks with metadata header and verify output
6. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] Embedding input includes hierarchical context (manual > group > section > procedure)
- [ ] Body text is truncated to 150 words
- [ ] Old `\n\n` split logic is removed
- [ ] Graceful fallback when metadata key is missing
- [ ] All tests pass

---

### Phase 1 Testing Requirements

- [ ] Multi-page boundary/chunking test catches the coordinate bug and passes after fix
- [ ] Metadata completeness QA check passes for well-formed chunks
- [ ] Embedding composition tests verify header comes from metadata
- [ ] All 250+ existing tests pass
- [ ] New tests added: ~10-15

### Phase 1 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing (`pytest -v --tb=short`)
- [ ] LEARNINGS.md updated with coordinate model decision
- [ ] No regressions introduced

---

## Phase 2: Reliability & Error Handling

**Estimated Effort:** ~40,000 tokens (including testing/fixes)
**Dependencies:** None (can run in parallel with Phase 1)
**Parallelizable:** All work items are independent

### Goals

- Add timeout and retry for embedding HTTP calls (REVIEW #6)
- Surface retrieval failures (REVIEW #7)
- Fix safety callout regex inconsistency (REVIEW #8)
- Make bootstrap-profile fail fast (REVIEW #4)
- Use deterministic Qdrant point IDs (REVIEW #5)

### Work Items

#### 2.1 Add HTTP timeout and retry for embedding calls

**Recommendation Ref:** R1
**Files Affected:**
- `src/pipeline/embeddings.py` (modify — `generate_embedding()`)
- `tests/test_embeddings.py` (modify — add timeout and retry tests)

**Description:**
Add `timeout=30` to `requests.post()`. Add retry logic (3 attempts with exponential backoff) for transient errors.

**Tasks:**
1. [ ] Add `timeout=30` parameter to `requests.post()` at `embeddings.py:79`
2. [ ] Wrap the request in a retry loop: 3 attempts, `time.sleep(2 ** attempt)` between failures
3. [ ] Catch `requests.exceptions.ConnectionError`, `requests.exceptions.Timeout`, and 5xx responses
4. [ ] Raise `RuntimeError(f"Embedding generation failed after 3 attempts: {last_error}")` on exhaustion
5. [ ] Add test: mock `requests.post` to raise `ConnectionError` once then succeed — verify retry works
6. [ ] Add test: mock `requests.post` to always fail — verify RuntimeError after 3 attempts

**Acceptance Criteria:**
- [ ] `requests.post()` has `timeout=30`
- [ ] Transient failures are retried up to 3 times
- [ ] Permanent failures raise `RuntimeError` with clear message
- [ ] All tests pass

---

#### 2.2 Surface retrieval failures

**Recommendation Ref:** R2
**Files Affected:**
- `src/pipeline/retrieval.py` (modify — `resolve_cross_references()`)
- `tests/test_retrieval.py` (modify — add error handling tests)

**Description:**
Replace bare `except sqlite3.Error: pass` with `warnings.warn()` so failures are visible. Add `retrieval_warnings: list[str]` field to `RetrievalResponse`.

**Tasks:**
1. [ ] Add `import warnings` to `retrieval.py`
2. [ ] Replace `except sqlite3.Error: pass` with `except sqlite3.Error as e: warnings.warn(f"Cross-reference resolution failed: {e}")`
3. [ ] Add `retrieval_warnings: list[str] = field(default_factory=list)` to `RetrievalResponse`
4. [ ] Capture warnings in `retrieve()` and add to response
5. [ ] Add test: mock SQLite to raise `sqlite3.OperationalError`, verify warning is issued and partial results returned
6. [ ] Document placeholder results in `enrich_with_parent()` and `enrich_with_siblings()` with clear comments

**Acceptance Criteria:**
- [ ] SQLite errors produce `warnings.warn()` rather than silent pass
- [ ] `RetrievalResponse` carries warning messages
- [ ] Partial results still returned on degraded path
- [ ] All tests pass

---

#### 2.3 Fix safety callout regex handling

**Recommendation Ref:** R3
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify — `detect_safety_callouts()`)
- `tests/test_chunk_assembly.py` (modify — add mixed-case pattern test)

**Description:**
`detect_safety_callouts()` compiles patterns with flags at line 141 but then uses `re.search(sc.pattern, stripped)` (the raw string) at line 145 instead of the compiled `pat`. The inner loop at line 157 has the same issue.

**Tasks:**
1. [ ] Change `re.search(sc.pattern, stripped)` at line 145 to `pat.search(stripped)`
2. [ ] Pre-compile inner loop patterns: build a list of compiled safety patterns before the line loop, and use them at line 157 instead of `re.search(sc2.pattern, next_stripped)`
3. [ ] Add test: create a profile with a case-insensitive safety pattern (lowercase "warning"), verify it matches uppercase text
4. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] All pattern matching in `detect_safety_callouts()` uses compiled regex objects
- [ ] No raw `re.search(sc.pattern, ...)` calls remain
- [ ] Mixed-case test passes
- [ ] All existing tests pass

---

#### 2.4 Make bootstrap-profile fail fast

**Recommendation Ref:** R4
**Files Affected:**
- `src/pipeline/cli.py` (modify — `cmd_bootstrap_profile()`)
- `tests/test_cli.py` (modify — update expected exit code)

**Description:**
`cmd_bootstrap_profile()` has a TODO comment and `return 0`. Should print an error and return 1.

**Tasks:**
1. [ ] Replace TODO block with: `print("Error: bootstrap-profile is not yet implemented.", file=sys.stderr)` + `return 1`
2. [ ] Update test in `test_cli.py` that checks bootstrap-profile behavior to expect exit code 1

**Acceptance Criteria:**
- [ ] `pipeline bootstrap-profile` returns exit code 1
- [ ] Error message clearly states the feature is not implemented
- [ ] All tests pass

---

#### 2.5 Use deterministic Qdrant point IDs

**Recommendation Ref:** R5
**Files Affected:**
- `src/pipeline/embeddings.py` (modify — `index_chunks()`)
- `tests/test_embeddings.py` (modify — update ID assertions)

**Description:**
Replace `id=i` with deterministic UUID5 derived from `chunk_id`.

**Tasks:**
1. [ ] Add `import uuid` to `embeddings.py`
2. [ ] Change `id=i` at line 131 to `id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id))`
3. [ ] Update tests that assert point IDs
4. [ ] Add test: verify same chunk_id always produces same point ID
5. [ ] Add test: verify different chunk_ids produce different point IDs

**Acceptance Criteria:**
- [ ] Point IDs are deterministic UUIDs derived from chunk_id
- [ ] Re-indexing the same chunks produces the same point IDs (idempotent)
- [ ] Different manuals don't collide
- [ ] All tests pass

---

### Phase 2 Testing Requirements

- [ ] HTTP timeout/retry behavior tested with mocks
- [ ] SQLite error surfacing tested
- [ ] Regex compilation verified with case-sensitivity test
- [ ] Bootstrap-profile exit code tested
- [ ] Deterministic ID generation tested
- [ ] All 250+ existing tests pass
- [ ] New tests added: ~10-12

### Phase 2 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing (`pytest -v --tb=short`)
- [ ] No regressions introduced

---

## Phase 3: Output & Persistence

**Estimated Effort:** ~60,000 tokens (including testing/fixes)
**Dependencies:** Phase 1 (metadata alignment — chunks need correct metadata before persisting)
**Parallelizable:** 3.1-3.2 are sequential; 3.3 depends on 3.1; 3.4 is independent

### Goals

- Add chunk and manifest persistence (JSONL/JSON export and import)
- Enable offline QA (run validation without Qdrant)
- Implement content-type detection using profile configuration
- Implement functional R5 (table integrity) and R8 (figure continuity)

### Work Items

#### 3.1 Add chunk persistence (JSONL export/import)

**Recommendation Ref:** Q1
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify — add `save_chunks()`, `load_chunks()`)
- `tests/test_chunk_assembly.py` (modify — add persistence tests)
- `src/pipeline/cli.py` (modify — add `--output-dir` to `process` command)

**Description:**
Add functions to serialize chunks to JSONL and deserialize them back. Each line is a JSON object with `chunk_id`, `manual_id`, `text`, and `metadata`. Add `--output-dir` flag to `pipeline process`.

**Tasks:**
1. [ ] Add `save_chunks(chunks: list[Chunk], output_path: Path) -> None` — writes one JSON line per chunk
2. [ ] Add `load_chunks(input_path: Path) -> list[Chunk]` — reads JSONL back into Chunk objects
3. [ ] Add round-trip test: save chunks, load them back, verify equality
4. [ ] Add `--output-dir` flag to `process` subcommand in `build_parser()`
5. [ ] Update `cmd_process()` to write `{manual_id}_chunks.jsonl` when `--output-dir` is provided
6. [ ] Add test for CLI output flag

**Acceptance Criteria:**
- [ ] `save_chunks` produces valid JSONL
- [ ] `load_chunks` round-trips perfectly (identical Chunk objects)
- [ ] `pipeline process --output-dir ./out` writes chunks file
- [ ] All tests pass

---

#### 3.2 Add manifest persistence

**Recommendation Ref:** Q1 (complement)
**Files Affected:**
- `src/pipeline/structural_parser.py` (modify — add `save_manifest()`, `load_manifest()`)
- `tests/test_structural_parser.py` (modify — add persistence tests)
- `src/pipeline/cli.py` (modify — write manifest alongside chunks)

**Description:**
Add manifest serialization to JSON (not JSONL — manifest is a single hierarchical document). Write alongside chunks in `pipeline process --output-dir`.

**Tasks:**
1. [ ] Add `save_manifest(manifest: Manifest, output_path: Path) -> None`
2. [ ] Add `load_manifest(input_path: Path) -> Manifest`
3. [ ] Add round-trip test
4. [ ] Update `cmd_process()` to write `{manual_id}_manifest.json`

**Acceptance Criteria:**
- [ ] Manifest serializes to readable JSON
- [ ] Round-trip preserves all fields
- [ ] All tests pass

---

#### 3.3 Enable offline QA

**Recommendation Ref:** N1
**Files Affected:**
- `src/pipeline/cli.py` (modify — rewrite `cmd_qa()`)
- `tests/test_cli.py` (modify — add offline QA test)

**Description:**
Add `--chunks` and `--profile` flags to `pipeline qa`. Load chunks from JSONL, load profile from YAML, run `run_validation_suite()`. No Qdrant needed.

**Tasks:**
1. [ ] Update `qa` subcommand in `build_parser()`: add `--chunks` (required), `--profile` (required), make `--manual-id` and `--test-set` optional
2. [ ] Rewrite `cmd_qa()`: if `--chunks` provided, load from JSONL and run offline validation
3. [ ] Print validation report to stdout (same format as `cmd_validate()`)
4. [ ] Add test: create temp JSONL, run offline QA, verify report
5. [ ] Keep existing Qdrant-required path as a future option

**Acceptance Criteria:**
- [ ] `pipeline qa --chunks chunks.jsonl --profile profile.yaml` runs validation offline
- [ ] All 7 QA checks run on loaded chunks
- [ ] Exit code 0 on pass, 1 on failure
- [ ] All tests pass

---

#### 3.4 Implement functional R5 and R8

**Recommendation Ref:** Q3
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify — `apply_rule_r5_table_integrity()`, `apply_rule_r8_figure_continuity()`)
- `tests/test_chunk_assembly.py` (modify — add tests for table and figure handling)

**Description:**
R5 currently just returns `list(chunks)`. R8 appends the chunk in both branches. Make both rules functional.

R5: For each chunk, detect tables via `detect_tables()`. If a table spans a chunk boundary (table starts in one chunk and continues in the next), merge those chunks. If a prior splitting rule broke a table apart, reassemble.

R8: If a chunk starts with a figure reference line (matches `figure_pattern`) and the previous chunk's content references the same figure, merge the figure reference into the previous chunk.

**Tasks:**
1. [ ] Implement R5: iterate chunks, detect tables within each, if a table's last line is the chunk's last line AND the next chunk starts with table-like content, merge
2. [ ] Implement R8: iterate chunks, if chunk starts with figure reference, check if previous chunk contains text referencing that figure — if so, merge
3. [ ] Add test for R5: create chunks where a table is split across two chunks, verify they get merged
4. [ ] Add test for R8: create chunks where a figure ref is separated from its context, verify merge
5. [ ] Run full test suite — existing pass-through behavior tests should still pass (rules were no-ops, so inputs that don't trigger the rules should produce identical output)

**Acceptance Criteria:**
- [ ] R5 detects and re-merges split tables
- [ ] R8 detects and re-attaches orphaned figure references
- [ ] Existing tests still pass (rules were no-ops, so non-triggering inputs are unchanged)
- [ ] New tests verify merge behavior
- [ ] All tests pass

---

### Phase 3 Testing Requirements

- [ ] JSONL round-trip for chunks (save/load identity)
- [ ] JSON round-trip for manifest
- [ ] Offline QA produces correct validation report
- [ ] R5 merges split tables
- [ ] R8 merges orphaned figure references
- [ ] CLI `--output-dir` writes expected files
- [ ] All 250+ existing tests pass
- [ ] New tests added: ~15-20

### Phase 3 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing
- [ ] `CLAUDE.md` updated with new CLI flags and persistence functions
- [ ] No regressions introduced

---

## Phase 4: Developer Experience

**Estimated Effort:** ~40,000 tokens (including testing/fixes)
**Dependencies:** None (can run in parallel with Phases 1-3)
**Parallelizable:** All work items are independent

### Goals

- Add structured logging throughout the pipeline
- Type ManifestEntry range fields
- Add multi-page test fixtures
- Configure mypy for type checking

### Work Items

#### 4.1 Add structured logging

**Recommendation Ref:** A2
**Files Affected:**
- `src/pipeline/cli.py` (modify — configure logging, add `--verbose`/`--quiet`)
- `src/pipeline/structural_parser.py` (modify — add debug logging)
- `src/pipeline/ocr_cleanup.py` (modify — add debug logging)
- `src/pipeline/chunk_assembly.py` (modify — add debug logging)
- `src/pipeline/embeddings.py` (modify — add debug logging)
- `src/pipeline/retrieval.py` (modify — add debug logging)

**Description:**
Add Python `logging` to every pipeline module. Configure via CLI flags. Replace `print()` calls with `logger.info()`.

**Tasks:**
1. [ ] Add `import logging` and `logger = logging.getLogger(__name__)` to each source module
2. [ ] Replace all `print()` calls in `cli.py` with `logger.info()` / `logger.error()`
3. [ ] Add `--verbose` flag (sets DEBUG) and `--quiet` flag (sets WARNING) to CLI
4. [ ] Configure root logger in `main()` based on flags
5. [ ] Add `logger.debug()` calls at key decision points: boundary detection, rule application, embedding generation
6. [ ] Update CLI tests to capture log output instead of stdout

**Acceptance Criteria:**
- [ ] All modules use `logging` instead of `print()`
- [ ] `--verbose` shows debug-level output
- [ ] Default shows info-level output
- [ ] `--quiet` suppresses info
- [ ] All tests pass

---

#### 4.2 Type ManifestEntry range fields

**Recommendation Ref:** A1
**Files Affected:**
- `src/pipeline/structural_parser.py` (modify — add `PageRange`, `LineRange` dataclasses, update `ManifestEntry`)
- `src/pipeline/chunk_assembly.py` (modify — update `.get("start", ...)` to attribute access)
- `tests/test_structural_parser.py` (modify — update assertions)
- `tests/test_chunk_assembly.py` (modify — update manifest construction)
- `tests/conftest.py` (modify — update `sample_manifest_entry` fixture)

**Description:**
Replace `page_range: dict[str, str]` and `line_range: dict[str, int]` with typed dataclasses.

**Tasks:**
1. [ ] Define `PageRange` and `LineRange` dataclasses in `structural_parser.py`
2. [ ] Update `ManifestEntry` fields
3. [ ] Update `build_manifest()` to construct typed ranges
4. [ ] Search for `.get("start"` and `.get("end"` — update to `.start` / `.end`
5. [ ] Update test fixtures and assertions
6. [ ] Run full test suite

**Acceptance Criteria:**
- [ ] No dict-style access on range fields
- [ ] `entry.line_range.start` / `entry.line_range.end` work correctly
- [ ] `entry.page_range.start` / `entry.page_range.end` work correctly
- [ ] All tests pass

---

#### 4.3 Add multi-page test fixtures

**Recommendation Ref:** X2
**Files Affected:**
- `tests/conftest.py` (modify — add multi-page fixtures)
- `tests/test_structural_parser.py` (modify — add multi-page boundary tests)
- `tests/test_chunk_assembly.py` (modify — add multi-page assembly tests)

**Description:**
Current test fixtures are all single-page. The cross-page slicing bug (fixed in Phase 1) was latent because no test exercised multi-page behavior. Add multi-page fixtures to prevent regression.

Note: Phase 1 (item 1.1) adds a minimal multi-page test to catch the coordinate bug. This work item adds comprehensive multi-page coverage: multiple boundaries per page, cross-page sections, edge cases (boundary on first/last line of a page).

**Tasks:**
1. [ ] Create `xj_multipage_fixture` — 3 pages with Group, Section, Procedure boundaries spanning pages
2. [ ] Create `tm9_multipage_fixture` — 2 pages with Chapter and Section boundaries
3. [ ] Write tests: detect boundaries across pages, verify global line numbers
4. [ ] Write tests: build manifest from multi-page boundaries, verify chunk_ids and line_ranges
5. [ ] Write tests: assemble chunks from multi-page manifest, verify text extraction
6. [ ] Write edge case test: boundary on first line of page 2

**Acceptance Criteria:**
- [ ] At least 2 multi-page fixtures covering different profile types
- [ ] Boundary detection correctly handles page transitions
- [ ] Manifest line_range values are global offsets
- [ ] Chunk text extraction is correct for boundaries on any page
- [ ] All tests pass

---

#### 4.4 Configure mypy

**Recommendation Ref:** X1
**Files Affected:**
- `pyproject.toml` (modify — add `[tool.mypy]` section)
- `pyproject.toml` (modify — add `mypy` to dev dependencies)

**Description:**
Add mypy to the project for static type checking. Start with permissive settings and fix any immediate errors.

**Tasks:**
1. [ ] Add `"mypy>=1.0"` to `[project.optional-dependencies] dev`
2. [ ] Add `[tool.mypy]` section to `pyproject.toml` with `python_version = "3.10"`, `warn_return_any = true`, `warn_unused_configs = true`
3. [ ] Run `mypy src/pipeline/` and fix any type errors
4. [ ] Document mypy invocation in CLAUDE.md Quick Reference

**Acceptance Criteria:**
- [ ] `mypy src/pipeline/` passes (possibly with some `# type: ignore` for Qdrant client)
- [ ] Dev install includes mypy
- [ ] All tests still pass

---

### Phase 4 Testing Requirements

- [ ] Logging output captured and verified in CLI tests
- [ ] Typed ranges pass all existing tests
- [ ] Multi-page tests cover page transitions and edge cases
- [ ] mypy passes on all source modules
- [ ] All 250+ existing tests pass
- [ ] New tests added: ~15-20

### Phase 4 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing
- [ ] CLAUDE.md updated (Quick Reference, Key Data Types)
- [ ] No regressions introduced

---

## Parallel Work Opportunities

Phases 1 and 2 are fully independent and can execute concurrently. Phase 3 depends on Phase 1 (metadata must be correct before persisting). Phase 4 is independent of everything.

| Work Stream | Can Run With | Notes |
|-------------|--------------|-------|
| Phase 1 (Data Integrity) | Phase 2, Phase 4 | Touches parser, assembler metadata, embeddings |
| Phase 2 (Reliability) | Phase 1, Phase 4 | Touches embeddings HTTP, retrieval error handling, CLI, regex |
| Phase 3 (Persistence) | Phase 4 | Blocked by Phase 1 (needs correct metadata) |
| Phase 4 (DX) | Phase 1, Phase 2 | Touches logging, types, tests — orthogonal to fixes |

Within phases, work items can often run in parallel:

| Item | Can Run With | Conflict |
|------|--------------|----------|
| 1.1 (coordinates) | — | Must complete before 1.2, 1.3 test (touches same files) |
| 1.2 (metadata) | 1.3 (embedding) | Independent — different files |
| 2.1 (timeout) | 2.2, 2.3, 2.4, 2.5 | All independent |
| 3.1 (chunk JSONL) | 3.4 (R5/R8) | Independent |
| 3.2 (manifest JSON) | 3.4 (R5/R8) | Independent |
| 4.1 (logging) | 4.2, 4.3, 4.4 | 4.1 touches many files; run separately to avoid merge conflicts |

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Cross-page fix breaks single-page tests | Medium | Medium | Single-page behavior is a special case of global offsets (page 0 offset = 0). Existing tests should work with minor adjustments. |
| Metadata additions break test assertions | Low | Low | Tests that assert exact metadata dicts need updating. Use `assert "manual_id" in chunk.metadata` rather than exact dict comparison. |
| Embedding contract change affects downstream | Medium | Medium | No downstream consumers yet (Qdrant is stubbed in tests). The change is purely correctness. |
| JSONL format needs future changes | Low | Medium | Use a simple, flat format. Include a `_version` field in the JSONL header for future compat. |
| R5/R8 implementation creates false merges | Medium | Medium | Start conservative — only merge when both signals agree (table pattern match AND adjacency). Add regression tests. |
| Logging changes break CLI test assertions | Medium | Low | Use `caplog` fixture instead of `capsys` in tests. Keep structured output for programmatic use. |
| mypy reveals many type errors | Low | Low | Start permissive. `# type: ignore` on Qdrant client types. Fix real errors, skip vendor types. |

---

## Success Metrics

- [ ] Cross-page chunk extraction produces correct text for the 7 real PDFs in `data/`
- [ ] No QA false positives from metadata contract mismatch
- [ ] Embedding input includes hierarchical context for every chunk
- [ ] `bootstrap-profile` returns error (not silent success)
- [ ] HTTP timeout prevents hanging on Ollama failure
- [ ] Retrieval failures are visible (warnings, not silent)
- [ ] Chunks persist to JSONL and round-trip correctly
- [ ] Offline QA works without external services
- [ ] R5 and R8 are functional (not no-ops)
- [ ] All 250+ tests pass at every phase boundary
- [ ] mypy passes on source modules

---

## Appendix: Requirement Traceability

| Recommendation | REVIEW.md Ref | Phase | Work Item |
|----------------|---------------|-------|-----------|
| D1 — Cross-page coordinates | Critical #1 | 1 | 1.1 |
| D2 — Metadata alignment | High #2 | 1 | 1.2 |
| D3 — Embedding contract | High #3 | 1 | 1.3 |
| R1 — HTTP timeout/retry | Should Fix #6 | 2 | 2.1 |
| R2 — Surface retrieval failures | Must Fix #7 | 2 | 2.2 |
| R3 — Regex consistency | Should Fix #8 | 2 | 2.3 |
| R4 — Bootstrap fail-fast | Must Fix #4 | 2 | 2.4 |
| R5 — Deterministic IDs | Should Fix #5 | 2 | 2.5 |
| Q1 — Chunk persistence | New finding | 3 | 3.1, 3.2 |
| Q3 — R5/R8 no-ops | New finding | 3 | 3.4 |
| N1 — Offline QA | New finding | 3 | 3.3 |
| A1 — Typed ranges | New finding | 4 | 4.2 |
| A2 — Structured logging | New finding | 4 | 4.1 |
| X1 — mypy | New finding | 4 | 4.4 |
| X2 — Multi-page tests | New finding | 4 | 4.3 |

---

*Implementation plan generated by Claude on 2026-02-16*
*Source: RECOMMENDATIONS.md + REVIEW.md architectural audit*
