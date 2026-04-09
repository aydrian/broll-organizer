"""
Vector embedding generation using Fireworks AI or Ollama embedding models.

Converts video descriptions and tags into 768-dimensional vectors
for semantic similarity search via sqlite-vec.

Policy: Ollama (local) is the default to preserve Fireworks AI quota
for vision analysis tasks. Fireworks can be enabled via EMBEDDING_PROVIDER env.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .clients import get_fireworks_client, get_ollama_client
from .config import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_PROVIDER,
    FIREWORKS_EMBEDDING_MODEL,
    OLLAMA_EMBEDDING_MODEL,
)

if TYPE_CHECKING:
    pass


def generate_embedding(text: str) -> list[float]:
    """
    Generate a vector embedding for the given text.

    Uses nomic-embed-text via Ollama (default) or Fireworks (if configured)
    to produce a 768-dimensional vector.

    Policy: Local Ollama is default to preserve Fireworks quota for vision tasks.
    """
    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty text")

    if EMBEDDING_PROVIDER == "fireworks":
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


def build_searchable_text(video: dict, include_transcript: bool = True) -> str:
    """
    Combine all descriptive fields from a video record into a single
    string optimized for embedding generation.

    Args:
        video: Video record dict with metadata and analysis
        include_transcript: Whether to include transcript text (default: True)

    Returns:
        Combined searchable text string
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

    # Include transcript if available (NEW for transcription feature)
    if include_transcript:
        transcript = video.get("transcript")
        if transcript:
            # Truncate to first 500 chars to keep embeddings manageable
            truncated = transcript[:500].strip()
            if truncated:
                parts.append(f"transcript: {truncated}")

    return " | ".join(parts)


# ---- Batch embedding generation ----

async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts in a batch.

    Uses Ollama by default (local) or Fireworks if EMBEDDING_PROVIDER=fireworks.
    Processes in batches to avoid overwhelming the API.

    Args:
        texts: List of text strings to embed

    Returns:
        List of embedding vectors (same order as input texts)
    """
    import asyncio

    # Filter empty texts
    valid_texts = [(i, t) for i, t in enumerate(texts) if t and t.strip()]

    if not valid_texts:
        return [[] for _ in texts]

    # Use Ollama by default, Fireworks if explicitly set
    if EMBEDDING_PROVIDER == "fireworks":
        embeddings_dict = await _embeddings_batch_fireworks_async([t for _, t in valid_texts])
    else:
        embeddings_dict = await _embeddings_batch_ollama_async([t for _, t in valid_texts])

    # Reconstruct results in original order
    results = [[] for _ in texts]
    for original_idx, text in valid_texts:
        embedding = embeddings_dict.get(text)
        if embedding:
            results[original_idx] = embedding

    return results


async def _embeddings_batch_ollama_async(texts: list[str]) -> dict[str, list[float]]:
    """
    Generate embeddings via Ollama (async, batched).

    Ollama processes locally - we can batch efficiently.
    """
    import asyncio

    ollama = get_ollama_client()
    if ollama is None:
        raise RuntimeError("Ollama not available")

    results = {}

    # Ollama nomic-embed-text is fast locally - batch by running concurrently
    # with semaphore to avoid overwhelming the local model
    semaphore = asyncio.Semaphore(10)

    async def embed_one(text: str) -> tuple[str, list[float]]:
        async with semaphore:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: ollama.embed(model=OLLAMA_EMBEDDING_MODEL, input=text)
            )
            embeddings = response.get("embeddings")
            if embeddings and embeddings[0]:
                return text, embeddings[0]
            return text, []

    tasks = [embed_one(t) for t in texts]
    completed = await asyncio.gather(*tasks)

    for text, embedding in completed:
        results[text] = embedding

    return results


async def _embeddings_batch_fireworks_async(texts: list[str]) -> dict[str, list[float]]:
    """
    Generate embeddings via Fireworks AI (async, batched).

    Fireworks supports up to 100 texts per request, but we use smaller
    batches for reliability.
    """
    import asyncio

    from .clients import get_async_http_client

    client = get_async_http_client()
    api_key = None

    # Get API key from environment (same as Fireworks client)
    import os
    api_key = os.environ.get("FIREWORKS_API_KEY")
    if not api_key:
        raise RuntimeError("FIREWORKS_API_KEY not set")

    results = {}
    batch_size = 20  # Conservative batch size for reliability

    async def embed_batch(batch: list[str]) -> dict[str, list[float]]:
        response = await client.post(
            "https://api.fireworks.ai/inference/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": FIREWORKS_EMBEDDING_MODEL,
                "input": batch,
            },
        )
        response.raise_for_status()
        data = response.json()

        batch_results = {}
        for item in data.get("data", []):
            idx = item.get("index", 0)
            embedding = item.get("embedding", [])
            if idx < len(batch):
                batch_results[batch[idx]] = embedding
        return batch_results

    # Process in batches
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            batch_results = await embed_batch(batch)
            results.update(batch_results)
        except Exception as e:
            # Log error but continue with other batches
            print(f"Batch embedding error (indices {i}-{i + len(batch)}): {e}")
            # Fallback to empty embeddings for this batch
            for text in batch:
                results[text] = []

    return results
