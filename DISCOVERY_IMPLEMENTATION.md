# Discovery & Similarity Search Implementation

**Branch:** `feature/discovery-similarity-issue-25`
**Commit:** `19bc92b`
**References:** Issue #25

## Summary

Implemented discovery features for the broll-organizer Web UI, enabling users to find random clips, browse with shuffle mode, and discover similar videos.

## Features Implemented

### 1. "I'm Feeling Lucky" Button
- **Location:** Browse page discovery bar
- **Function:** Returns a random video matching optional filters
- **Filters:** Mood, time of day, location
- **Smart behavior:** Tracks shown videos to avoid repeats within a session; resets when filters change

### 2. Shuffle Mode
- **Location:** Browse page
- **Toggle button:** Enables random ordering of videos
- **Behavior:** Replaces normal browse with shuffled results; pagination maintained

### 3. "Unseen Only" Filter
- **Location:** Browse page discovery bar
- **Function:** Returns videos in random order (simulating unseen content)
- **Future:** Can be extended with actual view tracking

### 4. Similar Videos Section
- **Location:** Video detail page (below video info)
- **Display:** Grid of up to 8 similar videos
- **Info shown:** Thumbnail, duration, similarity score, mood/time/location tags

## Similarity Algorithm

Videos are scored based on shared attributes:
- **Tags (most important):** 2 points per shared tag
- **Mood match:** 2 points
- **Location match:** 2 points  
- **Time of day match:** 1 point

## New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/random` | GET | Random video with optional filters (mood, time_of_day, location, exclude list) |
| `/api/similar/<video_id>` | GET | Similar videos for a given ID (limit parameter) |
| `/api/discovery/filters` | GET | Available filter values (moods, times, locations) |
| `/api/browse/shuffle` | GET | Shuffled browse results (path, limit, pagination) |

## Database Methods Added (db.py)

- `get_random_video(filters, exclude_ids)` - Random selection with optional filters
- `get_similar_videos(video_id, limit)` - Similarity matching by tags/mood/location/time
- `get_unseen_videos(limit, offset)` - Randomized results for "unseen" filter
- `get_shuffle_videos(limit, offset, folder_path)` - Shuffled browse results
- `get_distinct_moods()` - List of unique moods
- `get_distinct_times_of_day()` - List of unique times of day
- `get_distinct_locations()` - List of locations with counts

## Files Modified

| File | Changes |
|------|---------|
| `src/broll/db.py` | Added discovery database methods |
| `src/broll/web/app.py` | Added discovery API endpoints |
| `src/broll/web/static/browse.js` | Added lucky button, shuffle mode, filter handlers |
| `src/broll/web/templates/video_detail.html` | Added similar videos section |
| `src/broll/web/templates/base.html` | Added discovery.css include |
| `src/broll/web/static/discovery.css` | New styles for discovery UI (created) |

## Testing

Both Python files compile without errors:
```bash
python -m py_compile src/broll/db.py  # OK
python -m py_compile src/broll/web/app.py  # OK
```

## Next Steps for Full Integration

1. Run the application: `uv run broll web /path/to/drive`
2. Test the "I'm Feeling Lucky" button with different filters
3. Verify shuffle mode works across pagination
4. Check similar videos appear on video detail pages
5. Create a PR from branch `feature/discovery-similarity-issue-25` to main

## Screenshot Preview

The discovery bar appears at the top of the browse page with:
- 🎲 I'm Feeling Lucky button (gold/gradient)
- 🔀 Shuffle toggle button
- 👁️ Unseen Only button
- Filter dropdowns: Any Mood, Any Time, Any Location

When clicked, lucky results display in an expandable section showing the random clip with its tags and metadata.

Similar videos appear at the bottom of video detail pages in a responsive grid, showing matching factors with star ratings.