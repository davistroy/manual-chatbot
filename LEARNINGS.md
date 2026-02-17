# Learnings

Issues encountered and solutions discovered during implementation.

## Summary

- OCR garbage detection requires per-token non-ASCII density analysis, not per-line, to catch lines with mixed clean/garbage content
- The `assess_quality` needs_reocr threshold is `< 0.7` dictionary match rate (not `< 0.85` as initially assumed from PRD)
- Structural boundary detection needs context-based disambiguation when a line matches multiple hierarchy levels - track current depth and pick the shallowest level deeper than current context
- Chunk assembly rule ordering matters: R1 -> R3 -> R4 -> R5 -> R2 -> R6 -> R7 -> R8 (not strictly sequential R1-R8) to ensure step/safety/table integrity is established before size splitting
- Duplicate content detection uses word-level SequenceMatcher (not character-level) to avoid false positives with short texts
- Cross-reference validity checking needs to consider prefix sub-IDs (e.g., `xj-1999::8A` is valid if `xj-1999::8A::SP` exists)
- Query analysis for vehicle/engine/drivetrain uses regex pattern matching with scoring-based type classification and priority tie-breaking

## REVIEW.md Remediation Round (2026-02-16)

- Parallel subagent execution requires careful management of shared file edits — typed dataclass refactoring (PageRange/LineRange) needed coordinated updates across modules
- `dataclasses.asdict()` is essential for JSON serialization of nested dataclasses in metadata
- Safety regex pre-compilation with `re.IGNORECASE` must use the compiled pattern object (not pattern string) for case-insensitive matching
- Structured logging with Python's `logging` module requires `logging.basicConfig()` configuration before any handlers emit output
- CLI testing for log output requires `caplog` fixture instead of `capsys` when using `logging` module

## Output Quality Round (2026-02-16)

- `require_known_id` filter is highly effective at eliminating false-positive L1 boundaries — dropped from ~2,748 to only valid group IDs
- Cross-reference qualification with `manual_id::` prefix is essential for multi-manual environments and prevents false resolution
- Chrysler group numbering uses "Group 8" to refer to the entire 8A-8W electrical family — cross-ref validation needs string-prefix matching (not just `::` segment matching) to handle this
- L3 closed-vocabulary procedure patterns work well but produce undersized chunks when the procedure has minimal content
- Skip-section downgrade (error → warning) for wiring diagrams (8W) keeps QA clean while preserving the reference information
- Production profiles should be separate from test fixtures — prevents regressions and allows independent tuning

## Multi-Manual Code Fixes Round (2026-02-17)

- All 4 Phase 5 work items (cross-ref partial-path, regex substitutions, character-spacing collapse, per-pass filter logging) ran in parallel with no merge conflicts — different files or sufficiently isolated functions within shared files
- All 465 tests pass after Phase 5 completion

## Production Profile Creation Round (2026-02-17)

- All 3 profile agents (6.1 CJ universal, 7.1 TM9-8014, 8.1 TM9-8015-2) ran in parallel with no merge conflicts — each creates a new YAML profile and appends tests to test_profile.py in non-overlapping test classes
- Each profile required iterative tuning against real PDFs: TOC false positives needed known_ids filtering, OCR artifacts required manual-specific substitution lists, and boundary post-filters (min_gap_lines, min_content_words, require_blank_before) needed per-manual calibration
- 502 tests pass after all 3 profiles completed (up from 465 after Phase 5)
