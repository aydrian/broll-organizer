"""
OpenClaw Agent API for programmatic access to the B-roll catalog.

This lightweight Flask API exposes endpoints for AI assistants to query
the catalog without using the CLI or web UI.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

from .config import get_db_path, get_thumbs_dir, AGENT_API_HOST, AGENT_API_PORT


def create_agent_app(drive_path: str | Path) -> Flask:
    """
    Create the Flask app for the agent API.

    Args:
        drive_path: Root path to the external drive containing the catalog.

    Returns:
        Configured Flask application.
    """
    drive = Path(drive_path)
    db_path = get_db_path(drive)
    thumbs_dir = get_thumbs_dir(drive)

    app = Flask(__name__)
    app.config["DRIVE_PATH"] = drive
    app.config["DB_PATH"] = db_path
    app.config["THUMBS_DIR"] = thumbs_dir

    def get_db_conn() -> sqlite3.Connection:
        """Get a simple database connection (without sqlite-vec for queries)."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @app.route("/health", methods=["GET"])
    def health() -> dict:
        """Health check endpoint."""
        return jsonify({
            "status": "ok",
            "drive": str(drive),
            "database_exists": db_path.exists(),
        })

    @app.route("/stats", methods=["GET"])
    def stats() -> dict:
        """Get catalog statistics."""
        if not db_path.exists():
            return jsonify({"error": "Database not found"}), 404

        conn = get_db_conn()
        cursor = conn.cursor()

        stats = {}

        # Total videos
        cursor.execute("SELECT COUNT(*) FROM videos")
        stats["total_videos"] = cursor.fetchone()[0]

        # Videos with descriptions
        cursor.execute("SELECT COUNT(*) FROM videos WHERE scene_description IS NOT NULL AND scene_description != ''")
        stats["analyzed_count"] = cursor.fetchone()[0]

        # Videos with embeddings (check if column exists first)
        try:
            cursor.execute("SELECT COUNT(*) FROM videos WHERE embedding IS NOT NULL")
            stats["total_with_embeddings"] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            stats["total_with_embeddings"] = 0

        # Geotagged
        cursor.execute("SELECT COUNT(*) FROM videos WHERE gps_latitude IS NOT NULL")
        stats["geotagged_count"] = cursor.fetchone()[0]

        # Source devices
        cursor.execute("SELECT COUNT(DISTINCT source_device) FROM videos")
        stats["device_count"] = cursor.fetchone()[0]

        # Total size and duration
        cursor.execute("SELECT SUM(file_size), SUM(duration_seconds) FROM videos")
        row = cursor.fetchone()
        stats["total_size_bytes"] = row[0] or 0
        stats["total_duration_seconds"] = row[1] or 0

        conn.close()

        return jsonify(stats)

    @app.route("/search", methods=["GET"])
    def search() -> dict:
        """
        Search the catalog using FTS5.

        Query params:
            q: Search query string
            limit: Max results (default 10)
        """
        if not db_path.exists():
            return jsonify({"error": "Database not found"}), 404

        query = request.args.get("q", "")
        limit = request.args.get("limit", 10, type=int)

        if not query:
            return jsonify({"error": "Missing query parameter 'q'"}), 400

        conn = get_db_conn()

        # Use FTS5 for full-text search
        sql = """
            SELECT v.*, rank
            FROM videos v
            JOIN videos_fts fts ON v.id = fts.rowid
            WHERE videos_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """

        try:
            cursor = conn.execute(sql, (query, limit))
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            # Fallback if FTS fails
            pattern = f"%{query}%"
            sql = """
                SELECT v.*, 0 as rank
                FROM videos v
                WHERE scene_description LIKE ?
                   OR file_name LIKE ?
                   OR tags LIKE ?
                LIMIT ?
            """
            cursor = conn.execute(sql, (pattern, pattern, pattern, limit))
            rows = cursor.fetchall()

        conn.close()

        # Simplify results for JSON response
        simplified = [_simplify_video(dict(r)) for r in rows]

        return jsonify({
            "query": query,
            "count": len(simplified),
            "results": simplified,
        })

    @app.route("/video/<int:video_id>", methods=["GET"])
    def get_video(video_id: int) -> dict:
        """Get a single video by ID."""
        if not db_path.exists():
            return jsonify({"error": "Database not found"}), 404

        conn = get_db_conn()
        cursor = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"error": "Video not found"}), 404

        return jsonify(_simplify_video(dict(row)))

    @app.route("/videos", methods=["GET"])
    def list_videos() -> dict:
        """
        List videos with optional filtering.

        Query params:
            limit: Max results (default 50)
            location: Filter by location name
            device: Filter by source device
        """
        if not db_path.exists():
            return jsonify({"error": "Database not found"}), 404

        limit = request.args.get("limit", 50, type=int)
        location = request.args.get("location")
        device = request.args.get("device")

        conn = get_db_conn()

        if location:
            # Search in gps_location_name and file_path for location
            pattern = f"%{location}%"
            sql = """
                SELECT * FROM videos
                WHERE gps_location_name LIKE ? OR file_path LIKE ?
                ORDER BY create_date
                LIMIT ?
            """
            cursor = conn.execute(sql, (pattern, pattern, limit))
        elif device:
            sql = "SELECT * FROM videos WHERE source_device = ? LIMIT ?"
            cursor = conn.execute(sql, (device, limit))
        else:
            sql = "SELECT * FROM videos ORDER BY file_path LIMIT ?"
            cursor = conn.execute(sql, (limit,))

        rows = cursor.fetchall()
        conn.close()

        simplified = [_simplify_video(dict(r)) for r in rows]

        return jsonify({
            "count": len(simplified),
            "results": simplified,
        })

    @app.route("/thumbnail/<int:video_id>", methods=["GET"])
    def get_thumbnail(video_id: int) -> Any:
        """Get the thumbnail image for a video."""
        if not db_path.exists():
            return jsonify({"error": "Database not found"}), 404

        conn = get_db_conn()
        cursor = conn.execute("SELECT file_hash FROM videos WHERE id = ?", (video_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"error": "Video not found"}), 404

        # Try to find thumbnail by hash
        file_hash = row[0]
        if file_hash:
            thumb_path = thumbs_dir / f"{file_hash}.jpg"
            if thumb_path.exists():
                from flask import send_file
                return send_file(thumb_path, mimetype="image/jpeg")

        return jsonify({"error": "Thumbnail not found"}), 404

    @app.route("/chat", methods=["POST"])
    def chat() -> dict:
        """
        Chat with the catalog.

        Request body (JSON):
            message: User message string
            history: Optional list of previous messages [{role, content}, ...]
        """
        if not db_path.exists():
            return jsonify({"error": "Database not found"}), 404

        data = request.get_json() or {}
        message = data.get("message", "")

        if not message:
            return jsonify({"error": "Missing 'message' field"}), 400

        # Simple keyword search from the message
        # (Full chat with LLM requires additional setup)
        search_terms = " ".join([w for w in message.lower().split() if len(w) > 3])

        conn = get_db_conn()

        try:
            # Try FTS first
            sql = """
                SELECT v.*, rank
                FROM videos v
                JOIN videos_fts fts ON v.id = fts.rowid
                WHERE videos_fts MATCH ?
                ORDER BY rank
                LIMIT 5
            """
            cursor = conn.execute(sql, (search_terms,))
            rows = cursor.fetchall()
        except:
            # Fallback
            pattern = f"%{search_terms}%"
            sql = """
                SELECT v.*, 0 as rank
                FROM videos v
                WHERE scene_description LIKE ? OR tags LIKE ?
                LIMIT 5
            """
            cursor = conn.execute(sql, (pattern, pattern))
            rows = cursor.fetchall()

        conn.close()

        videos = [_simplify_video(dict(r)) for r in rows]

        return jsonify({
            "response": f"Found {len(videos)} videos related to your query.",
            "videos": videos,
        })

    return app


def _simplify_video(video: dict) -> dict:
    """Simplify video dict for API response."""
    return {
        "id": video.get("id"),
        "file_name": video.get("file_name"),
        "file_path": video.get("file_path"),
        "file_hash": video.get("file_hash"),
        "duration_seconds": video.get("duration_seconds"),
        "resolution": video.get("resolution"),
        "source_device": video.get("source_device"),
        "scene_description": video.get("scene_description"),
        "tags": video.get("tags"),
        "mood": video.get("mood"),
        "camera_movement": video.get("camera_movement"),
        "time_of_day": video.get("time_of_day"),
        "gps_location_name": video.get("gps_location_name"),
        "creation_date": video.get("creation_date"),
    }
