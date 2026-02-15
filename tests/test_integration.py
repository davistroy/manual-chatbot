"""Integration tests — full pipeline from PDF to chunks against real manuals."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import extract_pages
from pipeline.profile import load_profile, validate_profile
from pipeline.ocr_cleanup import clean_page, assess_quality
from pipeline.structural_parser import detect_boundaries, build_manifest, validate_boundaries
from pipeline.chunk_assembly import assemble_chunks, count_tokens

# ── Paths ─────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FIXTURES_DIR = Path(__file__).parent / "fixtures"

XJ_PDF = DATA_DIR / "99 XJ Service Manual.pdf"
CJ_PDF = DATA_DIR / "53-71 CJ5 Service Manual.pdf"
TM9_PDF = DATA_DIR / "TM9-8014.pdf"

XJ_PROFILE = FIXTURES_DIR / "xj_1999_profile.yaml"
CJ_PROFILE = FIXTURES_DIR / "cj_universal_profile.yaml"
TM9_PROFILE = FIXTURES_DIR / "tm9_8014_profile.yaml"

_skip_xj = pytest.mark.skipif(not XJ_PDF.exists(), reason=f"PDF not found: {XJ_PDF}")
_skip_cj = pytest.mark.skipif(not CJ_PDF.exists(), reason=f"PDF not found: {CJ_PDF}")
_skip_tm9 = pytest.mark.skipif(not TM9_PDF.exists(), reason=f"PDF not found: {TM9_PDF}")


# ── PDF Extraction ────────────────────────────────────────────────


@pytest.mark.integration
class TestPDFExtraction:
    """Verify extract_pages works against real PDFs."""

    @_skip_xj
    def test_xj_extracts_pages(self):
        pages = extract_pages(XJ_PDF)
        assert len(pages) > 0
        assert all(isinstance(p, str) for p in pages)

    @_skip_cj
    def test_cj_extracts_pages(self):
        pages = extract_pages(CJ_PDF)
        assert len(pages) > 0

    @_skip_tm9
    def test_tm9_extracts_pages(self):
        pages = extract_pages(TM9_PDF)
        assert len(pages) > 0

    def test_missing_pdf_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            extract_pages(tmp_path / "nonexistent.pdf")


# ── XJ Full Pipeline ─────────────────────────────────────────────


@pytest.mark.integration
@_skip_xj
class TestXJFullPipeline:
    """Full pipeline test for 1999 Cherokee XJ manual."""

    @pytest.fixture(scope="class")
    def profile(self):
        return load_profile(XJ_PROFILE)

    @pytest.fixture(scope="class")
    def raw_pages(self):
        return extract_pages(XJ_PDF)

    @pytest.fixture(scope="class")
    def cleaned_pages(self, raw_pages, profile):
        return [clean_page(p, i, profile) for i, p in enumerate(raw_pages)]

    @pytest.fixture(scope="class")
    def cleaned_texts(self, cleaned_pages):
        return [c.cleaned_text for c in cleaned_pages]

    @pytest.fixture(scope="class")
    def boundaries(self, cleaned_texts, profile):
        return detect_boundaries(cleaned_texts, profile)

    @pytest.fixture(scope="class")
    def manifest(self, boundaries, profile):
        return build_manifest(boundaries, profile)

    @pytest.fixture(scope="class")
    def chunks(self, cleaned_texts, manifest, profile):
        return assemble_chunks(cleaned_texts, manifest, profile)

    def test_profile_validates_clean(self, profile):
        errors = validate_profile(profile)
        assert errors == [], f"Profile validation errors: {errors}"

    def test_extraction_produces_pages(self, raw_pages):
        assert len(raw_pages) > 100, f"Expected >100 pages, got {len(raw_pages)}"

    def test_ocr_quality_acceptable(self, cleaned_pages):
        report = assess_quality(cleaned_pages)
        assert report.dictionary_match_rate > 0.5, (
            f"Dictionary match rate too low: {report.dictionary_match_rate:.2%}"
        )

    def test_boundaries_detected(self, boundaries):
        assert len(boundaries) > 10, f"Expected >10 boundaries, got {len(boundaries)}"
        level_1 = [b for b in boundaries if b.level == 1]
        assert len(level_1) > 0, "No level-1 boundaries detected"

    def test_manifest_has_entries(self, manifest):
        assert len(manifest.entries) > 0
        assert manifest.manual_id == "xj-1999"

    def test_manifest_chunk_ids_have_manual_prefix(self, manifest):
        for entry in manifest.entries:
            assert entry.chunk_id.startswith("xj-1999"), (
                f"Chunk ID missing manual prefix: {entry.chunk_id}"
            )

    def test_chunks_produced(self, chunks):
        assert len(chunks) > 20, f"Expected >20 chunks, got {len(chunks)}"

    def test_chunks_have_text(self, chunks):
        for chunk in chunks:
            assert chunk.text.strip(), f"Empty text in chunk {chunk.chunk_id}"

    def test_chunks_have_metadata(self, chunks):
        for chunk in chunks:
            assert isinstance(chunk.metadata, dict)
            assert chunk.manual_id == "xj-1999"

    def test_chunk_sizes_reasonable(self, chunks):
        for chunk in chunks:
            tokens = count_tokens(chunk.text)
            assert tokens < 5000, (
                f"Chunk {chunk.chunk_id} too large: {tokens} tokens"
            )


# ── CJ Full Pipeline ─────────────────────────────────────────────


@pytest.mark.integration
@_skip_cj
class TestCJFullPipeline:
    """Full pipeline test for CJ Universal manual."""

    @pytest.fixture(scope="class")
    def profile(self):
        return load_profile(CJ_PROFILE)

    @pytest.fixture(scope="class")
    def raw_pages(self):
        return extract_pages(CJ_PDF)

    @pytest.fixture(scope="class")
    def cleaned_texts(self, raw_pages, profile):
        cleaned = [clean_page(p, i, profile) for i, p in enumerate(raw_pages)]
        return [c.cleaned_text for c in cleaned]

    @pytest.fixture(scope="class")
    def chunks(self, cleaned_texts, profile):
        boundaries = detect_boundaries(cleaned_texts, profile)
        manifest = build_manifest(boundaries, profile)
        return assemble_chunks(cleaned_texts, manifest, profile)

    def test_profile_valid(self, profile):
        assert validate_profile(profile) == []

    def test_pages_extracted(self, raw_pages):
        assert len(raw_pages) > 0

    def test_chunks_produced(self, chunks):
        assert len(chunks) > 0

    def test_manual_id_correct(self, chunks):
        for chunk in chunks:
            assert chunk.manual_id == "cj-universal-53-71"


# ── TM9 Full Pipeline ────────────────────────────────────────────


@pytest.mark.integration
@_skip_tm9
class TestTM9FullPipeline:
    """Full pipeline test for TM 9-8014 military manual."""

    @pytest.fixture(scope="class")
    def profile(self):
        return load_profile(TM9_PROFILE)

    @pytest.fixture(scope="class")
    def raw_pages(self):
        return extract_pages(TM9_PDF)

    @pytest.fixture(scope="class")
    def cleaned_texts(self, raw_pages, profile):
        cleaned = [clean_page(p, i, profile) for i, p in enumerate(raw_pages)]
        return [c.cleaned_text for c in cleaned]

    @pytest.fixture(scope="class")
    def chunks(self, cleaned_texts, profile):
        boundaries = detect_boundaries(cleaned_texts, profile)
        manifest = build_manifest(boundaries, profile)
        return assemble_chunks(cleaned_texts, manifest, profile)

    def test_profile_valid(self, profile):
        assert validate_profile(profile) == []

    def test_pages_extracted(self, raw_pages):
        assert len(raw_pages) > 0

    def test_chunks_produced(self, chunks):
        assert len(chunks) > 0

    def test_manual_id_correct(self, chunks):
        for chunk in chunks:
            assert chunk.manual_id == "tm9-8014-m38a1"


# ── CLI Smoke Tests ───────────────────────────────────────────────


@pytest.mark.integration
@_skip_xj
class TestCLIProcess:
    """Smoke-test the CLI subcommands against a real PDF."""

    def test_process_runs(self):
        from pipeline.cli import main

        exit_code = main([
            "process",
            "--profile", str(XJ_PROFILE),
            "--pdf", str(XJ_PDF),
        ])
        assert exit_code == 0

    def test_validate_runs(self):
        from pipeline.cli import main

        exit_code = main([
            "validate",
            "--profile", str(XJ_PROFILE),
            "--pdf", str(XJ_PDF),
        ])
        # May return 1 due to validation warnings/errors on real data — that's OK.
        # Just verify it doesn't crash (exit code is 0 or 1).
        assert exit_code in (0, 1)

    def test_process_bad_profile_fails(self, tmp_path):
        from pipeline.cli import main

        exit_code = main([
            "process",
            "--profile", str(tmp_path / "nope.yaml"),
            "--pdf", str(XJ_PDF),
        ])
        assert exit_code == 1
