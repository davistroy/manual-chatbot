# Implementation Plan

**Generated:** 2026-02-15
**Source Documents:**
- Conversation analysis of three architectural decisions needing documentation
- `src/pipeline/chunk_assembly.py` (rule ordering, token counting)
- `src/pipeline/profile.py` (schema definition, validation, loading)
- `tests/fixtures/*.yaml` (4 profile fixtures)
- `LEARNINGS.md` (existing decision notes)

**Total Phases:** 3
**Estimated Total Effort:** ~45,000 tokens

---

## Executive Summary

Three architectural decisions in the chunking pipeline are undocumented or insufficiently documented, creating maintenance risk. The rule ordering in `assemble_chunks()` is intentionally non-sequential but appears wrong to anyone unfamiliar with the rationale. The `count_tokens()` function uses word-split as a deliberate dependency tradeoff but looks like a shortcut. The YAML profile schema — the system's core extension point — has no version marker, no formal schema definition, and minimal validation despite affecting all manual profiles and all 229 tests.

This plan addresses all three with source-level documentation, a JSON Schema for the profile format, typed dataclasses for the currently-untyped dict fields, expanded validation, and a guard test for rule ordering.

---

## Plan Overview

The three items are independent and can be implemented in any order. They are sequenced by risk (schema stability first, as it has the highest blast radius) and by complexity (documentation-only changes last).

### Phase Summary Table

| Phase | Focus Area | Key Deliverables | Est. Tokens | Dependencies |
|-------|------------|------------------|-------------|--------------|
| 1 | Profile Schema Stability | Version marker, JSON Schema, typed dicts, expanded validation | ~30K | None |
| 2 | Token Counting Documentation | Docstring, scaling constant, accuracy notes | ~5K | None |
| 3 | Rule Ordering Documentation | Inline comment block, ordering guard test | ~10K | None |

---

## Phase 1: Profile Schema Stability

**Estimated Effort:** ~30,000 tokens (including testing/fixes)
**Dependencies:** None
**Parallelizable:** Work items 1.1-1.4 are sequential; 1.5 can run after 1.3

### Goals

- Establish a versioned profile schema so future changes are detectable
- Replace `dict[str, Any]` fields with typed dataclasses for compile-time safety
- Expand `validate_profile()` to catch malformed regexes and missing OCR fields
- Create a JSON Schema file that serves as machine-readable documentation

### Work Items

#### 1.1 Add `schema_version` field to ManualProfile and all YAML fixtures

**Requirement Refs:** Architectural Decision #3
**Files Affected:**
- `src/pipeline/profile.py` (modify — add field to dataclass, update loader and validator)
- `tests/fixtures/xj_1999_profile.yaml` (modify — add `schema_version: "1.0"`)
- `tests/fixtures/cj_universal_profile.yaml` (modify — add `schema_version: "1.0"`)
- `tests/fixtures/tm9_8014_profile.yaml` (modify — add `schema_version: "1.0"`)
- `tests/fixtures/invalid_profile.yaml` (modify — add `schema_version: "1.0"` so it remains testable for other invalid fields)
- `tests/test_profile.py` (modify — add schema version tests)

**Description:**
Add a `schema_version: str` field to `ManualProfile` (after `manual_id`). Define a module-level constant `CURRENT_SCHEMA_VERSION = "1.0"`. Update `load_profile()` to read the field from YAML data. Update `validate_profile()` to check that `schema_version` is present and matches `CURRENT_SCHEMA_VERSION`.

**Tasks:**
1. [ ] Add `CURRENT_SCHEMA_VERSION = "1.0"` constant to `profile.py`
2. [ ] Add `schema_version: str` field to `ManualProfile` dataclass
3. [ ] Update `load_profile()` to extract `schema_version` from YAML data (line ~165)
4. [ ] Update `validate_profile()` to error on missing or mismatched version (line ~189)
5. [ ] Add `schema_version: "1.0"` as first line of all 4 YAML fixtures
6. [ ] Update existing tests that construct `ManualProfile` directly (if any)
7. [ ] Add tests: missing version raises error, wrong version raises error, correct version passes

**Acceptance Criteria:**
- [ ] All profiles load with `schema_version: "1.0"`
- [ ] `validate_profile()` returns error for missing `schema_version`
- [ ] `validate_profile()` returns error for `schema_version: "2.0"` (unknown)
- [ ] All 229 existing tests still pass

