"""
OpenClaw Agent API for programmatic access to the B-roll catalog.

This lightweight Flask API exposes endpoints for AI assistants to query
the catalog without using the CLI or web UI.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

from .config import get_db_path, get_thumbs_dir, AGENT_API_HOST, AGENT_API_PORT
from .db import Database
from .search import hybrid_search, keyword_search, semantic_search
from .chat import chat_with_catalog


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

    def get_db() -> Database:
        """Get a database connection."""
        return Database(db_path)

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

        with get_db() as db:
            s = db.get_catalog_stats()

        return jsonify({
            "total_videos": s["total_videos"],
            "analyzed_count": s["analyzed_count"],
            "total_with_embeddings": s["total_with_embeddings"],
            "geotagged_count": s["geotagged_count"],
            "device_count": s["device_count"],
            "total_size_bytes": s["total_size_bytes"],
            "total_duration_seconds": s["total_duration_seconds"],
        })

    @app.route("/search", methods=["GET"])
    def search() -> dict:
        """
        Search the catalog.

        Query params:
            q: Search query string
            mode: "hybrid" (default), "keyword", or "semantic"
            limit: Max results (default 10)
        """
        if not db_path.exists():
            return jsonify({"error": "Database not found"}), 404

        query = request.args.get("q", "")
        mode = request.args.get("mode", "hybrid")
        limit = request.args.get("limit", 10, type=int)

        if not query:
            return jsonify({"error": "Missing query parameter 'q'"}), 400

        with get_db() as db:
            if mode == "keyword":
                results = keyword_search(query, db, limit)
            elif mode == "semantic":
                results = semantic_search(query, db, limit)
            else:
                results = hybrid_search(query, db, limit)

        # Simplify results for JSON response
        simplified = [_simplify_video(v) for v in results]

        return jsonify({
            "query": query,
            "mode": mode,
            "count": len(simplified),
            "results": simplified,
        })

    @app.route("/video/<int:video_id>", methods=["GET"])
    def get_video(video_id: int) -> dict:
        """Get a single video by ID."""
        if not db_path.exists():
            return jsonify({"error": "Database not found"}), 404

        with get_db() as db:
            video = db.get_video_by_id(video_id)

        if not video:
            return jsonify({"error": "Video not found"}), 404

        return jsonify(_simplify_video(video))

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

        with get_db() as db:
            if location:
                # Search in gps_location_name and file_path for location
                pattern = f"%{location}%"
                sql = """
                    SELECT * FROM videos
                    WHERE gps_location_name LIKE ? OR file_path LIKE ?
                    ORDER BY create_date
                    LIMIT ?
                """
                results = db._execute(sql, (pattern, pattern, limit)).fetchall()
            elif device:
                sql = "SELECT * FROM videos WHERE source_device = ? LIMIT ?"
                results = db._execute(sql, (device, limit)).fetchall()
            else:
                sql = "SELECT * FROM videos ORDER BY file_path LIMIT ?"
                results = db._execute(sql, (limit,)).fetchall()

        simplified = [_simplify_video(dict(r)) for r in results]

        return jsonify({
            "count": len(simplified),
            "results": simplified,
        })

    @app.route("/thumbnail/<int:video_id>", methods=["GET"])
    def get_thumbnail(video_id: int) -> Any:
        """Get the thumbnail image for a video."""
        if not db_path.exists():
            return jsonify({"error": "Database not found"}), 404

        with get_db() as db:
            video = db.get_video_by_id(video_id)

        if not video:
            return jsonify({"error": "Video not found"}), 404

        # Try to find thumbnail by hash
        file_hash = video.get("file_hash")
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
        history = data.get("history", [])

        if not message:
            return jsonify({"error": "Missing 'message' field"}), 400

        with get_db() as db:
            result = chat_with_catalog(message, db, history)

        return jsonify({
            "response": result["response"],
            "videos": [_simplify_video(v) for v in result["videos"]],
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
