"""
Shared AI client initialization for b-roll organizer.

Provides factory functions for creating Fireworks AI and Ollama clients,
eliminating duplicate initialization code across analyzer, embeddings, and chat modules.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

from .config import AI_PROVIDER

if TYPE_CHECKING:
    pass


@lru_cache(maxsize=1)
def get_fireworks_client():
    """
    Get or create a cached Fireworks client instance.
    
    Uses lru_cache to ensure only one client is created per process,
    reducing connection overhead and API initialization time.
    
    Returns:
        Fireworks client instance or None if import fails.
    """
    try:
        from fireworks.client import Fireworks

        return Fireworks(
            api_key=os.environ.get("FIREWORKS_API_KEY"),
            base_url="https://api.fireworks.ai/inference/v1"
        )
    except ImportError:
        return None


@lru_cache(maxsize=1)
def get_ollama_client():
    """
    Get or create a cached Ollama module.
    
    Uses lru_cache to ensure consistent access to the Ollama module.
    
    Returns:
        Ollama module or None if import fails.
    """
    try:
        import ollama
        return ollama
    except ImportError:
        return None


def get_ai_client(provider: str | None = None):
    """
    Get the appropriate AI client based on provider setting.
    
    Args:
        provider: The AI provider to use ("fireworks" or "ollama").
                Defaults to the AI_PROVIDER config value.
    
    Returns:
        Tuple of (client, provider_name) where client is the initialized
        client instance or None if unavailable.
    
    Raises:
        RuntimeError: If the requested provider is not available.
    """
    provider = provider or AI_PROVIDER
    
    if provider == "fireworks":
        client = get_fireworks_client()
        if client is None:
            raise RuntimeError(
                "Fireworks client not available. "
                "Install with: pip install fireworks-client"
            )
        return client, "fireworks"
    else:
        client = get_ollama_client()
        if client is None:
            raise RuntimeError(
                "Ollama not available. "
                "Install with: pip install ollama or ensure Ollama is running."
            )
        return client, "ollama"


def check_ai_availability() -> dict[str, bool]:
    """
    Check which AI providers are available.
    
    Returns:
        Dict with availability status for each provider.
    """
    return {
        "fireworks": get_fireworks_client() is not None,
        "ollama": get_ollama_client() is not None,
    }