---

#### 1.2 Type the `content_types`, `ocr_cleanup`, and `variants` dicts

**Requirement Refs:** Architectural Decision #3
**Files Affected:**
- `src/pipeline/profile.py` (modify — add 4 new dataclasses, update ManualProfile fields, update `load_profile()`)
- `src/pipeline/ocr_cleanup.py` (modify — update field access from dict syntax to attribute syntax)
- `tests/test_profile.py` (modify — update field access assertions)
- `tests/test_ocr_cleanup.py` (modify — update field access if any)
- `tests/test_chunk_assembly.py` (modify — update if any dict-style access)

**Description:**
Replace the three `dict[str, Any]` fields on `ManualProfile` with proper dataclasses. This makes the schema self-documenting and catches typos at load time.

New dataclasses:

```python
@dataclass
class ContentTypeConfig:
    """Content type metadata — sub-fields remain dicts because structure
    varies fundamentally across manual types (mileage-bands vs echelon-based
    vs interval-table)."""
    maintenance_schedule: dict[str, Any] = field(default_factory=dict)
    wiring_diagrams: dict[str, Any] = field(default_factory=dict)
    specification_tables: dict[str, Any] = field(default_factory=dict)

@dataclass
class GarbageDetectionConfig:
    """Garbage line detection parameters."""
    enabled: bool = False
    threshold: float = 0.5

@dataclass
class OcrCleanupConfig:
    """OCR cleanup configuration from manual profile."""
    quality_estimate: str = ""
    known_substitutions: list[dict[str, str]] = field(default_factory=list)
    header_footer_patterns: list[str] = field(default_factory=list)
    garbage_detection: GarbageDetectionConfig = field(default_factory=GarbageDetectionConfig)

@dataclass
class VariantConfig:
    """Market variant configuration."""
    has_market_variants: bool = False
    variant_indicator: str = "none"
    markets: list[str] = field(default_factory=list)
```

**Tasks:**
1. [ ] Define `GarbageDetectionConfig` dataclass in `profile.py`
2. [ ] Define `OcrCleanupConfig` dataclass in `profile.py`
3. [ ] Define `ContentTypeConfig` dataclass in `profile.py`
4. [ ] Define `VariantConfig` dataclass in `profile.py`
5. [ ] Update `ManualProfile` field types: `content_types: ContentTypeConfig`, `ocr_cleanup: OcrCleanupConfig`, `variants: VariantConfig`
6. [ ] Update `load_profile()` to construct these dataclasses from YAML data
7. [ ] Search all source files for dict-style access to these fields (e.g., `profile.ocr_cleanup["quality_estimate"]`) and update to attribute syntax
8. [ ] Search all test files for the same and update
9. [ ] Verify the `invalid_profile.yaml` fixture still loads correctly (it has empty/default values for these sections)

**Acceptance Criteria:**
- [ ] `ManualProfile` no longer has any `dict[str, Any]` top-level fields
- [ ] All 3 valid profile fixtures load into typed dataclasses without error
- [ ] Field access uses attribute syntax (`profile.ocr_cleanup.quality_estimate`) not dict syntax
- [ ] All 229 tests pass

**Notes:**
`ContentTypeConfig` sub-fields (`maintenance_schedule`, `wiring_diagrams`, `specification_tables`) remain `dict[str, Any]` because their structure varies fundamentally across manual types. Typing these further would over-constrain the schema for no safety gain.

---

#### 1.3 Expand `validate_profile()` with structural checks

**Requirement Refs:** Architectural Decision #3
**Files Affected:**
- `src/pipeline/profile.py` (modify — expand `validate_profile()` at line 184)
- `tests/test_profile.py` (modify — add validation tests to `TestValidateProfile` class)

**Description:**
The current validator checks 6 fields for non-emptiness. Expand it to catch the errors that actually happen when authoring new profiles:

1. **Regex compilation** — validate that all `id_pattern`, `title_pattern`, step patterns, safety callout patterns, figure reference, cross-reference, and page number patterns compile as valid regex
2. **OCR cleanup structure** — validate `known_substitutions` entries have `from` and `to` keys
3. **Hierarchy consistency** — validate hierarchy levels are sequential (1, 2, 3...) with no gaps
4. **Safety callout levels** — validate callout levels are one of `{"warning", "caution", "note"}`
5. **Safety callout styles** — validate styles are one of `{"block", "inline"}`

