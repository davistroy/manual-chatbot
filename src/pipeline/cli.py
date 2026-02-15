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

    # TODO: Implement full pipeline processing
    return 0


def cmd_bootstrap_profile(args: argparse.Namespace) -> int:
    """Bootstrap a profile from a new manual PDF using LLM.

    Returns exit code (0 = success).
    """
    pdf_path = Path(args.pdf)

    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}", file=sys.stderr)
        return 1

    # TODO: Implement bootstrap profile logic
    return 0


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

    # TODO: Implement validation logic
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    """Run QA checks on an indexed manual.

    Returns exit code (0 = success).
    """
    # TODO: Implement QA check logic
    return 0


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
