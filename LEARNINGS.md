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