**Tasks:**
1. [ ] Add regex validation for all pattern fields (try `re.compile()`, catch `re.error`)
2. [ ] Add `known_substitutions` structure validation (each entry must have `from` and `to` keys)
3. [ ] Add hierarchy level sequence validation (levels must be 1, 2, 3... with no gaps)
4. [ ] Add safety callout level validation (must be `warning`, `caution`, or `note`)
5. [ ] Add safety callout style validation (must be `block` or `inline`)
6. [ ] Write tests for each new validation check (valid patterns pass, invalid patterns caught)
7. [ ] Write test with a profile containing an invalid regex pattern
8. [ ] Write test with a profile containing malformed substitution entries

**Acceptance Criteria:**
- [ ] Invalid regex patterns produce clear validation errors (e.g., `"Invalid id_pattern at hierarchy level 1: ..."`)
- [ ] Malformed `known_substitutions` entries produce validation errors
- [ ] Non-sequential hierarchy levels produce validation errors
- [ ] Invalid safety callout levels/styles produce validation errors
- [ ] All valid profiles still pass validation (XJ, CJ, TM9)
- [ ] All 229+ tests pass

---

#### 1.4 Create JSON Schema definition file

**Requirement Refs:** Architectural Decision #3
**Files Affected:**
- `schema/manual_profile_v1.schema.json` (create)

**Description:**
Create a JSON Schema (draft 2020-12) that formally defines the YAML profile structure. This serves as:
- Machine-readable documentation of the profile format
- IDE autocompletion support (VS Code YAML extension reads JSON Schema)
- A validation reference independent of the Python code

The schema should document every field, type, required/optional status, enum values, and pattern constraints. Include a `description` on non-obvious fields explaining their purpose.

**Tasks:**
1. [ ] Create `schema/` directory in project root
2. [ ] Write JSON Schema covering all top-level fields (`schema_version`, `manual_id`, `manual_title`, `source_url`, `source_format`, `vehicles`, `structure`, `safety_callouts`, `content_types`, `ocr_cleanup`, `variants`)
3. [ ] Define `vehicles` array schema with nested `engines` and `transmissions`
4. [ ] Define `structure.hierarchy` array schema with `level`, `name`, `id_pattern`, `title_pattern`, `known_ids`
5. [ ] Define `safety_callouts` array schema with enum constraints on `level` and `style`
6. [ ] Define `ocr_cleanup` object schema with `garbage_detection` sub-object
7. [ ] Add enum constraints: `source_format` in `["pdf-ocr", "pdf-native", "html", "epub"]`, `safety level` in `["warning", "caution", "note"]`, `safety style` in `["block", "inline"]`, `figure_reference_scope` in `["per-section", "global"]`
8. [ ] Add `required` arrays for mandatory fields at each nesting level
9. [ ] Validate all 3 valid fixture profiles against the schema (manual spot-check)

**Acceptance Criteria:**
- [ ] Schema file exists at `schema/manual_profile_v1.schema.json`
- [ ] All 3 valid fixture profiles conform to the schema
- [ ] Schema documents every field present in the YAML fixtures
- [ ] Enum constraints match the validation logic in `validate_profile()`
- [ ] Schema includes `description` on key fields

**Notes:**
Do not add `jsonschema` as a runtime dependency. The schema file is documentation and tooling support. If schema validation is desired at runtime, it can be added as an optional dependency later.

---

### Phase 1 Testing Requirements

- [ ] All existing 229 tests pass (with field access updates from 1.2)
- [ ] New validation tests cover: regex compilation, substitution structure, hierarchy sequence, callout level/style
- [ ] Schema version tests cover: missing version, wrong version, correct version
- [ ] `load_profile()` correctly constructs typed dataclasses from all 4 fixtures

### Phase 1 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing (`pytest -v --tb=short`)
- [ ] `CLAUDE.md` Key Data Types section updated with `OcrCleanupConfig`, `VariantConfig`, `ContentTypeConfig`, `GarbageDetectionConfig`
- [ ] No regressions introduced
- [ ] `LEARNINGS.md` updated if any surprises encountered

---

## Phase 2: Token Counting Documentation

