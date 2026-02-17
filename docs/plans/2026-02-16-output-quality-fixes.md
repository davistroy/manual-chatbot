# Output Quality Fixes — Implementation Plan

**Date:** 2026-02-16
**Branch:** `implement-output-quality`
**Baseline:** 2,408 chunks, 113 errors, 2,379 warnings, 17% false-positive boundaries

## Problem Summary

End-to-end run of the XJ 1999 Service Manual (1,948 pages, 50MB PDF) exposed four systemic issues:

| # | Issue | Root Cause | Severity |
|---|-------|-----------|----------|
| 1 | Hierarchy collapse — 92% of procedures missed | L1 pattern too loose, L2/L3 overlap, single-word headings invisible | P0 |
| 2 | 637 undersized chunks (26%) | Wiring diagram fragments leak through skip_sections; merge blocked by false L1 IDs | P1 |
| 3 | 1,716 known_ids warnings | Test fixture only declares 8 of ~50 groups | P1 |
| 4 | 113 cross-ref errors (100% failure rate) | Bare group numbers vs qualified `{manual_id}::` prefixes | P2 |

Issues 1-3 share a common root: the L1 `id_pattern` matches any line starting with a digit. Fixing L1 precision unwinds the cascade.

## Design Decisions

- **Mandatory known_ids filter**: `filter_boundaries()` will reject L1 boundaries whose ID is not in `known_ids` when a new `require_known_id: true` flag is set on the hierarchy level. This replaces advisory warnings with hard filtering.
- **Separate production profile**: Create `profiles/xj-1999.yaml` with complete config. Test fixture stays simplified for unit tests.
- **Cross-ref qualification at creation time**: Fix in `enrich_chunk_metadata()`, not in the QA validator.

---

## Phase 1: Mandatory known_ids Filter

**Goal:** Add `require_known_id` support to the profile schema, dataclass, and boundary filter. When enabled, L1 boundaries with unrecognized IDs are dropped during `filter_boundaries()`.

### 1.1 — Schema: add `require_known_id` property

**File:** `schema/manual_profile_v1.schema.json`

Add to the hierarchy level item properties (after `require_blank_before`):

```json
"require_known_id": {
  "type": "boolean",
  "default": false,
  "description": "When true and known_ids is non-empty, reject boundaries whose extracted ID is not in the known_ids list. Use for levels where the complete set of valid IDs is known."
}
```

### 1.2 — Dataclass: add field to `HierarchyLevel`

**File:** `src/pipeline/profile.py`, `HierarchyLevel` dataclass (line 16)

Add field:
```python
require_known_id: bool = False
```

Update `_parse_hierarchy_level()` (or wherever the YAML dict is unpacked) to read this field from the YAML.

### 1.3 — Parser: enforce in `filter_boundaries()`

**File:** `src/pipeline/structural_parser.py`, `filter_boundaries()` (line 167)

Add a new **Pass 0** before the existing Pass 1 (require_blank_before):

```python
# --- Pass 0: require_known_id ---
# For levels with require_known_id=True and non-empty known_ids,
# drop any boundary whose extracted ID is not in the known set.
known_id_sets: dict[int, set[str]] = {}
for h in profile.hierarchy:
    if h.require_known_id and h.known_ids:
        known_id_sets[h.level] = {entry["id"] for entry in h.known_ids}

if known_id_sets:
    filtered = []
    for b in boundaries:
        if b.level in known_id_sets:
            if b.id is None or b.id not in known_id_sets[b.level]:
                continue  # rejected: ID not in known set
        filtered.append(b)
    boundaries = filtered
```

This runs first so subsequent passes (blank-line, gap, content-words) operate on a cleaner set.

### 1.4 — Tests

**File:** `tests/test_structural_parser.py`

Add tests in a new class `TestRequireKnownId`:

1. `test_require_known_id_rejects_unknown` — profile with `require_known_id: true` and known_ids `["7", "9"]`. Feed boundaries with IDs `"7"`, `"9"`, `"42"`, `"1999"`. Assert only `"7"` and `"9"` survive.
2. `test_require_known_id_false_passes_all` — same boundaries but `require_known_id: false`. All pass.
3. `test_require_known_id_empty_known_ids_passes_all` — `require_known_id: true` but empty `known_ids`. All pass (guard clause).
4. `test_require_known_id_none_id_rejected` — boundary with `id=None` is dropped when `require_known_id: true`.
5. `test_require_known_id_only_affects_configured_level` — L1 has `require_known_id: true`, L2 does not. L2 boundaries with any ID pass through.

### 1.5 — Acceptance Criteria

- [ ] Schema validates profiles with the new field
- [ ] Existing test suite passes (349 tests) — `require_known_id` defaults to `false`, so no behavior change for existing profiles
- [ ] New unit tests pass

---

## Phase 2: Production XJ Profile

**Goal:** Create `profiles/xj-1999.yaml` with complete known_ids, tuned hierarchy patterns, and relaxed L3 filters.

### 2.1 — Create profiles directory and production profile

**File:** `profiles/xj-1999.yaml` (new)

Copy from `tests/fixtures/xj_1999_profile.yaml` as starting point, then apply all changes below.

### 2.2 — Complete the known_ids list

Add all ~50 groups from the XJ Tab Locator. The full list (from our investigation):

```yaml
known_ids:
  - { id: "IN", title: "Introduction" }
  - { id: "0", title: "Lubrication and Maintenance" }
  - { id: "2", title: "Suspension" }
  - { id: "3", title: "Differential and Driveline" }
  - { id: "5", title: "Brakes" }
  - { id: "6", title: "Clutch" }
  - { id: "7", title: "Cooling System" }
  - { id: "8A", title: "Battery" }
  - { id: "8B", title: "Starting System" }
  - { id: "8C", title: "Charging System" }
  - { id: "8D", title: "Ignition System" }
  - { id: "8E", title: "Instrument Panel Systems" }
  - { id: "8F", title: "Audio Systems" }
  - { id: "8G", title: "Horn Systems" }
  - { id: "8H", title: "Vehicle Speed Control System" }
  - { id: "8J", title: "Turn Signal and Hazard Warning Systems" }
  - { id: "8K", title: "Wiper and Washer Systems" }
  - { id: "8L", title: "Lamps" }
  - { id: "8M", title: "Passive Restraint Systems" }
  - { id: "8N", title: "Electrically Heated Systems" }
  - { id: "8O", title: "Power Distribution Systems" }
  - { id: "8P", title: "Power Lock Systems" }
  - { id: "8Q", title: "Vehicle Theft/Security Systems" }
  - { id: "8R", title: "Power Seats Systems" }
  - { id: "8S", title: "Power Window Systems" }
  - { id: "8T", title: "Power Mirror Systems" }
  - { id: "8U", title: "Chime/Buzzer Warning Systems" }
  - { id: "8V", title: "Overhead Console Systems" }
  - { id: "8W", title: "Wiring Diagrams" }
  - { id: "9", title: "Engine" }
  - { id: "11", title: "Exhaust System and Intake Manifold" }
  - { id: "13", title: "Frame and Bumpers" }
  - { id: "14", title: "Fuel System" }
  - { id: "19", title: "Steering" }
  - { id: "21", title: "Transmission and Transfer Case" }
  - { id: "22", title: "Tires and Wheels" }
  - { id: "23", title: "Body" }
  - { id: "24", title: "Heating and Air Conditioning" }
  - { id: "25", title: "Emission Control Systems" }
```

Note: Some groups have `a`-suffixed variants (e.g., `0a`, `9a`). These will be discovered during validation and added iteratively.

Set `require_known_id: true` on the L1 hierarchy level.

### 2.3 — L2 pattern: add negative lookahead for procedure keywords

Replace the current L2 patterns:

```yaml
# BEFORE
id_pattern: "^([A-Z]{2,}(?:\\s+[A-Z]{2,})+)$"
title_pattern: "^([A-Z]{2,}(?:\\s+[A-Z]{2,})+)$"

# AFTER
id_pattern: "^(?!REMOVAL|INSTALLATION|REMOVAL AND INSTALLATION|DIAGNOSIS|DIAGNOSIS AND TESTING|DESCRIPTION AND OPERATION|SERVICE PROCEDURES|DISASSEMBLY|ASSEMBLY|DISASSEMBLY AND ASSEMBLY|CLEANING|INSPECTION|CLEANING AND INSPECTION|ADJUSTMENT|ADJUSTMENTS|OVERHAUL|TESTING|SPECIFICATIONS|SPECIAL TOOLS|TORQUE CHART|TORQUE SPECIFICATIONS)([A-Z]{2,}(?:\\s+[A-Z]{2,})+)$"
title_pattern: "^(?!REMOVAL|INSTALLATION|REMOVAL AND INSTALLATION|DIAGNOSIS|DIAGNOSIS AND TESTING|DESCRIPTION AND OPERATION|SERVICE PROCEDURES|DISASSEMBLY|ASSEMBLY|DISASSEMBLY AND ASSEMBLY|CLEANING|INSPECTION|CLEANING AND INSPECTION|ADJUSTMENT|ADJUSTMENTS|OVERHAUL|TESTING|SPECIFICATIONS|SPECIAL TOOLS|TORQUE CHART|TORQUE SPECIFICATIONS)([A-Z]{2,}(?:\\s+[A-Z]{2,})+)$"
```

This prevents procedure-type headings from matching L2, forcing them to only match L3.

### 2.4 — L3 pattern: closed vocabulary of procedure keywords

Replace the current L3 patterns:

```yaml
# BEFORE
title_pattern: "^([A-Z]{2,}(?:\\s+[A-Z/\\-\\(\\) ]{2,})+)$"
min_gap_lines: 2
min_content_words: 5
require_blank_before: true

# AFTER
title_pattern: "^(REMOVAL AND INSTALLATION|REMOVAL|INSTALLATION|DIAGNOSIS AND TESTING|DIAGNOSIS|TESTING|DESCRIPTION AND OPERATION|SERVICE PROCEDURES|DISASSEMBLY AND ASSEMBLY|DISASSEMBLY|ASSEMBLY|CLEANING AND INSPECTION|CLEANING|INSPECTION|ADJUSTMENT|ADJUSTMENTS|OVERHAUL|SPECIFICATIONS|SPECIAL TOOLS|TORQUE CHART|TORQUE SPECIFICATIONS)$"
min_gap_lines: 0
min_content_words: 3
require_blank_before: false
```

Key changes:
- **Closed vocabulary** — matches only the standardized Chrysler procedure category names
- **Single-word headings included** — REMOVAL, INSTALLATION, DISASSEMBLY, etc.
- **`require_blank_before: false`** — OCR output lacks consistent blank lines (only 25.5% have them)
- **`min_gap_lines: 0`** — procedure headings can appear close together
- **`min_content_words: 3`** — keep light filtering to suppress empty procedure headers

### 2.5 — L4 pattern: broader component name matching

Replace the current L4 pattern:

```yaml
# BEFORE
title_pattern: "^([A-Z][A-Z \\-]+\\([A-Z ]+\\))$"

# AFTER
title_pattern: "^([A-Z][A-Z][A-Z \\-/]{1,}(?:\\([A-Z0-9\\. ]+\\))?)$"
min_content_words: 3
```

Changes:
- No longer requires parenthetical qualifier — matches `WATER PUMP`, `THERMOSTAT`, `MASTER CYLINDER`
- Still matches parenthetical variants like `MANIFOLD ABSOLUTE PRESSURE (MAP)`
- Requires 3+ chars (avoids matching 2-letter OCR noise)
- `min_content_words: 3` prevents empty component headers from becoming boundaries

### 2.6 — Acceptance Criteria

- [ ] Profile passes schema validation
- [ ] Pipeline runs end-to-end with the production profile
- [ ] L1 boundaries drop from ~2,748 to ~55 (known_ids filter)
- [ ] L3/L4 boundaries increase substantially (target: 500+)
- [ ] Undersized chunks drop below 10% (from 26%)
- [ ] known_ids warnings drop to near zero

---

## Phase 3: Cross-Reference Namespace Fix

