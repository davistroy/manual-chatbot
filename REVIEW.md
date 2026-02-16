# Architectural Review: manual-chatbot

## Executive Summary

The project is a modular Python monolith with clear pipeline stages:

1. PDF extraction
2. OCR cleanup
3. Structural parsing
4. Chunk assembly
5. Embedding/indexing
6. Retrieval
7. QA validation

The codebase is small and navigable, with broad test coverage and strong intent in comments/docstrings. The main risks are contract mismatches between modules and one core data-integrity issue in chunk text slicing across pages. Based on your clarifications:

- `pipeline process` being extraction/chunk-only is intentional for now.
- Retrieval failures should be surfaced, not silently swallowed.

## Scope and Method

Read-only architectural audit across:

- `src/pipeline/*.py`
- `tests/*.py`
- `pyproject.toml`
- `schema/manual_profile_v1.schema.json`
- `README.md`

No files were modified during analysis. This document is the output artifact requested afterward.

## Architecture Snapshot

### Stack

- Python `>=3.10` (`pyproject.toml:9`)
- Core deps: `pymupdf`, `pyyaml`, `qdrant-client`, `requests` (`pyproject.toml:10`)
- Test deps: `pytest`, `pytest-cov`, `pytest-mock` (`pyproject.toml:18`)

### Pattern

- Single-package modular monolith (`src/pipeline`)
- Pipeline orchestration in CLI (`src/pipeline/cli.py`)
- External boundaries:
  - Ollama HTTP embeddings (`src/pipeline/embeddings.py`)
  - Qdrant vector store (`src/pipeline/embeddings.py`, `src/pipeline/retrieval.py`)
  - SQLite secondary index (`src/pipeline/embeddings.py`)

### Entry Points and Boundaries

- CLI script entrypoint: `pipeline = "pipeline.cli:main"` (`pyproject.toml:25`)
- Main command handlers:
  - `process` (`src/pipeline/cli.py`)
  - `validate` (`src/pipeline/cli.py`)
  - `qa` (`src/pipeline/cli.py`)
  - `bootstrap-profile` (stubbed)

## Findings

## Critical (Must Fix)

### 1) Cross-page chunk slicing uses inconsistent coordinates

- `detect_boundaries` records `page_number` + per-page `line_number` (`src/pipeline/structural_parser.py:128`).
- `build_manifest` stores `line_range.start = boundary.line_number` directly (`src/pipeline/structural_parser.py:237`).
- `assemble_chunks` joins all pages into one global line list, then slices by `line_range.start` (`src/pipeline/chunk_assembly.py:591`, `src/pipeline/chunk_assembly.py:599`).

Risk: chunk content can be misaligned or wrong for multi-page manuals. This is a data-integrity defect and can degrade retrieval quality.

## High (Must/Should Fix)

### 2) Metadata contract mismatch between chunk assembly and QA (Must Fix)

- QA requires metadata keys `manual_id`, `level1_id`, `content_type` (`src/pipeline/qa.py:169`).
- Assembler metadata omits `manual_id` and `level1_id` (`src/pipeline/chunk_assembly.py:682`).

Risk: false errors in validation and noisy QA reports.

### 3) Embedding input contract mismatch (Must Fix)

- `compose_embedding_input` assumes `chunk.text` contains `header\n\nbody` and splits on first blank line (`src/pipeline/embeddings.py:40`).
- Assembler stores hierarchical header in metadata, not in `chunk.text` (`src/pipeline/chunk_assembly.py:683`).

Risk: embedding text loses important context or behaves inconsistently.

Recommendation adopted from discussion: keep `chunk.text` body-only; build embedding text from `metadata.hierarchical_header + chunk.text`.

### 4) `bootstrap-profile` returns success while unimplemented (Must Fix)

- Explicit TODO and `return 0` (`src/pipeline/cli.py:139`).

Risk: command appears successful but does no work.

### 5) Qdrant point IDs are non-deterministic across runs (Should Fix)

- Points are inserted with `id=i` (`src/pipeline/embeddings.py:131`).

Risk: non-idempotent indexing, collisions or overwritten records between runs.

### 6) External HTTP call has no timeout/retry (Should Fix)

- `requests.post(...)` without timeout (`src/pipeline/embeddings.py:79`).

Risk: hanging calls and brittle behavior under service/network issues.

## Medium (Should/Could Fix)

### 7) Retrieval hides backend failures (Must Fix per clarified intent)

- SQLite errors are swallowed: `except sqlite3.Error: pass` (`src/pipeline/retrieval.py:354`).
- Enrichment may add placeholder results with empty `text` (`src/pipeline/retrieval.py:259`, `src/pipeline/retrieval.py:286`, `src/pipeline/retrieval.py:345`).

Risk: silent degradation and hard debugging.

### 8) Safety callout detection has inconsistent regex handling (Should Fix)

- Compiles with flags (`src/pipeline/chunk_assembly.py:141`), but matching calls `re.search(sc.pattern, ...)` instead of compiled regex (`src/pipeline/chunk_assembly.py:145`).