**Estimated Effort:** ~5,000 tokens (including testing/fixes)
**Dependencies:** None
**Parallelizable:** Yes — independent of Phases 1 and 3

### Goals

- Document the word-split vs. BPE tokenizer tradeoff at the point of use
- Make the implicit 1:1 word-to-token ratio explicit and tunable
- Provide a clear upgrade path for future precision needs

### Work Items

#### 2.1 Expand `count_tokens()` with documented tradeoff and scaling constant

**Requirement Refs:** Architectural Decision #2
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify — lines 22-29)
- `tests/test_chunk_assembly.py` (modify — add test for scaling factor behavior)

**Description:**
Replace the minimal docstring on `count_tokens()` with a full explanation of the design decision. Extract the implicit 1:1 word-to-token ratio as a named module constant `TOKEN_ESTIMATE_FACTOR` so it's visible and tunable.

Current implementation (lines 22-29):
```python
def count_tokens(text: str) -> int:
    """Estimate token count for a text string.

    Uses a simple whitespace-based approximation.
    """
    if not text or not text.strip():
        return 0
    return len(text.split())
```

Target implementation:
```python
# Word-to-token scaling factor. Set to 1.0 because word count approximates
# token count for English prose. Actual BPE ratio is ~1.3x for technical
# English, meaning this intentionally undercounts — chunks may be ~30% larger
# than the nominal 200-2000 token target. The error direction is safe for RAG
# (slightly oversized chunks preserve more context per retrieval hit).
#
# To use a real tokenizer: swap the count_tokens() implementation for
# tiktoken or sentencepiece, and set this factor to 1.0.
TOKEN_ESTIMATE_FACTOR: float = 1.0


def count_tokens(text: str) -> int:
    """Estimate token count using whitespace word splitting.

    Deliberate tradeoff: avoids a tokenizer dependency (tiktoken,
    sentencepiece) at the cost of ~20-30% undercount vs actual BPE
    tokens for technical English. Chunks may run ~30% larger than
    the nominal 200-2000 token target defined in R2.

    The error direction is safe for RAG — slightly oversized chunks
    preserve more context per retrieval hit. If precision matters
    (e.g., strict model context limits), swap this implementation
    for a BPE tokenizer.
    """
    if not text or not text.strip():
        return 0
    return int(len(text.split()) * TOKEN_ESTIMATE_FACTOR)
```

**Tasks:**
1. [ ] Add `TOKEN_ESTIMATE_FACTOR = 1.0` constant with explanatory comment block above `count_tokens()` (after the `Chunk` dataclass, before the function)
2. [ ] Expand `count_tokens()` docstring with tradeoff rationale, accuracy implications, and upgrade path
3. [ ] Update `return` statement to `return int(len(text.split()) * TOKEN_ESTIMATE_FACTOR)`
4. [ ] Add test verifying `TOKEN_ESTIMATE_FACTOR` is applied: monkeypatch the constant to 2.0 and verify count doubles
5. [ ] Verify all 4 existing `TestCountTokens` tests still pass (factor is 1.0, so `int(n * 1.0) == n`)

**Acceptance Criteria:**
- [ ] `TOKEN_ESTIMATE_FACTOR` constant exists at module level and is documented
- [ ] `count_tokens()` docstring explains the word-split vs. BPE tradeoff
- [ ] Docstring mentions the ~20-30% undercount and why it's acceptable for RAG
- [ ] Docstring provides upgrade path (what to change for precise counting)
- [ ] `int()` wrapping handles non-integer results when factor != 1.0
- [ ] All existing tests pass unchanged

---

### Phase 2 Testing Requirements

- [ ] `count_tokens("hello world")` still returns 2 (factor = 1.0)
- [ ] `count_tokens("")` and `count_tokens("   ")` still return 0
- [ ] Scaling factor test confirms multiplication is applied
- [ ] All 41 chunk assembly tests pass

### Phase 2 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing
- [ ] No regressions introduced

---

## Phase 3: Rule Ordering Documentation

**Estimated Effort:** ~10,000 tokens (including testing/fixes)
**Dependencies:** None
**Parallelizable:** Yes — independent of Phases 1 and 2

### Goals

- Document the non-sequential rule ordering at the exact code location where it matters
- Add a guard test that detects if someone reorders the rules incorrectly

