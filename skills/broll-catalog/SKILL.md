---
name: broll-catalog
description: Query and search Aydrian's B-roll video catalog stored on external drives. Use when the user wants to find specific video clips, search footage by keyword/location/mood, get video details, or browse their Japan travel B-roll. Triggers on phrases like "find B-roll", "search my videos", "get clips from Japan", "show me footage from", "what videos do I have", "find footage of", "query the catalog".
---

# B-Roll Catalog Skill

Query Aydrian's B-roll footage catalog stored on external drives using the `broll` CLI.

## Quick Start

Use the broll CLI to search:

```bash
uv run broll search "tokyo sunset" --drive /media/openclaw/Crucial\ X10
```

## Key Facts

- **Database Location:** `/media/openclaw/Crucial X10/.broll/broll_catalog.db`
- **Drive:** Crucial X10 2TB external SSD (mounted at `/media/openclaw/Crucial X10`)
- **Thumbnails:** `/media/openclaw/Crucial X10/.broll/thumbs/`
- **Current Catalog:** Japan 2025-26 footage (293 videos across 12 locations)
- **Important:** Osmo Pocket 3 does NOT encode GPS data — location is inferred from folder names

## Prerequisites

The `broll` CLI must be installed from the main repo:

```bash
cd ~/broll-organizer
uv sync
```

## Commands

### Search by keyword
```bash
uv run broll search "QUERY" --drive /media/openclaw/Crucial\ X10 --limit 10
```

### Search with contact sheet grid
```bash
uv run broll search "tokyo sunset" --drive /media/openclaw/Crucial\ X10 --grid 3x3
```

### Search with HTML gallery export
```bash
uv run broll search "tokyo" --drive /media/openclaw/Crucial\ X10 --export-gallery /tmp/tokyo-gallery.html
```

### Get video thumbnail path
```bash
uv run broll thumbnail --id 42 --drive /media/openclaw/Crucial\ X10
```

### Get thumbnail as base64 (for embedding)
```bash
uv run broll thumbnail --id 42 --drive /media/openclaw/Crucial\ X10 --base64
```

### Get video by ID
```bash
uv run broll search --drive /media/openclaw/Crucial\ X10 --video-id 42
```

### Search by location
```bash
uv run broll search --drive /media/openclaw/Crucial\ X10 --location "Beppu"
```

### Get catalog stats (basic)
```bash
uv run broll stats /media/openclaw/Crucial\ X10
```

### Get detailed stats with location breakdown
```bash
uv run broll stats /media/openclaw/Crucial\ X10 --detailed
```

### Get timeline of videos by month
```bash
uv run broll stats /media/openclaw/Crucial\ X10 --timeline
```

### Find videos missing metadata
```bash
uv run broll stats /media/openclaw/Crucial\ X10 --missing-metadata
```

### Run health check (doctor)
```bash
uv run broll doctor /media/openclaw/Crucial\ X10
```

### Check for specific issues
```bash
uv run broll doctor /media/openclaw/Crucial\ X10 --thumbnails    # Missing thumbnails
uv run broll doctor /media/openclaw/Crucial\ X10 --orphaned      # Orphaned records
uv run broll doctor /media/openclaw/Crucial\ X10 --hashes        # Hash mismatches
```

### Fix issues automatically
```bash
uv run broll doctor /media/openclaw/Crucial\ X10 --fix
```

### Launch web UI for browsing
```bash
uv run broll web /media/openclaw/Crucial\ X10
```

## Workflow: Finding Clips for Content

1. **Search with keywords:** Use natural language like "onsen steam", "disney castle", "mountain sunset"
2. **Narrow by location:** Use `--location` flag with place names
3. **Browse visually:** Launch the web UI with `broll web` for grid view and thumbnails
4. **Get details:** Use search with `--video-id` for full metadata
5. **Access files:** Use the `file_path` from results to locate the actual video

## Workflow: Catalog Maintenance

1. **Check catalog health:** Run `broll doctor` to find missing files, orphaned records, or hash mismatches
2. **View detailed stats:** Use `broll stats --detailed` to see breakdown by location
3. **Find gaps:** Use `broll stats --missing-metadata` to identify videos needing reprocessing
4. **Fix issues:** Run `broll doctor --fix` to auto-cleanup orphaned entries

## Output Format

CLI commands output JSON by default. Parse with `jq` or add for human-readable:
```bash
uv run broll search "tokyo" --format text
```

## Troubleshooting

- **"Database not found"** — Check if the Crucial X10 drive is mounted at `/media/openclaw/Crucial X10`
- **"command not found"** — Run `uv sync` from the broll-organizer directory
- **Empty results** — Try broader search terms; catalog may need processing with `broll process`
- **Missing thumbnails** — Thumbnails are generated during processing; not all videos may have them yet
