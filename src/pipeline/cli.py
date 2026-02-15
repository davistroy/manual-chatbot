"""Pipeline CLI — command-line interface for the chunking pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all subcommands."""
    raise NotImplementedError


def cmd_process(args: argparse.Namespace) -> int:
    """Process a single manual: extract, parse, chunk, embed, index.

    Returns exit code (0 = success).
    """
    raise NotImplementedError


def cmd_bootstrap_profile(args: argparse.Namespace) -> int:
    """Bootstrap a profile from a new manual PDF using LLM.

    Returns exit code (0 = success).
    """
    raise NotImplementedError


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a profile against its PDF.

    Returns exit code (0 = success).
    """
    raise NotImplementedError


def cmd_qa(args: argparse.Namespace) -> int:
    """Run QA checks on an indexed manual.

    Returns exit code (0 = success).
    """
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    raise NotImplementedError
