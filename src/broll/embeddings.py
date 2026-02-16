# src/broll/embeddings.py
'''
Vector embedding generation using Ollama&#x27;s embedding models.

Converts video descriptions and tags into 768-dimensional vectors
for semantic similarity search via sqlite-vec.
'''
from __future__ import annotations

import ollama

from .config import EMBEDDING_MODEL


def generate_embedding(text: str) -> list[float]:
    '''
    Generate a vector embedding for the given text.

    Uses nomic-embed-text via Ollama to produce a 768-dimensional vector.
    '''
    if not text or not text.strip():
        raise ValueError('Cannot generate embedding for empty text')

    response = ollama.embed(
        model=EMBEDDING_MODEL,
        input=text.strip(),
    )

    embeddings = response.get('embeddings')
    if not embeddings or not embeddings[0]:
        raise RuntimeError(f'Ollama returned empty embeddings for model {EMBEDDING_MODEL}')

    return embeddings[0]


def build_searchable_text(video: dict) -> str:
    '''
    Combine all descriptive fields from a video record into a single
    string optimized for embedding generation.
    '''
    parts: list[str] = []

    desc = video.get('scene_description')
    if desc:
        parts.append(desc)

    tags = video.get('tags')
    if isinstance(tags, list):
        parts.append(' '.join(tags))
    elif isinstance(tags, str):
        parts.append(tags)

    mood = video.get('mood')
    if mood and mood != 'unknown':
        parts.append(f'mood: {mood}')

    movement = video.get('camera_movement')
    if movement and movement != 'unknown':
        parts.append(f'camera: {movement}')

    time_of_day = video.get('time_of_day')
    if time_of_day and time_of_day != 'unknown':
        parts.append(f'time: {time_of_day}')

    location = video.get('gps_location_name')
    if location:
        parts.append(f'location: {location}')

    device = video.get('source_device')
    if device == 'dji_pocket3':
        parts.append('gimbal camera')
    elif device == 'iphone':
        parts.append('smartphone camera')

    return ' | '.join(parts)
