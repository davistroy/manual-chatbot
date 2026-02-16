"""Tests for embedding composition and vector store indexing."""

from __future__ import annotations

import uuid

import pytest

from pipeline.chunk_assembly import Chunk
from unittest.mock import MagicMock, patch

import requests

from pipeline.embeddings import (
    EmbeddingInput,
    build_sqlite_index,
    compose_embedding_input,
    generate_embedding,
    get_first_n_words,
    index_chunks,
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
            text="WARNING: REVIEW COMPLETE JUMP STARTING PROCEDURE BEFORE PROCEEDING.",
            metadata={
                "hierarchical_header": (
                    "1999 Jeep Cherokee XJ | Lubrication and Maintenance | "
                    "Service Procedures | Jump Starting Procedure"
                ),
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
            text="Body text here.",
            metadata={"hierarchical_header": "Header"},
        )
        result = compose_embedding_input(chunk)
        assert result.chunk_id == "xj-1999::0::SP::JSP"

    def test_embedding_input_contains_header_from_metadata(self):
        """Header is read from metadata, not parsed from chunk text."""
        chunk = Chunk(
            chunk_id="xj-1999::0::SP::JSP",
            manual_id="xj-1999",
            text="Detailed body text follows here with instructions.",
            metadata={
                "hierarchical_header": "1999 Jeep Cherokee XJ | Lubrication | Jump Starting",
            },
        )
        result = compose_embedding_input(chunk)
        assert result.text.startswith("1999 Jeep Cherokee XJ | Lubrication | Jump Starting")
        assert "\n\n" in result.text
        assert "Detailed body text" in result.text

    def test_embedding_input_truncated_to_150_words(self):
        body = " ".join(f"word{i}" for i in range(300))
        chunk = Chunk(
            chunk_id="test::1",
            manual_id="test",
            text=body,
            metadata={"hierarchical_header": "Header Line"},
        )
        result = compose_embedding_input(chunk)
        # Header + separator + at most 150 words of body
        parts = result.text.split("\n\n", 1)
        assert len(parts) == 2
        body_words = parts[1].split()
        assert len(body_words) == 150

    def test_missing_hierarchical_header_falls_back_to_text_only(self):
        """When hierarchical_header is absent, output is just truncated body."""
        chunk = Chunk(
            chunk_id="test::2",
            manual_id="test",
            text="Some body text without any header metadata.",
            metadata={},
        )
        result = compose_embedding_input(chunk)
        assert result.text == "Some body text without any header metadata."
        assert "\n\n" not in result.text

    def test_empty_hierarchical_header_falls_back_to_text_only(self):
        """When hierarchical_header is empty string, output is just truncated body."""
        chunk = Chunk(
            chunk_id="test::3",
            manual_id="test",
            text="Body content here.",
            metadata={"hierarchical_header": ""},
        )
        result = compose_embedding_input(chunk)
        assert result.text == "Body content here."
        assert "\n\n" not in result.text

    def test_whitespace_only_header_falls_back_to_text_only(self):
        """Whitespace-only header is treated as missing."""
        chunk = Chunk(
            chunk_id="test::4",
            manual_id="test",
            text="Body content here.",
            metadata={"hierarchical_header": "   "},
        )
        result = compose_embedding_input(chunk)
        assert result.text == "Body content here."

    def test_text_with_double_newline_not_split(self):
        """Body text containing \\n\\n is NOT split -- the whole text is the body."""
        chunk = Chunk(
            chunk_id="test::5",
            manual_id="test",
            text="Paragraph one.\n\nParagraph two.",
            metadata={"hierarchical_header": "My Header"},
        )
        result = compose_embedding_input(chunk)
        assert result.text.startswith("My Header\n\n")
        # Body should include words from both paragraphs
        assert "Paragraph" in result.text
        assert "one." in result.text
        assert "two." in result.text


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


# ── Embedding Generation Retry Tests ─────────────────────────────


class TestGenerateEmbeddingRetry:
    """Test timeout and retry behavior for generate_embedding."""

    @patch("pipeline.embeddings.time.sleep")
    @patch("pipeline.embeddings.requests.post")
    def test_retries_on_connection_error_then_succeeds(self, mock_post, mock_sleep):
        """Retry should recover when first attempt fails with ConnectionError."""
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        success_response.raise_for_status = MagicMock()

        mock_post.side_effect = [
            requests.exceptions.ConnectionError("Connection refused"),
            success_response,
        ]

        result = generate_embedding("test text")
        assert result == [0.1, 0.2, 0.3]
        assert mock_post.call_count == 2
        # Verify sleep was called once with 2^0 = 1 second
        mock_sleep.assert_called_once_with(1)

    @patch("pipeline.embeddings.time.sleep")
    @patch("pipeline.embeddings.requests.post")
    def test_raises_runtime_error_after_3_failures(self, mock_post, mock_sleep):
        """Should raise RuntimeError after exhausting all 3 retry attempts."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(RuntimeError, match="Embedding generation failed after 3 attempts"):
            generate_embedding("test text")

        assert mock_post.call_count == 3
        # Verify sleep was called twice (between attempts 0-1 and 1-2)
        assert mock_sleep.call_count == 2

    @patch("pipeline.embeddings.time.sleep")
    @patch("pipeline.embeddings.requests.post")
    def test_retries_on_timeout_then_succeeds(self, mock_post, mock_sleep):
        """Retry should recover when first attempt times out."""
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"embedding": [0.4, 0.5]}
        success_response.raise_for_status = MagicMock()

        mock_post.side_effect = [
            requests.exceptions.Timeout("Request timed out"),
            success_response,
        ]

        result = generate_embedding("test text")
        assert result == [0.4, 0.5]
        assert mock_post.call_count == 2

    @patch("pipeline.embeddings.time.sleep")
    @patch("pipeline.embeddings.requests.post")
    def test_retries_on_5xx_then_succeeds(self, mock_post, mock_sleep):
        """Retry should recover when server returns 5xx error."""
        error_response = MagicMock()
        error_response.status_code = 503

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"embedding": [0.6, 0.7]}
        success_response.raise_for_status = MagicMock()

        mock_post.side_effect = [error_response, success_response]

        result = generate_embedding("test text")
        assert result == [0.6, 0.7]
        assert mock_post.call_count == 2

    @patch("pipeline.embeddings.time.sleep")
    @patch("pipeline.embeddings.requests.post")
    def test_passes_timeout_to_requests(self, mock_post, mock_sleep):
        """Verify that requests.post is called with timeout=30."""
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"embedding": [0.1]}
        success_response.raise_for_status = MagicMock()
        mock_post.return_value = success_response

        generate_embedding("test text")

        _, kwargs = mock_post.call_args
        assert kwargs["timeout"] == 30


# ── Deterministic Point ID Tests ─────────────────────────────────


class TestDeterministicPointIds:
    """Test that index_chunks uses deterministic UUID5 point IDs derived from chunk_id."""

    def _make_chunk(self, chunk_id: str, text: str = "Test chunk text") -> Chunk:
        return Chunk(
            chunk_id=chunk_id,
            manual_id="test-manual",
            text=text,
            metadata={},
        )

    @patch("pipeline.embeddings.generate_embedding")
    def test_point_id_is_uuid5_of_chunk_id(self, mock_embed):
        """Point ID should be UUID5(NAMESPACE_URL, chunk_id) as a string."""
        mock_embed.return_value = [0.1, 0.2, 0.3]
        mock_client = MagicMock()

        chunk = self._make_chunk("xj-1999::0::SP::JSP")
        index_chunks([chunk], profile=None, client=mock_client)

        expected_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "xj-1999::0::SP::JSP"))
        upserted_points = mock_client.upsert.call_args[1]["points"]
        assert upserted_points[0].id == expected_id

    @patch("pipeline.embeddings.generate_embedding")
    def test_same_chunk_id_produces_same_point_id(self, mock_embed):
        """The same chunk_id must always produce the same point ID (deterministic)."""
        mock_embed.return_value = [0.1, 0.2, 0.3]

        chunk_id = "cj::B::B4"
        mock_client_1 = MagicMock()
        mock_client_2 = MagicMock()

        index_chunks([self._make_chunk(chunk_id)], profile=None, client=mock_client_1)
        index_chunks([self._make_chunk(chunk_id)], profile=None, client=mock_client_2)

        id_1 = mock_client_1.upsert.call_args[1]["points"][0].id
        id_2 = mock_client_2.upsert.call_args[1]["points"][0].id
        assert id_1 == id_2

    @patch("pipeline.embeddings.generate_embedding")
    def test_different_chunk_ids_produce_different_point_ids(self, mock_embed):
        """Different chunk_ids must produce different point IDs."""
        mock_embed.return_value = [0.1, 0.2, 0.3]
        mock_client = MagicMock()

        chunks = [
            self._make_chunk("xj-1999::0::SP::JSP"),
            self._make_chunk("cj::B::B4"),
        ]
        index_chunks(chunks, profile=None, client=mock_client)

        upserted_points = mock_client.upsert.call_args[1]["points"]
        assert upserted_points[0].id != upserted_points[1].id

    @patch("pipeline.embeddings.generate_embedding")
    def test_point_id_is_not_sequential_integer(self, mock_embed):
        """Point IDs should no longer be sequential integers."""
        mock_embed.return_value = [0.1, 0.2, 0.3]
        mock_client = MagicMock()

        chunks = [self._make_chunk("test::1"), self._make_chunk("test::2")]
        index_chunks(chunks, profile=None, client=mock_client)

        upserted_points = mock_client.upsert.call_args[1]["points"]
        for point in upserted_points:
            # Should be a UUID string, not an integer
            assert isinstance(point.id, str)
            # Verify it parses as a valid UUID
            uuid.UUID(point.id)
