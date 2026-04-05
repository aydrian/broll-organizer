"""
Vector embedding generation using Fireworks AI or Ollama embedding models.

Converts video descriptions and tags into 768-dimensional vectors
for semantic similarity search via sqlite-vec.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .clients import get_fireworks_client, get_ollama_client
from .config import (
    AI_PROVIDER,
    EMBEDDING_DIMENSIONS,
    FIREWORKS_EMBEDDING_MODEL,
    OLLAMA_EMBEDDING_MODEL,
)

if TYPE_CHECKING:
    pass


def generate_embedding(text: str) -> list[float]:
    """
    Generate a vector embedding for the given text.

    Uses nomic-embed-text via Fireworks or Ollama to produce a 768-dimensional vector.
    """
    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty text")

    if AI_PROVIDER == "fireworks":
        return _generate_embedding_fireworks(text.strip())
    else:
        return _generate_embedding_ollama(text.strip())


def _generate_embedding_fireworks(text: str) -> list[float]:
    """Generate embedding using Fireworks AI."""
    fireworks_client = get_fireworks_client()
    if fireworks_client is None:
        raise RuntimeError("Fireworks client not available")

    response = fireworks_client.embeddings.create(
        model=FIREWORKS_EMBEDDING_MODEL,
        input=[text],
    )

    embeddings = response.data
    if not embeddings or not embeddings[0].embedding:
        raise RuntimeError(f"Fireworks returned empty embeddings for model {FIREWORKS_EMBEDDING_MODEL}")

    return embeddings[0].embedding


def _generate_embedding_ollama(text: str) -> list[float]:
    """Generate embedding using local Ollama."""
    ollama = get_ollama_client()
    if ollama is None:
        raise RuntimeError("Ollama not available")

    response = ollama.embed(
        model=OLLAMA_EMBEDDING_MODEL,
        input=text,
    )

    embeddings = response.get("embeddings")
    if not embeddings or not embeddings[0]:
        raise RuntimeError(f"Ollama returned empty embeddings for model {OLLAMA_EMBEDDING_MODEL}")

    return embeddings[0]


def build_searchable_text(video: dict) -> str:
    """
    Combine all descriptive fields from a video record into a single
    string optimized for embedding generation.
    """
    parts: list[str] = []

    desc = video.get("scene_description")
    if desc:
        parts.append(desc)

    tags = video.get("tags")
    if isinstance(tags, list):
        parts.append(" ".join(tags))
    elif isinstance(tags, str):
        parts.append(tags)

    mood = video.get("mood")
    if mood and mood != "unknown":
        parts.append(f"mood: {mood}")

    movement = video.get("camera_movement")
    if movement and movement != "unknown":
        parts.append(f"camera: {movement}")

    time_of_day = video.get("time_of_day")
    if time_of_day and time_of_day != "unknown":
        parts.append(f"time: {time_of_day}")

    location = video.get("gps_location_name")
    if location:
        parts.append(f"location: {location}")

    # Infer location from folder path if not in gps_location_name
    file_path = video.get("file_path", "")
    if not location and file_path:
        # Extract folder names like "01 Kusatsu Onsen" from paths
        import re

        match = re.search(r"/\d+\s+([^/]+)/", file_path)
        if match:
            parts.append(f"location: {match.group(1)}")

    device = video.get("source_device")
    if device == "dji_pocket3":
        parts.append("gimbal camera")
    elif device == "iphone":
        parts.append("smartphone camera")

    return " | ".join(parts)
