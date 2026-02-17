# Implementation Plan: Output Quality — Phase 2

**Generated:** 2026-02-16
**Based On:** RECOMMENDATIONS.md + docs/plans/2026-02-16-output-quality-fixes.md
**Supersedes:** Previous IMPLEMENTATION_PLAN.md (Phase 1-3 remediation — complete, 349 tests passing)
**Total Phases:** 4
**Estimated Total Effort:** ~100K tokens

---

## Plan Overview

This plan addresses the four remaining output quality issues identified by running the 1,948-page XJ service manual through the pipeline. The previous three-phase implementation (skip list, metadata enrichment, boundary filtering, cross-entry merge) is complete with 349 tests passing. This plan builds on that foundation to reach QA-passing output quality.

**Strategy:** Phase 1 adds the mandatory known_ids filter (schema + code). Phase 2 creates the production XJ profile with complete configuration. Phase 3 fixes the cross-reference namespace mismatch. Phase 4 validates end-to-end and tunes iteratively. Phases 1 and 3 are independent and can run in parallel. Phase 2 depends on Phase 1. Phase 4 depends on all prior phases.

**Validation approach:** After Phase 4, re-run the full XJ pipeline and confirm:
- L1 boundaries drop from ~2,748 to ~55
- L3 boundaries increase from 82 to 500+
- Cross-ref errors drop from 113 to 0
- known_ids warnings drop from 1,716 to <20
- QA passed: True

### Phase Summary Table

| Phase | Focus Area | Key Deliverables | Est. Tokens | Dependencies |
|-------|------------|------------------|-------------|--------------|
| 1 | Mandatory known_ids filter | Schema field, dataclass field, filter pass, 5 tests | ~25K | None |
| 2 | Production XJ profile | Complete profile YAML, L2/L3/L4 patterns, profile regression test | ~30K | Phase 1 |
| 3 | Cross-ref namespace fix | Qualify refs, downgrade skip_section refs, 5 tests | ~20K | None |
| 4 | End-to-end validation | Pipeline run, metric comparison, iterative tuning | ~25K | Phases 1-3 |

---

## Phase 1: Mandatory known_ids Filter

**Estimated Effort:** ~25,000 tokens (including testing/fixes)
**Dependencies:** None
**Parallelizable:** Yes — can run concurrently with Phase 3

### Goals
- Add `require_known_id` support to the profile schema, dataclass, and boundary filter
- When enabled, L1 boundaries with unrecognized IDs are dropped during `filter_boundaries()`
- Zero behavior change for existing profiles and tests

### Work Items

#### 1.1 Schema: Add `require_known_id` Property

**Recommendation Ref:** Q1
**Files Affected:** `schema/manual_profile_v1.schema.json`

**Description:**
Add `require_known_id` boolean property to the hierarchy level item in the JSON Schema, with `default: false`.

**Acceptance Criteria:**
- [ ] Property appears in hierarchy level item properties
- [ ] Default is `false`
- [ ] Description explains behavior
- [ ] Existing profiles validate without changes

---

#### 1.2 Dataclass: Add Field to `HierarchyLevel`

**Recommendation Ref:** Q1
**Files Affected:** `src/pipeline/profile.py`

**Description:**
Add `require_known_id: bool = False` field to the `HierarchyLevel` dataclass. Update the hierarchy parsing in `load_profile()` to read this field from the YAML dict.

**Acceptance Criteria:**
- [ ] Field exists on `HierarchyLevel` with default `False`
- [ ] `load_profile()` reads `require_known_id` from YAML
- [ ] Existing profiles load without changes (field defaults to `False`)

---

#### 1.3 Parser: Enforce in `filter_boundaries()`

**Recommendation Ref:** Q1
**Files Affected:** `src/pipeline/structural_parser.py`

**Description:**
Add Pass 0 to `filter_boundaries()` — before the existing blank-line, gap, and content-words passes. For levels where `require_known_id` is `True` and `known_ids` is non-empty, reject any boundary whose extracted ID is not in the known set. Boundaries with `id=None` are also rejected.

