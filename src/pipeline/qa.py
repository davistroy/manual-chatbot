"""Chunk validation and QA suite."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from typing import Any

from .chunk_assembly import Chunk, count_tokens
from .profile import ManualProfile


@dataclass
class ValidationIssue:
    """A single validation issue found during QA."""
    check: str
    severity: str  # "error" | "warning"
    chunk_id: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Complete validation report for a set of chunks."""
    total_chunks: int
    issues: list[ValidationIssue]
    checks_run: list[str]
    passed: bool

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


def check_orphaned_steps(
    chunks: list[Chunk], step_patterns: list[str]
) -> list[ValidationIssue]:
    """Check no chunk starts mid-sequence (per profile step_patterns)."""
    issues: list[ValidationIssue] = []
    compiled = [re.compile(p) for p in step_patterns]

    for chunk in chunks:
        text = chunk.text.strip()
        if not text:
            continue

        # Get the first line of the chunk
        first_line = text.split("\n")[0].strip()

        for pat in compiled:
            match = pat.search(first_line)
            if match:
                step_val = match.group(1)
                # Check if the first step is NOT the beginning of a sequence
                is_start = False
                if step_val.isdigit():
                    is_start = int(step_val) == 1
                elif step_val.isalpha():
                    is_start = step_val.lower() == "a"

                if not is_start:
                    issues.append(
                        ValidationIssue(
                            check="orphaned_steps",
                            severity="warning",
                            chunk_id=chunk.chunk_id,
                            message=f"Chunk starts mid-sequence at step '{step_val}'",
                            details={"first_step": step_val},
                        )
                    )
                break  # Only check the first matching pattern

    return issues


def check_split_safety_callouts(
    chunks: list[Chunk], profile: ManualProfile
) -> list[ValidationIssue]:
    """Check no safety callout at chunk start without preceding context."""
    issues: list[ValidationIssue] = []

    safety_patterns = [(sc.level, re.compile(sc.pattern)) for sc in profile.safety_callouts]

    for chunk in chunks:
        text = chunk.text.strip()
        if not text:
            continue

        lines = text.split("\n")
        first_line = lines[0].strip()

        for level, pat in safety_patterns:
            if pat.search(first_line):
                # Check if there's substantive procedure content after the callout
                # A chunk that is ONLY a safety callout (no procedure steps) is suspicious
                has_procedure = False
                for line in lines[1:]:
                    stripped = line.strip()
                    # Look for procedure content: numbered steps, lettered steps, or
                    # substantial non-callout text
                    if re.match(r'^\(\d+\)\s', stripped) or re.match(r'^[a-z]\.\s', stripped):
                        has_procedure = True
                        break
                    # Non-empty, non-callout continuation line that looks like content
                    if stripped and not any(p.search(stripped) for _, p in safety_patterns):
                        # Check if it's actually continuation of the callout (all caps for WARNING)
                        # or real content
                        if not stripped.isupper() and len(stripped.split()) > 3:
                            has_procedure = True
                            break

                if not has_procedure:
                    severity = "warning" if level == "note" else "error"
                    issues.append(
                        ValidationIssue(
                            check="split_safety_callouts",
                            severity=severity,
                            chunk_id=chunk.chunk_id,
                            message=f"Safety callout ({level}) without governed procedure",
                            details={"callout_level": level},
                        )
                    )
                break  # Only check first matching safety pattern

    return issues


def check_size_outliers(
    chunks: list[Chunk], min_tokens: int = 100, max_tokens: int = 3000
) -> list[ValidationIssue]:
    """Flag chunks below min or above max token count."""
    issues: list[ValidationIssue] = []

    for chunk in chunks:
        tokens = count_tokens(chunk.text)
        if tokens < min_tokens:
            issues.append(
                ValidationIssue(
                    check="size_outliers",
                    severity="warning",
                    chunk_id=chunk.chunk_id,
                    message=f"Chunk too small: {tokens} tokens (min {min_tokens})",
                    details={"token_count": tokens, "min_tokens": min_tokens},
                )
            )
        elif tokens > max_tokens:
            issues.append(
                ValidationIssue(
                    check="size_outliers",
                    severity="warning",
                    chunk_id=chunk.chunk_id,
                    message=f"Chunk too large: {tokens} tokens (max {max_tokens})",
                    details={"token_count": tokens, "max_tokens": max_tokens},
                )
            )

    return issues


