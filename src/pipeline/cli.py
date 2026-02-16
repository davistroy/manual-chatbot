"""Pipeline CLI — command-line interface for the chunking pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Smart Chunking Pipeline for Vehicle Service Manual RAG",
    )

    # Global logging verbosity flags
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging output",
    )
    verbosity.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress all output except warnings and errors",
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
    process_parser.add_argument(
        "--output-dir",
        required=False,
        default=None,
        help="Directory to write {manual_id}_chunks.jsonl output",
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
        logger.error("Profile file not found: %s", profile_path)
        return 1

    if not pdf_path.exists():
        logger.error("PDF file not found: %s", pdf_path)
        return 1

    # Imports inside function to avoid circular imports
    from .profile import load_profile, validate_profile
    from . import extract_pages
    from .ocr_cleanup import clean_page
    from .structural_parser import detect_boundaries, build_manifest
    from .chunk_assembly import assemble_chunks, save_chunks

    # 1. Load and validate profile
    profile = load_profile(profile_path)
    errors = validate_profile(profile)
    if errors:
        for err in errors:
            logger.error("Profile error: %s", err)
        return 1
    logger.info("Profile loaded: %s", profile.manual_id)

    # 2. Extract pages from PDF
    pages = extract_pages(pdf_path)
    logger.info("Extracted %d pages from PDF", len(pages))

    # 3. OCR cleanup per page
    cleaned = [clean_page(p, i, profile) for i, p in enumerate(pages)]
    cleaned_texts = [c.cleaned_text for c in cleaned]
    logger.info("Cleaned %d pages", len(cleaned))

    # 4. Detect boundaries and build manifest
    boundaries = detect_boundaries(cleaned_texts, profile)
    manifest = build_manifest(boundaries, profile)
    logger.info("Detected %d boundaries, %d manifest entries", len(boundaries), len(manifest.entries))

    # 5. Assemble chunks
    chunks = assemble_chunks(cleaned_texts, manifest, profile)
    logger.info("Assembled %d chunks", len(chunks))

    # 5b. Write chunks to JSONL if --output-dir was provided
    if args.output_dir is not None:
        output_dir = Path(args.output_dir)
        output_path = output_dir / f"{profile.manual_id}_chunks.jsonl"
        save_chunks(chunks, output_path)
        logger.info("Wrote %d chunks to %s", len(chunks), output_path)

    # 6. Indexing requires running Qdrant + Ollama — skip with message
    logger.info("Skipping embedding/indexing (requires running Qdrant and Ollama).")
    logger.info("To index, start Qdrant and Ollama, then use the Python API directly.")

    return 0


def cmd_bootstrap_profile(args: argparse.Namespace) -> int:
    """Bootstrap a profile from a new manual PDF using LLM.

    Returns exit code (0 = success).
    """
    pdf_path = Path(args.pdf)

    if not pdf_path.exists():
        logger.error("PDF file not found: %s", pdf_path)
        return 1

    logger.error("bootstrap-profile is not yet implemented.")
    return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a profile against its PDF.

    Returns exit code (0 = success).
    """
    profile_path = Path(args.profile)
    pdf_path = Path(args.pdf)

    if not profile_path.exists():
        logger.error("Profile file not found: %s", profile_path)
        return 1

    if not pdf_path.exists():
        logger.error("PDF file not found: %s", pdf_path)
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
            logger.error("Profile error: %s", err)
        return 1
    logger.info("Profile loaded: %s", profile.manual_id)

    # 2. Extract pages from PDF
    pages = extract_pages(pdf_path)
    logger.info("Extracted %d pages from PDF", len(pages))

    # 3. OCR cleanup per page
    cleaned = [clean_page(p, i, profile) for i, p in enumerate(pages)]
    cleaned_texts = [c.cleaned_text for c in cleaned]
    logger.info("Cleaned %d pages", len(cleaned))

    # 4. Detect boundaries and build manifest
    boundaries = detect_boundaries(cleaned_texts, profile)
    manifest = build_manifest(boundaries, profile)
    logger.info("Detected %d boundaries, %d manifest entries", len(boundaries), len(manifest.entries))

    # 5. Validate boundaries against profile known_ids
    boundary_warnings = validate_boundaries(boundaries, profile)
    if boundary_warnings:
        logger.warning("Boundary warnings (%d):", len(boundary_warnings))
        for w in boundary_warnings:
            logger.warning("  %s", w)

    # 6. Assemble chunks
    chunks = assemble_chunks(cleaned_texts, manifest, profile)
    logger.info("Assembled %d chunks", len(chunks))

    # 7. Run QA validation suite
    report = run_validation_suite(chunks, profile)
    logger.info("Validation: %d checks run on %d chunks", len(report.checks_run), report.total_chunks)
    logger.info("  Errors:   %d", report.error_count)
    logger.info("  Warnings: %d", report.warning_count)
    logger.info("  Passed:   %s", report.passed)

    if report.issues:
        logger.info("Issues:")
        for issue in report.issues:
            logger.info("  [%s] %s: %s (chunk: %s)", issue.severity, issue.check, issue.message, issue.chunk_id)

    return 0 if report.passed else 1


def cmd_qa(args: argparse.Namespace) -> int:
    """Run QA checks on an indexed manual.

    Returns exit code (0 = success).
    """
    logger.error("QA checks require a running Qdrant instance and indexed data.")
    logger.error("Index a manual first with 'pipeline process', then run QA.")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = build_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # Return the exit code from argparse (0 for --help, 2 for errors)
        return e.code if isinstance(e.code, int) else 1

    # Configure root logger based on verbosity flags
    if getattr(args, "verbose", False):
        log_level = logging.DEBUG
    elif getattr(args, "quiet", False):
        log_level = logging.WARNING
    else:
        log_level = logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
    )

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
        logger.error("%s", e)
        return 1