```python
# --- Pass 0: require_known_id ---
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

**Acceptance Criteria:**
- [ ] Pass 0 runs before existing passes
- [ ] Only affects levels with `require_known_id: True` AND non-empty `known_ids`
- [ ] Boundaries at unaffected levels pass through untouched
- [ ] `id=None` boundaries are rejected when filter is active

---

#### 1.4 Tests

**Recommendation Ref:** Q1
**Files Affected:** `tests/test_structural_parser.py`

**Description:**
Add `TestRequireKnownId` test class with 5 tests:

1. `test_require_known_id_rejects_unknown` — profile with `require_known_id: true` and known_ids `["7", "9"]`. Boundaries with IDs `"7"`, `"9"`, `"42"`, `"1999"`. Assert only `"7"` and `"9"` survive.
2. `test_require_known_id_false_passes_all` — same boundaries, `require_known_id: false`. All pass.
3. `test_require_known_id_empty_known_ids_passes_all` — `require_known_id: true`, empty `known_ids`. All pass (guard clause).
4. `test_require_known_id_none_id_rejected` — boundary with `id=None`, `require_known_id: true`. Rejected.
5. `test_require_known_id_only_affects_configured_level` — L1 has `require_known_id: true`, L2 does not. L2 boundaries pass through.

**Acceptance Criteria:**
- [ ] All 5 new tests pass
- [ ] All 349 existing tests still pass

---

### Phase 1 Testing Requirements
- [ ] Schema validates profiles with the new field
- [ ] Existing test suite passes (349 tests) — `require_known_id` defaults to `false`
- [ ] 5 new unit tests pass
- [ ] `pytest -v --tb=short` — all green

### Phase 1 Completion Checklist
- [ ] All work items complete (1.1-1.4)
- [ ] Tests passing (354 total)
- [ ] No regressions introduced

---

## Phase 2: Production XJ Profile

**Estimated Effort:** ~30,000 tokens (including testing/fixes)
**Dependencies:** Phase 1 (need `require_known_id` field)
**Parallelizable:** No — sequential with Phase 1

### Goals
- Create `profiles/xj-1999.yaml` with complete known_ids, tuned patterns, and relaxed L3 filters
- Keep test fixture `tests/fixtures/xj_1999_profile.yaml` unchanged
- Add profile regression test

### Work Items

#### 2.1 Create Production Profile

**Recommendation Ref:** Q2, Q5
**Files Affected:** `profiles/xj-1999.yaml` (new)

**Description:**
Copy from `tests/fixtures/xj_1999_profile.yaml` and apply all changes:

1. **Complete known_ids list** (~39 groups from XJ Tab Locator):
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

2. **Set `require_known_id: true`** on L1 hierarchy level.

3. **L2 pattern — add negative lookahead** for procedure keywords:
   ```yaml
   id_pattern: "^(?!REMOVAL|INSTALLATION|REMOVAL AND INSTALLATION|DIAGNOSIS|DIAGNOSIS AND TESTING|DESCRIPTION AND OPERATION|SERVICE PROCEDURES|DISASSEMBLY|ASSEMBLY|DISASSEMBLY AND ASSEMBLY|CLEANING|INSPECTION|CLEANING AND INSPECTION|ADJUSTMENT|ADJUSTMENTS|OVERHAUL|TESTING|SPECIFICATIONS|SPECIAL TOOLS|TORQUE CHART|TORQUE SPECIFICATIONS)([A-Z]{2,}(?:\\s+[A-Z]{2,})+)$"
   ```

4. **L3 pattern — closed vocabulary**:
   ```yaml
   title_pattern: "^(REMOVAL AND INSTALLATION|REMOVAL|INSTALLATION|DIAGNOSIS AND TESTING|DIAGNOSIS|TESTING|DESCRIPTION AND OPERATION|SERVICE PROCEDURES|DISASSEMBLY AND ASSEMBLY|DISASSEMBLY|ASSEMBLY|CLEANING AND INSPECTION|CLEANING|INSPECTION|ADJUSTMENT|ADJUSTMENTS|OVERHAUL|SPECIFICATIONS|SPECIAL TOOLS|TORQUE CHART|TORQUE SPECIFICATIONS)$"
   min_gap_lines: 0
   min_content_words: 3
   require_blank_before: false
   ```

5. **L4 pattern — broader component matching**:
   ```yaml
   title_pattern: "^([A-Z][A-Z][A-Z \\-/]{1,}(?:\\([A-Z0-9\\. ]+\\))?)$"
   min_content_words: 3
   ```

**Acceptance Criteria:**
- [ ] Profile passes schema validation
- [ ] All regex patterns compile without error
- [ ] known_ids count >= 35
- [ ] `require_known_id: true` is set on L1

---

#### 2.2 Add Profile Regression Test

**Recommendation Ref:** D2
**Files Affected:** `tests/test_profile.py`

**Description:**
Add an integration test that loads `profiles/xj-1999.yaml`, validates it, compiles all regex patterns, and asserts basic invariants.

**Acceptance Criteria:**
- [ ] Production profile loads successfully
- [ ] Profile passes `validate_profile()` with no errors
- [ ] All regex patterns compile
- [ ] known_ids count >= 35
- [ ] L1 has `require_known_id: True`
- [ ] L3 title_pattern contains "REMOVAL"

---

### Phase 2 Testing Requirements
- [ ] Production profile loads and validates
- [ ] Regression test passes
- [ ] All 354+ existing tests still pass
- [ ] Profile is ready for end-to-end validation in Phase 4

### Phase 2 Completion Checklist
- [ ] `profiles/xj-1999.yaml` created
- [ ] Profile regression test added
- [ ] All tests passing
- [ ] No regressions introduced

---

## Phase 3: Cross-Reference Namespace Fix

**Estimated Effort:** ~20,000 tokens (including testing/fixes)
**Dependencies:** None — independent of Phases 1 and 2
**Parallelizable:** Yes — can run concurrently with Phase 1

### Goals
- Fix the 100% cross-reference validation failure caused by bare group numbers
- Downgrade references to skipped sections from error to warning
- Maintain backward compatibility

### Work Items

#### 3.1 Qualify Cross-References at Creation Time

**Recommendation Ref:** Q3
**Files Affected:** `src/pipeline/chunk_assembly.py`

**Description:**
In `enrich_chunk_metadata()`, after collecting cross-reference matches, qualify them with `{manual_id}::` prefix:

```python
# AFTER existing xref collection (line 744-748)
manual_id = metadata.get("manual_id", "")
if manual_id:
    xref_matches = [f"{manual_id}::{ref}" for ref in xref_matches]
