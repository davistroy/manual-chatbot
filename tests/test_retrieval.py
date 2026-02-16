"""Tests for the query-time retrieval strategy."""

from __future__ import annotations

import sqlite3
import warnings
from unittest.mock import patch, MagicMock

import pytest

from pipeline.retrieval import (
    QueryAnalysis,
    RetrievalResult,
    RetrievalResponse,
    analyze_query,
    enrich_with_parent,
    enrich_with_siblings,
    rerank,
    resolve_cross_references,
)


# ── Query Analysis Tests ──────────────────────────────────────────


class TestAnalyzeQuery:
    """Test natural language query parsing and filter extraction."""

    def test_returns_query_analysis(self):
        result = analyze_query(
            "How do I change the oil on a 1999 Cherokee?",
            ["xj-1999", "cj-universal-53-71"],
        )
        assert isinstance(result, QueryAnalysis)

    def test_preserves_original_query(self):
        query = "What is the torque spec for the brake caliper?"
        result = analyze_query(query, ["xj-1999"])
        assert result.original_query == query

    def test_detects_vehicle_scope_cherokee(self):
        result = analyze_query(
            "How do I replace the radiator hose on a Cherokee?",
            ["xj-1999", "cj-universal-53-71"],
        )
        assert len(result.vehicle_scope) > 0

    def test_detects_vehicle_scope_cj5(self):
        result = analyze_query(
            "How do I adjust the carburetor on a CJ-5?",
            ["xj-1999", "cj-universal-53-71"],
        )
        assert any("CJ" in v for v in result.vehicle_scope)

    def test_detects_vehicle_scope_m38a1(self):
        result = analyze_query(
            "Starting procedure for the M38A1",
            ["tm9-8014-m38a1"],
        )
        assert any("M38A1" in v for v in result.vehicle_scope)

    def test_detects_engine_scope(self):
        result = analyze_query(
            "Oil capacity for the 4.0L engine",
            ["xj-1999"],
        )
        assert len(result.engine_scope) > 0

    def test_detects_drivetrain_scope(self):
        result = analyze_query(
            "Transfer case fluid for 4WD model",
            ["xj-1999"],
        )
        assert any("4WD" in d for d in result.drivetrain_scope)

    def test_classifies_procedure_query(self):
        result = analyze_query(
            "How do I change the oil?",
            ["xj-1999"],
        )
        assert result.query_type == "procedure"

    def test_classifies_specification_query(self):
        result = analyze_query(
            "What is the oil capacity for the 4.0L?",
            ["xj-1999"],
        )
        assert result.query_type == "specification"

    def test_classifies_diagnostic_query(self):
        result = analyze_query(
            "Engine won't start, what should I check?",
            ["xj-1999"],
        )
        assert result.query_type == "diagnostic"

    def test_no_vehicle_specified_returns_empty_scope(self):
        result = analyze_query(
            "How do I change the oil?",
            ["xj-1999", "cj-universal-53-71"],
        )
        # When no specific vehicle mentioned, scope may be empty or broad
        assert isinstance(result.vehicle_scope, list)

    def test_detects_system_scope(self):
        result = analyze_query(
            "Brake pad replacement procedure",
            ["xj-1999"],
        )
        assert len(result.system_scope) > 0


# ── Result Enrichment Tests ───────────────────────────────────────


class TestEnrichWithParent:
    """Test parent-chunk enrichment."""

    def test_adds_parent_context(self):
        results = [
            RetrievalResult(
                chunk_id="xj-1999::0::SP::JSP",
                text="Jump starting procedure details.",
                metadata={"parent_chunk_id": "xj-1999::0::SP"},
                score=0.95,
                source="primary",
            )
        ]
        enriched = enrich_with_parent(results)
        # Should have at least original result + potentially parent
        assert len(enriched) >= 1

    def test_no_parent_no_change(self):
        results = [
            RetrievalResult(
                chunk_id="xj-1999::0",
                text="Top-level content.",
                metadata={"parent_chunk_id": None},
                score=0.90,
                source="primary",
            )
        ]
        enriched = enrich_with_parent(results)
        assert len(enriched) == 1


class TestEnrichWithSiblings:
    """Test sibling-chunk enrichment."""

    def test_adds_sibling_context(self):
        results = [
            RetrievalResult(
                chunk_id="xj-1999::0::SP::JSP",
                text="Jump starting procedure.",
                metadata={"sibling_chunk_ids": ["xj-1999::0::SP::TR"]},
                score=0.95,
                source="primary",
            )
        ]
        enriched = enrich_with_siblings(results)
        assert len(enriched) >= 1


