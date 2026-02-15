"""Embedding composition and vector store indexing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .chunk_assembly import Chunk


@dataclass
class EmbeddingInput:
    """Prepared input for embedding generation."""
    chunk_id: str
    text: str


def compose_embedding_input(chunk: Chunk) -> EmbeddingInput:
    """Build the embedding input from a chunk.

    Format: {hierarchical_header}\\n\\n{first_150_words_of_body}
    """
    raise NotImplementedError


def get_first_n_words(text: str, n: int = 150) -> str:
    """Extract the first N words from text."""
    raise NotImplementedError


def generate_embedding(text: str, model: str = "nomic-embed-text") -> list[float]:
    """Generate embedding vector via Ollama.

    Args:
        text: Text to embed.
        model: Ollama model name.

    Returns:
        Embedding vector as list of floats.
    """
    raise NotImplementedError


def create_qdrant_collection(
    collection_name: str, vector_size: int = 768
) -> None:
    """Create a Qdrant collection with the correct schema and metadata indexes."""
    raise NotImplementedError


def index_chunks(
    chunks: list[Chunk], collection_name: str = "service_manuals"
) -> int:
    """Index a list of chunks into Qdrant.

    Returns the number of successfully indexed chunks.
    """
    raise NotImplementedError


def build_sqlite_index(chunks: list[Chunk], db_path: str) -> None:
    """Build the secondary SQLite metadata index for cross-manual lookup."""
    raise NotImplementedError
