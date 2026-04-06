# src/broll/db.py
"""
Database layer — SQLite with FTS5 (keyword search) + sqlite-vec (semantic search).

The database file lives on the external SSD so everything is portable.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlite_vec

from .config import EMBEDDING_DIMENSIONS


class Database:
    """Manages the SQLite database for the b-roll catalog."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """Open (or return existing) database connection."""
        if self._conn is not None:
            return self._conn

        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row  # Access columns by name
        self._conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent reads
        self._conn.execute("PRAGMA foreign_keys=ON")

        # Load the sqlite-vec extension for vector search
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)

        return self._conn

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Database:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ------------------------------------------------------------------
    # Schema initialization
    # ------------------------------------------------------------------

    def initialize(self):
        """Create all tables and indexes if they don't exist."""
        conn = self.connect()

        # ---- Main videos table ----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path       TEXT UNIQUE NOT NULL,
                file_name       TEXT NOT NULL,
                file_size       INTEGER,
                file_hash       TEXT NOT NULL,
                source_device   TEXT,
                lrf_path        TEXT,

                -- Technical metadata
                duration_seconds REAL,
                resolution      TEXT,
                width           INTEGER,
                height          INTEGER,
                fps             REAL,
                codec           TEXT,
                creation_date   TEXT,

                -- GPS metadata
                gps_latitude    REAL,
                gps_longitude   REAL,
                gps_location_name TEXT,

                -- LLM-generated analysis
                scene_description TEXT,
                tags            TEXT,
                mood            TEXT,
                camera_movement TEXT,
                time_of_day     TEXT,

                -- Housekeeping
                thumbnail_path  TEXT,
                processed_at    TEXT,
                created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
        """)

        # ---- Full-text search index (FTS5) for keyword search ----
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts USING fts5(
                file_name,
                scene_description,
                tags,
                mood,
                camera_movement,
                time_of_day,
                gps_location_name,
                content='videos',
                content_rowid='id'
            )
        """)

        # ---- Triggers to keep FTS5 index in sync with the videos table ----
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS videos_ai AFTER INSERT ON videos BEGIN
                INSERT INTO videos_fts(
                    rowid, file_name, scene_description, tags,
                    mood, camera_movement, time_of_day, gps_location_name
                ) VALUES (
                    new.id, new.file_name, new.scene_description, new.tags,
                    new.mood, new.camera_movement, new.time_of_day,
                    new.gps_location_name
                );
            END;

            CREATE TRIGGER IF NOT EXISTS videos_ad AFTER DELETE ON videos BEGIN
                INSERT INTO videos_fts(
                    videos_fts, rowid, file_name, scene_description, tags,
                    mood, camera_movement, time_of_day, gps_location_name
                ) VALUES (
                    'delete', old.id, old.file_name, old.scene_description,
                    old.tags, old.mood, old.camera_movement, old.time_of_day,
                    old.gps_location_name
                );
            END;

            CREATE TRIGGER IF NOT EXISTS videos_au AFTER UPDATE ON videos BEGIN
                INSERT INTO videos_fts(
                    videos_fts, rowid, file_name, scene_description, tags,
                    mood, camera_movement, time_of_day, gps_location_name
                ) VALUES (
                    'delete', old.id, old.file_name, old.scene_description,
                    old.tags, old.mood, old.camera_movement, old.time_of_day,
                    old.gps_location_name
                );
                INSERT INTO videos_fts(
                    rowid, file_name, scene_description, tags,
                    mood, camera_movement, time_of_day, gps_location_name
                ) VALUES (
                    new.id, new.file_name, new.scene_description, new.tags,
                    new.mood, new.camera_movement, new.time_of_day,
                    new.gps_location_name
                );
            END;
        """)

        # ---- Vector table for semantic search (sqlite-vec) ----
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS videos_vec USING vec0(
                video_id INTEGER PRIMARY KEY,
                description_embedding FLOAT[{EMBEDDING_DIMENSIONS}]
            )
        """)

        # ---- Index for fast hash lookups during scanning ----
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_videos_file_hash
            ON videos(file_path, file_hash)
        """)

        # ---- Location cache table for geocoding results ----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS location_cache (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                search_key      TEXT UNIQUE NOT NULL,
                display_name    TEXT NOT NULL,
                location_name   TEXT,
                lat             REAL NOT NULL,
                lon             REAL NOT NULL,
                cached_at       TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
        """)

        # ---- Playlist tables ----
        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                description     TEXT,
                color           TEXT DEFAULT '#3b82f6',
                created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlist_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id     INTEGER NOT NULL,
                video_id        INTEGER NOT NULL,
                position        INTEGER NOT NULL,
                added_at        TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
                UNIQUE(playlist_id, video_id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_playlist_items_playlist_id 
            ON playlist_items(playlist_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_playlist_items_video_id 
            ON playlist_items(video_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_playlist_items_position 
            ON playlist_items(playlist_id, position)
        """)

        conn.commit()
        print(f"✅ Database initialized at {self.db_path}")

    # ------------------------------------------------------------------
    # Schema migration
    # ------------------------------------------------------------------

    def migrate(self):
        """Run any pending migrations to update schema."""
        conn = self.connect()
        
        # Get existing columns
        cursor = conn.execute("PRAGMA table_info(videos)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        # Add folder_location column if not exists
        if "folder_location" not in existing_columns:
            conn.execute("ALTER TABLE videos ADD COLUMN folder_location TEXT")
            print("✓ Added folder_location column")
        
        # Add gps_accuracy column if not exists
        if "gps_accuracy" not in existing_columns:
            conn.execute("ALTER TABLE videos ADD COLUMN gps_accuracy REAL")
            print("✓ Added gps_accuracy column")
        
        # Add location_source column if not exists
        if "location_source" not in existing_columns:
            conn.execute("ALTER TABLE videos ADD COLUMN location_source TEXT DEFAULT 'folder'")
            print("✓ Added location_source column")
        
        conn.commit()
        print("✅ Database migration complete")

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_all_file_hashes(self) -> dict[str, str]:
        """Return a dict of {relative_file_path: file_hash} for all known videos."""
        conn = self.connect()
        rows = conn.execute("SELECT file_path, file_hash FROM videos").fetchall()
        return {row["file_path"]: row["file_hash"] for row in rows}

    def get_video_by_path(self, file_path: str) -> dict[str, Any] | None:
        """Fetch a single video record by its relative path."""
        conn = self.connect()
        row = conn.execute("SELECT * FROM videos WHERE file_path = ?", (file_path,)).fetchone()
        return dict(row) if row else None

    def get_video_by_id(self, video_id: int) -> dict[str, Any] | None:
        """Fetch a single video record by its ID."""
        conn = self.connect()
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        return dict(row) if row else None

    def get_all_videos(
        self, limit: int = 100, offset: int = 0, order_by: str = "creation_date DESC"
    ) -> list[dict[str, Any]]:
        """Fetch all videos with pagination."""
        conn = self.connect()
        # Whitelist allowed order_by values to prevent SQL injection
        allowed_orders = {
            "creation_date DESC",
            "creation_date ASC",
            "file_name ASC",
            "file_name DESC",
            "duration_seconds DESC",
            "duration_seconds ASC",
            "processed_at DESC",
            "processed_at ASC",
        }
        if order_by not in allowed_orders:
            order_by = "creation_date DESC"

        rows = conn.execute(
            f"SELECT * FROM videos ORDER BY {order_by} LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_folder_contents(
        self, folder_path: str = ".", limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        """
        Get contents of a specific folder: subdirectories and videos.
        folder_path: relative path from drive root (e.g. "2023/Trip"). Use "." for root.
        """
        conn = self.connect()

        # Normalize path
        if folder_path == ".":
            folder_path = ""

        # 1. Get subdirectories
        # We look for files that start with the folder_path + "/"
        # and extract the immediate next directory component.

        # SQL logic:
        # - Find paths starting with folder_path/ (or just anything for root)
        # - substr(...) logic is complex in pure SQL without a custom function usually,
        #   but we can try a glob match and distinct extraction.

        # Actually, it's easier to do a somewhat broader query or use specific logic.
        # Given SQLite limitations, let's do:
        # SELECT DISTINCT file_path FROM videos WHERE file_path GLOB 'folder_path/*'

        glob_pattern = f"{folder_path}/*" if folder_path else "*"
        prefix_len = len(folder_path) + 1 if folder_path else 0

        # Getting all paths might be heavy if there are thousands.
        # But we only need immediate subdirs.
        # Optimization: We can maintain a separate folders table, but we don't have one.
        # Let's try to do it with string manipulation in python for now if the dataset isn't huge,
        # OR use a recursive CTE or just smart grouping.

        # Better approach for now:
        # SELECT file_path FROM videos WHERE file_path LIKE ?
        # And process in python to find unique immediate subdirs.
        # For a few thousand videos this is fine. For millions, we'd need a different schema.

        like_pattern = f"{folder_path}/%" if folder_path else "%"

        # We only need paths that match the immediate level.
        # This query might still be expensive if we select ALL.
        # Let's try to limit scanning.

        cursor = conn.execute(
            "SELECT file_path FROM videos WHERE file_path LIKE ?", (like_pattern,)
        )

        subfolders = set()

        for row in cursor:
            path = row[0]
            # Strip the prefix
            if prefix_len > 0:
                rel_path = path[prefix_len:]
            else:
                rel_path = path

            if "/" in rel_path:
                # It has a subdirectory
                subdir = rel_path.split("/", 1)[0]
                subfolders.add(subdir)

        sorted_folders = sorted(list(subfolders))

        # 2. Get videos directly in this folder (no subfolders)
        # We want file_path NOT LIKE 'folder_path/%/%' essentially.
        # i.e. it shouldn't have another slash after the prefix.

        # SQLite GLOB is case sensitive, LIKE is case insensitive (usually). Paths are case sensitive?
        # Let's stick to standard logic.

        # Construct a query to find videos in this folder ONLY.
        # We can filter in Python or try to be clever with SQL.
        # SQL: ... AND file_path NOT LIKE ?

        exclude_pattern = f"{folder_path}/%/%" if folder_path else "%/%"

        videos_query = """
            SELECT * FROM videos 
            WHERE file_path LIKE ? 
            AND file_path NOT LIKE ?
            ORDER BY creation_date DESC 
            LIMIT ? OFFSET ?
        """

        video_rows = conn.execute(
            videos_query, (like_pattern, exclude_pattern, limit, offset)
        ).fetchall()

        videos = [dict(row) for row in video_rows]

        return {"folders": sorted_folders, "videos": videos}

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics about the catalog."""
        conn = self.connect()
        stats = {}
        stats["total_videos"] = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        stats["total_duration_seconds"] = conn.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM videos"
        ).fetchone()[0]
        stats["total_size_bytes"] = conn.execute(
            "SELECT COALESCE(SUM(file_size), 0) FROM videos"
        ).fetchone()[0]
        stats["devices"] = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT source_device FROM videos WHERE source_device IS NOT NULL"
            ).fetchall()
        ]
        stats["locations"] = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE gps_location_name IS NOT NULL"
        ).fetchone()[0]
        return stats

    def nearby_videos(
        self, 
        lat: float, 
        lon: float, 
        radius_km: float = 5.0,
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        Find videos within a radius using Haversine formula.
        
        Args:
            lat: Center latitude
            lon: Center longitude  
            radius_km: Search radius in kilometers (default: 5.0)
            limit: Maximum results to return
            
        Returns:
            List of video dicts with 'distance_km' field added
        """
        import math
        
        conn = self.connect()
        
        # Haversine formula components
        # Using SQLite math functions for calculation
        # 6371 is Earth's radius in kilometers
        
        rows = conn.execute(
            """
            SELECT *,
                (6371 * acos(
                    cos(radians(?)) * 
                    cos(radians(COALESCE(gps_latitude, 0))) * 
                    cos(radians(COALESCE(gps_longitude, 0)) - radians(?)) + 
                    sin(radians(?)) * 
                    sin(radians(COALESCE(gps_latitude, 0)))
                )) AS distance_km
            FROM videos
            WHERE gps_latitude IS NOT NULL 
              AND gps_longitude IS NOT NULL
              AND (6371 * acos(
                    cos(radians(?)) * 
                    cos(radians(gps_latitude)) * 
                    cos(radians(gps_longitude) - radians(?)) + 
                    sin(radians(?)) * 
                    sin(radians(gps_latitude))
                )) <= ?
            ORDER BY distance_km
            LIMIT ?
            """,
            (lat, lon, lat, lat, lon, lat, radius_km, limit)
        ).fetchall()
        
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Timeline / Date-based queries
    # ------------------------------------------------------------------

    def get_years_with_counts(self) -> list[dict[str, Any]]:
        """
        Get all years that have videos, with video counts and activity data.
        
        Returns list of dicts with year, count, and total_seconds.
        """
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT 
                strftime('%Y', creation_date) as year,
                COUNT(*) as count,
                COALESCE(SUM(duration_seconds), 0) as total_seconds
            FROM videos 
            WHERE creation_date IS NOT NULL
            GROUP BY year
            ORDER BY year DESC
            """
        ).fetchall()
        
        return [
            {
                "year": row[0],
                "count": row[1],
                "total_seconds": row[2]
            }
            for row in rows
        ]

    def get_year_activity_heatmap(self, year: int) -> list[dict[str, Any]]:
        """
        Get daily video counts for a year (for heatmap visualization).
        
        Returns list of dicts with date and count for each day with videos.
        """
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT 
                strftime('%Y-%m-%d', creation_date) as date,
                COUNT(*) as count,
                COALESCE(SUM(duration_seconds), 0) as total_seconds
            FROM videos 
            WHERE creation_date IS NOT NULL
              AND strftime('%Y', creation_date) = ?
            GROUP BY date
            ORDER BY date
            """,
            (str(year),)
        ).fetchall()
        
        return [
            {
                "date": row[0],
                "count": row[1],
                "total_seconds": row[2]
            }
            for row in rows
        ]

    def get_month_grid(self, year: int, month: int) -> list[dict[str, Any]]:
        """
        Get video counts for each day in a specific month.
        
        Returns list of dicts with day, count, and total_seconds.
        """
        conn = self.connect()
        # Pad month with leading zero if needed
        month_str = f"{year}-{month:02d}"
        
        rows = conn.execute(
            """
            SELECT 
                CAST(strftime('%d', creation_date) AS INTEGER) as day,
                COUNT(*) as count,
                COALESCE(SUM(duration_seconds), 0) as total_seconds
            FROM videos 
            WHERE creation_date IS NOT NULL
              AND strftime('%Y-%m', creation_date) = ?
            GROUP BY day
            ORDER BY day
            """,
            (month_str,)
        ).fetchall()
        
        return [
            {
                "day": row[0],
                "count": row[1],
                "total_seconds": row[2]
            }
            for row in rows
        ]

    def get_videos_by_date(self, date_str: str) -> list[dict[str, Any]]:
        """
        Get all videos for a specific date (YYYY-MM-DD format).
        
        Returns list of video dicts.
        """
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT * FROM videos 
            WHERE creation_date IS NOT NULL
              AND strftime('%Y-%m-%d', creation_date) = ?
            ORDER BY file_name
            """,
            (date_str,)
        ).fetchall()
        
        return [dict(row) for row in rows]

    def get_on_this_day(self, month: int, day: int, exclude_year: int | None = None) -> list[dict[str, Any]]:
        """
        Get videos from the same month/day across different years.
        
        Args:
            month: Month number (1-12)
            day: Day of month (1-31)
            exclude_year: Optional year to exclude (e.g., current year)
            
        Returns list of video dicts with year info.
        """
        conn = self.connect()
        
        sql = """
            SELECT *, strftime('%Y', creation_date) as year
            FROM videos 
            WHERE creation_date IS NOT NULL
              AND CAST(strftime('%m', creation_date) AS INTEGER) = ?
              AND CAST(strftime('%d', creation_date) AS INTEGER) = ?
        """
        params = [month, day]
        
        if exclude_year:
            sql += " AND strftime('%Y', creation_date) != ?"
            params.append(str(exclude_year))
        
        sql += " ORDER BY year DESC, file_name"
        
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_date_range(self) -> dict[str, str] | None:
        """
        Get the earliest and latest dates in the catalog.
        
        Returns dict with 'earliest' and 'latest' dates, or None if no dates.
        """
        conn = self.connect()
        row = conn.execute(
            """
            SELECT 
                MIN(creation_date) as earliest,
                MAX(creation_date) as latest
            FROM videos 
            WHERE creation_date IS NOT NULL
            """
        ).fetchone()
        
        if row and row[0] and row[1]:
            return {
                "earliest": row[0],
                "latest": row[1]
            }
        return None

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert_video(self, video: dict[str, Any]) -> int:
        """
        Insert a fully processed video record + its embedding vector.
        Returns the new row ID.
        """
        conn = self.connect()

        # Serialize tags list to JSON string if needed
        tags = video.get("tags")
        if isinstance(tags, list):
            tags = json.dumps(tags)

        cursor = conn.execute(
            """
            INSERT INTO videos (
                file_path, file_name, file_size, file_hash, source_device, lrf_path,
                duration_seconds, resolution, width, height, fps, codec, creation_date,
                gps_latitude, gps_longitude, gps_location_name, folder_location,
                gps_accuracy, location_source,
                scene_description, tags, mood, camera_movement, time_of_day,
                thumbnail_path, proxy_path, processed_at
            ) VALUES (
                :file_path, :file_name, :file_size, :file_hash, :source_device, :lrf_path,
                :duration_seconds, :resolution, :width, :height, :fps, :codec, :creation_date,
                :gps_latitude, :gps_longitude, :gps_location_name, :folder_location,
                :gps_accuracy, :location_source,
                :scene_description, :tags, :mood, :camera_movement, :time_of_day,
                :thumbnail_path, :proxy_path, :processed_at
            )
            """,
            {
                "file_path": video["relative_path"],
                "file_name": video["file_name"],
                "file_size": video.get("file_size"),
                "file_hash": video["file_hash"],
                "source_device": video.get("source_device"),
                "lrf_path": video.get("lrf_path"),
                "duration_seconds": video.get("duration_seconds"),
                "resolution": video.get("resolution"),
                "width": video.get("width"),
                "height": video.get("height"),
                "fps": video.get("fps"),
                "codec": video.get("codec"),
                "creation_date": video.get("creation_date"),
                "gps_latitude": video.get("gps_latitude"),
                "gps_longitude": video.get("gps_longitude"),
                "gps_location_name": video.get("gps_location_name"),
                "folder_location": video.get("folder_location"),
                "gps_accuracy": video.get("gps_accuracy"),
                "location_source": video.get("location_source", "folder"),
                "scene_description": video.get("scene_description"),
                "tags": tags,
                "mood": video.get("mood"),
                "camera_movement": video.get("camera_movement"),
                "time_of_day": video.get("time_of_day"),
                "thumbnail_path": video.get("thumbnail_path"),
                "proxy_path": video.get("proxy_path"),
                "processed_at": video.get(
                    "processed_at",
                    datetime.now(timezone.utc).isoformat(),
                ),
            },
        )

        video_id = cursor.lastrowid

        # Insert the embedding vector if provided
        embedding = video.get("embedding")
        if embedding and video_id:
            self._insert_embedding(video_id, embedding)

        conn.commit()
        return video_id

    def update_video(self, file_path: str, updates: dict[str, Any]):
        """Update specific fields on an existing video record."""
        conn = self.connect()

        if "tags" in updates and isinstance(updates["tags"], list):
            updates["tags"] = json.dumps(updates["tags"])

        set_clause = ", ".join(f"{key} = :{key}" for key in updates)
        updates["_file_path"] = file_path

        conn.execute(
            f"UPDATE videos SET {set_clause} WHERE file_path = :_file_path",
            updates,
        )
        conn.commit()

    def update_video_location(
        self, 
        video_id: int, 
        lat: float, 
        lon: float,
        location_name: str | None = None,
        accuracy: float | None = None
    ):
        """
        Update GPS coordinates for a video (manual override).
        
        Args:
            video_id: The video ID
            lat: Latitude
            lon: Longitude
            location_name: Optional location name
            accuracy: Optional accuracy in meters
        """
        conn = self.connect()
        
        updates = {
            "gps_latitude": lat,
            "gps_longitude": lon,
            "location_source": "manual"
        }
        
        if location_name:
            updates["gps_location_name"] = location_name
        if accuracy is not None:
            updates["gps_accuracy"] = accuracy
            
        set_clause = ", ".join(f"{key} = ?" for key in updates.keys())
        values = list(updates.values()) + [video_id]
        
        conn.execute(
            f"UPDATE videos SET {set_clause} WHERE id = ?",
            values,
        )
        conn.commit()

    def delete_video(self, video_id: int):
        """Delete a video record and its embedding."""
        conn = self.connect()
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        conn.execute("DELETE FROM videos_vec WHERE video_id = ?", (video_id,))
        conn.commit()

    # ------------------------------------------------------------------
    # Embedding / vector operations
    # ------------------------------------------------------------------

    def _insert_embedding(self, video_id: int, embedding: list[float]):
        """Insert a vector embedding for a video."""
        conn = self.connect()
        embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)
        conn.execute(
            "INSERT INTO videos_vec (video_id, description_embedding) VALUES (?, ?)",
            (video_id, embedding_bytes),
        )

    def update_embedding(self, video_id: int, embedding: list[float]):
        """Replace the embedding for a video."""
        conn = self.connect()
        conn.execute("DELETE FROM videos_vec WHERE video_id = ?", (video_id,))
        self._insert_embedding(video_id, embedding)
        conn.commit()

    # ------------------------------------------------------------------
    # Search operations
    # ------------------------------------------------------------------

    def keyword_search(self, query: str, limit: int = 20) -> list[tuple[int, float]]:
        """Full-text keyword search via FTS5. Returns [(video_id, rank), ...]."""
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT v.id, fts.rank
            FROM videos_fts fts
            JOIN videos v ON fts.rowid = v.id
            WHERE videos_fts MATCH ?
            ORDER BY fts.rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def vector_search(self, embedding: list[float], limit: int = 20) -> list[tuple[int, float]]:
        """Semantic vector search via sqlite-vec. Returns [(video_id, distance), ...]."""
        conn = self.connect()
        embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)
        rows = conn.execute(
            """
            SELECT video_id, distance
            FROM videos_vec
            WHERE description_embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (embedding_bytes, limit),
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def count_videos(self) -> int:
        """Quick count of total videos."""
        conn = self.connect()
        return conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]

    # ── Search Methods ──
    def search_fts(self, query: str, limit: int = 20) -> list[dict]:
        """
        Full-text keyword search using FTS5.

        Returns list of dicts with video_id and fts_rank (lower is better match).
        """
        sql = """
            SELECT v.id, fts.rank
            FROM videos_fts fts
            JOIN videos v ON v.id = fts.rowid
            WHERE videos_fts MATCH ?
            ORDER BY fts.rank
            LIMIT ?
        """
        try:
            rows = self._conn.execute(sql, (query, limit)).fetchall()
            return [{"video_id": row[0], "rank": row[1]} for row in rows]
        except Exception:
            # FTS5 can throw on malformed queries; return empty
            return []

    def search_vector(self, embedding: list[float], limit: int = 20) -> list[dict]:
        """
        Semantic similarity search using sqlite-vec.

        Returns list of dicts with video_id and distance (lower is more similar).
        """
        import json as _json
        import struct

        # sqlite-vec expects the query as a binary blob of floats
        query_blob = struct.pack(f"{len(embedding)}f", *embedding)

        sql = """
            SELECT video_id, distance
            FROM videos_vec
            WHERE embedding MATCH ?
            AND k = ?
            ORDER BY distance
        """
        rows = self._conn.execute(sql, (query_blob, limit)).fetchall()
        return [{"video_id": row[0], "distance": row[1]} for row in rows]

    def get_video_by_id(self, video_id: int) -> dict | None:
        """Fetch a single video record by ID."""
        row = self._conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not row:
            return None
        columns = [
            desc[0] for desc in self._conn.execute("SELECT * FROM videos LIMIT 0").description
        ]
        return dict(zip(columns, row))

    def get_videos_by_ids(self, video_ids: list[int]) -> list[dict]:
        """Fetch multiple video records by ID, preserving the input order."""
        if not video_ids:
            return []
        placeholders = ",".join("?" for _ in video_ids)
        sql = f"SELECT * FROM videos WHERE id IN ({placeholders})"
        rows = self._conn.execute(sql, video_ids).fetchall()
        columns = [
            desc[0] for desc in self._conn.execute("SELECT * FROM videos LIMIT 0").description
        ]

        # Build a lookup and return in the original order
        lookup = {}
        for row in rows:
            record = dict(zip(columns, row))
            lookup[record["id"]] = record
        return [lookup[vid] for vid in video_ids if vid in lookup]

    def get_all_videos(self, limit: int = 500, offset: int = 0) -> list[dict]:
        """Fetch all videos, most recent first."""
        sql = "SELECT * FROM videos ORDER BY creation_date DESC, id DESC LIMIT ? OFFSET ?"
        rows = self._conn.execute(sql, (limit, offset)).fetchall()
        columns = [
            desc[0] for desc in self._conn.execute("SELECT * FROM videos LIMIT 0").description
        ]
        return [dict(zip(columns, row)) for row in rows]

    def get_catalog_stats(self) -> dict:
        """Get summary statistics about the catalog."""
        stats = {}
        stats["total_videos"] = self._conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        stats["total_with_embeddings"] = self._conn.execute(
            "SELECT COUNT(*) FROM videos_vec"
        ).fetchone()[0]

        row = self._conn.execute("SELECT SUM(file_size) FROM videos").fetchone()
        stats["total_size_bytes"] = row[0] or 0

        row = self._conn.execute(
            "SELECT SUM(duration_seconds) FROM videos WHERE duration_seconds IS NOT NULL"
        ).fetchone()
        stats["total_duration_seconds"] = row[0] or 0

        row = self._conn.execute("SELECT COUNT(DISTINCT source_device) FROM videos").fetchone()
        stats["device_count"] = row[0] or 0

        row = self._conn.execute(
            "SELECT COUNT(*) FROM videos WHERE gps_latitude IS NOT NULL"
        ).fetchone()
        stats["geotagged_count"] = row[0] or 0

        row = self._conn.execute(
            "SELECT COUNT(*) FROM videos WHERE scene_description IS NOT NULL AND scene_description NOT LIKE 'ERROR%'"
        ).fetchone()
        stats["analyzed_count"] = row[0] or 0

        return stats

    # ------------------------------------------------------------------
    # Geocoding cache operations
    # ------------------------------------------------------------------

    def get_cached_location(self, location_name: str) -> dict[str, Any] | None:
        """
        Get cached geocoding result for a location name.
        
        Returns dict with 'lat', 'lon', 'cached_at' or None if not found.
        """
        conn = self.connect()
        row = conn.execute(
            "SELECT lat, lon, cached_at FROM location_cache WHERE location_name = ?",
            (location_name,)
        ).fetchone()
        
        if row:
            return {
                "lat": row[0],
                "lon": row[1],
                "cached_at": row[2]
            }
        return None

    def cache_location(self, location_name: str, lat: float, lon: float) -> bool:
        """
        Cache geocoding result for a location name.
        
        Returns True if successful.
        """
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO location_cache (location_name, lat, lon) 
                VALUES (?, ?, ?)
                ON CONFLICT(location_name) DO UPDATE SET
                    lat = excluded.lat,
                    lon = excluded.lon,
                    cached_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                """,
                (location_name, lat, lon)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error caching location: {e}")
            return False

    def get_all_cached_locations(self) -> list[dict[str, Any]]:
        """Get all cached location geocoding results."""
        conn = self.connect()
        rows = conn.execute(
            "SELECT location_name, lat, lon, cached_at FROM location_cache ORDER BY location_name"
        ).fetchall()

        return [
            {
                "location_name": row[0],
                "lat": row[1],
                "lon": row[2],
                "cached_at": row[3]
            }
            for row in rows
        ]

    def find_cached_location_by_query(self, query: str) -> dict[str, Any] | None:
        """
        Search cached locations by query - matches exact or partial search_key or display_name.

        Returns the most recently cached matching result, or None if not found.
        """
        conn = self.connect()
        search_term = f"%{query}%"
        row = conn.execute(
            """SELECT search_key, display_name, lat, lon, cached_at FROM location_cache
               WHERE search_key = ?
                  OR display_name LIKE ?
                  OR search_key LIKE ?
                  OR ? LIKE '%' || search_key || '%'
               ORDER BY cached_at DESC LIMIT 1""",
            (query, search_term, search_term, query)
        ).fetchone()

        if row:
            return {
                "search_key": row[0],
                "display_name": row[1],
                "lat": row[2],
                "lon": row[3],
                "cached_at": row[4]
            }
        return None

    def get_cached_location_by_search_key(self, search_key: str) -> dict[str, Any] | None:
        """
        Get cached location by exact search key match (case-insensitive).

        Returns dict with 'search_key', 'display_name', 'lat', 'lon', 'cached_at' or None.
        """
        conn = self.connect()
        row = conn.execute(
            """SELECT search_key, display_name, lat, lon, cached_at FROM location_cache
               WHERE search_key = ?""",
            (search_key.lower().strip(),)
        ).fetchone()

        if row:
            return {
                "search_key": row[0],
                "display_name": row[1],
                "lat": row[2],
                "lon": row[3],
                "cached_at": row[4]
            }
        return None

    def cache_location_with_display_name(
        self, search_key: str, display_name: str, lat: float, lon: float
    ) -> bool:
        """
        Cache a location with separate search key and display name.
        The search_key is normalized (lowercase) for matching queries.
        The display_name is the full pretty name shown to users.

        Returns True if successful.
        """
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO location_cache (search_key, display_name, location_name, lat, lon)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(search_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    location_name = excluded.location_name,
                    lat = excluded.lat,
                    lon = excluded.lon,
                    cached_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                """,
                (search_key.lower().strip(), display_name, display_name, lat, lon)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error caching location: {e}")
            return False

    def get_recent_cached_locations(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get most recently used cached locations, sorted by newest first."""
        conn = self.connect()
        rows = conn.execute(
            """SELECT display_name, lat, lon, cached_at FROM location_cache
               ORDER BY cached_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()

        return [
            {
                "display_name": row[0],
                "lat": row[1],
                "lon": row[2],
                "cached_at": row[3]
            }
            for row in rows
        ]

    def get_videos_with_coordinates(self, include_folder_locations: bool = True) -> list[dict[str, Any]]:
        """
        Get all videos that have GPS coordinates or can use cached folder location.
        
        Args:
            include_folder_locations: If True, also include videos with folder_location 
                                      that has a cached geocoding result
                                      
        Returns:
            List of video dicts with coordinates
        """
        conn = self.connect()
        
        # First get videos with direct GPS coordinates
        sql = """
            SELECT * FROM videos 
            WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL
        """
        rows = conn.execute(sql).fetchall()
        videos = [dict(row) for row in rows]
        
        if include_folder_locations:
            # Get folder locations that have been geocoded
            cache_rows = conn.execute(
                "SELECT location_name, lat, lon FROM location_cache"
            ).fetchall()
            
            # Build a lookup for quick access
            cache_lookup = {row[0]: {"lat": row[1], "lon": row[2]} for row in cache_rows}
            
            # Get videos with folder_location that have cached coordinates
            folder_rows = conn.execute(
                """
                SELECT * FROM videos 
                WHERE folder_location IS NOT NULL 
                AND (gps_latitude IS NULL OR gps_longitude IS NULL)
                """
            ).fetchall()
            
            for row in folder_rows:
                folder = row["folder_location"]
                if folder in cache_lookup:
                    video = dict(row)
                    video["gps_latitude"] = cache_lookup[folder]["lat"]
                    video["gps_longitude"] = cache_lookup[folder]["lon"]
                    video["location_source"] = "folder_cache"
                    videos.append(video)
        
        return videos

    def get_location_counts(self) -> list[dict[str, Any]]:
        """
        Get unique locations with video counts.
        
        Returns list of dicts with location info and video count.
        """
        conn = self.connect()
        
        # Get locations with direct GPS coordinates
        sql = """
            SELECT 
                COALESCE(gps_location_name, 'Unknown Location') as location_name,
                COUNT(*) as count,
                AVG(gps_latitude) as avg_lat,
                AVG(gps_longitude) as avg_lon
            FROM videos 
            WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL
            GROUP BY gps_location_name
            ORDER BY count DESC
        """
        rows = conn.execute(sql).fetchall()
        
        locations = []
        for row in rows:
            locations.append({
                "location_name": row[0],
                "count": row[1],
                "lat": row[2],
                "lon": row[3]
            })
        
        # Get folder locations with cached coordinates
        cache_rows = conn.execute(
            """
            SELECT lc.location_name, lc.lat, lc.lon,
                   COUNT(v.id) as count
            FROM location_cache lc
            JOIN videos v ON v.folder_location = lc.location_name
            WHERE v.gps_latitude IS NULL OR v.gps_longitude IS NULL
            GROUP BY lc.location_name
            ORDER BY count DESC
            """
        ).fetchall()
        
        for row in cache_rows:
            locations.append({
                "location_name": row[0],
                "count": row[3],
                "lat": row[1],
                "lon": row[2]
            })
        
        return locations

    # ------------------------------------------------------------------
    # Playlist operations
    # ------------------------------------------------------------------

    def create_playlist(self, name: str, description: str = None, color: str = "#3b82f6") -> int:
        """Create a new playlist and return its ID."""
        conn = self.connect()
        cursor = conn.execute(
            """
            INSERT INTO playlists (name, description, color)
            VALUES (?, ?, ?)
            """,
            (name, description, color)
        )
        conn.commit()
        return cursor.lastrowid

    def get_playlist(self, playlist_id: int) -> dict[str, Any] | None:
        """Get a single playlist by ID."""
        conn = self.connect()
        row = conn.execute(
            """
            SELECT p.*, COUNT(pi.id) as video_count
            FROM playlists p
            LEFT JOIN playlist_items pi ON p.id = pi.playlist_id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (playlist_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_playlists(self) -> list[dict[str, Any]]:
        """Get all playlists with video counts."""
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT p.*, COUNT(pi.id) as video_count
            FROM playlists p
            LEFT JOIN playlist_items pi ON p.id = pi.playlist_id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def update_playlist(self, playlist_id: int, updates: dict[str, Any]):
        """Update playlist fields."""
        conn = self.connect()
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        sql = f"UPDATE playlists SET {set_clause} WHERE id = ?"
        conn.execute(sql, list(updates.values()) + [playlist_id])
        conn.commit()

    def delete_playlist(self, playlist_id: int):
        """Delete a playlist and all its items."""
        conn = self.connect()
        conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        conn.commit()

    def add_video_to_playlist(self, playlist_id: int, video_id: int, position: int = None) -> int:
        """Add a video to a playlist. Returns the item ID."""
        conn = self.connect()
        
        if position is None:
            # Get next position
            row = conn.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,)
            ).fetchone()
            position = row[0]
        
        try:
            cursor = conn.execute(
                """
                INSERT INTO playlist_items (playlist_id, video_id, position)
                VALUES (?, ?, ?)
                """,
                (playlist_id, video_id, position)
            )
            conn.execute(
                "UPDATE playlists SET updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), playlist_id)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Video already in playlist
            return None

    def remove_video_from_playlist(self, playlist_id: int, video_id: int):
        """Remove a video from a playlist."""
        conn = self.connect()
        conn.execute(
            "DELETE FROM playlist_items WHERE playlist_id = ? AND video_id = ?",
            (playlist_id, video_id)
        )
        conn.execute(
            "UPDATE playlists SET updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), playlist_id)
        )
        conn.commit()

    def get_playlist_items(self, playlist_id: int) -> list[dict[str, Any]]:
        """Get all videos in a playlist with their positions."""
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT v.*, pi.position, pi.added_at as item_added_at, pi.id as item_id
            FROM playlist_items pi
            JOIN videos v ON pi.video_id = v.id
            WHERE pi.playlist_id = ?
            ORDER BY pi.position
            """,
            (playlist_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def reorder_playlist_item(self, playlist_id: int, video_id: int, new_position: int):
        """Move a video to a new position in the playlist."""
        conn = self.connect()
        
        conn.execute("BEGIN TRANSACTION")
        try:
            # Get current position
            row = conn.execute(
                "SELECT position FROM playlist_items WHERE playlist_id = ? AND video_id = ?",
                (playlist_id, video_id)
            ).fetchone()
            
            if not row:
                conn.execute("ROLLBACK")
                return
            
            old_position = row[0]
            
            if old_position == new_position:
                conn.execute("ROLLBACK")
                return
            
            if old_position < new_position:
                # Moving down: decrement positions between old and new
                conn.execute(
                    """
                    UPDATE playlist_items
                    SET position = position - 1
                    WHERE playlist_id = ? AND position > ? AND position <= ?
                    """,
                    (playlist_id, old_position, new_position)
                )
            else:
                # Moving up: increment positions between new and old
                conn.execute(
                    """
                    UPDATE playlist_items
                    SET position = position + 1
                    WHERE playlist_id = ? AND position >= ? AND position < ?
                    """,
                    (playlist_id, new_position, old_position)
                )
            
            # Update the moved item
            conn.execute(
                "UPDATE playlist_items SET position = ? WHERE playlist_id = ? AND video_id = ?",
                (new_position, playlist_id, video_id)
            )
            
            conn.execute(
                "UPDATE playlists SET updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), playlist_id)
            )
            
            conn.commit()
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_playlists_containing_video(self, video_id: int) -> list[dict[str, Any]]:
        """Get all playlists that contain a specific video."""
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT p.*, pi.position
            FROM playlists p
            JOIN playlist_items pi ON p.id = pi.playlist_id
            WHERE pi.video_id = ?
            ORDER BY p.name
            """,
            (video_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Filter query builder for structured search
    # ------------------------------------------------------------------

    def build_filtered_query(
        self, filters: dict[str, Any]
    ) -> tuple[str, list[Any]]:
        """
        Build WHERE clause and parameters for structured filters.

        Args:
            filters: Dict with filter criteria:
                - duration_min, duration_max: float (seconds)
                - min_width, min_height: int (pixels)
                - aspect_ratio: str (e.g., "16:9", "4:3", "9:16")
                - orientation: str ("portrait", "landscape", "square")
                - date_from, date_to: str (ISO date strings)
                - mood: str (exact match)
                - movement: str (camera_movement exact match)
                - time_of_day: str (exact match)
                - location: str (LIKE pattern match on gps_location_name)
                - device: str (exact match on source_device)

        Returns:
            Tuple of (WHERE clause string without "WHERE" prefix, list of params)
        """
        conditions: list[str] = []
        params: list[Any] = []

        # Duration filters
        if "duration_min" in filters:
            conditions.append("duration_seconds >= ?")
            params.append(filters["duration_min"])
        if "duration_max" in filters:
            conditions.append("duration_seconds <= ?")
            params.append(filters["duration_max"])

        # Resolution filters
        if "min_width" in filters:
            conditions.append("width >= ?")
            params.append(filters["min_width"])
        if "min_height" in filters:
            conditions.append("height >= ?")
            params.append(filters["min_height"])

        # Aspect ratio filter (with 5% tolerance)
        if "aspect_ratio" in filters:
            target = filters["aspect_ratio"]
            # Parse aspect ratio like "16:9" or "4:3"
            if ":" in target:
                try:
                    w, h = target.split(":")
                    ratio = float(w) / float(h)
                    # Allow 5% tolerance
                    tolerance = ratio * 0.05
                    min_ratio = ratio - tolerance
                    max_ratio = ratio + tolerance
                    conditions.append("CAST(width AS REAL) / height BETWEEN ? AND ?")
                    params.append(min_ratio)
                    params.append(max_ratio)
                except (ValueError, ZeroDivisionError):
                    pass  # Invalid aspect ratio, skip

        # Orientation filter
        if "orientation" in filters:
            orient = filters["orientation"]
            if orient == "portrait":
                conditions.append("height > width")
            elif orient == "landscape":
                conditions.append("width > height")
            elif orient == "square":
                conditions.append("width = height")

        # Date range filters
        if "date_from" in filters:
            conditions.append("creation_date >= ?")
            params.append(filters["date_from"])
        if "date_to" in filters:
            conditions.append("creation_date <= ?")
            params.append(filters["date_to"])

        # Metadata filters
        if "mood" in filters:
            conditions.append("mood = ?")
            params.append(filters["mood"])
        if "movement" in filters:
            conditions.append("camera_movement = ?")
            params.append(filters["movement"])
        if "time_of_day" in filters:
            conditions.append("time_of_day = ?")
            params.append(filters["time_of_day"])

        # Location filter (LIKE pattern)
        if "location" in filters:
            conditions.append("gps_location_name LIKE ?")
            params.append(f"%{filters['location']}%")

        # Device filter
        if "device" in filters:
            conditions.append("source_device = ?")
            params.append(filters["device"])

        if conditions:
            return " AND ".join(conditions), params
        else:
            return "1=1", []  # No filters, match all

    def get_filtered_ids(
        self, filters: dict[str, Any], limit: int = 1000
    ) -> list[int]:
        """
        Get video IDs matching the structured filters.

        Args:
            filters: Dict with filter criteria (see build_filtered_query)
            limit: Maximum number of IDs to return

        Returns:
            List of video IDs matching all filters
        """
        where_clause, params = self.build_filtered_query(filters)
        conn = self.connect()

        sql = f"""
            SELECT id FROM videos
            WHERE {where_clause}
            ORDER BY creation_date DESC
            LIMIT ?
        """
        rows = conn.execute(sql, (*params, limit)).fetchall()
        return [row[0] for row in rows]

    def get_videos_by_filters(
        self, filters: dict[str, Any], limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """
        Fetch full video records matching the structured filters.

        Args:
            filters: Dict with filter criteria (see build_filtered_query)
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of video dicts matching all filters
        """
        where_clause, params = self.build_filtered_query(filters)
        conn = self.connect()

        sql = f"""
            SELECT * FROM videos
            WHERE {where_clause}
            ORDER BY creation_date DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(sql, (*params, limit, offset)).fetchall()
        columns = [
            desc[0] for desc in conn.execute("SELECT * FROM videos LIMIT 0").description
        ]
        return [dict(zip(columns, row)) for row in rows]
