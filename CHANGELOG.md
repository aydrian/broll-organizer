# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-04-05

### Added
- Systemd service for auto-start on boot (`systemd/broll-catalog.service`)
- Install script for easy service setup (`systemd/install.sh`)
- Drive disconnection handling with friendly error page
- Graceful handling when external SSD is unplugged/plugged in
- Template `drive_not_connected.html` for offline drive status

### Changed
- Moved project to `/home/openclaw/apps/broll-organizer`
- Web UI now detects drive connection status before each request
- API returns 503 with JSON error when drive is offline

### Fixed
- Folder display bug: video files no longer appear as folders
- Merge conflicts in PR #9 resolved
- All code review issues addressed (#1, #2, #3, #4, #5, #6)

## [0.2.3] - 2026-04-05

### Fixed
- Upgrade sqlite-vec to 0.1.9 (includes aarch64 64-bit wheel for Raspberry Pi)
- Web UI and Agent API now work with full sqlite-vec functionality on Pi
- Revert web/app.py to use Database class with sqlite-vec support

## [0.2.1] - 2026-04-05

### Added
- `.env` file support via `python-dotenv` for easy configuration
- `.env.example` template file

## [0.2.0] - 2026-04-05

### Added
- Fireworks AI support with Kimi K2.5 Turbo for vision, chat, and embeddings
- Ollama fallback mode for local/offline usage (`AI_PROVIDER=ollama`)
- OpenClaw Agent API (`broll agent` command) with REST endpoints:
  - `GET /health` - Health check
  - `GET /stats` - Catalog statistics
  - `GET /search?q=...` - Full-text search
  - `GET /videos` - List videos with filtering
  - `GET /video/<id>` - Get single video
  - `GET /thumbnail/<id>` - Get video thumbnail
  - `POST /chat` - Chat with catalog (keyword search)
- OpenClaw skill in `skills/broll-catalog/` for `npx openclaw skills add`
- Environment-based configuration for AI provider selection

### Changed
- Updated README with Fireworks setup instructions
- `analyzer.py`, `embeddings.py`, `chat.py` now support dual providers
- Agent API uses plain sqlite3 (avoids sqlite-vec architecture issues)

### Fixed
- Handle missing database columns gracefully in Agent API
- Column name compatibility (`file_size` vs `file_size_bytes`)

## [0.1.0] - 2026-02-15

### Added
- Initial release with Ollama-only support
- CLI commands: `init`, `process`, `search`, `stats`, `web`
- Web UI for browsing and searching catalog
- SQLite database with FTS5 and sqlite-vec
- Video metadata extraction via FFmpeg
- Vision analysis with minicpm-v via Ollama
- Keyframe extraction and thumbnail generation
- GPS reverse geocoding for location names
