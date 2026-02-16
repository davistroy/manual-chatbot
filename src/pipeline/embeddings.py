"""Embedding composition and vector store indexing."""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any

import requests

from .chunk_assembly import Chunk


@dataclass
class EmbeddingInput:
    """Prepared input for embedding generation."""
    chunk_id: str
    text: str


def get_first_n_words(text: str, n: int = 150) -> str:
    """Extract the first N words from text."""
    if not text:
        return ""
    words = text.split()
    return " ".join(words[:n])


def compose_embedding_input(chunk: Chunk) -> EmbeddingInput:
    """Build the embedding input from a chunk.

    Format: {hierarchical_header}\\n\\n{first_150_words_of_body}

    The hierarchical header is read from chunk.metadata["hierarchical_header"].
    The body is the full chunk.text, truncated to the first 150 words.
    If the metadata key is missing, falls back to body text only.
    """
    header = chunk.metadata.get("hierarchical_header", "").strip()
    truncated_body = get_first_n_words(chunk.text, 150)

    if header:
        embedding_text = f"{header}\n\n{truncated_body}"
    else:
        embedding_text = truncated_body

    return EmbeddingInput(
        chunk_id=chunk.chunk_id,
        text=embedding_text,
    )


def generate_embedding(
    text: str, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"
) -> list[float]:
    """Generate embedding vector via Ollama.

    Args:
        text: Text to embed.
        model: Ollama model name.
        base_url: Base URL for the Ollama API.

    Returns:
        Embedding vector as list of floats.

    Raises:
        RuntimeError: If embedding generation fails after 3 attempts.
    """
    url = f"{base_url}/api/embeddings"
    payload = {"model": model, "prompt": text}
    max_attempts = 3
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code >= 500:
                last_error = RuntimeError(f"Server error: HTTP {response.status_code}")
                if attempt < max_attempts - 1:
                    time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            data = response.json()
            return data["embedding"]
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Embedding generation failed after {max_attempts} attempts: {last_error}")


def create_qdrant_collection(
    client: Any,
    collection_name: str,
    vector_size: int = 768,
) -> None:
    """Create a Qdrant collection with the correct schema and metadata indexes."""
    from qdrant_client.models import Distance, VectorParams

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
        ),
    )


def index_chunks(
    chunks: list[Chunk],
    profile: Any,
    client: Any,
    collection_name: str = "service_manuals",
    base_url: str = "http://localhost:11434",
) -> int:
    """Index a list of chunks into Qdrant.

    Returns the number of successfully indexed chunks.
    """
    from qdrant_client.models import PointStruct

    points = []
    for i, chunk in enumerate(chunks):
        # Compose embedding input
        emb_input = compose_embedding_input(chunk)
        # Generate embedding vector
        vector = generate_embedding(emb_input.text, base_url=base_url)

        # Build payload from chunk metadata plus chunk_id and manual_id
        payload = {
            "chunk_id": chunk.chunk_id,
            "manual_id": chunk.manual_id,
            "text": chunk.text,
        }
        payload.update(chunk.metadata)

        point = PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
            vector=vector,
            payload=payload,
        )
        points.append(point)

    if points:
        client.upsert(
            collection_name=collection_name,
            points=points,
        )

    return len(points)


def build_sqlite_index(chunks: list[Chunk], db_path: str) -> None:
    """Build the secondary SQLite metadata index for cross-manual lookup."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create lookup tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS procedure_lookup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL,
            manual_id TEXT NOT NULL,
            procedure_name TEXT,
            level1_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_model_lookup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL,
            manual_id TEXT NOT NULL,
            vehicle_model TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS figure_lookup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL,
            manual_id TEXT NOT NULL,
            figure_reference TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cross_ref_lookup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_id TEXT NOT NULL,
            manual_id TEXT NOT NULL,
            cross_reference TEXT NOT NULL
        )
    """)

    for chunk in chunks:
        metadata = chunk.metadata

        # procedure_lookup
        procedure_name = metadata.get("procedure_name", "")
        level1_id = metadata.get("level1_id", "")
        cursor.execute(
            "INSERT INTO procedure_lookup (chunk_id, manual_id, procedure_name, level1_id) VALUES (?, ?, ?, ?)",
            (chunk.chunk_id, chunk.manual_id, procedure_name, level1_id),
        )

        # vehicle_model_lookup
        vehicle_models = metadata.get("vehicle_models", [])
        for model in vehicle_models:
            cursor.execute(
                "INSERT INTO vehicle_model_lookup (chunk_id, manual_id, vehicle_model) VALUES (?, ?, ?)",
                (chunk.chunk_id, chunk.manual_id, model),
            )

        # figure_lookup
        figure_refs = metadata.get("figure_references", [])
        for fig_ref in figure_refs:
            cursor.execute(
                "INSERT INTO figure_lookup (chunk_id, manual_id, figure_reference) VALUES (?, ?, ?)",
                (chunk.chunk_id, chunk.manual_id, fig_ref),
            )

        # cross_ref_lookup
        cross_refs = metadata.get("cross_references", [])
        for xref in cross_refs:
            cursor.execute(
                "INSERT INTO cross_ref_lookup (chunk_id, manual_id, cross_reference) VALUES (?, ?, ?)",
                (chunk.chunk_id, chunk.manual_id, xref),
            )

    conn.commit()
    conn.close()
