# Database Schema Reference

## Tables

### videos
Main table containing all video metadata.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-incrementing ID |
| file_hash | TEXT UNIQUE | MD5 hash of file for deduplication |
| file_path | TEXT | Full path to video file |
| file_name | TEXT | Just the filename |
| file_size_bytes | INTEGER | File size in bytes |
| create_date | TEXT | Creation date from EXIF/metadata |
| duration_seconds | REAL | Video duration |
| width | INTEGER | Video width in pixels |
| height | INTEGER | Video height in pixels |
| source_device | TEXT | 'dji_pocket3', 'iphone', 'unknown' |
| has_gps | INTEGER (0/1) | Whether GPS data was found |
| latitude | REAL | GPS latitude (if available) |
| longitude | REAL | GPS longitude (if available) |
| gps_location_name | TEXT | Human-readable location name |
| scene_description | TEXT | LLM-generated description |
| tags | TEXT | JSON array of tags |
| mood | TEXT | Single word or short phrase |
| camera_movement | TEXT | 'static', 'pan', 'tilt', 'tracking', 'handheld', 'gimbal', etc. |
| time_of_day | TEXT | 'morning', 'afternoon', 'golden_hour', 'night', etc. |

### videos_fts
Full Text Search (FTS5) virtual table for searching videos.

Searchable fields:
- file_name
- scene_description  
- tags
- mood
- camera_movement
- time_of_day
- gps_location_name

## Key Queries

### Search by keyword
```sql
SELECT v.*, rank
FROM videos v
JOIN videos_fts fts ON v.id = fts.rowid
WHERE videos_fts MATCH 'tokyo sunset'
ORDER BY rank
LIMIT 10;
```

### Get videos by location (folder-based)
```sql
SELECT * FROM videos
WHERE gps_location_name LIKE '%Kusatsu%'
   OR file_path LIKE '%Kusatsu%'
ORDER BY create_date;
```

### Get videos with descriptions
```sql
SELECT * FROM videos 
WHERE scene_description IS NOT NULL 
  AND scene_description != ''
ORDER BY RANDOM()
LIMIT 5;
```
