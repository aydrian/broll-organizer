# src/broll/web/app.py
"""
Flask web application for browsing, searching, and chatting
with the b-roll catalog.
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import (
    Flask,
    abort,
    current_app,
    g,
    jsonify,
    render_template,
    request,
    send_file,
)

from ..config import get_db_path, get_thumbs_dir
from ..db import Database


def create_app(drive_path: str) -> Flask:
    """Factory function to create and configure the Flask app."""
    drive = Path(drive_path).resolve()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.config["DRIVE_PATH"] = str(drive)
    app.config["DB_PATH"] = str(get_db_path(drive))
    app.config["THUMBS_DIR"] = str(get_thumbs_dir(drive))
    app.config["SECRET_KEY"] = "broll-local-dev"

    # ── Jinja2 filters ──

    @app.template_filter("parse_tags")
    def parse_tags_filter(value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            return [value] if value else []
        return []

    @app.template_filter("duration")
    def duration_filter(seconds):
        if not seconds:
            return "--:--"
        total = int(seconds)
        mins = total // 60
        secs = total % 60
        return f"{mins}:{secs:02d}"

    @app.template_filter("filesize")
    def filesize_filter(size_bytes):
        if not size_bytes:
            return "?"
        gb = size_bytes / (1024**3)
        if gb >= 1:
            return f"{gb:.1f} GB"
        mb = size_bytes / (1024**2)
        return f"{mb:.0f} MB"

    # ── Database helper ──

    def get_db() -> Database:
        if "db" not in g:
            g.db = Database(current_app.config["DB_PATH"])
            g.db.connect()
        return g.db

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop("db", None)
        if db and hasattr(db, "_conn") and db._conn:
            db._conn.close()

    # ── Routes ──

    @app.route("/")
    def browse():
        """Render the browse page shell."""
        # We pass initial stats but no videos, as the frontend will fetch them.
        db = get_db()
        stats = db.get_catalog_stats()

        # Check if there's a specific video to highlight/scroll to (optional, but good for deep linking)
        # For now, just render the shell.
        return render_template(
            "browse.html",
            stats=stats,
        )

    @app.route("/api/browse")
    def api_browse():
        """JSON API for browsing folders and videos."""
        path = request.args.get("path", "")
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 24, type=int)

        offset = (page - 1) * limit
        db = get_db()

        # Use our new folder-aware query
        contents = db.get_folder_contents(folder_path=path, limit=limit, offset=offset)

        # Calculate pagination for videos only (folders don't paginate currently)
        # Note: We don't have a cheap "count videos in this folder" query yet.
        # For infinite scroll, we can just return what we have.
        # If we return fewer than limit videos, the frontend knows it's the end.

        return jsonify(
            {
                "path": path,
                "folders": contents["folders"],
                "videos": contents["videos"],
                "page": page,
                "has_more": len(contents["videos"]) == limit,
            }
        )

    @app.route("/search")
    def search_page():
        from ..search import hybrid_search, keyword_search, semantic_search

        query = request.args.get("q", "").strip()
        mode = request.args.get("mode", "hybrid")
        limit = request.args.get("limit", 20, type=int)

        if not query:
            return render_template("search_results.html", query="", results=[], mode=mode)

        db = get_db()

        if mode == "keyword":
            results = keyword_search(query, db, limit)
        elif mode == "semantic":
            results = semantic_search(query, db, limit)
        else:
            results = hybrid_search(query, db, limit)

        return render_template(
            "search_results.html",
            query=query,
            results=results,
            mode=mode,
        )

    @app.route("/video/<int:video_id>")
    def video_detail(video_id: int):
        db = get_db()
        video = db.get_video_by_id(video_id)
        if not video:
            abort(404)
        return render_template("video_detail.html", video=video)

    @app.route("/chat")
    def chat_page():
        return render_template("chat.html")

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        from ..chat import chat_with_catalog

        data = request.get_json()
        if not data or not data.get("message"):
            return jsonify({"error": "No message provided"}), 400

        db = get_db()
        history = data.get("history", [])

        result = chat_with_catalog(data["message"], db, history)
        return jsonify(result)

    @app.route("/thumbnail/<file_hash>")
    def thumbnail(file_hash: str):
        # Sanitize the hash to prevent path traversal
        safe_hash = "".join(c for c in file_hash if c.isalnum())
        thumb_path = Path(current_app.config["THUMBS_DIR"]) / f"{safe_hash}.jpg"
        if thumb_path.exists():
            return send_file(thumb_path, mimetype="image/jpeg")
        abort(404)

    @app.route("/video/stream/<int:video_id>")
    def stream_video(video_id: int):
        db = get_db()
        video = db.get_video_by_id(video_id)
        if not video:
            abort(404)

        drive = Path(current_app.config["DRIVE_PATH"])
        video_path = drive / video["file_path"]

        if not video_path.exists():
            abort(404)

        return send_file(
            video_path,
            mimetype="video/mp4",
            conditional=True,
        )

    @app.route("/api/stats")
    def api_stats():
        db = get_db()
        return jsonify(db.get_catalog_stats())

    return app