Risk: behavior drift for case-sensitive/case-insensitive patterns.

### 9) Step sequence restart edge cases (Should Fix)

- Restart split depends on both restart and gap > 1 (`src/pipeline/chunk_assembly.py:117`).

Risk: adjacent restarted sequences may merge unexpectedly.

### 10) Schema file is not runtime-enforced via JSON Schema validator (Could Fix)

- Schema exists (`schema/manual_profile_v1.schema.json`) but runtime relies on manual checks (`src/pipeline/profile.py`).

Risk: schema/runtime drift.

### 11) Duplicate-content QA check is O(n^2) (Could Fix)

- Nested pair loops (`src/pipeline/qa.py:198`, `src/pipeline/qa.py:199`).

Risk: slower QA for large corpora.

## Low (Could Fix)

### 12) Documentation/test quality inconsistencies

- README reports both "250/250 tests" and "229 tests" (`README.md:27`).
- Some CLI parser tests are weak and one has no assertion (`tests/test_cli.py:71`).

Risk: onboarding trust and maintainability friction.

## Security Posture

- No hardcoded secrets found in scanned source/tests.
- Main security/reliability issues are operational robustness (timeouts, surfaced failures, deterministic IDs) rather than auth/credential exposure.
- Dependency CVE status was not assessed in this review run.

## Testability and Reliability

Strengths:

- Good breadth of unit tests by module.
- Clear separation of checks in QA suite.

Gaps:

- Retrieval orchestration (`retrieve`) is not directly tested in `tests/test_retrieval.py`.
- Integration tests are excluded by default (`pyproject.toml:32`), so key pipeline behavior may regress without CI signals.

## Prioritized Remediation Roadmap

## Quick Wins (< 1 day each)

1. Make `bootstrap-profile` fail fast with explicit "not implemented" error and non-zero exit.
- Files: `src/pipeline/cli.py`
- Risk: Low
- Effort: S
- Depends on: none

2. Add timeout + retry/backoff around embedding HTTP calls.
- Files: `src/pipeline/embeddings.py`
- Risk: Low
- Effort: S
- Depends on: none

3. Align metadata contract (`manual_id`, `level1_id`, `content_type`) between assembler and QA.
- Files: `src/pipeline/chunk_assembly.py`, `src/pipeline/qa.py`
- Risk: Medium
- Effort: S
- Depends on: none

4. Surface retrieval failures instead of swallowing exceptions.
- Files: `src/pipeline/retrieval.py`
- Risk: Medium
- Effort: S
- Depends on: none

## Short-Term Targets (1-2 weeks)

1. Fix coordinate model for chunk extraction across pages.
- Files: `src/pipeline/structural_parser.py`, `src/pipeline/chunk_assembly.py`, tests
- Approach: use absolute offsets or `(page_number, line_number)` aware slicing.
- Risk: High
- Effort: M
- Depends on: none

2. Normalize embedding contract: metadata header + body text.
- Files: `src/pipeline/embeddings.py`, `tests/test_embeddings.py`, optional comments in `src/pipeline/chunk_assembly.py`
- Risk: Medium
- Effort: S-M
- Depends on: metadata contract alignment

3. Use deterministic Qdrant point IDs derived from `chunk_id`.
- Files: `src/pipeline/embeddings.py`
- Risk: Medium
- Effort: S
- Depends on: none

## Strategic Initiatives

1. Define explicit typed contracts for chunk metadata and retrieval payloads.
- Files: cross-cutting (`chunk_assembly`, `qa`, `retrieval`, `embeddings`)
- Risk: Medium
- Effort: M-L
- Depends on: short-term contract fixes

2. Add end-to-end retrieval/indexing integration tests with failure-mode assertions.
- Files: `tests/test_retrieval.py`, `tests/test_integration.py`, new test fixtures
- Risk: Medium
- Effort: M
- Depends on: deterministic IDs + surfaced failure policy

## Long-Term Considerations

1. Improve boundary detection robustness beyond regex-only heuristics for heterogeneous manuals.
2. Add observability (structured logs, counters, timings) for each pipeline stage.
3. Evaluate async/batched indexing once corpus size grows.

## ADRs to Add

1. Chunk coordinate system and slicing semantics.
2. Canonical chunk schema (`text` vs metadata responsibilities).
3. Embedding input format contract.
4. External dependency failure policy (timeouts/retries/error surfacing).
5. Deterministic vector ID and reindex idempotency policy.

## Final Priority View

- Must fix now:
  - Cross-page slicing integrity
  - Metadata contract mismatch
  - Embedding contract mismatch
  - `bootstrap-profile` success-on-noop
  - Retrieval failure surfacing

- Should fix next:
  - Deterministic Qdrant IDs
  - HTTP timeout/retries
  - Regex handling consistency

- Could fix later:
  - JSON Schema enforcement
  - O(n^2) duplicate check scaling
  - README/test hygiene improvements
