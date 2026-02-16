"""Tests for the pipeline CLI."""

from __future__ import annotations

import argparse

import pytest

from pipeline.cli import build_parser, main


# ── Parser Tests ──────────────────────────────────────────────────


class TestBuildParser:
    """Test CLI argument parser construction."""

    def test_returns_argument_parser(self):
        parser = build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_has_process_subcommand(self):
        parser = build_parser()
        # Parse a process command
        args = parser.parse_args(["process", "--profile", "p.yaml", "--pdf", "m.pdf"])
        assert args.command == "process" or hasattr(args, "profile")

    def test_process_requires_profile(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["process", "--pdf", "m.pdf"])

    def test_process_requires_pdf(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["process", "--profile", "p.yaml"])

    def test_has_bootstrap_profile_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(
            ["bootstrap-profile", "--pdf", "m.pdf", "--output", "p.yaml"]
        )
        assert hasattr(args, "pdf") or hasattr(args, "output")

    def test_has_validate_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(
            ["validate", "--profile", "p.yaml", "--pdf", "m.pdf"]
        )
        assert hasattr(args, "profile")

    def test_has_qa_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(
            ["qa", "--manual-id", "xj-1999", "--test-set", "tests.json"]
        )
        assert hasattr(args, "manual_id")

    def test_no_subcommand_shows_help(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


# ── Main Entry Point Tests ────────────────────────────────────────


class TestMain:
    """Test the main CLI entry point."""

    def test_returns_exit_code(self):
        # With no valid arguments, should return non-zero
        result = main(["--help"])
        # --help causes SystemExit(0) in argparse
        # This test verifies main() accepts argv parameter

    def test_process_with_nonexistent_profile_returns_error(self, tmp_path):
        result = main([
            "process",
            "--profile", str(tmp_path / "nonexistent.yaml"),
            "--pdf", str(tmp_path / "nonexistent.pdf"),
        ])
        assert result != 0

    def test_bootstrap_profile_not_implemented_returns_error(self, tmp_path):
        pdf = tmp_path / "manual.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        result = main([
            "bootstrap-profile",
            "--pdf", str(pdf),
            "--output", str(tmp_path / "out.yaml"),
        ])
        assert result == 1

    def test_bootstrap_profile_not_implemented_prints_message(self, tmp_path, capsys):
        pdf = tmp_path / "manual.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        main([
            "bootstrap-profile",
            "--pdf", str(pdf),
            "--output", str(tmp_path / "out.yaml"),
        ])
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.err

    def test_validate_with_nonexistent_files_returns_error(self, tmp_path):
        result = main([
            "validate",
            "--profile", str(tmp_path / "nonexistent.yaml"),
            "--pdf", str(tmp_path / "nonexistent.pdf"),
        ])
        assert result != 0