**Goal:** Fix the 100% cross-reference validation failure caused by bare group numbers not matching qualified chunk ID prefixes.

### 3.1 — Qualify cross-references at creation time

**File:** `src/pipeline/chunk_assembly.py`, `enrich_chunk_metadata()` (line 744-748)

```python
# BEFORE (line 744-748)
xref_matches: list[str] = []
for pat in profile.cross_reference_patterns:
    xref_matches.extend(re.findall(pat, text))
metadata["cross_references"] = sorted(set(xref_matches))

# AFTER
xref_matches: list[str] = []
for pat in profile.cross_reference_patterns:
    xref_matches.extend(re.findall(pat, text))
# Qualify bare references with manual_id so they match chunk ID prefixes
manual_id = metadata.get("manual_id", "")
if manual_id:
    xref_matches = [f"{manual_id}::{ref}" for ref in xref_matches]
metadata["cross_references"] = sorted(set(xref_matches))
```

### 3.2 — Downgrade skip_section refs from error to warning

**File:** `src/pipeline/qa.py`, `check_cross_ref_validity()` (line 242-275)

After the "target not found" check, add logic to detect references to skipped sections and downgrade:

```python
def check_cross_ref_validity(
    chunks: list[Chunk],
    profile: ManualProfile | None = None,  # add optional profile param
) -> list[ValidationIssue]:
    # ... existing logic ...

    # Build set of skipped section prefixes
    skip_prefixes: set[str] = set()
    if profile and profile.skip_sections:
        manual_id = chunks[0].manual_id if chunks else ""
        for sid in profile.skip_sections:
            skip_prefixes.add(f"{manual_id}::{sid}")

    for chunk in chunks:
        for ref in chunk.metadata.get("cross_references", []):
            if ref not in all_chunk_ids and ref not in all_prefixes:
                # Check if this references a skipped section
                is_skipped = any(ref.startswith(sp) for sp in skip_prefixes)
                issues.append(
                    ValidationIssue(
                        check="cross_ref_validity",
                        severity="warning" if is_skipped else "error",
                        chunk_id=chunk.chunk_id,
                        message=f"Cross-reference target not found: '{ref}'"
                            + (" (skipped section)" if is_skipped else ""),
                        details={"target": ref, "skipped": is_skipped},
                    )
                )
```

Update `run_validation_suite()` call site to pass `profile` to `check_cross_ref_validity()`.

### 3.3 — Tests

**File:** `tests/test_qa.py`

1. `test_cross_ref_qualified_resolves` — chunk with `cross_references: ["xj-1999::7"]` and a chunk with ID starting with `xj-1999::7`. No error.
2. `test_cross_ref_bare_id_fails` — chunk with `cross_references: ["7"]`. Error emitted (bare ref does not resolve).
3. `test_cross_ref_skipped_section_is_warning` — chunk with `cross_references: ["xj-1999::8W"]`, profile with `skip_sections: ["8W"]`. Warning, not error.

**File:** `tests/test_chunk_assembly.py`

4. `test_enrich_cross_refs_qualified` — text containing "Refer to Group 7", profile with `manual_id: "xj-1999"`. Assert `metadata["cross_references"] == ["xj-1999::7"]`.
5. `test_enrich_cross_refs_deduped` — text containing "Refer to Group 7" twice. Assert single entry.

### 3.4 — Acceptance Criteria

- [ ] Cross-ref errors drop from 113 to 0 (for targets that exist)
- [ ] 8W references produce warnings, not errors
- [ ] Existing cross-ref tests still pass
- [ ] New tests pass

---

## Phase 4: Validate End-to-End

**Goal:** Re-run the full pipeline with the production profile and confirm all metrics improve.

### 4.1 — Run pipeline

```bash
pipeline -v process \
  --profile profiles/xj-1999.yaml \
  --pdf "data/99 XJ Service Manual.pdf" \
  --output-dir output/
```

### 4.2 — Run validation with diagnostics

```bash
pipeline -v validate \
  --profile profiles/xj-1999.yaml \
  --pdf "data/99 XJ Service Manual.pdf" \
  --diagnostics
```

### 4.3 — Compare metrics