metadata["cross_references"] = sorted(set(xref_matches))
```

**Acceptance Criteria:**
- [ ] Cross-references include `{manual_id}::` prefix
- [ ] Empty `manual_id` falls back to bare references (no crash)
- [ ] Deduplication still works after qualification

---

#### 3.2 Downgrade Skip-Section References to Warning

**Recommendation Ref:** Q3
**Files Affected:** `src/pipeline/qa.py`

**Description:**
Add `profile` parameter to `check_cross_ref_validity()`. When a cross-reference target matches a skipped section prefix, emit a warning instead of an error. Update `run_validation_suite()` to pass `profile`.

```python
def check_cross_ref_validity(
    chunks: list[Chunk],
    profile: ManualProfile | None = None,
) -> list[ValidationIssue]:
    # ... existing logic ...

    skip_prefixes: set[str] = set()
    if profile and profile.skip_sections:
        manual_id = chunks[0].manual_id if chunks else ""
        for sid in profile.skip_sections:
            skip_prefixes.add(f"{manual_id}::{sid}")

    for chunk in chunks:
        for ref in chunk.metadata.get("cross_references", []):
            if ref not in all_chunk_ids and ref not in all_prefixes:
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

**Acceptance Criteria:**
- [ ] `check_cross_ref_validity()` accepts optional `profile` parameter
- [ ] References to skipped sections produce warnings, not errors
- [ ] References to non-skipped missing targets still produce errors
- [ ] `run_validation_suite()` passes `profile` to the function
- [ ] Backward compatible — `profile=None` produces errors for all unresolved refs

---

#### 3.3 Tests

**Recommendation Ref:** Q3
**Files Affected:** `tests/test_qa.py`, `tests/test_chunk_assembly.py`

