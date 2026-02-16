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

        conn.commit()
        print(f"✅ Database initialized at {self.db_path}")

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
        row = conn.execute(
            "SELECT * FROM videos WHERE file_path = ?", (file_path,)
        ).fetchone()
        return dict(row) if row else None

    def get_video_by_id(self, video_id: int) -> dict[str, Any] | None:
        """Fetch a single video record by its ID."""
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_videos(
        self, limit: int = 100, offset: int = 0, order_by: str = "creation_date DESC"
    ) -> list[dict[str, Any]]:
        """Fetch all videos with pagination."""
        conn = self.connect()
        # Whitelist allowed order_by values to prevent SQL injection
        allowed_orders = {
            "creation_date DESC", "creation_date ASC",
            "file_name ASC", "file_name DESC",
            "duration_seconds DESC", "duration_seconds ASC",
            "processed_at DESC", "processed_at ASC",
        }
        if order_by not in allowed_orders:
            order_by = "creation_date DESC"

        rows = conn.execute(
            f"SELECT * FROM videos ORDER BY {order_by} LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics about the catalog."""
        conn = self.connect()
        stats = {}
        stats["total_videos"] = conn.execute(
            "SELECT COUNT(*) FROM videos"
        ).fetchone()[0]
        stats["total_duration_seconds"] = conn.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM videos"
        ).fetchone()[0]
        stats["total_size_bytes"] = conn.execute(
            "SELECT COALESCE(SUM(file_size), 0) FROM videos"
        ).fetchone()[0]
        stats["devices"] = [
            row[0] for row in conn.execute(
                "SELECT DISTINCT source_device FROM videos WHERE source_device IS NOT NULL"
            ).fetchall()
        ]
        stats["locations"] = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE gps_location_name IS NOT NULL"
        ).fetchone()[0]
        return stats

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
                gps_latitude, gps_longitude, gps_location_name,
                scene_description, tags, mood, camera_movement, time_of_day,
                thumbnail_path, processed_at
            ) VALUES (
                :file_path, :file_name, :file_size, :file_hash, :source_device, :lrf_path,
                :duration_seconds, :resolution, :width, :height, :fps, :codec, :creation_date,
                :gps_latitude, :gps_longitude, :gps_location_name,
                :scene_description, :tags, :mood, :camera_movement, :time_of_day,
                :thumbnail_path, :processed_at
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
                "scene_description": video.get("scene_description"),
                "tags": tags,
                "mood": video.get("mood"),
                "camera_movement": video.get("camera_movement"),
                "time_of_day": video.get("time_of_day"),
                "thumbnail_path": video.get("thumbnail_path"),
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

    def vector_search(
        self, embedding: list[float], limit: int = 20
    ) -> list[tuple[int, float]]:
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
        row = self._conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in self._conn.execute("SELECT * FROM videos LIMIT 0").description]
        return dict(zip(columns, row))

    def get_videos_by_ids(self, video_ids: list[int]) -> list[dict]:
        """Fetch multiple video records by ID, preserving the input order."""
        if not video_ids:
            return []
        placeholders = ",".join("?" for _ in video_ids)
        sql = f"SELECT * FROM videos WHERE id IN ({placeholders})"
        rows = self._conn.execute(sql, video_ids).fetchall()
        columns = [desc[0] for desc in self._conn.execute("SELECT * FROM videos LIMIT 0").description]

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
        columns = [desc[0] for desc in self._conn.execute("SELECT * FROM videos LIMIT 0").description]
        return [dict(zip(columns, row)) for row in rows]

    def get_catalog_stats(self) -> dict:
        """Get summary statistics about the catalog."""
        stats = {}
        stats["total_videos"] = self._conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        stats["total_with_embeddings"] = self._conn.execute("SELECT COUNT(*) FROM videos_vec").fetchone()[0]

        row = self._conn.execute("SELECT SUM(file_size) FROM videos").fetchone()
        stats["total_size_bytes"] = row[0] or 0

        row = self._conn.execute("SELECT SUM(duration_seconds) FROM videos WHERE duration_seconds IS NOT NULL").fetchone()
        stats["total_duration_seconds"] = row[0] or 0

        row = self._conn.execute("SELECT COUNT(DISTINCT source_device) FROM videos").fetchone()
        stats["device_count"] = row[0] or 0

        row = self._conn.execute("SELECT COUNT(*) FROM videos WHERE gps_latitude IS NOT NULL").fetchone()
        stats["geotagged_count"] = row[0] or 0

        row = self._conn.execute(
            "SELECT COUNT(*) FROM videos WHERE scene_description IS NOT NULL AND scene_description NOT LIKE 'ERROR%'"
        ).fetchone()
        stats["analyzed_count"] = row[0] or 0

        return stats