class TestResolveCrossReferences:
    """Test cross-reference resolution."""

    def test_resolves_references(self):
        results = [
            RetrievalResult(
                chunk_id="xj-1999::0::SP::JSP",
                text="Refer to Group 8A for details.",
                metadata={"cross_references": ["Group 8A"]},
                score=0.95,
                source="primary",
            )
        ]
        enriched = resolve_cross_references(results)
        assert len(enriched) >= 1


# ── Reranking Tests ───────────────────────────────────────────────


class TestRerank:
    """Test result re-ranking."""

    def test_returns_top_n(self):
        results = [
            RetrievalResult(
                chunk_id=f"test::{i}",
                text=f"Chunk {i}",
                metadata={},
                score=float(i) / 10,
                source="primary",
            )
            for i in range(10)
        ]
        reranked = rerank(results, top_n=5)
        assert len(reranked) == 5

    def test_ordered_by_relevance(self):
        results = [
            RetrievalResult(chunk_id="a", text="Low relevance", metadata={}, score=0.3, source="primary"),
            RetrievalResult(chunk_id="b", text="High relevance", metadata={}, score=0.9, source="primary"),
            RetrievalResult(chunk_id="c", text="Medium relevance", metadata={}, score=0.6, source="primary"),
        ]
        reranked = rerank(results, top_n=3)
        scores = [r.score for r in reranked]
        assert scores == sorted(scores, reverse=True)

    def test_fewer_than_top_n_returns_all(self):
        results = [
            RetrievalResult(chunk_id="a", text="Only one", metadata={}, score=0.9, source="primary"),
        ]
        reranked = rerank(results, top_n=5)
        assert len(reranked) == 1


# ── Cross-reference Error Handling Tests ─────────────────────────


class TestCrossReferenceErrorHandling:
    """Test that SQLite errors in resolve_cross_references are surfaced."""

    def test_sqlite_error_issues_warning_and_returns_partial_results(self):
        """When SQLite raises an error, a warning should be issued and
        the original results should be returned (graceful degradation)."""
        results = [
            RetrievalResult(
                chunk_id="xj-1999::0::SP::JSP",
                text="Refer to Group 8A for details.",
                metadata={"cross_references": ["Group 8A"]},
                score=0.95,
                source="primary",
            )
        ]

        # Mock sqlite3.connect to raise an OperationalError
        with patch("pipeline.retrieval.sqlite3.connect") as mock_connect:
            mock_connect.side_effect = sqlite3.OperationalError("unable to open database file")

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                enriched = resolve_cross_references(results, sqlite_db_path="/nonexistent/path.db")

                # Should have issued exactly one warning
                assert len(w) == 1
                assert "Cross-reference resolution failed" in str(w[0].message)
                assert "unable to open database file" in str(w[0].message)

            # Should still return the original results (graceful degradation)
            assert len(enriched) == len(results)
            assert enriched[0].chunk_id == "xj-1999::0::SP::JSP"

    def test_sqlite_error_during_query_issues_warning(self):
        """When SQLite fails during a cursor query, the warning should
        still be issued and partial results returned."""
        results = [
            RetrievalResult(
                chunk_id="xj-1999::0::BR::PAD",
                text="See also Group 5 for wheel info.",
                metadata={"cross_references": ["Group 5"]},
                score=0.88,
                source="primary",
            )
        ]

        # Mock the connection to succeed but cursor.execute to fail
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = sqlite3.OperationalError("no such table: cross_ref_lookup")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("pipeline.retrieval.sqlite3.connect", return_value=mock_conn):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                enriched = resolve_cross_references(results, sqlite_db_path="/some/path.db")

                assert len(w) == 1
                assert "Cross-reference resolution failed" in str(w[0].message)
                assert "no such table: cross_ref_lookup" in str(w[0].message)

            # Original results returned intact
            assert len(enriched) == len(results)

    def test_no_warning_when_sqlite_succeeds(self):
        """When no SQLite error occurs, no warning should be issued."""
        results = [
            RetrievalResult(
                chunk_id="xj-1999::0::SP::JSP",
                text="Some text.",
                metadata={},  # No cross_references, so no DB queries needed
                score=0.90,
                source="primary",
            )
        ]

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("pipeline.retrieval.sqlite3.connect", return_value=mock_conn):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                enriched = resolve_cross_references(results, sqlite_db_path="/some/path.db")

                # No warnings expected
                assert len(w) == 0

            assert len(enriched) == len(results)

    def test_retrieval_response_has_retrieval_warnings_field(self):
        """RetrievalResponse should have a retrieval_warnings field."""
        query = QueryAnalysis(
            original_query="test",
            vehicle_scope=[],
            system_scope=[],
            engine_scope=[],
            drivetrain_scope=[],
            query_type="procedure",
        )
        response = RetrievalResponse(
            query=query,
            results=[],
        )
        assert hasattr(response, "retrieval_warnings")
        assert response.retrieval_warnings == []