**Description:**
Add 5 tests across two files:

**`tests/test_qa.py`:**
1. `test_cross_ref_qualified_resolves` — chunk with `cross_references: ["xj-1999::7"]` and a chunk with ID starting with `xj-1999::7`. No error.
2. `test_cross_ref_bare_id_fails` — chunk with `cross_references: ["7"]`. Error emitted.
3. `test_cross_ref_skipped_section_is_warning` — chunk with `cross_references: ["xj-1999::8W"]`, profile with `skip_sections: ["8W"]`. Warning, not error.

**`tests/test_chunk_assembly.py`:**
4. `test_enrich_cross_refs_qualified` — text with "Refer to Group 7", profile with `manual_id: "xj-1999"`. Assert `metadata["cross_references"] == ["xj-1999::7"]`.
5. `test_enrich_cross_refs_deduped` — text with "Refer to Group 7" twice. Assert single entry.

**Acceptance Criteria:**
- [ ] All 5 new tests pass
- [ ] All existing cross-ref tests still pass
- [ ] Total test count increases by 5

---

### Phase 3 Testing Requirements
- [ ] Cross-ref qualification tested in chunk_assembly
- [ ] Skip-section downgrade tested in qa
- [ ] Backward compatibility verified (profile=None)
- [ ] All 354+ existing tests pass

### Phase 3 Completion Checklist
- [ ] Cross-refs qualified at creation time
- [ ] Skip-section refs downgraded to warning
- [ ] 5 new tests passing
- [ ] No regressions introduced

---

## Phase 4: End-to-End Validation

**Estimated Effort:** ~25,000 tokens (including iterative tuning)
**Dependencies:** Phases 1, 2, and 3 (all must be complete)
**Parallelizable:** No — final integration validation

### Goals
- Run the full pipeline with the production profile and confirm all metrics improve
- Iteratively tune the production profile based on results
- Achieve QA passing status

### Work Items

#### 4.1 Run Pipeline

**Recommendation Ref:** All
**Files Affected:** None (validation only)

**Description:**
```bash
pipeline -v process \
  --profile profiles/xj-1999.yaml \
  --pdf "data/99 XJ Service Manual.pdf" \
  --output-dir output/
```

**Acceptance Criteria:**
- [ ] Pipeline completes without errors

---

#### 4.2 Run Validation with Diagnostics

**Recommendation Ref:** All
**Files Affected:** None (validation only)

**Description:**
```bash
pipeline -v validate \
  --profile profiles/xj-1999.yaml \
  --pdf "data/99 XJ Service Manual.pdf" \
  --diagnostics
```

**Acceptance Criteria:**
- [ ] Validation completes
- [ ] Diagnostics output shows improved boundary distribution

---

#### 4.3 Compare Metrics

**Recommendation Ref:** All

**Description:**
Compare pipeline output against baseline:

| Metric | Before | Target |
|--------|--------|--------|
| Total chunks | 2,408 | 1,500-2,500 |
| L1 boundaries | 2,748 | ~55 |
| L2 boundaries | 3,432 | ~200-400 |
| L3 boundaries | 82 | 500+ |
| L4 boundaries | 53 | 200+ |
| Undersized chunks (<100 tok) | 637 (26%) | <10% |
| Cross-ref errors | 113 | 0 |
| Cross-ref warnings (8W) | 0 | ~3 |
| known_ids warnings | 1,716 | <20 |
| False-positive boundaries (<=3 words) | 17% | <5% |
| QA passed | False | True |

**Acceptance Criteria:**
- [ ] All metrics improve or stay within acceptable range
- [ ] QA passes (zero errors)

---

#### 4.4 Iterative Tuning

**Recommendation Ref:** Q2, Q5

**Description:**
After the first run, review output for:
- Missing `a`-suffixed group variants — add to known_ids if discovered
- L3 procedure keywords not in the closed vocabulary — add to pattern
- L4 false positives from overly broad component pattern — tighten if needed
- Remaining undersized chunks — identify patterns and address

**Acceptance Criteria:**
- [ ] All discovered variants added to profile
- [ ] No systematic false-positive patterns remain

---

#### 4.5 Run Full Test Suite

