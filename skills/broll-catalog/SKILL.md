---
name: broll-catalog
description: Query and search Aydrian's B-roll video catalog stored on external drives. Use when the user wants to find specific video clips, search footage by keyword/location/mood, get video details, or browse their Japan travel B-roll. Triggers on phrases like "find B-roll", "search my videos", "get clips from Japan", "show me footage from", "what videos do I have", "find footage of", "query the catalog".
---

# B-Roll Catalog Skill

Query Aydrian's B-roll footage catalog stored on external drives.

## Quick Start

Use the query script to search:

```bash
python3 scripts/query_catalog.py search -q "tokyo sunset"
```

## Key Facts

- **Database Location:** `/media/openclaw/Crucial X10/.broll/broll_catalog.db`
- **Drive:** Crucial X10 2TB external SSD (mounted at `/media/openclaw/Crucial X10`)
- **Thumbnails:** `/media/openclaw/Crucial X10/.broll/thumbs/`
- **Current Catalog:** Japan 2025-26 footage (293 videos across 12 locations)
- **Important:** Osmo Pocket 3 does NOT encode GPS data — location is inferred from folder names

## Folder-Based Location Mapping

Since videos lack GPS metadata, location is derived from parent folder names:

| Folder | Inferred Location |
|--------|-------------------|
| `01 Kusatsu Onsen` | Kusatsu Onsen |
| `02 Tokyo Disneyland` | Tokyo Disneyland |
| `03 Tokyo Disney Sea` | Tokyo Disney Sea |
| `04 Fukuoka` | Fukuoka |
| `05 Driving to Nagasaki` | Nagasaki (road trip) |
| `06 Nagasaki` | Nagasaki |
| `07 Kumamoto` | Kumamoto |
| `08 Takachiho` | Takachiho |
| `09 Mt Aso` | Mt Aso |
| `10 Beppu` | Beppu |
| `11 Okayama` | Okayama |
| `12 Himeji` | Himeji |

## Commands

### Search by keyword
```bash
python3 scripts/query_catalog.py search -q "QUERY" --limit 10
```

### Get video by ID
```bash
python3 scripts/query_catalog.py video -i 42
```

### Search by location
```bash
python3 scripts/query_catalog.py location -l "Beppu"
```

### List all videos
```bash
python3 scripts/query_catalog.py list --limit 20
```

### Get catalog stats
```bash
python3 scripts/query_catalog.py stats
```

### Get thumbnail path
```bash
python3 scripts/query_catalog.py thumbnail -i 42
```

## Workflow: Finding Clips for Content

1. **Search with keywords:** Use `search` with descriptive terms like "onsen steam", "disney castle", "mountain sunset"
2. **Narrow by location:** If you know the place, use `location` command
3. **Get details:** Use `video -i ID` to see full metadata
4. **View thumbnail:** Use `thumbnail -i ID` to get path, then read the image
5. **Pull the clip:** Use the `file_path` from video details to access the actual video file

## Database Details

See [references/database_schema.md](references/database_schema.md) for full schema and example queries.

## Output Format

All query commands output JSON by default. Parse with `jq` or use `--format text` for human-readable output.

## Troubleshooting

- **"Database not found"** — Check if the Crucial X10 drive is mounted at `/media/openclaw/Crucial X10`
- **Empty results** — Try broader search terms; catalog may need processing with `broll process`
- **Missing thumbnails** — Thumbnails are generated during processing; not all videos may have them yet
