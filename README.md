# manual-chatbot

Smart Chunking Pipeline for Vehicle Service Manual RAG. Transforms OCR'd vehicle service manuals into a high-quality vector store optimized for a troubleshooting/repair chatbot.

## Overview

This pipeline processes PDF service manuals from different manufacturers, eras, and document conventions through a configurable **manual profile system**. Each manual gets a YAML profile that teaches the pipeline how to parse its structure, clean OCR artifacts, and chunk content while preserving procedural integrity.

### Target Manuals

| Manual | Era | Structure |
|--------|-----|-----------|
| 1999 Jeep Cherokee (XJ) Factory Service Manual | Modern (1999) | Group/Section/Procedure |
| 1953-71 Jeep Universal CJ Series Service Manual | Classic (1953-71) | Lettered Section/Paragraph |
| TM 9-8014: M38A1/M170 Operator & Org. Maintenance | Military (1955) | Chapter/Section/Paragraph |

### Key Design Goals

- **Procedural integrity**: Never split a step sequence or separate a safety callout from its governed procedure
- **Profile-driven**: Adapt to fundamentally different manual structures via YAML configuration
- **Rich metadata**: Every chunk carries structured metadata for filtered retrieval (vehicle, engine, drivetrain, content type)
- **OCR-aware**: Handle varied OCR quality with manual-specific substitution rules and garbage detection
- **Multi-manual**: Single unified vector store with all manuals, filterable by metadata

## Current Status

All pipeline components are **fully implemented** and passing the complete test suite (**349 tests**). The codebase was developed using TDD, then hardened through an architectural review remediation that added persistence, structured logging, typed range fields, and comprehensive multi-page test coverage.

## Project Structure

```
manual-chatbot/
  pyproject.toml              # Package config, dependencies, pytest settings
  PRD.pdf                     # Detailed product requirements document (30 pages)
  IMPLEMENTATION_PLAN.md      # Completed remediation plan (15 work items)
  PROGRESS.md                 # Implementation progress log
  LEARNINGS.md                # Issues encountered and solutions discovered
  RECOMMENDATIONS.md          # Improvement recommendations from architectural review
  REVIEW.md                   # Architectural review findings
  schema/
    manual_profile_v1.schema.json  # JSON Schema for YAML profiles
  src/
    pipeline/
      __init__.py
      cli.py                  # CLI: process, bootstrap-profile, validate, validate-chunks, qa
      profile.py              # YAML profile loader, validator, pattern compiler
      structural_parser.py    # Boundary detection, manifest building, persistence
      ocr_cleanup.py          # OCR substitutions, header stripping, garbage detection
      chunk_assembly.py       # Chunk rules R1-R8, vehicle tagging, persistence
      embeddings.py           # Embedding composition, Qdrant/SQLite indexing
      retrieval.py            # Query analysis, retrieval pipeline, reranking
      qa.py                   # Chunk validation suite (7 checks)
  tests/
    conftest.py               # Shared fixtures (profiles, sample texts, chunks)
    fixtures/
      xj_1999_profile.yaml    # 1999 Cherokee XJ test profile
      cj_universal_profile.yaml  # 1953-71 CJ Universal test profile
      tm9_8014_profile.yaml   # TM 9-8014 M38A1 test profile
      invalid_profile.yaml    # Invalid profile for validation testing
    test_profile.py
    test_structural_parser.py
    test_ocr_cleanup.py
    test_chunk_assembly.py
    test_embeddings.py
    test_retrieval.py
    test_qa.py
    test_cli.py
    test_integration.py       # End-to-end pipeline tests with real PDFs
```

## Pipeline Architecture

The pipeline has four stages, each driven by the manual profile:

1. **Text Extraction & OCR Cleanup** - Extract text from PDF via pymupdf, apply profile-specific OCR substitutions, strip headers/footers, detect garbage lines, normalize unicode
2. **Structural Parsing** - Detect hierarchy boundaries using profile regex patterns, validate against known IDs, build a hierarchical manifest with chunk boundaries
3. **Chunk Assembly** - Apply 8 universal rules (R1-R8) to produce final chunks with metadata:
   - R1: One procedure/topic per chunk at the lowest meaningful hierarchy level
   - R2: Size targets (min 200, target 500-1500, max 2000 tokens)
   - R3: Never split numbered/lettered step sequences
   - R4: Safety callouts stay with their governed procedure
   - R5: Specification tables are never split
   - R6: Merge small chunks (<200 tokens) with siblings or parent
   - R7: Cross-reference-only sections merge into parent
   - R8: Figure references stay with describing text
4. **Embedding & Indexing** - Compose embedding input (hierarchical header + first 150 words), generate embeddings via Ollama (nomic-embed-text), index into Qdrant with metadata filters, build SQLite secondary index

## Manual Profile System

Each manual is described by a YAML profile that configures:

- **Vehicle coverage** - Models, years, engines, transmissions, drive types with aliases
- **Document hierarchy** - Levels with regex patterns for ID and title extraction, known IDs for validation
- **Step patterns** - Regex patterns for numbered `(1), (2)` and lettered `a., b.` steps
- **Figure/cross-reference patterns** - How figures and internal references are formatted
- **Safety callouts** - WARNING/CAUTION/NOTE patterns and styles (block vs inline)
- **Content types** - Maintenance schedule structure, wiring diagram locations, spec table placement
- **OCR cleanup rules** - Known substitutions, header/footer patterns, garbage detection threshold
- **Market variants** - Domestic/international variant handling

See `tests/fixtures/` for example profiles.

## Installation

Requires Python >= 3.10.

```bash
pip install -e .
```

With dev dependencies (pytest, coverage):

```bash
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=pipeline
```

Run only unit tests:

```bash
pytest -m unit
```

## CLI Usage

```bash
# Process a single manual (extract, parse, chunk)
pipeline process --profile profiles/xj-1999.yaml --pdf data/xj-manual.pdf

# Process and save chunks to JSONL
pipeline process --profile profiles/xj-1999.yaml --pdf data/xj-manual.pdf --output-dir output/

# Validate a profile against its PDF
pipeline validate --profile profiles/xj-1999.yaml --pdf data/xj-manual.pdf

# Run offline QA on saved chunks (no Qdrant needed)
pipeline validate-chunks --chunks output/xj-1999_chunks.jsonl --profile profiles/xj-1999.yaml

# Bootstrap a profile from a new manual PDF (not yet implemented)
pipeline bootstrap-profile --pdf data/new-manual.pdf --output profiles/new.yaml

# Run QA checks on an indexed manual (requires Qdrant)
pipeline qa --manual-id xj-1999 --test-set tests/xj-queries.json
```

Global flags: `--verbose`/`-v` (debug output), `--quiet`/`-q` (warnings only).

## Dependencies

- **pymupdf** (>=1.23.0) - PDF text extraction
- **pyyaml** (>=6.0) - Profile loading
- **qdrant-client** (>=1.7.0) - Vector store
- **requests** (>=2.31.0) - Ollama API communication

## External Services (for full pipeline)

- **Ollama** with `nomic-embed-text` model - Embedding generation
- **Qdrant** - Vector store for chunk retrieval
