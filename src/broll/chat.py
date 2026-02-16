# src/broll/chat.py
"""
Chat interface for the b-roll catalog.
Uses search results as context for the chat LLM.
"""
from __future__ import annotations

import json

import ollama

from .config import CHAT_MODEL
from .search import hybrid_search
from .db import Database


SYSTEM_PROMPT = (
    "You are a helpful assistant for a video editor's b-roll footage catalog. "
    "You have access to information about video clips stored in the catalog. "
    "When answering questions, reference specific clips by their filename so the editor can find them. "
    "If asked to find or suggest clips, describe the relevant ones from the context provided. "
    "If the context doesn't contain relevant clips, say so honestly. "
    "Be concise, specific, and practical."
)


def chat_with_catalog(
    message: str,
    db: Database,
    history: list[dict] | None = None,
) -> dict:
    """
    Chat with the catalog using an LLM with search-augmented context.

    Args:
        message: The user's message.
        db: Database instance.
        history: List of previous messages [{role, content}, ...].

    Returns:
        Dict with 'response' (str) and 'videos' (list of referenced video dicts).
    """
    # Search the catalog for relevant clips
    context_videos = hybrid_search(message, db, limit=5)

    # Build context string from search results
    context = _build_context(context_videos)

    # Assemble the conversation
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history (keep last 10 exchanges to stay within context window)
    if history:
        messages.extend(history[-20:])

    # Add the current message with catalog context
    if context:
        user_content = (
            f"Here are relevant clips from the catalog:\n\n"
            f"{context}\n\n"
            f"User question: {message}"
        )
    else:
        user_content = message

    messages.append({"role": "user", "content": user_content})

    try:
        response = ollama.chat(
            model=CHAT_MODEL,
            messages=messages,
            options={
                "temperature": 0.7,
                "num_predict": 2048,
            },
        )
        reply = response["message"]["content"]
    except Exception as e:
        reply = f"Sorry, I encountered an error talking to the LLM: {e}"

    return {
        "response": reply,
        "videos": _simplify_videos(context_videos),
    }


def _build_context(videos: list[dict]) -> str:
    """Build a text context block from search results for the LLM."""
    if not videos:
        return ""

    parts = []
    for v in videos:
        desc = v.get("scene_description", "")
        if not desc or desc.startswith("ERROR"):
            continue

        line = f"- {v.get('file_name', '?')}"

        duration = v.get("duration_seconds")
        if duration:
            mins = int(duration) // 60
            secs = int(duration) % 60
            line += f" ({mins}:{secs:02d})"

        line += f": {desc}"

        tags = v.get("tags", "")
        if tags:
            if isinstance(tags, str):
                try:
                    parsed = json.loads(tags)
                    if isinstance(parsed, list):
                        tags = ", ".join(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(tags, list):
                tags = ", ".join(tags)
            line += f" [Tags: {tags}]"

        location = v.get("gps_location_name")
        if location:
            line += f" [Location: {location}]"

        mood = v.get("mood")
        if mood and mood != "unknown":
            line += f" [Mood: {mood}]"

        parts.append(line)

    return "\n".join(parts)


def _simplify_videos(videos: list[dict]) -> list[dict]:
    """Return a simplified version of video dicts for the chat response."""
    simplified = []
    for v in videos:
        desc = v.get("scene_description", "")
        if not desc or desc.startswith("ERROR"):
            continue
        simplified.append({
            "id": v.get("id"),
            "file_name": v.get("file_name"),
            "file_path": v.get("file_path"),
            "scene_description": desc[:200],
            "file_hash": v.get("file_hash"),
            "duration_seconds": v.get("duration_seconds"),
            "gps_location_name": v.get("gps_location_name"),
        })
    return simplified
