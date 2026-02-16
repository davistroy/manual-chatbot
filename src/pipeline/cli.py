"""Pipeline CLI — command-line interface for the chunking pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Smart Chunking Pipeline for Vehicle Service Manual RAG",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    # process subcommand
    process_parser = subparsers.add_parser(
        "process",
        help="Process a single manual: extract, parse, chunk, embed, index",
    )
    process_parser.add_argument(
        "--profile", required=True, help="Path to the YAML profile file"
    )
    process_parser.add_argument(
        "--pdf", required=True, help="Path to the PDF manual file"
    )

    # bootstrap-profile subcommand
    bootstrap_parser = subparsers.add_parser(
        "bootstrap-profile",
        help="Bootstrap a profile from a new manual PDF using LLM",
    )
    bootstrap_parser.add_argument(
        "--pdf", required=True, help="Path to the PDF manual file"
    )
    bootstrap_parser.add_argument(
        "--output", required=True, help="Output path for the generated profile YAML"
    )

    # validate subcommand
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a profile against its PDF",
    )
    validate_parser.add_argument(
        "--profile", required=True, help="Path to the YAML profile file"
    )
    validate_parser.add_argument(
        "--pdf", required=True, help="Path to the PDF manual file"
    )

    # qa subcommand
    qa_parser = subparsers.add_parser(
        "qa",
        help="Run QA checks on an indexed manual",
    )
    qa_parser.add_argument(
        "--manual-id", required=True, help="Manual ID to run QA checks on"
    )
    qa_parser.add_argument(
        "--test-set", required=True, help="Path to the test set JSON file"
    )

    return parser


def cmd_process(args: argparse.Namespace) -> int:
    """Process a single manual: extract, parse, chunk, embed, index.

    Returns exit code (0 = success).
    """
    profile_path = Path(args.profile)
    pdf_path = Path(args.pdf)

    if not profile_path.exists():
        print(f"Error: Profile file not found: {profile_path}", file=sys.stderr)
        return 1

    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        return 1

    # Imports inside function to avoid circular imports
    from .profile import load_profile, validate_profile
    from . import extract_pages
    from .ocr_cleanup import clean_page
    from .structural_parser import detect_boundaries, build_manifest
    from .chunk_assembly import assemble_chunks

    # 1. Load and validate profile
    profile = load_profile(profile_path)
    errors = validate_profile(profile)
    if errors:
        for err in errors:
            print(f"  Profile error: {err}", file=sys.stderr)
        return 1
    print(f"Profile loaded: {profile.manual_id}")

    # 2. Extract pages from PDF
    pages = extract_pages(pdf_path)
    print(f"Extracted {len(pages)} pages from PDF")

    # 3. OCR cleanup per page
    cleaned = [clean_page(p, i, profile) for i, p in enumerate(pages)]
    cleaned_texts = [c.cleaned_text for c in cleaned]
    print(f"Cleaned {len(cleaned)} pages")

    # 4. Detect boundaries and build manifest
    boundaries = detect_boundaries(cleaned_texts, profile)
    manifest = build_manifest(boundaries, profile)
    print(f"Detected {len(boundaries)} boundaries, {len(manifest.entries)} manifest entries")

    # 5. Assemble chunks
    chunks = assemble_chunks(cleaned_texts, manifest, profile)
    print(f"Assembled {len(chunks)} chunks")

    # 6. Indexing requires running Qdrant + Ollama — skip with message
    print("\nSkipping embedding/indexing (requires running Qdrant and Ollama).")
    print("To index, start Qdrant and Ollama, then use the Python API directly.")

    return 0


def cmd_bootstrap_profile(args: argparse.Namespace) -> int:
    """Bootstrap a profile from a new manual PDF using LLM.

    Returns exit code (0 = success).
    """
    pdf_path = Path(args.pdf)

    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        return 1

    print("Error: bootstrap-profile is not yet implemented.", file=sys.stderr)
    return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a profile against its PDF.

    Returns exit code (0 = success).
    """
    profile_path = Path(args.profile)
    pdf_path = Path(args.pdf)

    if not profile_path.exists():
        print(f"Error: Profile file not found: {profile_path}", file=sys.stderr)
        return 1

    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        return 1

    # Imports inside function to avoid circular imports
    from .profile import load_profile, validate_profile
    from . import extract_pages
    from .ocr_cleanup import clean_page
    from .structural_parser import detect_boundaries, build_manifest, validate_boundaries
    from .chunk_assembly import assemble_chunks
    from .qa import run_validation_suite

    # 1. Load and validate profile
    profile = load_profile(profile_path)
    errors = validate_profile(profile)
    if errors:
        for err in errors:
            print(f"  Profile error: {err}", file=sys.stderr)
        return 1
    print(f"Profile loaded: {profile.manual_id}")

    # 2. Extract pages from PDF
    pages = extract_pages(pdf_path)
    print(f"Extracted {len(pages)} pages from PDF")

    # 3. OCR cleanup per page
    cleaned = [clean_page(p, i, profile) for i, p in enumerate(pages)]
    cleaned_texts = [c.cleaned_text for c in cleaned]
    print(f"Cleaned {len(cleaned)} pages")

    # 4. Detect boundaries and build manifest
    boundaries = detect_boundaries(cleaned_texts, profile)
    manifest = build_manifest(boundaries, profile)
    print(f"Detected {len(boundaries)} boundaries, {len(manifest.entries)} manifest entries")

    # 5. Validate boundaries against profile known_ids
    boundary_warnings = validate_boundaries(boundaries, profile)
    if boundary_warnings:
        print(f"\nBoundary warnings ({len(boundary_warnings)}):")
        for w in boundary_warnings:
            print(f"  {w}")

    # 6. Assemble chunks
    chunks = assemble_chunks(cleaned_texts, manifest, profile)
    print(f"Assembled {len(chunks)} chunks")

    # 7. Run QA validation suite
    report = run_validation_suite(chunks, profile)
    print(f"\nValidation: {len(report.checks_run)} checks run on {report.total_chunks} chunks")
    print(f"  Errors:   {report.error_count}")
    print(f"  Warnings: {report.warning_count}")
    print(f"  Passed:   {report.passed}")

    if report.issues:
        print("\nIssues:")
        for issue in report.issues:
            print(f"  [{issue.severity}] {issue.check}: {issue.message} (chunk: {issue.chunk_id})")

    return 0 if report.passed else 1


def cmd_qa(args: argparse.Namespace) -> int:
    """Run QA checks on an indexed manual.

    Returns exit code (0 = success).
    """
    print("Error: QA checks require a running Qdrant instance and indexed data.", file=sys.stderr)
    print("Index a manual first with 'pipeline process', then run QA.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = build_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # Return the exit code from argparse (0 for --help, 2 for errors)
        return e.code if isinstance(e.code, int) else 1

    command_handlers = {
        "process": cmd_process,
        "bootstrap-profile": cmd_bootstrap_profile,
        "validate": cmd_validate,
        "qa": cmd_qa,
    }

    handler = command_handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