def check_metadata_completeness(chunks: list[Chunk]) -> list[ValidationIssue]:
    """Verify every chunk has manual_id, level1_id, and content_type."""
    issues: list[ValidationIssue] = []
    required_fields = ["manual_id", "level1_id", "content_type"]

    for chunk in chunks:
        for field_name in required_fields:
            if field_name not in chunk.metadata:
                issues.append(
                    ValidationIssue(
                        check="metadata_completeness",
                        severity="error",
                        chunk_id=chunk.chunk_id,
                        message=f"Missing required metadata field: {field_name}",
                        details={"missing_field": field_name},
                    )
                )

    return issues


def check_duplicate_content(
    chunks: list[Chunk], similarity_threshold: float = 0.95
) -> list[ValidationIssue]:
    """Detect near-duplicate chunks within the same manual."""
    issues: list[ValidationIssue] = []
    seen_pairs: set[tuple[str, str]] = set()

    # Pre-tokenize all chunks once
    token_sets = [set(c.text.split()) for c in chunks]
    token_counts = [len(c.text.split()) for c in chunks]

    for i in range(len(chunks)):
        for j in range(i + 1, len(chunks)):
            chunk_a = chunks[i]
            chunk_b = chunks[j]

            # Only compare chunks from the same manual
            if chunk_a.manual_id != chunk_b.manual_id:
                continue

            pair_key = (chunk_a.chunk_id, chunk_b.chunk_id)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            # Quick length check — skip if token counts differ by more than
            # what the threshold allows (avoids expensive set operations)
            min_count = min(token_counts[i], token_counts[j])
            max_count = max(token_counts[i], token_counts[j])
            if max_count > 0 and min_count / max_count < similarity_threshold:
                continue

            # Jaccard similarity on token sets
            intersection = len(token_sets[i] & token_sets[j])
            union = len(token_sets[i] | token_sets[j])
            ratio = intersection / union if union > 0 else 0.0

            if ratio >= similarity_threshold:
                issues.append(
                    ValidationIssue(
                        check="duplicate_content",
                        severity="warning",
                        chunk_id=chunk_a.chunk_id,
                        message=f"Near-duplicate with chunk '{chunk_b.chunk_id}' "
                                f"(similarity: {ratio:.2%})",
                        details={
                            "duplicate_chunk_id": chunk_b.chunk_id,
                            "similarity": ratio,
                        },
                    )
                )

    return issues


