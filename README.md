# 🎬 B-Roll Organizer

AI-powered b-roll organizer using **Fireworks AI** (with Ollama fallback for local-only use).

## Overview

`broll-organizer` is an AI-powered video cataloging tool designed to organize and search large collections of b-roll footage stored on external drives. It uses Large Language Models (LLMs) to automatically analyze, tag, and describe video clips, making them searchable through natural language.

The project has two main interfaces:
1.  A **Command-Line Interface (CLI)** for initializing the catalog, processing videos, and performing searches.
2.  A **Web Interface (Flask)** for visually browsing the catalog, searching for clips, and viewing video details.

An **OpenClaw Agent API** is also available for programmatic access by AI assistants.

## Key Technologies

*   **Backend:** Python 3.12+
*   **CLI:** `click`
*   **Web Framework:** `flask`
*   **Video Processing:** `ffmpeg-python`
*   **Image Processing:** `pillow`
*   **Database:** SQLite with vector support via `sqlite-vec` for semantic search.
*   **AI/ML:** [Fireworks AI](https://fireworks.ai/) for fast, high-quality inference (or local Ollama as fallback)
    *   **Vision Analysis:** `kimi-k2p5-turbo` (multimodal) - for scene descriptions and tags
    *   **Embeddings:** `nomic-embed-text-v1.5` - for semantic search
*   **Folder-based location:** Since devices like Osmo Pocket 3 don't encode GPS, location is inferred from folder names.

## AI Provider Setup

### Option 1: Fireworks AI (Recommended)

Set your Fireworks API key. You can either:

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

The app defaults to Fireworks mode when `AI_PROVIDER=fireworks` (or unset).

### Option 2: Ollama (Local-only)

For offline use, install [Ollama](https://ollama.com/):

1.  **Install Ollama:** Download via [ollama.com](https://ollama.com/)
2.  **Pull Required Models:**
    ```bash
    ollama pull minicpm-v      # Vision analysis
    ollama pull nomic-embed-text  # Embeddings
    ```
3.  **Set Provider in `.env` or env var:**
    ```bash
    # In .env file or:
    export AI_PROVIDER=ollama
    ```

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
Scan the drive to find new videos, extract metadata, analyze them with the LLM, and add them to the catalog.
```bash
uv run broll process /path/to/your/external-drive
```
*   Use `--scan-only` to quickly catalog files by metadata without running the slower LLM analysis.
*   Use `--force` to re-process all videos, even if they are already in the catalog.

## Usage

### CLI

*   **Search:** Find videos using natural language.
    ```bash
    uv run broll search "a slow-motion shot of a waterfall at sunset" --drive /path/to/drive
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
| `AI_PROVIDER` | AI backend to use: `fireworks` or `ollama` | `fireworks` |
| `FIREWORKS_API_KEY` | Your Fireworks API key | (required for Fireworks) |
| `FIREWORKS_VISION_MODEL` | Vision model identifier | `accounts/fireworks/models/kimi-k2p5-turbo` |
| `FIREWORKS_EMBEDDING_MODEL` | Embedding model identifier | `accounts/fireworks/models/nomic-embed-text-v1.5` |

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
