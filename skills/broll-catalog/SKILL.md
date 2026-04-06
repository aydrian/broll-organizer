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
- **Clip Markers:** Use `broll marker` to save in/out points ("money shot" at seconds 12-18) and export segments

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

### Search with structured filters (duration, resolution, date, mood, etc.)
```bash
# Duration range (5-30 seconds)
uv run broll search "sunset" --drive /media/openclaw/Crucial\ X10 --duration 5-30

# Minimum resolution (4K, 1080p, 720p, or pixel width)
uv run broll search "beach" --drive /media/openclaw/Crucial\ X10 --resolution 4K

# Aspect ratio or orientation
uv run broll search "portrait" --drive /media/openclaw/Crucial\ X10 --aspect 9:16
uv run broll search "landscape" --drive /media/openclaw/Crucial\ X10 --portrait

# Date range
uv run broll search "snow" --drive /media/openclaw/Crucial\ X10 --date 2025-12-01..2026-01-15
uv run broll search "spring" --drive /media/openclaw/Crucial\ X10 --since 2025-03-01 --until 2025-05-31

# Mood and movement filters
uv run broll search "city" --drive /media/openclaw/Crucial\ X10 --mood calm --movement static
uv run broll search "night" --drive /media/openclaw/Crucial\ X10 --time golden_hour

# Combined filters
uv run broll search "temple" --drive /media/openclaw/Crucial\ X10 --duration 5-15 --resolution 4K --mood mysterious

# Filters without keyword (browse all matching filters)
uv run broll search --drive /media/openclaw/Crucial\ X10 --location "Kusatsu" --time night --movement static
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

### Find videos near GPS coordinates
```bash
uv run broll nearby --drive /media/openclaw/Crucial\ X10 --lat 35.6762 --lon 139.6503 --radius 5km
```

### Find videos near a location name
```bash
uv run broll nearby --drive /media/openclaw/Crucial\ X10 --location "Shibuya Station" --radius 2km
```

### Manually set video location
```bash
uv run broll set-location --drive /media/openclaw/Crucial\ X10 --id 42 --lat 35.0 --lon 139.0
```

### Set a clip marker (in/out points)
```bash
uv run broll marker set 42 --drive /media/openclaw/Crucial\ X10 --in 12.5 --out 18.3 --label "money shot"
```

### List markers for a video
```bash
uv run broll marker list 42 --drive /media/openclaw/Crucial\ X10
```

### Delete a marker
```bash
uv run broll marker delete 5 --drive /media/openclaw/Crucial\ X10
```

### Export a marked clip
```bash
uv run broll marker export 5 --drive /media/openclaw/Crucial\ X10 --output /tmp/money_shot.mp4
```

### Launch web UI for browsing
```bash
uv run broll web /media/openclaw/Crucial\ X10
```

## Structured Search Filters Reference

All filters can be combined with each other and with keyword search. Query is now optional if you provide at least one filter.

| Filter | Option | Example | Description |
|--------|--------|---------|-------------|
| **Duration** | `--duration` | `--duration 5-30` | Range in seconds (formats: `5-30`, `5:30`, `5..30`) |
| | `--min-duration` | `--min-duration 10` | Minimum duration in seconds |
| | `--max-duration` | `--max-duration 60` | Maximum duration in seconds |
| **Resolution** | `--resolution` | `--resolution 4K` | Name (`4K`, `1080p`, `720p`) or min pixels |
| | `--min-width` | `--min-width 1920` | Minimum video width |
| | `--min-height` | `--min-height 1080` | Minimum video height |
| **Aspect** | `--aspect` | `--aspect 16:9` | Aspect ratio (`16:9`, `4:3`, `9:16`, `1:1`) |
| | `--portrait` | `--portrait` | Portrait orientation (height > width) |
| | `--landscape` | `--landscape` | Landscape orientation (width > height) |
| **Date** | `--date` | `--date 2025-01-01..2025-12-31` | Date range (`YYYY-MM-DD..YYYY-MM-DD`) |
| | `--since` | `--since 2025-01-01` | Videos from date onwards |
| | `--until` | `--until 2025-12-31` | Videos up to date |
| **Metadata** | `--mood` | `--mood calm` | Mood: `calm`, `energetic`, `mysterious` |
| | `--movement` | `--movement static` | Camera: `static`, `pan`, `gimbal` |
| | `--time` | `--time golden_hour` | Time of day: `morning`, `night`, `golden_hour` |
| | `--location` | `--location "Tokyo"` | Location name (partial match) |
| | `--device` | `--device dji_pocket3` | Source device filter |

## Workflow: Finding Clips for Content

1. **Search with keywords:** Use natural language like "onsen steam", "disney castle", "mountain sunset"
2. **Narrow by filters:** Use `--duration`, `--resolution`, `--mood`, `--time` for precise matches
3. **Browse by location:** Use `--location` flag with place names (filters are partial match)
4. **Filters-only browsing:** Omit the query to browse all clips matching filter criteria
5. **Browse visually:** Launch the web UI with `broll web` for grid view and thumbnails
6. **Get details:** Use search with `--video-id` for full metadata
7. **Access files:** Use the `file_path` from results to locate the actual video

## Workflow: Marking Best Segments

1. **Find the video:** Search for the clip using keyword or `--video-id`
2. **Set markers:** Use `broll marker set` with in/out times and a label like "money shot" or "intro"
3. **Multiple markers:** Add multiple segments per video with different labels
4. **List markers:** View all markers for a video with `broll marker list`
5. **Export clips:** Extract specific marker segments with `broll marker export`
6. **Web UI:** In the browser, use 🚩 button to save current trim as marker

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
- **"in point must be less than out point"** — When setting markers, ensure --in value is less than --out value
- **"Label already exists"** — Each marker label must be unique per video; use a different label or delete the existing one first