def check_cross_ref_validity(
    chunks: list[Chunk],
    profile: ManualProfile | None = None,
) -> list[ValidationIssue]:
    """Verify every cross-reference target resolves to a real chunk ID.

    When *profile* is provided and has ``skip_sections``, references that
    resolve to a skipped section are downgraded from error to warning
    (the target is intentionally absent from the chunk set).
    """
    issues: list[ValidationIssue] = []

    # Build a set of all known chunk IDs
    all_chunk_ids = {chunk.chunk_id for chunk in chunks}
    # Also build a set of prefix IDs (for partial matches like "xj-1999::8A")
    all_prefixes: set[str] = set()
    for cid in all_chunk_ids:
        parts = cid.split("::")
        for k in range(1, len(parts) + 1):
            all_prefixes.add("::".join(parts[:k]))

    # Build skip prefixes from profile.skip_sections so that references
    # to intentionally skipped sections produce warnings, not errors.
    skip_prefixes: set[str] = set()
    if profile and profile.skip_sections:
        manual_id = chunks[0].manual_id if chunks else ""
        for sid in profile.skip_sections:
            skip_prefixes.add(f"{manual_id}::{sid}")

    for chunk in chunks:
        cross_refs = chunk.metadata.get("cross_references", [])
        if not cross_refs:
            continue

        for ref in cross_refs:
            # Strategy 1-3: exact chunk ID, exact prefix, or string-prefix match
            # (e.g., "xj-1999::8" matches "xj-1999::8A", "xj-1999::8B", etc.)
            if ref in all_chunk_ids or ref in all_prefixes or any(
                p.startswith(ref) for p in all_prefixes
            ):
                continue  # resolved

            # Strategy 4: suffix-segment match — extract the segment after
            # the last "::" in the reference and check if any chunk ID
            # contains "::suffix::" or ends with "::suffix".  This handles
            # hierarchical IDs like "tm9-8014-m38a1::69" resolving to
            # "tm9-8014-m38a1::1::IV::69".
            ref_parts = ref.split("::")
            if len(ref_parts) >= 2:
                suffix = ref_parts[-1]
                segment_pattern = f"::{suffix}::"
                segment_end = f"::{suffix}"
                if any(
                    segment_pattern in cid or cid.endswith(segment_end)
                    for cid in all_chunk_ids
                ):
                    continue  # resolved via suffix-segment match

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

    return issues


def check_profile_validation(
    chunks: list[Chunk], profile: ManualProfile
) -> list[ValidationIssue]:
    """Check all Level 1 IDs match profile known_ids."""
    issues: list[ValidationIssue] = []

    # Get known Level 1 IDs from the profile hierarchy
    known_level1_ids: set[str] = set()
    for level in profile.hierarchy:
        if level.level == 1:
            for kid in level.known_ids:
                known_level1_ids.add(kid["id"])
            break  # Only need level 1

    if not known_level1_ids:
        # No known_ids defined in profile; skip check
        return issues

    for chunk in chunks:
        level1_id = chunk.metadata.get("level1_id")
        if level1_id is not None and level1_id not in known_level1_ids:
            issues.append(
                ValidationIssue(
                    check="profile_validation",
                    severity="warning",
                    chunk_id=chunk.chunk_id,
                    message=f"Level 1 ID '{level1_id}' not in profile known_ids",
                    details={"level1_id": level1_id, "known_ids": sorted(known_level1_ids)},
                )
            )

    return issues


def run_validation_suite(
    chunks: list[Chunk], profile: ManualProfile
) -> ValidationReport:
    """Run all validation checks and produce a comprehensive report."""
    all_issues: list[ValidationIssue] = []
    checks_run: list[str] = []

    # 1. Orphaned steps
    checks_run.append("orphaned_steps")
    all_issues.extend(check_orphaned_steps(chunks, profile.step_patterns))

    # 2. Split safety callouts
    checks_run.append("split_safety_callouts")
    all_issues.extend(check_split_safety_callouts(chunks, profile))

    # 3. Size outliers
    checks_run.append("size_outliers")
    all_issues.extend(check_size_outliers(chunks))

    # 4. Metadata completeness
    checks_run.append("metadata_completeness")
    all_issues.extend(check_metadata_completeness(chunks))

    # 5. Duplicate content
    checks_run.append("duplicate_content")
    all_issues.extend(check_duplicate_content(chunks))

    # 6. Cross-reference validity
    checks_run.append("cross_ref_validity")
    all_issues.extend(check_cross_ref_validity(chunks, profile))

    # 7. Profile validation
    checks_run.append("profile_validation")
    all_issues.extend(check_profile_validation(chunks, profile))

    error_count = sum(1 for i in all_issues if i.severity == "error")
    passed = error_count == 0

    return ValidationReport(
        total_chunks=len(chunks),
        issues=all_issues,
        checks_run=checks_run,
        passed=passed,
    )
