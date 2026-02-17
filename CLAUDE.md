# CLAUDE.md

## Project Overview

Smart Chunking Pipeline for Vehicle Service Manual RAG. Processes OCR'd vehicle service manuals (PDF) into chunked, metadata-enriched vectors for a repair/troubleshooting chatbot.

**Current state**: Core pipeline fully implemented — 439 tests pass (464 total, 25 integration-deselected). Built TDD-style, then hardened through architectural review remediation (15 work items) and output quality hardening (4 phases). Profile schema is versioned (v1.0) with typed dataclasses and expanded validation. All pipeline modules use structured logging. Production XJ profile validated against real 1,948-page manual with QA passing. Chatbot integration layer (PRD Phase 6) and Docker deployment not yet started.

## Quick Reference

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run all tests
pytest

# Run tests for a specific module
pytest tests/test_profile.py
pytest tests/test_ocr_cleanup.py

# Run with verbose output
pytest -v --tb=short
```

## Code Layout

```
data/                  # Source PDFs (not committed — local only)
  99 XJ Service Manual.pdf
  53-71 CJ5 Service Manual.pdf
  TM9-8014.pdf
  TM9-8015-1.pdf, TM9-8015-2.pdf
  M38A1wiring.pdf, ORD_SNL_G-758.pdf
profiles/              # Production YAML profiles (validated against real PDFs)
  xj-1999.yaml         # 39 known_ids, production-tested
schema/                # JSON Schema for profile YAML format
  manual_profile_v1.schema.json
src/pipeline/          # All source code
  profile.py           # YAML profile loading, validation, pattern compilation
  structural_parser.py # Boundary detection, manifest building, JSON persistence
  ocr_cleanup.py       # OCR cleanup (substitutions, headers, garbage, unicode)
  chunk_assembly.py    # Chunk rules R1-R8, vehicle tagging, JSONL persistence
  embeddings.py        # Embedding composition, Qdrant + SQLite indexing
  retrieval.py         # Query analysis, retrieval pipeline
  qa.py                # 7-check validation suite
  cli.py               # CLI entry point (process, bootstrap-profile, validate, validate-chunks, qa)

tests/                 # Test suite (439 tests, 25 integration-deselected)
  conftest.py          # Shared fixtures — profile paths, sample texts, chunk helpers
  fixtures/            # YAML test profiles (xj_1999, cj_universal, tm9_8014, invalid)
  test_*.py            # One test file per source module
```

## Architecture

Four-stage pipeline, each driven by a YAML manual profile:

1. **OCR Cleanup** (`ocr_cleanup.py`) — Profile-specific substitutions, header/footer stripping, garbage line detection, unicode normalization
2. **Structural Parsing** (`structural_parser.py`) — Regex-based boundary detection per profile hierarchy, **known_ids filtering** (require_known_id drops unrecognized L1 boundaries), **boundary post-filtering** (min_gap_lines, min_content_words, require_blank_before), manifest generation with chunk IDs in format `{manual_id}::{level1}::{level2}::...`
3. **Chunk Assembly** (`chunk_assembly.py`) — 8 universal rules (R1-R8): primary unit, size targets (200-2000 tokens), never split steps, safety attachment, table integrity, merge small, crossref merge, figure continuity. Cross-references namespace-qualified with `{manual_id}::` prefix.
4. **Embedding & Indexing** (`embeddings.py`) — Hierarchical header + first 150 words as embedding input, Qdrant vector store, SQLite secondary index

**Not yet implemented:** LLM-assisted parsing fallback (PRD 4.3.2), LLM profile bootstrapping (PRD Phase 5 — CLI stub exists), Docker Compose deployment (PRD 7.2), chatbot integration (PRD Phase 6).

## Key Data Types

- `ManualProfile` (profile.py) — Loaded from YAML, contains hierarchy patterns, vehicle info, OCR rules, safety callout patterns. Schema versioned (`schema_version: "1.0"`)
- `HierarchyLevel` (profile.py) — Single hierarchy level with patterns, known_ids, and filtering config (require_known_id, min_gap_lines, min_content_words, require_blank_before)
- `OcrCleanupConfig` (profile.py) — Typed OCR cleanup configuration (quality_estimate, known_substitutions, header_footer_patterns, garbage_detection)
- `GarbageDetectionConfig` (profile.py) — Garbage line detection parameters (enabled, threshold)
- `ContentTypeConfig` (profile.py) — Content type metadata (maintenance_schedule, wiring_diagrams, specification_tables)
- `VariantConfig` (profile.py) — Market variant configuration (has_market_variants, variant_indicator, markets)
- `Boundary` (structural_parser.py) — Detected structural boundary with level, ID, title, page/line
- `PageRange` / `LineRange` (structural_parser.py) — Typed range dataclasses for manifest entries
- `Manifest` / `ManifestEntry` (structural_parser.py) — Hierarchical document map with chunk boundaries
- `CleanedPage` (ocr_cleanup.py) — Cleaned page with original text, cleaned text, garbage lines, substitution count
- `OCRQualityReport` (ocr_cleanup.py) — Quality assessment (dictionary_match_rate, garbage_line_rate, needs_reocr)
- `Chunk` (chunk_assembly.py) — Final chunk with text, metadata dict, chunk_id, manual_id
- `QueryAnalysis` / `RetrievalResult` (retrieval.py) — Query parsing and retrieval types
- `ValidationReport` / `ValidationIssue` (qa.py) — QA validation results

## Conventions

- Python >= 3.10, uses `from __future__ import annotations` in all modules
- Dataclasses for all data types (no Pydantic)
- Type hints throughout
- Tests use pytest with class-based grouping (`class TestXxx`)
- Test markers: `unit`, `integration`, `slow`
- Profile fixtures are simplified versions of the full PRD profiles (fewer vehicles/known_ids)

## Dependencies

Runtime: `pymupdf`, `pyyaml`, `qdrant-client`, `requests`
Dev: `pytest`, `pytest-cov`, `pytest-mock`

## PRD Reference

`PRD.pdf` in the repo root contains the full 30-page product requirements document with:
- Complete profile schema (Section 3.1)
- Full profiles for all 3 target manuals (Sections 3.2-3.4)
- Pipeline architecture details (Section 4)
- Chunk boundary rules R1-R8 (Section 4.4.1)
- Retrieval strategy (Section 5)
- QA validation checks (Section 6.1)
