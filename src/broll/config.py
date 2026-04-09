"""
Central configuration for the b-roll organizer.
All paths are relative to the drive root so the database stays portable.
"""
import os
import platform
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root (where pyproject.toml is)
# Falls back to current working directory if not found
load_dotenv(Path(__file__).parent.parent.parent / ".env")

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

# Proxy video directory name (stored in .broll/)
PROXY_DIRNAME: str = "proxy"

# Legacy provider selection (backward compatibility): "fireworks" or "ollama"
AI_PROVIDER: str = os.environ.get("BROLL_AI_PROVIDER", "fireworks")

# Per-task provider selection (NEW - allows granular control)
# Policy: Fireworks AI Kimi K2.5 Turbo ONLY for vision analysis (core value)
#         Local models for high-volume tasks (embeddings, transcription)
VISION_PROVIDER: str = os.environ.get("BROLL_VISION_PROVIDER", AI_PROVIDER)
EMBEDDING_PROVIDER: str = os.environ.get("BROLL_EMBEDDING_PROVIDER", "ollama")  # DEFAULT: local
TRANSCRIPTION_PROVIDER: str = "local"  # whisper.cpp only (no cloud option)

# Fireworks AI model names (using FirePass Kimi K2.5 Turbo)
FIREWORKS_VISION_MODEL: str = "accounts/fireworks/routers/kimi-k2p5-turbo"
FIREWORKS_CHAT_MODEL: str = "accounts/fireworks/routers/kimi-k2p5-turbo"
FIREWORKS_EMBEDDING_MODEL: str = "accounts/fireworks/models/nomic-embed-text-v1.5"

# Ollama model names (fallback)
OLLAMA_VISION_MODEL: str = "minicpm-v"
OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
OLLAMA_CHAT_MODEL: str = "gemma3:4b"

# Active model names (determined by provider)
VISION_MODEL: str = FIREWORKS_VISION_MODEL if VISION_PROVIDER == "fireworks" else OLLAMA_VISION_MODEL
CHAT_MODEL: str = FIREWORKS_CHAT_MODEL if VISION_PROVIDER == "fireworks" else OLLAMA_CHAT_MODEL
EMBEDDING_MODEL: str = (
    FIREWORKS_EMBEDDING_MODEL if EMBEDDING_PROVIDER == "fireworks" else OLLAMA_EMBEDDING_MODEL
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

# ---- Transcription Settings ----
# Enable/disable transcription (auto-detected based on whisper.cpp availability)
TRANSCRIPTION_ENABLED: bool = os.environ.get("BROLL_TRANSCRIPTION_ENABLED", "true").lower() in ("true", "1", "yes")

# Path to whisper.cpp CLI (auto-detected if not set)
WHISPER_CPP_PATH: str | None = os.environ.get("WHISPER_CPP_PATH")

# Whisper model size: tiny, base, small, medium, large
# Platform-optimized defaults set below
WHISPER_MODEL: str = os.environ.get("BROLL_WHISPER_MODEL", "auto")

# Language for transcription ("auto" for auto-detect)
WHISPER_LANGUAGE: str = os.environ.get("BROLL_WHISPER_LANGUAGE", "auto")

# ---- Platform Detection ----
def _detect_platform_type() -> str:
    """Detect platform type for optimized defaults."""
    system = platform.system()
    machine = platform.machine()

    if system == "Darwin" and machine in ("arm64", "aarch64"):
        return "macos_metal"  # Apple Silicon with Metal GPU
    elif system == "Linux" and machine in ("arm64", "aarch64"):
        return "linux_arm64"  # Raspberry Pi 5, ARM64 servers
    elif system == "Linux" and machine == "x86_64":
        return "linux_x86"  # Desktop/server x86_64
    else:
        return "cpu_generic"  # Fallback


PLATFORM_TYPE: str = _detect_platform_type()

# Check if running on Apple Silicon with Metal support
IS_MACOS_SILICON: bool = PLATFORM_TYPE == "macos_metal"

# Check if running on Raspberry Pi or similar ARM64 Linux
IS_LINUX_ARM64: bool = PLATFORM_TYPE == "linux_arm64"


def get_default_whisper_model() -> str:
    """Return platform-optimized default whisper model."""
    if WHISPER_MODEL != "auto":
        return WHISPER_MODEL

    defaults = {
        "macos_metal": "small",    # ~2-4x real-time with Metal
        "linux_x86": "base",       # ~0.5-1x real-time on CPU
        "linux_arm64": "tiny",     # ~0.1-0.3x real-time on Pi 5
        "cpu_generic": "base",     # Conservative default
    }
    return defaults.get(PLATFORM_TYPE, "base")


def get_app_dir(drive_root: str | Path) -> Path:
    """Return the full path to the .broll directory on the drive."""
    return Path(drive_root) / APP_DIR_NAME


def get_db_path(drive_root: str | Path) -> Path:
    """Return the full path to the SQLite database on the drive."""
    return get_app_dir(drive_root) / DB_FILENAME


def get_thumbs_dir(drive_root: str | Path) -> Path:
    """Return the full path to the thumbnails directory on the drive."""
    return get_app_dir(drive_root) / THUMBS_DIRNAME


def get_proxy_dir(drive_root: str | Path) -> Path:
    """Return the full path to the proxy video directory on the drive."""
    return get_app_dir(drive_root) / PROXY_DIRNAME
