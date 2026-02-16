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

# Ollama model names
VISION_MODEL: str = "minicpm-v"
EMBEDDING_MODEL: str = "nomic-embed-text"
CHAT_MODEL: str = "gemma3:4b"

# Embedding dimensions (nomic-embed-text produces 768-dim vectors)
EMBEDDING_DIMENSIONS: int = 768

# Number of keyframes to extract per video for LLM analysis
NUM_KEYFRAMES: int = 4

# Web UI defaults
WEB_HOST: str = "127.0.0.1"
WEB_PORT: int = 5555


def get_app_dir(drive_root: str | Path) -> Path:
    """Return the full path to the .broll directory on the drive."""
    return Path(drive_root) / APP_DIR_NAME


def get_db_path(drive_root: str | Path) -> Path:
    """Return the full path to the SQLite database on the drive."""
    return get_app_dir(drive_root) / DB_FILENAME


def get_thumbs_dir(drive_root: str | Path) -> Path:
    """Return the full path to the thumbnails directory on the drive."""
    return get_app_dir(drive_root) / THUMBS_DIRNAME
