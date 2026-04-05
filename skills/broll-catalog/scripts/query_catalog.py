#!/usr/bin/env python3
"""
Query the broll catalog database.
Used by OpenClaw agent to search for video clips.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def get_db_path() -> Path:
    """Return the default database path on the external drive."""
    # Check for mounted Crucial X10 drive
    drive_path = Path("/media/openclaw/Crucial X10")
    if drive_path.exists():
        return drive_path / ".broll" / "broll_catalog.db"
    
    # Fallback: check if BROLL_DB env var is set
    env_path = Path(os.environ.get("BROLL_DB", "/media/openclaw/Crucial X10/.broll/broll_catalog.db"))
    return env_path


def search_catalog(query: str, limit: int = 10) -> list[dict]:
    """
    Search the catalog using FTS (Full Text Search).
    
    Args:
        query: Search query string
        limit: Maximum results to return
        
    Returns:
        List of video dictionaries
    """
    db_path = get_db_path()
    
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Use FTS5 for full-text search
    sql = """
        SELECT v.*, rank
        FROM videos v
        JOIN videos_fts fts ON v.id = fts.rowid
        WHERE videos_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    
    cursor = conn.execute(sql, (query, limit))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_video_by_id(video_id: int) -> dict | None:
    """Get a single video by its ID."""
    db_path = get_db_path()
    
    if not db_path.exists():
        return None
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


def get_videos_by_location(location: str, limit: int = 20) -> list[dict]:
    """
    Get videos by location name.
    Uses folder-based location inference since Osmo Pocket 3 doesn't encode GPS.
    """
    db_path = get_db_path()
    
    if not db_path.exists():
        return []
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Search in gps_location_name field (populated from folder names)
    sql = """
        SELECT * FROM videos
        WHERE gps_location_name LIKE ?
           OR file_path LIKE ?
        ORDER BY create_date
        LIMIT ?
    """
    
    pattern = f"%{location}%"
    cursor = conn.execute(sql, (pattern, pattern, limit))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def list_all_videos(limit: int = 50) -> list[dict]:
    """List all videos with basic info."""
    db_path = get_db_path()
    
    if not db_path.exists():
        return []
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    sql = """
        SELECT id, file_name, file_path, duration_seconds, 
               scene_description, tags, gps_location_name
        FROM videos
        ORDER BY file_path
        LIMIT ?
    """
    
    cursor = conn.execute(sql, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_thumbnail_path(video_id: int) -> Path | None:
    """Get the path to a video's thumbnail."""
    db_path = get_db_path()
    drive_root = db_path.parent.parent  # .broll/broll_catalog.db -> drive root
    thumbs_dir = drive_root / ".broll" / "thumbs"
    
    # Get video hash from DB
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT file_hash FROM videos WHERE id = ?", (video_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    file_hash = row[0]
    thumb_path = thumbs_dir / f"{file_hash}.jpg"
    
    return thumb_path if thumb_path.exists() else None


def get_stats() -> dict:
    """Get catalog statistics."""
    db_path = get_db_path()
    
    if not db_path.exists():
        return {"error": "Database not found"}
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    stats = {}
    
    # Total videos
    cursor.execute("SELECT COUNT(*) FROM videos")
    stats["total_videos"] = cursor.fetchone()[0]
    
    # Videos with descriptions
    cursor.execute("SELECT COUNT(*) FROM videos WHERE scene_description IS NOT NULL AND scene_description != ''")
    stats["with_descriptions"] = cursor.fetchone()[0]
    
    # Videos with tags
    cursor.execute("SELECT COUNT(*) FROM videos WHERE tags IS NOT NULL AND tags != ''")
    stats["with_tags"] = cursor.fetchone()[0]
    
    # Locations (from gps_location_name)
    cursor.execute("""
        SELECT gps_location_name, COUNT(*) as count
        FROM videos
        WHERE gps_location_name IS NOT NULL AND gps_location_name != ''
        GROUP BY gps_location_name
        ORDER BY count DESC
    """)
    stats["locations"] = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Query broll catalog")
    parser.add_argument("action", choices=["search", "video", "location", "list", "stats", "thumbnail"])
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--id", "-i", type=int, help="Video ID")
    parser.add_argument("--location", "-l", help="Location name")
    parser.add_argument("--limit", type=int, default=10, help="Result limit")
    parser.add_argument("--format", "-f", choices=["json", "text"], default="json")
    
    args = parser.parse_args()
    
    result = None
    
    if args.action == "search":
        if not args.query:
            print("Error: --query required for search", file=sys.stderr)
            sys.exit(1)
        result = search_catalog(args.query, args.limit)
    
    elif args.action == "video":
        if not args.id:
            print("Error: --id required", file=sys.stderr)
            sys.exit(1)
        result = get_video_by_id(args.id)
    
    elif args.action == "location":
        if not args.location:
            print("Error: --location required", file=sys.stderr)
            sys.exit(1)
        result = get_videos_by_location(args.location, args.limit)
    
    elif args.action == "list":
        result = list_all_videos(args.limit)
    
    elif args.action == "stats":
        result = get_stats()
    
    elif args.action == "thumbnail":
        if not args.id:
            print("Error: --id required", file=sys.stderr)
            sys.exit(1)
        result = str(get_thumbnail_path(args.id)) if get_thumbnail_path(args.id) else None
    
    if args.format == "json":
        print(json.dumps(result, indent=2, default=str))
    else:
        # Simple text output for quick reading
        if isinstance(result, list):
            for item in result:
                print(f"[{item.get('id', '?')}] {item.get('file_name', 'Unknown')}")
                if item.get('scene_description'):
                    print(f"    {item['scene_description'][:100]}...")
                print()
        elif isinstance(result, dict):
            for key, value in result.items():
                print(f"{key}: {value}")
        else:
            print(result)


if __name__ == "__main__":
    import os  # Import here to avoid issues if module is imported
    main()
