"""Tests for the pipeline CLI."""

from __future__ import annotations

import argparse
import json

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

    def test_process_accepts_output_dir(self):
        parser = build_parser()
        args = parser.parse_args([
            "process", "--profile", "p.yaml", "--pdf", "m.pdf",
            "--output-dir", "/tmp/output",
        ])
        assert args.output_dir == "/tmp/output"

    def test_process_output_dir_defaults_to_none(self):
        parser = build_parser()
        args = parser.parse_args([
            "process", "--profile", "p.yaml", "--pdf", "m.pdf",
        ])
        assert args.output_dir is None

    def test_verbose_flag_accepted(self):
        parser = build_parser()
        args = parser.parse_args(["--verbose", "process", "--profile", "p.yaml", "--pdf", "m.pdf"])
        assert args.verbose is True
        assert args.quiet is False

    def test_quiet_flag_accepted(self):
        parser = build_parser()
        args = parser.parse_args(["--quiet", "process", "--profile", "p.yaml", "--pdf", "m.pdf"])
        assert args.quiet is True
        assert args.verbose is False

    def test_verbose_and_quiet_mutually_exclusive(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--verbose", "--quiet", "process", "--profile", "p.yaml", "--pdf", "m.pdf"])

    def test_short_verbose_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-v", "process", "--profile", "p.yaml", "--pdf", "m.pdf"])
        assert args.verbose is True

    def test_short_quiet_flag(self):
        parser = build_parser()
        args = parser.parse_args(["-q", "process", "--profile", "p.yaml", "--pdf", "m.pdf"])
        assert args.quiet is True

    def test_has_validate_chunks_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(
            ["validate-chunks", "--chunks", "chunks.jsonl", "--profile", "p.yaml"]
        )
        assert args.command == "validate-chunks"
        assert args.chunks == "chunks.jsonl"
        assert args.profile == "p.yaml"

    def test_validate_chunks_requires_chunks_flag(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["validate-chunks", "--profile", "p.yaml"])

    def test_validate_chunks_requires_profile_flag(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["validate-chunks", "--chunks", "chunks.jsonl"])

    def test_validate_chunks_requires_both_flags(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["validate-chunks"])

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

    def test_bootstrap_profile_not_implemented_prints_message(self, tmp_path, caplog):
        import logging

        pdf = tmp_path / "manual.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        with caplog.at_level(logging.ERROR):
            main([
                "bootstrap-profile",
                "--pdf", str(pdf),
                "--output", str(tmp_path / "out.yaml"),
            ])
        assert "not yet implemented" in caplog.text

    def test_validate_with_nonexistent_files_returns_error(self, tmp_path):
        result = main([
            "validate",
            "--profile", str(tmp_path / "nonexistent.yaml"),
            "--pdf", str(tmp_path / "nonexistent.pdf"),
        ])
        assert result != 0

    def test_validate_chunks_with_nonexistent_chunks_returns_error(self, tmp_path):
        result = main([
            "validate-chunks",
            "--chunks", str(tmp_path / "nonexistent.jsonl"),
            "--profile", str(tmp_path / "nonexistent.yaml"),
        ])
        assert result != 0

    def test_validate_chunks_with_nonexistent_profile_returns_error(self, tmp_path):
        # Create a valid chunks file but use a nonexistent profile
        chunks_file = tmp_path / "chunks.jsonl"
        chunk = {
            "chunk_id": "xj-1999::0::SP",
            "manual_id": "xj-1999",
            "text": "Some procedure text here with enough words to be valid.",
            "metadata": {
                "manual_id": "xj-1999",
                "level1_id": "0",
                "content_type": "procedure",
            },
        }
        chunks_file.write_text(json.dumps(chunk) + "\n", encoding="utf-8")

        result = main([
            "validate-chunks",
            "--chunks", str(chunks_file),
            "--profile", str(tmp_path / "nonexistent.yaml"),
        ])
        assert result != 0

    def test_validate_chunks_runs_qa_on_valid_input(self, tmp_path, xj_profile_path):
        # Create a minimal valid chunks JSONL file
        chunks_file = tmp_path / "chunks.jsonl"
        # Build a chunk that passes all validations: has required metadata,
        # reasonable size, and level1_id matching profile known_ids
        chunk_text = " ".join(["word"] * 250)  # ~250 tokens, above min threshold
        chunk = {
            "chunk_id": "xj-1999::0::SP",
            "manual_id": "xj-1999",
            "text": chunk_text,
            "metadata": {
                "manual_id": "xj-1999",
                "level1_id": "0",
                "content_type": "procedure",
            },
        }
        chunks_file.write_text(json.dumps(chunk) + "\n", encoding="utf-8")

        result = main([
            "validate-chunks",
            "--chunks", str(chunks_file),
            "--profile", str(xj_profile_path),
        ])
        # Should succeed (0) since the chunk has all required metadata and valid size
        assert result == 0

    def test_validate_chunks_detects_missing_metadata(self, tmp_path, xj_profile_path):
        # Create a chunk missing required metadata fields
        chunks_file = tmp_path / "chunks.jsonl"
        chunk_text = " ".join(["word"] * 250)
        chunk = {
            "chunk_id": "xj-1999::0::SP",
            "manual_id": "xj-1999",
            "text": chunk_text,
            "metadata": {},  # Missing manual_id, level1_id, content_type
        }
        chunks_file.write_text(json.dumps(chunk) + "\n", encoding="utf-8")

        result = main([
            "validate-chunks",
            "--chunks", str(chunks_file),
            "--profile", str(xj_profile_path),
        ])
        # Should fail (1) since metadata_completeness check finds errors
        assert result == 1

    def test_validate_chunks_logs_results(self, tmp_path, xj_profile_path, caplog):
        import logging

        chunks_file = tmp_path / "chunks.jsonl"
        chunk_text = " ".join(["word"] * 250)
        chunk = {
            "chunk_id": "xj-1999::0::SP",
            "manual_id": "xj-1999",
            "text": chunk_text,
            "metadata": {
                "manual_id": "xj-1999",
                "level1_id": "0",
                "content_type": "procedure",
            },
        }
        chunks_file.write_text(json.dumps(chunk) + "\n", encoding="utf-8")

        with caplog.at_level(logging.INFO):
            main([
                "validate-chunks",
                "--chunks", str(chunks_file),
                "--profile", str(xj_profile_path),
            ])
        assert "Validation:" in caplog.text
        assert "checks run" in caplog.text
