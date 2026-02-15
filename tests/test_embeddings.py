"""Tests for embedding composition and vector store indexing."""

from __future__ import annotations

import pytest

from pipeline.chunk_assembly import Chunk
from pipeline.embeddings import (
    EmbeddingInput,
    build_sqlite_index,
    compose_embedding_input,
    get_first_n_words,
)


# ── Helper Function Tests ─────────────────────────────────────────


class TestGetFirstNWords:
    """Test word extraction for embedding input."""

    def test_exact_n_words(self):
        text = "one two three four five"
        result = get_first_n_words(text, n=3)
        assert result == "one two three"

    def test_fewer_than_n_words(self):
        text = "just two"
        result = get_first_n_words(text, n=150)
        assert result == "just two"

    def test_default_150_words(self):
        text = " ".join(f"word{i}" for i in range(200))
        result = get_first_n_words(text)
        words = result.split()
        assert len(words) == 150

    def test_empty_string(self):
        result = get_first_n_words("", n=150)
        assert result == ""

    def test_multiline_text(self):
        text = "Line one with words.\nLine two with more words."
        result = get_first_n_words(text, n=5)
        words = result.split()
        assert len(words) == 5


# ── Embedding Input Composition Tests ─────────────────────────────


class TestComposeEmbeddingInput:
    """Test embedding input construction from chunks."""

    def test_returns_embedding_input(self):
        chunk = Chunk(
            chunk_id="xj-1999::0::SP::JSP",
            manual_id="xj-1999",
            text=(
                "1999 Jeep Cherokee XJ | Lubrication and Maintenance | "
                "Service Procedures | Jump Starting Procedure\n\n"
                "WARNING: REVIEW COMPLETE JUMP STARTING PROCEDURE BEFORE PROCEEDING."
            ),
            metadata={
                "hierarchy_path": [
                    "Lubrication and Maintenance",
                    "Service Procedures",
                    "Jump Starting Procedure",
                ],
                "manual_title": "1999 Jeep Cherokee (XJ) Factory Service Manual",
            },
        )
        result = compose_embedding_input(chunk)
        assert isinstance(result, EmbeddingInput)

    def test_embedding_input_has_chunk_id(self):
        chunk = Chunk(
            chunk_id="xj-1999::0::SP::JSP",
            manual_id="xj-1999",
            text="Header\n\nBody text here.",
            metadata={},
        )
        result = compose_embedding_input(chunk)
        assert result.chunk_id == "xj-1999::0::SP::JSP"

    def test_embedding_input_contains_header(self):
        chunk = Chunk(
            chunk_id="xj-1999::0::SP::JSP",
            manual_id="xj-1999",
            text=(
                "1999 Jeep Cherokee XJ | Lubrication | Jump Starting\n\n"
                "Detailed body text follows here with instructions."
            ),
            metadata={},
        )
        result = compose_embedding_input(chunk)
        assert "1999 Jeep Cherokee" in result.text

    def test_embedding_input_truncated_to_150_words(self):
        body = " ".join(f"word{i}" for i in range(300))
        chunk = Chunk(
            chunk_id="test::1",
            manual_id="test",
            text=f"Header Line\n\n{body}",
            metadata={},
        )
        result = compose_embedding_input(chunk)
        # Header + at most 150 words of body
        total_words = len(result.text.split())
        assert total_words <= 200  # Header words + 150 body words


# ── SQLite Index Tests ────────────────────────────────────────────


class TestBuildSQLiteIndex:
    """Test secondary SQLite metadata index construction."""

    def test_creates_database_file(self, tmp_path):
        db_path = str(tmp_path / "test_index.db")
        chunks = [
            Chunk(
                chunk_id="xj-1999::0::SP::JSP",
                manual_id="xj-1999",
                text="Test chunk",
                metadata={
                    "procedure_name": "Jump Starting Procedure",
                    "level1_id": "0",
                    "figure_references": ["Fig. 1"],
                    "cross_references": ["Group 8A"],
                    "vehicle_models": ["Cherokee XJ"],
                },
            ),
        ]
        build_sqlite_index(chunks, db_path)
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Verify tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert len(tables) > 0

    def test_stores_procedure_lookup(self, tmp_path):
        db_path = str(tmp_path / "test_index.db")
        chunks = [
            Chunk(
                chunk_id="xj-1999::0::SP::JSP",
                manual_id="xj-1999",
                text="Test chunk",
                metadata={
                    "procedure_name": "Jump Starting Procedure",
                    "level1_id": "0",
                    "figure_references": [],
                    "cross_references": [],
                    "vehicle_models": ["Cherokee XJ"],
                },
            ),
        ]
        build_sqlite_index(chunks, db_path)
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT chunk_id FROM procedure_lookup WHERE procedure_name = ?",
            ("Jump Starting Procedure",),
        )
        results = cursor.fetchall()
        conn.close()
        assert len(results) == 1
        assert results[0][0] == "xj-1999::0::SP::JSP"

    def test_stores_vehicle_model_lookup(self, tmp_path):
        db_path = str(tmp_path / "test_index.db")
        chunks = [
            Chunk(
                chunk_id="cj::B::B4",
                manual_id="cj-universal-53-71",
                text="CJ-5 specific content",
                metadata={
                    "procedure_name": "Engine Lubrication",
                    "level1_id": "B",
                    "figure_references": [],
                    "cross_references": [],
                    "vehicle_models": ["CJ-5"],
                },
            ),
        ]
        build_sqlite_index(chunks, db_path)
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT chunk_id FROM vehicle_model_lookup WHERE vehicle_model = ?",
            ("CJ-5",),
        )
        results = cursor.fetchall()
        conn.close()
        assert len(results) >= 1