### Work Items

#### 3.1 Add structured comment block to `assemble_chunks()`

**Requirement Refs:** Architectural Decision #1
**Files Affected:**
- `src/pipeline/chunk_assembly.py` (modify — insert comment block before line 593)

**Description:**
Insert a comment block directly above the first rule application (R1) in `assemble_chunks()` that explains the two-phase design and why R2 runs after R3-R5. Also update the function-level docstring to explicitly mention non-sequential ordering.

Current docstring (line 566-568):
```python
def assemble_chunks(
    pages: list[str], manifest: Manifest, profile: ManualProfile
) -> list[Chunk]:
    """Run the full chunk assembly pipeline.

    Applies all rules (R1-R8) and builds final Chunk objects with metadata.
    """
```

Target docstring:
```python
def assemble_chunks(
    pages: list[str], manifest: Manifest, profile: ManualProfile
) -> list[Chunk]:
    """Run the full chunk assembly pipeline.

    Applies rules R1-R8 in non-sequential order (R1,R3,R4,R5,R2,R6,R7,R8)
    to ensure semantic integrity before size enforcement. See the inline
    comment block above the rule applications for the full rationale.
    """
```

Comment block to insert before line 593 (before `# R1: Primary unit`):
```python
        # ── Rule Application Order ──────────────────────────────────
        # Intentionally non-sequential. Rules execute in two phases:
        #
        # Phase 1 — Semantic integrity (before any size enforcement):
        #   R1: Primary unit — establish procedure boundaries
        #   R3: Never split steps — protect step sequences as atomic
        #   R4: Safety attachment — bind callouts to parent content
        #   R5: Table integrity — keep tables with their headers
        #
        # Phase 2 — Size enforcement and cleanup:
        #   R2: Size targets — split oversized chunks (AFTER integrity
        #       rules so it respects step/safety/table boundaries)
        #   R6: Merge small — combine undersized fragments
        #   R7: Cross-reference merge — consolidate xref-only sections
        #   R8: Figure continuity — keep figure refs with context
        #
        # WHY: If R2 ran before R3-R5, it would split at token
        # boundaries before semantic units are identified, breaking
        # step sequences, safety callouts, and tables across chunks.
        # See LEARNINGS.md for discovery context.
        # ────────────────────────────────────────────────────────────
```

**Tasks:**
1. [ ] Update `assemble_chunks()` docstring to mention non-sequential ordering
2. [ ] Insert the structured comment block above the R1 application (before current line 593)
3. [ ] Verify the comment doesn't break any existing functionality (`pytest -v --tb=short`)

**Acceptance Criteria:**
- [ ] Comment block is present directly above rule application code in `assemble_chunks()`
- [ ] Comment explains both phases and the rationale for R2 placement
- [ ] Function docstring mentions non-sequential rule application order
- [ ] All 229 tests pass

---

#### 3.2 Add ordering guard test

**Requirement Refs:** Architectural Decision #1
**Files Affected:**
- `tests/test_chunk_assembly.py` (modify — add `TestRuleOrdering` class)

**Description:**
Write tests that validate the rule ordering produces correct results. The tests construct inputs where wrong ordering (R2 before R3/R4) would produce detectably different output. Two tests:

1. **Safety callout integrity:** A WARNING block followed by a procedure, where the combined text is under 2000 tokens. With correct ordering (R4 before R2), the callout stays attached. With wrong ordering (R2 before R4), the callout could be orphaned.

2. **Step sequence integrity:** A numbered step sequence under the size ceiling. With correct ordering (R3 before R2), all steps stay together. With wrong ordering (R2 before R3), steps could be split at a token boundary.

Both tests use `assemble_chunks()` end-to-end (not individual rule functions) to validate the integrated behavior.

**Tasks:**
1. [ ] Create `TestRuleOrdering` class in `test_chunk_assembly.py`
2. [ ] Write `test_safety_callout_not_split_from_procedure` — constructs a WARNING + procedure text as pages + manifest, calls `assemble_chunks()`, asserts WARNING text and procedure text appear in the same chunk
3. [ ] Write `test_step_sequence_preserved_before_size_split` — constructs a step sequence under the size ceiling as pages + manifest, calls `assemble_chunks()`, asserts all steps appear in one chunk
4. [ ] Add fixtures or inline data for the test inputs (manifest entries, profile loading)
5. [ ] Run full test suite to verify no conflicts

