# 🎬 GPS Support and Proximity Search

This PR implements GPS coordinate support and proximity search for the broll-organizer CLI, addressing issue #16.

## What's New

### Database Schema Updates
- Added `folder_location` TEXT column for folder-based location tracking
- Added `gps_accuracy` REAL column for GPS accuracy in meters
- Added `location_source` TEXT column ('folder', 'gps', 'manual') to track how location was determined
- Added `migrate()` method for schema migrations on existing databases

### New CLI Commands

#### `broll nearby`
Find videos within a radius of a specific location using the Haversine formula.

```bash
# Search by coordinates
broll nearby --drive /path/to/drive --lat 35.6762 --lon 139.6503 --radius 5km

# Search by location name (geocoded via Nominatim API)
broll nearby --drive /path/to/drive --location "Shibuya Station, Tokyo" --radius 2km
```

Features:
- Supports radius units: km, m, mi
- Results sorted by distance
- Shows distance, location source, and video details
- Geocoding results are cached to avoid repeated API calls

#### `broll set-location`
Manually set GPS coordinates for a video.

```bash
broll set-location --drive /path/to/drive --id 42 --lat 35.0 --lon 139.0 --name "Tokyo Tower"
```

Features:
- Validates coordinate ranges
- Auto-reverse-geocodes location name if not provided
- Sets location_source to 'manual'
- Optional accuracy parameter

### GPS Extraction Updates
- `extract_gps()` now extracts GPS accuracy from metadata when available
- `extract_all_metadata()` sets `location_source` to 'gps' when coordinates found, 'folder' otherwise
- Uses existing reverse_geocoder for offline location name lookup

### Technical Details
- Haversine formula implemented in SQL for efficient proximity search
- Nominatim API (OpenStreetMap) used for geocoding location names
- Geocoding cache prevents redundant API calls in the same session
- All new columns have defaults for backward compatibility

## Testing
- Syntax verified: `python3 -m py_compile` passes on all modified files
- Commands registered and help text accessible via `--help`

## Usage Example
```bash
# Initialize or migrate database
broll init /path/to/drive

# Process videos (extracts GPS metadata)
broll process /path/to/drive

# Find videos near a location
broll nearby --drive /path/to/drive --location "Kyoto Station" --radius 3km

# Manually set location for a video
broll set-location --drive /path/to/drive --id 123 --lat 35.0116 --lon 135.7681
```

Closes #16
