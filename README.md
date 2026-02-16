# 🎬 B-Roll Organizer

AI-powered b-roll organizer using local LLMs via Ollama.

## Overview

`broll-organizer` is an AI-powered video cataloging tool designed to organize and search large collections of b-roll footage stored on external drives. It uses local, open-source Large Language Models (LLMs) via Ollama to automatically analyze, tag, and describe video clips, making them searchable through natural language.

The project has two main interfaces:
1.  A **Command-Line Interface (CLI)** for initializing the catalog, processing videos, and performing searches.
2.  A **Web Interface (Flask)** for visually browsing the catalog, searching for clips, viewing video details, and using a chatbot to query the collection.

## Key Technologies

*   **Backend:** Python
*   **CLI:** `click`
*   **Web Framework:** `flask`
*   **Video Processing:** `ffmpeg-python`
*   **Image Processing:** `pillow`
*   **Database:** SQLite with vector support via `sqlite-vec` for semantic search.
*   **AI/ML:** Local LLMs via `ollama`. The specific models used are:
    *   **Vision Analysis:** `minicpm-v`
    *   **Embeddings:** `nomic-embed-text`
    *   **Chat:** `gemma3:4b`
*   **Geocoding:** `reverse-geocoder` to get location names from GPS data in video metadata.

## Ollama Setup

This project uses **[Ollama](https://ollama.com/)** to run the local LLMs.

1.  **Install Ollama:** Download and install via [ollama.com](https://ollama.com/).
2.  **Pull Required Models:** Run the following commands to download the models used by the app:
    ```bash
    ollama pull minicpm-v
    ollama pull nomic-embed-text
    ollama pull gemma3:4b
    ```
3.  **Start Server:** Ensure the Ollama app is running in the background.

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

### Web UI

*   Launch the web interface to browse and search the catalog visually.
    ```bash
    uv run broll web /path/to/drive
    ```
    The web UI will be available at `http://127.0.0.1:5555` by default.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
