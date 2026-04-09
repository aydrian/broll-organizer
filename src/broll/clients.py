"""
Shared AI client initialization for b-roll organizer.

Provides factory functions for creating Fireworks AI and Ollama clients,
eliminating duplicate initialization code across analyzer, embeddings, and chat modules.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

from .config import AI_PROVIDER, VISION_PROVIDER, EMBEDDING_PROVIDER

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


# ---- Async HTTP Client for Connection Pooling ----

@lru_cache(maxsize=1)
def get_async_http_client() -> "httpx.AsyncClient":
    """
    Get or create a cached async HTTP client with connection pooling.

    Uses httpx.AsyncClient with configured limits for efficient
    connection reuse across concurrent API calls.

    Returns:
        httpx.AsyncClient instance with connection pooling.
    """
    import httpx

    limits = httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
        keepalive_expiry=60.0
    )
    return httpx.AsyncClient(
        limits=limits,
        timeout=httpx.Timeout(60.0, connect=10.0),
        http2=True
    )


async def close_async_http_client():
    """Close the async HTTP client (for cleanup on shutdown)."""
    client = get_async_http_client()
    await client.aclose()
    # Clear the cache so a new client will be created if needed
    get_async_http_client.cache_clear()


def get_provider_for_task(task: str) -> str:
    """
    Get the appropriate provider for a specific task.

    Args:
        task: The task type ("vision", "embedding", "chat")

    Returns:
        Provider name ("fireworks" or "ollama")
    """
    if task == "vision":
        return VISION_PROVIDER
    elif task == "embedding":
        return EMBEDDING_PROVIDER
    elif task == "chat":
        # Chat uses same provider as vision for consistency
        return VISION_PROVIDER
    else:
        return AI_PROVIDER