**Recommendation Ref:** All

**Description:**
```bash
pytest -v --tb=short
```

All 349 existing tests plus ~10 new tests from Phases 1 and 3 must pass.

**Acceptance Criteria:**
- [ ] All tests pass (expected: 359+)
- [ ] No regressions

---

### Phase 4 Completion Checklist
- [ ] Pipeline runs end-to-end with production profile
- [ ] All metric targets met or close
- [ ] QA passes
- [ ] Full test suite green
- [ ] Profile tuned based on iterative findings

---

## Parallel Work Opportunities

Phases 1 and 3 are fully independent and can execute concurrently:

| Work Item | Can Run With | Notes |
|-----------|--------------|-------|
| Phase 1 (known_ids filter) | Phase 3 (cross-ref fix) | Different files: profile.py + parser vs. chunk_assembly + qa |
| 1.1 (schema) | 3.1 (qualify refs) | No file overlap |
| 1.2 (dataclass) | 3.2 (downgrade) | Different modules |
| 1.3 (filter) | 3.3 (tests) | Different test files |
| 1.4 (tests) | 3.3 (tests) | Different test classes |
| Phase 2 (profile) | — | Depends on Phase 1 |
| Phase 4 (validation) | — | Depends on all |

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| L4 pattern too broad, creates false positives | Medium | Medium | `min_content_words: 3` guards against empty component headers. Monitor during Phase 4, tighten if false-positive rate > 10%. |
| `a`-suffixed group variants rejected by known_ids filter | Medium | Low | Phase 4.4 handles iteratively — discover and add during first validation run. |
| L3 closed vocabulary misses non-standard procedure names | Low | Medium | Start with Chrysler standard keywords. Add more during Phase 4.4 if genuine procedures are missed. |
| Test fixture changes break existing tests | Zero | — | Test fixture is NOT modified. Production profile is a separate file. |
| Cross-ref qualification changes metadata format | Low | Low | References were previously bare — now qualified. QA validator already supports prefix matching. |
| Pattern changes interact unexpectedly with disambiguation | Low | High | The known_ids filter runs in `filter_boundaries()` AFTER `detect_boundaries()`, not during it. Disambiguation sees the same input. Filter cleans up afterward. |

---

## Success Metrics

| Metric | Current (Baseline) | Target | Measurement |
|--------|-------------------|--------|-------------|
| QA passed | False | True | `pipeline validate` exit code 0 |
| Cross-ref errors | 113 | 0 | QA report error count |
| known_ids warnings | 1,716 | <20 | QA report warning count |
| L1 false positives | ~2,700 | 0 | Boundary diagnostics |
| L3 procedure detection | 82 (8%) | 500+ (target) | Boundary diagnostics level distribution |
| Undersized chunks | 637 (26%) | <10% | Chunk size distribution |
| Total tests | 349 | 359+ | `pytest` summary |

---

## Files Changed

| File | Phase | Change |
|------|-------|--------|
| `schema/manual_profile_v1.schema.json` | 1 | Add `require_known_id` property |
| `src/pipeline/profile.py` | 1 | Add `require_known_id` field to `HierarchyLevel` |
| `src/pipeline/structural_parser.py` | 1 | Add known_id filtering pass (Pass 0) in `filter_boundaries()` |
| `tests/test_structural_parser.py` | 1 | Add `TestRequireKnownId` class (5 tests) |
| `profiles/xj-1999.yaml` | 2 | New production profile |
| `tests/test_profile.py` | 2 | Add production profile regression test |
| `src/pipeline/chunk_assembly.py` | 3 | Qualify cross-refs with `manual_id::` in `enrich_chunk_metadata()` |
| `src/pipeline/qa.py` | 3 | Add `profile` param to `check_cross_ref_validity()`; downgrade skip-section refs |
| `tests/test_qa.py` | 3 | Add cross-ref qualification tests (3 tests) |
| `tests/test_chunk_assembly.py` | 3 | Add cross-ref enrichment tests (2 tests) |

---

*Implementation plan generated by Claude on 2026-02-16*
*Based on: RECOMMENDATIONS.md + docs/plans/2026-02-16-output-quality-fixes.md*