| Metric | Before | Target |
|--------|--------|--------|
| Total chunks | 2,408 | 1,500-2,500 (depends on new L3/L4 boundaries) |
| L1 boundaries | 2,748 | ~55 |
| L2 boundaries | 3,432 | ~200-400 |
| L3 boundaries | 82 | 500+ |
| L4 boundaries | 53 | 200+ |
| Undersized chunks (<100 tok) | 637 (26%) | <10% |
| Cross-ref errors | 113 | 0 |
| Cross-ref warnings (8W) | 0 | 3 |
| known_ids warnings | 1,716 | <20 |
| False-positive boundaries (<=3 words) | 17% | <5% |
| QA passed | False | True (or close) |

### 4.4 — Iterative tuning

After the first run, review output for:
- Missing `a`-suffixed group variants (add to known_ids if found)
- L3 procedure keywords not in the closed vocabulary (add to pattern)
- L4 false positives from overly broad component pattern (tighten if needed)
- Remaining undersized chunks — identify new patterns and address

### 4.5 — Run test suite

```bash
pytest -v --tb=short
```

All 349 existing tests must pass. New tests from Phases 1 and 3 must also pass.

---

## Execution Order

```
Phase 1 (schema + parser)
  └── 1.1 schema.json
  └── 1.2 profile.py dataclass
  └── 1.3 structural_parser.py filter
  └── 1.4 tests
  └── 1.5 verify: pytest passes

Phase 2 (production profile) — depends on Phase 1
  └── 2.1 create profiles/xj-1999.yaml
  └── 2.2 complete known_ids
  └── 2.3 L2 negative lookahead
  └── 2.4 L3 closed vocabulary
  └── 2.5 L4 broader pattern
  └── 2.6 verify: pipeline runs, metrics improve

Phase 3 (cross-ref fix) — independent, can parallel with 1-2
  └── 3.1 chunk_assembly.py qualification
  └── 3.2 qa.py skip_section downgrade
  └── 3.3 tests
  └── 3.4 verify: pytest passes

Phase 4 (validation) — depends on all above
  └── 4.1 full pipeline run
  └── 4.2 validation with diagnostics
  └── 4.3 compare metrics
  └── 4.4 iterative tuning
  └── 4.5 full test suite
```

## Files Changed

| File | Phase | Change |
|------|-------|--------|
| `schema/manual_profile_v1.schema.json` | 1 | Add `require_known_id` property |
| `src/pipeline/profile.py` | 1 | Add `require_known_id` field to `HierarchyLevel` |
| `src/pipeline/structural_parser.py` | 1 | Add known_id filtering pass in `filter_boundaries()` |
| `tests/test_structural_parser.py` | 1 | Add `TestRequireKnownId` class (5 tests) |
| `profiles/xj-1999.yaml` | 2 | New production profile |
| `src/pipeline/chunk_assembly.py` | 3 | Qualify cross-refs with `manual_id::` in `enrich_chunk_metadata()` |
| `src/pipeline/qa.py` | 3 | Downgrade skip_section refs to warning; accept `profile` param |
| `tests/test_qa.py` | 3 | Add cross-ref qualification tests (3 tests) |
| `tests/test_chunk_assembly.py` | 3 | Add cross-ref enrichment tests (2 tests) |

## Risk Notes

- **L4 pattern may be too broad.** The pattern `^([A-Z][A-Z][A-Z \-/]+)$` will match many ALL-CAPS lines that are not component headings (table headers, warning text, etc.). The `min_content_words: 3` filter and the disambiguation logic (L4 only wins when current_level >= 3) provide some guard rails. Monitor during Phase 4 and tighten if false-positive rate is high.
- **`a`-suffixed variants.** Some groups may have `0a`, `9a`, etc. variants for international markets. These will be caught by the mandatory known_ids filter and rejected unless added to the list. Phase 4.4 handles this iteratively.
- **Test fixture unchanged.** The test fixture `tests/fixtures/xj_1999_profile.yaml` does NOT get `require_known_id: true`. It retains the original 8 known_ids. This means existing tests are unaffected. New integration tests that exercise the production profile should use `profiles/xj-1999.yaml`.