**Acceptance Criteria:**
- [ ] Both tests pass with current (correct) rule ordering
- [ ] Tests would fail if R2 were moved before R3/R4 (verify by mental model — actually reordering rules to prove it is optional but recommended)
- [ ] All 229+ tests pass
- [ ] Tests are in a clearly named `TestRuleOrdering` class with descriptive docstrings

---

### Phase 3 Testing Requirements

- [ ] Guard tests validate correct ordering behavior with end-to-end `assemble_chunks()` calls
- [ ] All existing 41 chunk assembly tests still pass
- [ ] Full suite (229+ tests) passes

### Phase 3 Completion Checklist

- [ ] All work items complete
- [ ] All tests passing
- [ ] Comment block is clear, accurate, and positioned at the decision point
- [ ] Function docstring updated
- [ ] No regressions introduced

---

## Parallel Work Opportunities

All three phases are fully independent and can be executed concurrently.

| Work Item | Can Run With | Notes |
|-----------|--------------|-------|
| Phase 1 (Schema) | Phase 2, Phase 3 | Touches `profile.py` and `ocr_cleanup.py` only — no overlap with `chunk_assembly.py` rule/token code |
| Phase 2 (Tokens) | Phase 1, Phase 3 | Touches `chunk_assembly.py` lines 22-29 only |
| Phase 3 (Rules) | Phase 1, Phase 2 | Touches `chunk_assembly.py` lines 566-625 and `test_chunk_assembly.py` only |

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation Strategy |
|------|------------|--------|---------------------|
| Typed dicts break tests that access fields by dict key | Medium | Medium | Search all test and source files for dict-style access on `ocr_cleanup`, `content_types`, `variants` before changing types; update in same commit |
| `schema_version` check breaks `invalid_profile.yaml` tests | Low | Low | Add `schema_version: "1.0"` to invalid profile; it tests other invalid fields (empty title, empty vehicles, bad format), not version |
| JSON Schema diverges from Python dataclass over time | Medium | Low | Add a comment in `profile.py` pointing to the schema file; schema is documentation, not runtime enforcement |
| `TOKEN_ESTIMATE_FACTOR` multiply changes existing test expectations | Very Low | Low | Factor is 1.0, and `int(n * 1.0)` == `n` for all integers; verified by existing tests |
| Guard tests are fragile or over-fitted to current implementation | Medium | Low | Use `assemble_chunks()` end-to-end rather than inspecting function internals; test observable behavior (which chunks contain which text) |
| Expanded validation rejects previously-valid profiles | Low | High | Run all 229 existing tests after every validation change; existing valid profiles must still pass |

---

## Success Metrics

- [ ] All three architectural decisions documented at source-code level
- [ ] Profile schema formally defined in JSON Schema (`schema/manual_profile_v1.schema.json`)
- [ ] `dict[str, Any]` fields replaced with typed dataclasses on `ManualProfile`
- [ ] `validate_profile()` catches regex errors, structural issues, malformed OCR config
- [ ] Guard tests prevent silent rule reordering in `assemble_chunks()`
- [ ] `count_tokens()` tradeoff documented with tunable scaling constant
- [ ] All existing 229 tests pass
- [ ] No new runtime dependencies added
- [ ] `CLAUDE.md` Key Data Types section updated with new dataclasses

---

## Appendix: Requirement Traceability

| Requirement | Source | Phase | Work Item |
|-------------|--------|-------|-----------|
| Profile schema version marker | Architectural Decision #3 | 1 | 1.1 |
| Typed dataclasses for dict fields | Architectural Decision #3 | 1 | 1.2 |
| Expanded profile validation | Architectural Decision #3 | 1 | 1.3 |
| JSON Schema definition | Architectural Decision #3 | 1 | 1.4 |
| Token counting tradeoff documentation | Architectural Decision #2 | 2 | 2.1 |
| Token scaling factor constant | Architectural Decision #2 | 2 | 2.1 |
| Rule ordering documentation in source | Architectural Decision #1 | 3 | 3.1 |
| Rule ordering guard test | Architectural Decision #1 | 3 | 3.2 |

---

*Implementation plan generated by Claude on 2026-02-15*
*Source: Architectural decision analysis conversation + /create-plan command*
