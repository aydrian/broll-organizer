# 🎬 B-Roll Organizer

AI-powered b-roll organizer using **Fireworks AI** for vision analysis (with Ollama for local embeddings and whisper.cpp for transcription).

## Overview

`broll-organizer` is an AI-powered video cataloging tool designed to organize and search large collections of b-roll footage stored on external drives. It uses Large Language Models (LLMs) to automatically analyze, tag, and describe video clips, making them searchable through natural language—including **spoken content** via audio transcription.

The project has two main interfaces:
1.  A **Command-Line Interface (CLI)** for initializing the catalog, processing videos, and performing searches.
2.  A **Web Interface (Flask)** for visually browsing the catalog, searching for clips, and viewing video details.

An **OpenClaw Agent API** is also available for programmatic access by AI assistants.

## Key Technologies

*   **Backend:** Python 3.12+ with **asyncio** for parallel processing
*   **CLI:** `click`
*   **Web Framework:** `flask`
*   **Video Processing:** `ffmpeg` (subprocess)
*   **Image Processing:** `pillow`
*   **Database:** SQLite with FTS5 (keyword search) + `sqlite-vec` (semantic search)
*   **AI/ML:**
    *   **Vision Analysis:** [Fireworks AI](https://fireworks.ai/) `kimi-k2p5-turbo` (multimodal) - scene descriptions and tags
    *   **Embeddings:** [Ollama](https://ollama.com/) `nomic-embed-text` (local, default) or Fireworks - semantic search
    *   **Transcription:** [whisper.cpp](https://github.com/ggerganov/whisper.cpp) (local) - audio-to-text for spoken content search
*   **Folder-based location:** Since devices like Osmo Pocket 3 don't encode GPS, location is inferred from folder names.

## AI Provider Setup

The application uses a **hybrid approach** to maximize speed while preserving API quotas:

| Task | Default Provider | Reason |
|------|-----------------|--------|
| Vision Analysis | **Fireworks AI** | Kimi K2.5 Turbo - high-quality scene analysis (core value) |
| Embeddings | **Ollama (local)** | nomic-embed-text - runs fast locally, high volume |
| Transcription | **whisper.cpp (local)** | Runs entirely offline - no API usage |

### Required Setup

#### 1. Fireworks AI (Vision Analysis)

Set your Fireworks API key for vision analysis. You can either:

**A. Use a `.env` file (recommended):**
```bash
cp .env.example .env
# Edit .env and add your key:
FIREWORKS_API_KEY=your-api-key-here
```

**B. Set environment variable:**
```bash
export FIREWORKS_API_KEY="your-api-key-here"
```

#### 2. Ollama (Embeddings - Local, Required)

Embeddings default to local Ollama to preserve Fireworks quota for vision tasks:

1.  **Install Ollama:** Download via [ollama.com](https://ollama.com/)
2.  **Pull the embedding model:**
    ```bash
    ollama pull nomic-embed-text  # Required for semantic search
    ```

#### 3. whisper.cpp (Transcription - Optional)

For audio transcription (enables search of spoken content):

**macOS (Apple Silicon with Metal GPU):**
```bash
# Install via Homebrew
brew install whisper.cpp

# Download model (small is fast with Metal GPU)
whisper-cli --model small --download-model
```

**Linux (x86_64 or ARM64 like Raspberry Pi):**
```bash
# Build from source
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
make

# Download appropriate model
# For Raspberry Pi 5 (ARM64): use 'tiny' (39MB)
./models/download-ggml-model.sh tiny

# For desktop x86_64: use 'base' (74MB)
./models/download-ggml-model.sh base
```

The application auto-detects your platform and selects the optimal model:
- **macOS Metal (M1/M2/M3):** `small` model (~2-4x real-time speed)
- **Linux x86_64:** `base` model (~0.5-1x real-time speed)
- **Linux ARM64 (Raspberry Pi 5):** `tiny` model (~0.1-0.3x real-time speed)

## Installation

This project is managed with [`uv`](https://github.com/astral-sh/uv).

```bash
# Install dependencies
uv sync

# Run the app
uv run broll --help
```

## Getting Started

The application is designed to be run directly on a host machine with access to an external drive containing video files.

### 1. Initialize the Catalog
Create the database and folder structure on the target drive.
```bash
uv run broll init /path/to/your/external-drive
```

### 2. Process Videos
Scan the drive to find new videos, extract metadata, analyze them with the LLM, and add them to the catalog. Processing now runs **in parallel** with a default concurrency of 5 videos.
```bash
uv run broll process /path/to/your/external-drive
```
*   Use `--scan-only` to quickly catalog files by metadata without running the slower LLM analysis.
*   Use `--force` to re-process all videos, even if they are already in the catalog.
*   Use `--concurrency N` to adjust parallel processing (default: 5).
*   Use `--no-transcribe` to skip audio transcription if whisper.cpp is installed but you want faster processing.

## Usage

### CLI

*   **Process Videos:** Scan, analyze, and catalog videos with **parallel processing** and optional **audio transcription**.
    ```bash
    # Process with default settings (concurrency=5, transcribe enabled)
    uv run broll process /path/to/drive

    # Adjust parallel processing
    uv run broll process /path/to/drive --concurrency 10

    # Skip transcription for faster processing
    uv run broll process /path/to/drive --no-transcribe
    ```

*   **Transcribe (Retroactive):** Add audio transcription to previously processed videos.
    ```bash
    # Transcribe all videos missing transcripts
    uv run broll transcribe /path/to/drive

    # Transcribe specific video by ID
    uv run broll transcribe /path/to/drive --video-id 123

    # Force re-transcribe all videos
    uv run broll transcribe /path/to/drive --force
    ```

*   **Search:** Find videos using natural language (including **spoken content** from transcripts).
    ```bash
    uv run broll search "a slow-motion shot of a waterfall at sunset" --drive /path/to/drive

    # Search for spoken content
    uv run broll search "interview about climate change" --drive /path/to/drive
    ```
    You can specify different search modes: `hybrid` (default), `keyword`, or `semantic`.

*   **Statistics:** View stats about the catalog.
    ```bash
    uv run broll stats /path/to/drive
    ```

*   **OpenClaw Agent Mode:** Launch the agent API for AI assistant integration.
    ```bash
    uv run broll agent /path/to/drive
    ```
    The agent API will be available at `http://127.0.0.1:5556`.

### Web UI

*   Launch the web interface to browse and search the catalog visually.
    ```bash
    uv run broll web /path/to/drive
    ```
    The web UI will be available at `http://127.0.0.1:5555` by default.

## OpenClaw Skill

This repo includes an OpenClaw skill for easy AI assistant integration:

```bash
# Install the skill via npx
npx openclaw skills add aydrian/broll-organizer/skills/broll-catalog
```

Once installed, OpenClaw agents can query your B-roll catalog directly:
- Search by keyword, location, mood
- Get video details and thumbnails
- Find clips for content creation

See [skills/broll-catalog/SKILL.md](skills/broll-catalog/SKILL.md) for details.

## Configuration

Environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `FIREWORKS_API_KEY` | Your Fireworks API key (required for vision analysis) | (none) |
| `VISION_PROVIDER` | Provider for vision analysis: `fireworks` or `ollama` | `fireworks` |
| `EMBEDDING_PROVIDER` | Provider for embeddings: `fireworks` or `ollama` | `ollama` (local) |
| `BROLL_WHISPER_MODEL` | Override whisper.cpp model (tiny, base, small, medium) | `auto` (platform-optimized) |
| `WHISPER_CPP_PATH` | Path to whisper-cli executable | (auto-detected) |
| `BROLL_TRANSCRIPTION_ENABLED` | Enable/disable transcription | `true` |

### Legacy Options

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_PROVIDER` | Legacy fallback for all tasks | `fireworks` |

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
