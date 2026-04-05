# src/broll/config.py
"""
Central configuration for the b-roll organizer.
All paths are relative to the drive root so the database stays portable.
"""
from pathlib import Path

# File extensions we consider video files
VIDEO_EXTENSIONS: set[str] = {".mp4", ".mov", ".m4v", ".MP4", ".MOV"}

# DJI low-res preview extension
LRF_EXTENSION: str = ".lrf"

# App data directory name
APP_DIR_NAME: str = ".broll"

# Database filename (stored in .broll/)
DB_FILENAME: str = "broll_catalog.db"

# Thumbnail directory name (stored in .broll/)
THUMBS_DIRNAME: str = "thumbs"

# Provider selection: "fireworks" or "ollama"
AI_PROVIDER: str = "fireworks"

# Fireworks AI model names (using FirePass Kimi K2.5 Turbo)
FIREWORKS_VISION_MODEL: str = "accounts/fireworks/models/kimi-k2p5-turbo"
FIREWORKS_CHAT_MODEL: str = "accounts/fireworks/models/kimi-k2p5-turbo"
FIREWORKS_EMBEDDING_MODEL: str = "accounts/fireworks/models/nomic-embed-text-v1.5"

# Ollama model names (fallback)
OLLAMA_VISION_MODEL: str = "minicpm-v"
OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
OLLAMA_CHAT_MODEL: str = "gemma3:4b"

# Active model names (determined by provider)
VISION_MODEL: str = FIREWORKS_VISION_MODEL if AI_PROVIDER == "fireworks" else OLLAMA_VISION_MODEL
CHAT_MODEL: str = FIREWORKS_CHAT_MODEL if AI_PROVIDER == "fireworks" else OLLAMA_CHAT_MODEL
EMBEDDING_MODEL: str = (
    FIREWORKS_EMBEDDING_MODEL if AI_PROVIDER == "fireworks" else OLLAMA_EMBEDDING_MODEL
)

# Embedding dimensions (nomic-embed-text produces 768-dim vectors)
EMBEDDING_DIMENSIONS: int = 768

# Number of keyframes to extract per video for LLM analysis
NUM_KEYFRAMES: int = 4

# Web UI defaults
WEB_HOST: str = "127.0.0.1"
WEB_PORT: int = 5555

# OpenClaw Agent API mode (new)
AGENT_API_HOST: str = "127.0.0.1"
AGENT_API_PORT: int = 5556


def get_app_dir(drive_root: str | Path) -> Path:
    """Return the full path to the .broll directory on the drive."""
    return Path(drive_root) / APP_DIR_NAME


def get_db_path(drive_root: str | Path) -> Path:
    """Return the full path to the SQLite database on the drive."""
    return get_app_dir(drive_root) / DB_FILENAME


def get_thumbs_dir(drive_root: str | Path) -> Path:
    """Return the full path to the thumbnails directory on the drive."""
    return get_app_dir(drive_root) / THUMBS_DIRNAME
