"""
Flask web application for browsing and searching the b-roll catalog.

Uses plain sqlite3 to avoid sqlite-vec architecture issues on Raspberry Pi.
Implements connection pooling using thread-local storage for improved performance.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
)

from ..config import get_db_path, get_thumbs_dir

# Thread-local storage for database connections per thread
_thread_local = threading.local()


def _get_thread_db_connection(db_path: str) -> sqlite3.Connection:
    """
    Get a thread-local database connection.
    
    Each thread gets its own connection stored in thread-local storage.
    Connections are reused across requests within the same thread,
    reducing connection overhead.
    
    Args:
        db_path: Path to the SQLite database file.
        
    Returns:
        A sqlite3 connection with Row factory configured.
    """
    # Use thread-local storage to ensure thread safety with SQLite
    if not hasattr(_thread_local, 'db_connections'):
        _thread_local.db_connections = {}
    
    if db_path not in _thread_local.db_connections:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _thread_local.db_connections[db_path] = conn
    
    return _thread_local.db_connections[db_path]


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

    # ── Drive connection check ──
    
    @app.before_request
    def check_drive_connected():
        """Check if the external drive is connected before each request."""
        db_path = Path(current_app.config["DB_PATH"])
        
        # Skip check for static files and the drive_not_connected page itself
        if request.path.startswith('/static/'):
            return None
        
        if not db_path.exists():
            # For API requests, return JSON error
            if request.path.startswith('/api/'):
                return jsonify({
                    "error": "Drive not connected",
                    "message": "Please connect the external drive containing your B-roll catalog"
                }), 503
            # For web requests, show the drive not connected page
            return render_template("drive_not_connected.html"), 503

    # ── Database helper ──

    def get_db_conn() -> sqlite3.Connection:
        """
        Get a database connection with thread-local caching.
        
        Uses thread-local storage to maintain one connection per thread,
        reducing connection overhead for concurrent requests.
        
        Returns:
            A sqlite3 connection with Row factory configured.
        """
        return _get_thread_db_connection(current_app.config["DB_PATH"])

    @app.teardown_appcontext
    def close_db(exc):
        """
        Cleanup at end of request.
        
        Note: With connection pooling via thread-local storage, we don't close
        the connection here. The connection remains open for reuse by the same
        thread in subsequent requests.
        """
        pass

    def get_stats() -> dict:
        """Get catalog statistics."""
        conn = get_db_conn()
        cursor = conn.cursor()

        stats = {}
        cursor.execute("SELECT COUNT(*) FROM videos")
        stats["total_videos"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM videos WHERE scene_description IS NOT NULL AND scene_description != ''")
        stats["analyzed_count"] = cursor.fetchone()[0]

        try:
            cursor.execute("SELECT COUNT(*) FROM videos WHERE embedding IS NOT NULL")
            stats["total_with_embeddings"] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            stats["total_with_embeddings"] = 0

        cursor.execute("SELECT COUNT(*) FROM videos WHERE gps_latitude IS NOT NULL")
        stats["geotagged_count"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT source_device) FROM videos")
        stats["device_count"] = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(file_size), SUM(duration_seconds) FROM videos")
        row = cursor.fetchone()
        stats["total_size_bytes"] = row[0] or 0
        stats["total_duration_seconds"] = row[1] or 0

        return stats

    def get_video_by_id(video_id: int) -> dict | None:
        """Get a single video by ID."""
        conn = get_db_conn()
        cursor = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_folder_contents(folder_path: str = "", limit: int = 24, offset: int = 0) -> dict:
        """Get folder contents (folders and videos)."""
        conn = get_db_conn()

        # Build the folder prefix pattern
        if folder_path:
            prefix = folder_path + "/"
        else:
            prefix = ""

        # Get subfolders (distinct first path component after prefix)
        folder_sql = """
            SELECT DISTINCT 
                CASE 
                    WHEN instr(substr(file_path, ?), '/') > 0 
                    THEN substr(substr(file_path, ?), 1, instr(substr(file_path, ?), '/') - 1)
                    ELSE substr(file_path, ?)
                END as folder_name
            FROM videos
            WHERE file_path LIKE ?
            ORDER BY folder_name
        """
        prefix_len = len(prefix) + 1
        like_pattern = prefix + "%"

        cursor = conn.execute(folder_sql, (prefix_len, prefix_len, prefix_len, prefix_len, like_pattern))
        folder_rows = cursor.fetchall()

        folders = []
        for row in folder_rows:
            name = row[0]
            # Skip nulls, empty strings, the current path itself, paths with slashes, and video files
            if name and name != folder_path and "/" not in name and not name.endswith('.MP4'):
                folders.append({"name": name, "path": (folder_path + "/" + name).strip("/")})

        # Get videos in this folder
        if folder_path:
            video_sql = """
                SELECT * FROM videos
                WHERE file_path LIKE ? AND file_path NOT LIKE ?
                ORDER BY file_name
                LIMIT ? OFFSET ?
            """
            cursor = conn.execute(video_sql, (prefix + "%", prefix + "%/%", limit, offset))
        else:
            video_sql = """
                SELECT * FROM videos
                WHERE file_path NOT LIKE '%/%'
                ORDER BY file_name
                LIMIT ? OFFSET ?
            """
            cursor = conn.execute(video_sql, (limit, offset))

        videos = [dict(r) for r in cursor.fetchall()]

        return {"folders": folders, "videos": videos}

    def search_videos(query: str, limit: int = 20) -> list[dict]:
        """Search videos using FTS5 or fallback to LIKE."""
        conn = get_db_conn()

        try:
            # Try FTS5 first
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
        except sqlite3.OperationalError:
            # Fallback to LIKE search
            pattern = f"%{query}%"
            sql = """
                SELECT v.*, 0 as rank
                FROM videos v
                WHERE scene_description LIKE ? OR file_name LIKE ? OR tags LIKE ?
                ORDER BY file_name
                LIMIT ?
            """
            cursor = conn.execute(sql, (pattern, pattern, pattern, limit))
            rows = cursor.fetchall()

        return [dict(r) for r in rows]

    def update_video(file_path: str, updates: dict):
        """Update video fields."""
        conn = get_db_conn()
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        sql = f"UPDATE videos SET {set_clause} WHERE file_path = ?"
        conn.execute(sql, list(updates.values()) + [file_path])
        conn.commit()

    # ── Routes ──

    @app.route("/timeline")
    def timeline_page():
        """Timeline/calendar view for browsing videos chronologically."""
        return render_template("timeline.html")

    @app.route("/api/timeline/years")
    def api_timeline_years():
        """Get all years with video counts."""
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    strftime('%Y', creation_date) as year,
                    COUNT(*) as video_count,
                    MIN(creation_date) as earliest,
                    MAX(creation_date) as latest
                FROM videos 
                WHERE creation_date IS NOT NULL
                GROUP BY year
                ORDER BY year DESC
            """)
            
            years = []
            for row in cursor.fetchall():
                years.append({
                    "year": row["year"],
                    "count": row["video_count"],
                    "total_seconds": 0  # Will calculate below
                })
            
            # Get total duration for each year
            for year_data in years:
                cursor.execute("""
                    SELECT SUM(duration_seconds) as total_seconds
                    FROM videos 
                    WHERE strftime('%Y', creation_date) = ?
                """, (year_data["year"],))
                result = cursor.fetchone()
                year_data["total_seconds"] = result["total_seconds"] or 0
            
            return jsonify({"years": years})
        except Exception as e:
            current_app.logger.error(f"Error fetching timeline years: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()

    @app.route("/api/timeline/year/<year>")
    def api_timeline_year(year: str):
        """Get video counts by month and activity heatmap for a specific year."""
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)
        
        try:
            cursor = conn.cursor()
            
            # Get monthly counts
            cursor.execute("""
                SELECT 
                    strftime('%m', creation_date) as month,
                    COUNT(*) as video_count,
                    SUM(duration_seconds) as total_seconds
                FROM videos 
                WHERE strftime('%Y', creation_date) = ?
                GROUP BY month
                ORDER BY month
            """, (year,))
            
            months = {str(i).zfill(2): 0 for i in range(1, 13)}
            total_seconds = 0
            for row in cursor.fetchall():
                months[row["month"]] = row["video_count"]
                total_seconds += row["total_seconds"] or 0
            
            # Get activity heatmap data (date -> count)
            cursor.execute("""
                SELECT 
                    date(creation_date) as date,
                    COUNT(*) as count
                FROM videos 
                WHERE strftime('%Y', creation_date) = ?
                GROUP BY date
                ORDER BY date
            """, (year,))
            
            activity = []
            active_days = 0
            for row in cursor.fetchall():
                if row["date"]:
                    activity.append({
                        "date": row["date"],
                        "count": row["count"]
                    })
                    if row["count"] > 0:
                        active_days += 1
            
            return jsonify({
                "year": year,
                "months": months,
                "total": sum(months.values()),
                "total_videos": sum(months.values()),
                "total_seconds": total_seconds,
                "active_days": active_days,
                "activity": activity
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching timeline year: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()

    @app.route("/api/timeline/month/<year>/<month>")
    def api_timeline_month(year: str, month: str):
        """Get all days in a month with video counts."""
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)
        
        try:
            cursor = conn.cursor()
            
            # Get daily counts for this month
            cursor.execute("""
                SELECT 
                    strftime('%d', creation_date) as day,
                    COUNT(*) as count,
                    SUM(duration_seconds) as total_seconds
                FROM videos 
                WHERE strftime('%Y-%m', creation_date) = ?
                GROUP BY day
                ORDER BY day
            """, (f"{year}-{month.zfill(2)}",))
            
            days = []
            total_videos = 0
            total_seconds = 0
            for row in cursor.fetchall():
                days.append({
                    "day": int(row["day"]),
                    "count": row["count"],
                    "total_seconds": row["total_seconds"] or 0
                })
                total_videos += row["count"]
                total_seconds += row["total_seconds"] or 0
            
            # Get all videos for this month for the grid
            cursor.execute("""
                SELECT 
                    id,
                    file_name,
                    file_path,
                    duration_seconds,
                    resolution,
                    thumbnail_path,
                    scene_description,
                    gps_location_name,
                    creation_date,
                    strftime('%d', creation_date) as day
                FROM videos 
                WHERE strftime('%Y-%m', creation_date) = ?
                ORDER BY creation_date
            """, (f"{year}-{month.zfill(2)}",))
            
            videos = []
            for row in cursor.fetchall():
                videos.append(dict(row))
            
            return jsonify({
                "year": year,
                "month": month,
                "days": days,
                "videos": videos,
                "total_videos": total_videos,
                "total_seconds": total_seconds
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching timeline month: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()

    @app.route("/api/timeline/day/<year>/<month>/<day>")
    def api_timeline_day(year: str, month: str, day: str):
        """Get videos for a specific date."""
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)
        
        try:
            cursor = conn.cursor()
            date_prefix = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            cursor.execute("""
                SELECT 
                    id,
                    file_name,
                    file_path,
                    duration_seconds,
                    resolution,
                    thumbnail_path,
                    scene_description,
                    gps_location_name,
                    creation_date
                FROM videos 
                WHERE date(creation_date) = date(?)
                ORDER BY creation_date
            """, (date_prefix,))
            
            videos = []
            for row in cursor.fetchall():
                videos.append(dict(row))
            
            return jsonify({
                "date": date_prefix,
                "videos": videos,
                "count": len(videos)
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching timeline day: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()

    @app.route("/api/timeline/on-this-day")
    def api_timeline_on_this_day():
        """Get videos from the same day in previous years."""
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)
        
        try:
            cursor = conn.cursor()
            
            # Get today's month and day
            from datetime import datetime
            today = datetime.now()
            month_day = f"{today.month:02d}-{today.day:02d}"
            
            cursor.execute("""
                SELECT 
                    id,
                    file_name,
                    file_path,
                    duration_seconds,
                    resolution,
                    thumbnail_path,
                    scene_description,
                    gps_location_name,
                    creation_date,
                    strftime('%Y', creation_date) as year
                FROM videos 
                WHERE strftime('%m-%d', creation_date) = ?
                    AND strftime('%Y', creation_date) < ?
                ORDER BY creation_date DESC
            """, (month_day, str(today.year)))
            
            videos = []
            for row in cursor.fetchall():
                videos.append(dict(row))
            
            return jsonify({
                "month_day": month_day,
                "videos": videos,
                "count": len(videos)
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching on-this-day: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()

    @app.route("/")
    def browse():
        """Render the browse page shell."""
        stats = get_stats()
        return render_template("browse.html", stats=stats)

    @app.route("/api/browse")
    def api_browse():
        """JSON API for browsing folders and videos."""
        path = request.args.get("path", "")
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 24, type=int)

        offset = (page - 1) * limit

        contents = get_folder_contents(folder_path=path, limit=limit, offset=offset)

        return jsonify({
            "path": path,
            "folders": contents["folders"],
            "videos": contents["videos"],
            "page": page,
            "has_more": len(contents["videos"]) == limit,
        })

    @app.route("/search")
    def search_page():
        query = request.args.get("q", "").strip()
        mode = request.args.get("mode", "hybrid")
        limit = request.args.get("limit", 20, type=int)

        if not query:
            return render_template("search_results.html", query="", results=[], mode=mode)

        results = search_videos(query, limit)

        return render_template(
            "search_results.html",
            query=query,
            results=results,
            mode=mode,
        )

    @app.route("/video/<int:video_id>")
    def video_detail(video_id: int):
        video = get_video_by_id(video_id)
        if not video:
            abort(404)
        return render_template("video_detail.html", video=video)

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
        video = get_video_by_id(video_id)
        if not video:
            abort(404)

        drive = Path(current_app.config["DRIVE_PATH"])

        # Prefer proxy if available (low-bitrate for smooth playback)
        proxy_path = video.get("proxy_path")
        if proxy_path and Path(proxy_path).exists():
            return send_file(
                proxy_path,
                mimetype="video/mp4",
                conditional=True,
            )

        # Fallback to original file
        file_path = video["file_path"]

        # Validate file_path to prevent directory traversal
        if file_path.startswith("..") or file_path.startswith("/"):
            abort(400)

        video_path = (drive / file_path).resolve()

        # Verify resolved path is within drive root
        if not str(video_path).startswith(str(drive)):
            abort(400)

        if not video_path.exists():
            abort(404)

        # Generate proxy on-demand if not exists (async, don't block)
        if not proxy_path:
            try:
                from ..proxy import generate_proxy, get_proxy_path
                from ..db import Database
                proxy_file = get_proxy_path(video["file_hash"], drive)
                if not proxy_file.exists():
                    # Start generation in background thread
                    def generate():
                        try:
                            success = generate_proxy(video_path, proxy_file)
                            if success:
                                db_path = current_app.config["DB_PATH"]
                                with Database(db_path) as db:
                                    db.update_video(file_path, {"proxy_path": str(proxy_file)})
                        except Exception:
                            pass  # Silently fail, will retry next time
                    threading.Thread(target=generate, daemon=True).start()
            except Exception:
                pass  # Fail silently, serve original

        return send_file(
            video_path,
            mimetype="video/mp4",
            conditional=True,
        )

    @app.route("/api/location/search")
    def search_location():
        """
        Search for a location using OpenStreetMap Nominatim API.
        Checks cache first for instant results, then queries Nominatim if needed.
        """
        import urllib.request
        import urllib.parse

        from ..db import Database

        query = request.args.get("q", "").strip()
        if not query:
            return jsonify([])

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        try:
            # Normalize query for cache lookup
            cache_key = query.lower().strip()

            # Check cache first - try exact match on search_key, then fuzzy search
            cached = db.get_cached_location_by_search_key(cache_key)
            if not cached:
                # Try to find any cached location that matches this query
                cached = db.find_cached_location_by_query(cache_key)

            if cached:
                # For cached results, return the display name
                return jsonify([{
                    "name": cached["display_name"],
                    "lat": cached["lat"],
                    "lon": cached["lon"],
                    "type": "cached",
                }])

            headers = {"User-Agent": "B-Roll-Organizer/0.2.1"}

            params = urllib.parse.urlencode(
                {"q": query, "format": "json", "limit": 5, "addressdetails": 0}
            )
            url = f"https://nominatim.openstreetmap.org/search?{params}"

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    return jsonify({"error": "Failed to fetch from Nominatim"}), 502

                data = json.loads(response.read().decode())

                results = []
                for item in data:
                    lat = float(item.get("lat"))
                    lon = float(item.get("lon"))
                    name = item.get("display_name")
                    results.append({
                        "name": name,
                        "lat": lat,
                        "lon": lon,
                        "type": item.get("type", "unknown"),
                    })
                # Note: We don't cache here - only cache when user actually selects a location

                return jsonify(results)

        except Exception as e:
            current_app.logger.error(f"Geocoding error: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/location/cache", methods=["POST"])
    def cache_selected_location():
        """
        Cache a location when it's actually used (selected by user).
        Stores both search key (normalized) and display name (full).

        Request: {"search_key": "tokyo", "display_name": "Tokyo, Japan", "lat": 35.6762, "lon": 139.6503}
        """
        from ..db import Database

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        search_key = data.get("search_key", "").lower().strip()
        display_name = data.get("display_name", "").strip()
        lat = data.get("lat")
        lon = data.get("lon")

        if not search_key or not display_name or lat is None or lon is None:
            return jsonify({"error": "Missing required fields"}), 400

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid coordinates"}), 400

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        try:
            db.cache_location_with_display_name(search_key, display_name, lat, lon)
            return jsonify({"success": True})
        except Exception as e:
            current_app.logger.error(f"Error caching location: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/location/recent")
    def get_recent_locations():
        """
        Get recently used locations from cache.
        Returns up to 10 most recently cached locations.
        """
        from ..db import Database

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        try:
            recent = db.get_recent_cached_locations(limit=10)
            results = [
                {
                    "name": loc["location_name"],
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "cached_at": loc["cached_at"],
                    "type": "recent"
                }
                for loc in recent
            ]
            return jsonify(results)
        except Exception as e:
            current_app.logger.error(f"Error fetching recent locations: {e}")
            return jsonify([])
        finally:
            db.close()

    @app.route("/api/location/parse-url", methods=["POST"])
    def parse_location_url():
        """
        Parse a Google Maps URL to extract coordinates.
        Supports various Google Maps URL formats including short URLs.

        Request: {"url": "https://www.google.com/maps?q=35.6586,139.7454"}
        Response: {"lat": 35.6586, "lon": 139.7454, "name": "Google Maps Location"}
        """
        import re
        import urllib.request
        import urllib.parse

        class RedirectHandler(urllib.request.HTTPRedirectHandler):
            """Handler that captures the final URL after redirects."""
            def __init__(self):
                super().__init__()
                self.final_url = None

            def http_error_302(self, req, fp, code, msg, headers):
                self.final_url = headers.get('Location')
                return super().http_error_302(req, fp, code, msg, headers)

            def http_error_301(self, req, fp, code, msg, headers):
                self.final_url = headers.get('Location')
                return super().http_error_301(req, fp, code, msg, headers)

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        url = data.get("url", "").strip()
        if not url:
            return jsonify({"error": "No URL provided"}), 400

        try:
            lat = None
            lon = None
            name = "Google Maps Location"

            # Handle Google Maps short URLs (follow redirects)
            if "maps.app.goo.gl" in url or "goo.gl/maps" in url:
                try:
                    redirect_handler = RedirectHandler()
                    opener = urllib.request.build_opener(redirect_handler)
                    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')]
                    urllib.request.install_opener(opener)

                    req = urllib.request.Request(url, method='GET')
                    # Follow redirects and get final URL
                    with urllib.request.urlopen(req, timeout=15) as response:
                        final_url = response.geturl()
                        if final_url and final_url != url:
                            url = final_url
                            current_app.logger.info(f"Expanded short URL to: {url[:100]}...")
                except Exception as e:
                    current_app.logger.warning(f"Could not expand short URL: {e}")
                    # Continue with original URL

            # Decode URL-encoded characters for easier parsing
            decoded_url = urllib.parse.unquote(url)

            # Try various Google Maps URL patterns (support both encoded and decoded URLs)

            # Pattern 1: ?q=lat,lon or ?query=lat,lon (handles both %2C and ,)
            query_match = re.search(r'[?&](q|query)=(-?\d+\.?\d*)[,%][2C]*(-?\d+\.?\d*)', url)
            if not query_match:
                query_match = re.search(r'[?&](q|query)=(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)', decoded_url)
            if query_match:
                lat = float(query_match.group(2))
                lon = float(query_match.group(3))

            # Pattern 2: /@lat,lon,zoom/ or /@lat,lon (handles both %2C and ,)
            if lat is None or lon is None:
                at_match = re.search(r'/@(-?\d+\.?\d*)[,\s%]+2?C?(-?\d+\.?\d*)(?:,\d+z)?', url)
                if not at_match:
                    at_match = re.search(r'/@(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)(?:,\d+z)?', decoded_url)
                if at_match:
                    lat = float(at_match.group(1))
                    lon = float(at_match.group(2))

            # Pattern 3: &ll=lat,lon (legacy format)
            if lat is None or lon is None:
                ll_match = re.search(r'[?&]ll=(-?\d+\.?\d*)[,\s%]+2?C?(-?\d+\.?\d*)', url)
                if not ll_match:
                    ll_match = re.search(r'[?&]ll=(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)', decoded_url)
                if ll_match:
                    lat = float(ll_match.group(1))
                    lon = float(ll_match.group(2))

            # Pattern 4: Google Maps data=... format with !3d{lat}!4d{lon}
            if lat is None or lon is None:
                data_match = re.search(r'!3d(-?\d+\.?\d+)!4d(-?\d+\.?\d+)', url)
                if data_match:
                    lat = float(data_match.group(1))
                    lon = float(data_match.group(2))

            # Pattern 5: Look for coordinates anywhere in the URL path (last resort)
            if lat is None or lon is None:
                # Match lat,lon pairs with 4+ decimal places (more specific)
                coord_match = re.search(r'(-?\d{1,3}\.\d{4,})[,\s%]+2?C?(-?\d{1,3}\.\d{4,})', url)
                if not coord_match:
                    coord_match = re.search(r'(-?\d{1,3}\.\d{4,})[,\s]+(-?\d{1,3}\.\d{4,})', decoded_url)
                if coord_match:
                    potential_lat = float(coord_match.group(1))
                    potential_lon = float(coord_match.group(2))
                    # Validate coordinate bounds
                    if -90 <= potential_lat <= 90 and -180 <= potential_lon <= 180:
                        lat = potential_lat
                        lon = potential_lon

            # Extract location name from URL path if present
            # Look for /place/PLACE_NAME/ or similar patterns
            if lat is not None and lon is not None:
                place_match = re.search(r'/place/([^/@]+)', decoded_url)
                if place_match:
                    # Decode and clean up the place name
                    raw_name = place_match.group(1)
                    # Replace + with spaces and decode any remaining URL encoding
                    cleaned_name = raw_name.replace('+', ' ')
                    cleaned_name = urllib.parse.unquote(cleaned_name)
                    # Clean up extra spaces
                    cleaned_name = ' '.join(cleaned_name.split())
                    if cleaned_name:
                        name = cleaned_name

            if lat is not None and lon is not None:
                # Final validation
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    current_app.logger.info(f"Parsed coordinates from URL: {lat}, {lon}, name: {name}")
                    return jsonify({
                        "lat": lat,
                        "lon": lon,
                        "name": name,
                        "source": "google_maps_url"
                    })

            current_app.logger.warning(f"Could not parse coordinates from URL: {url[:100]}...")
            return jsonify({"error": "Could not extract coordinates from URL"}), 400

        except Exception as e:
            current_app.logger.error(f"URL parsing error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/video/<int:video_id>/location", methods=["POST"])
    def update_video_location(video_id: int):
        """Update the location of a video."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        lat = data.get("lat")
        lon = data.get("lon")
        name = data.get("name")

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid coordinates"}), 400

        video = get_video_by_id(video_id)
        if not video:
            abort(404)

        updates = {"gps_latitude": lat, "gps_longitude": lon, "gps_location_name": name}
        update_video(video["file_path"], updates)

        return jsonify({"success": True})

    # ═════════════════════════════════════════════════════════════════
    # Health Check Endpoint
    # ═════════════════════════════════════════════════════════════════

    @app.route("/api/health")
    def api_health():
        """
        Health check endpoint for connection monitoring.
        Returns 200 if drive is connected, 503 if not.
        """
        db_path = Path(current_app.config["DB_PATH"])
        
        if db_path.exists():
            return jsonify({
                "status": "healthy",
                "drive_connected": True,
                "timestamp": time.time()
            }), 200
        else:
            return jsonify({
                "status": "unhealthy",
                "drive_connected": False,
                "message": "External drive not connected",
                "timestamp": time.time()
            }), 503


    # ═════════════════════════════════════════════════════════════════
    # Map Routes & API
    # ═════════════════════════════════════════════════════════════════

    @app.route("/map")
    def map_page():
        """Render the map view page."""
        return render_template("map.html")

    @app.route("/api/map/videos")
    def api_map_videos():
        """
        Get all videos with coordinates for the map.
        Returns videos with GPS coordinates or folder locations that have been geocoded.
        """
        from ..db import Database
        
        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)
        
        try:
            videos = db.get_videos_with_coordinates(include_folder_locations=True)
            
            # Add thumbnail URLs
            for video in videos:
                if video.get("file_hash"):
                    video["thumbnail_url"] = f"/thumbnail/{video['file_hash']}"
                else:
                    video["thumbnail_url"] = None
                    
            return jsonify({
                "videos": videos,
                "total": len(videos)
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching map videos: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/map/locations")
    def api_map_locations():
        """
        Get unique locations with video counts.
        Returns locations aggregated by name with average coordinates.
        """
        from ..db import Database
        
        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)
        
        try:
            locations = db.get_location_counts()
            return jsonify({
                "locations": locations,
                "total": len(locations)
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching map locations: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/map/geocode")
    def api_map_geocode():
        """
        Geocode a location name using Nominatim API.
        Checks cache first, then calls Nominatim if not cached.
        """
        import urllib.request
        import urllib.parse
        
        from ..db import Database
        
        location = request.args.get("location", "").strip()
        if not location:
            return jsonify({"error": "No location provided"}), 400
        
        # Check cache first
        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)
        
        try:
            cached = db.get_cached_location(location)
            if cached:
                return jsonify({
                    "source": "cache",
                    "lat": cached["lat"],
                    "lon": cached["lon"],
                    "cached_at": cached["cached_at"]
                })
            
            # Not in cache, geocode with Nominatim
            headers = {"User-Agent": "B-Roll-Organizer/0.2.1"}
            params = urllib.parse.urlencode(
                {"q": location, "format": "json", "limit": 1, "addressdetails": 0}
            )
            url = f"https://nominatim.openstreetmap.org/search?{params}"

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    return jsonify({"error": "Failed to fetch from Nominatim"}), 502

                data = json.loads(response.read().decode())
                
                if not data:
                    return jsonify({"error": "Location not found"}), 404
                
                result = data[0]
                lat = float(result.get("lat"))
                lon = float(result.get("lon"))
                
                # Cache the result
                db.cache_location(location, lat, lon)
                
                return jsonify({
                    "source": "nominatim",
                    "lat": lat,
                    "lon": lon,
                    "name": result.get("display_name"),
                    "type": result.get("type", "unknown")
                })
                
        except Exception as e:
            current_app.logger.error(f"Geocoding error: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/map/geocode-cache", methods=["POST"])
    def api_map_cache_geocode():
        """
        Cache a geocoding result.
        Expects JSON with { "location_name": str, "lat": float, "lon": float }
        """
        from ..db import Database
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        location_name = data.get("location_name", "").strip()
        lat = data.get("lat")
        lon = data.get("lon")
        
        if not location_name or lat is None or lon is None:
            return jsonify({"error": "Missing required fields: location_name, lat, lon"}), 400
        
        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid coordinates"}), 400
        
        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)
        
        try:
            success = db.cache_location(location_name, lat, lon)
            if success:
                return jsonify({"success": True, "message": "Location cached"})
            else:
                return jsonify({"error": "Failed to cache location"}), 500
        except Exception as e:
            current_app.logger.error(f"Error caching location: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/map/nearby")
    def api_map_nearby():
        """
        Find videos near a specific point.
        Query params: lat, lon, radius_km (default: 5.0)
        """
        from ..db import Database
        
        try:
            lat = float(request.args.get("lat", 0))
            lon = float(request.args.get("lon", 0))
            radius_km = float(request.args.get("radius_km", 5.0))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid coordinates or radius"}), 400
        
        if lat == 0 and lon == 0:
            return jsonify({"error": "Latitude and longitude required"}), 400
        
        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)
        
        try:
            videos = db.nearby_videos(lat, lon, radius_km, limit=50)
            
            # Add thumbnail URLs
            for video in videos:
                if video.get("file_hash"):
                    video["thumbnail_url"] = f"/thumbnail/{video['file_hash']}"
                else:
                    video["thumbnail_url"] = None
                    
            return jsonify({
                "videos": videos,
                "center": {"lat": lat, "lon": lon},
                "radius_km": radius_km,
                "total": len(videos)
            })
        except Exception as e:
            current_app.logger.error(f"Error finding nearby videos: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/stats")
    def api_stats():
        return jsonify(get_stats())

    # ═════════════════════════════════════════════════════════════════
    # Stats Dashboard API
    # ═════════════════════════════════════════════════════════════════

    @app.route("/stats")
    def stats_page():
        """Render the stats dashboard page."""
        return render_template("stats.html")

    @app.route("/api/stats/overview")
    def api_stats_overview():
        """Get overview statistics for the catalog."""
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)

        try:
            cursor = conn.cursor()

            # Basic counts
            cursor.execute("""
                SELECT
                    COUNT(*) as total_clips,
                    SUM(file_size) as total_size,
                    COUNT(DISTINCT folder_location) as locations_count,
                    COUNT(CASE WHEN scene_description IS NOT NULL AND scene_description != '' THEN 1 END) as analyzed_count,
                    COUNT(CASE WHEN thumbnail_path IS NOT NULL THEN 1 END) as thumbnail_count,
                    SUM(duration_seconds) as total_duration
                FROM videos
            """)
            row = cursor.fetchone()

            # Health check info
            cursor.execute("SELECT COUNT(*) FROM videos WHERE scene_description IS NULL OR scene_description = ''")
            pending_analysis = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM videos WHERE thumbnail_path IS NULL")
            missing_thumbnails = cursor.fetchone()[0]

            return jsonify({
                "total_clips": row["total_clips"] or 0,
                "total_size_bytes": row["total_size"] or 0,
                "total_duration_seconds": row["total_duration"] or 0,
                "locations_count": row["locations_count"] or 0,
                "analyzed_count": row["analyzed_count"] or 0,
                "thumbnail_count": row["thumbnail_count"] or 0,
                "health": {
                    "pending_analysis": pending_analysis,
                    "missing_thumbnails": missing_thumbnails,
                    "database_connected": True
                }
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching stats overview: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stats/by-location")
    def api_stats_by_location():
        """Get video counts and storage by location."""
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)

        try:
            cursor = conn.cursor()

            # Get all videos with file paths and calculate folder from path
            cursor.execute("""
                SELECT
                    file_path,
                    file_size
                FROM videos
            """)

            from collections import defaultdict
            location_data = defaultdict(lambda: {"clips": 0, "size_bytes": 0})

            for row in cursor.fetchall():
                file_path = row["file_path"]
                size = row["file_size"] or 0

                # Extract top-level folder from file_path
                if "/" in file_path:
                    folder = file_path.split("/")[0]
                elif "\\" in file_path:
                    folder = file_path.split("\\")[0]
                else:
                    folder = "Root"

                location_data[folder]["clips"] += 1
                location_data[folder]["size_bytes"] += size

            # Convert to list and calculate percentages
            locations = []
            total_size = 0
            for folder, data in location_data.items():
                total_size += data["size_bytes"]
                locations.append({
                    "location": folder,
                    "clips": data["clips"],
                    "size_bytes": data["size_bytes"]
                })

            # Sort by size descending
            locations.sort(key=lambda x: x["size_bytes"], reverse=True)

            # Calculate percentages
            for loc in locations:
                loc["percentage"] = round((loc["size_bytes"] / total_size * 100), 1) if total_size > 0 else 0

            return jsonify({
                "locations": locations,
                "total_size_bytes": total_size
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching stats by location: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stats/timeline")
    def api_stats_timeline():
        """Get video counts by month for a specific year."""
        year = request.args.get("year", "").strip()

        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)

        try:
            cursor = conn.cursor()

            # Get available years
            cursor.execute("""
                SELECT DISTINCT strftime('%Y', creation_date) as year
                FROM videos
                WHERE creation_date IS NOT NULL
                ORDER BY year DESC
            """)
            available_years = [row["year"] for row in cursor.fetchall()]

            # Default to most recent year if not specified
            if not year and available_years:
                year = available_years[0]

            if not year:
                return jsonify({
                    "year": None,
                    "months": [],
                    "available_years": [],
                    "total": 0
                })

            cursor.execute("""
                SELECT
                    strftime('%m', creation_date) as month,
                    COUNT(*) as clips
                FROM videos
                WHERE strftime('%Y', creation_date) = ?
                GROUP BY month
                ORDER BY month
            """, (year,))

            # Initialize all 12 months with 0
            months = {str(i).zfill(2): 0 for i in range(1, 13)}

            for row in cursor.fetchall():
                months[row["month"]] = row["clips"]

            return jsonify({
                "year": year,
                "months": [{"month": k, "clips": v} for k, v in sorted(months.items())],
                "available_years": available_years,
                "total": sum(months.values())
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching stats timeline: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stats/tags")
    def api_stats_tags():
        """Get most popular tags."""
        limit = request.args.get("limit", 20, type=int)

        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)

        try:
            cursor = conn.cursor()

            # Get all tags
            cursor.execute("SELECT tags FROM videos WHERE tags IS NOT NULL AND tags != ''")

            tag_counts = {}
            for row in cursor.fetchall():
                tags_str = row["tags"]
                if not tags_str:
                    continue

                # Try to parse as JSON
                try:
                    tags = json.loads(tags_str)
                    if isinstance(tags, list):
                        for tag in tags:
                            tag = tag.strip().lower()
                            if tag:
                                tag_counts[tag] = tag_counts.get(tag, 0) + 1
                    elif isinstance(tags, str):
                        # Comma-separated or single tag
                        for tag in tags.split(","):
                            tag = tag.strip().lower()
                            if tag:
                                tag_counts[tag] = tag_counts.get(tag, 0) + 1
                except json.JSONDecodeError:
                    # Not JSON, treat as comma-separated
                    for tag in tags_str.split(","):
                        tag = tag.strip().lower()
                        if tag:
                            tag_counts[tag] = tag_counts.get(tag, 0) + 1

            # Sort by count and take top N
            sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

            return jsonify({
                "tags": [{"tag": tag, "count": count} for tag, count in sorted_tags]
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching stats tags: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stats/devices")
    def api_stats_devices():
        """Get video counts by source device."""
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)

        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COALESCE(source_device, 'Unknown') as device,
                    COUNT(*) as count
                FROM videos
                GROUP BY source_device
                ORDER BY count DESC
            """)

            devices = []
            for row in cursor.fetchall():
                devices.append({
                    "device": row["device"],
                    "count": row["count"]
                })

            return jsonify({"devices": devices})
        except Exception as e:
            current_app.logger.error(f"Error fetching stats devices: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stats/resolutions")
    def api_stats_resolutions():
        """Get video counts by resolution."""
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)

        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    COALESCE(resolution, 'Unknown') as resolution,
                    COUNT(*) as count
                FROM videos
                GROUP BY resolution
                ORDER BY count DESC
            """)

            resolutions = []
            for row in cursor.fetchall():
                resolutions.append({
                    "resolution": row["resolution"],
                    "count": row["count"]
                })

            return jsonify({"resolutions": resolutions})
        except Exception as e:
            current_app.logger.error(f"Error fetching stats resolutions: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stats/recent")
    def api_stats_recent():
        """Get recently processed clips."""
        limit = request.args.get("limit", 10, type=int)

        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)

        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    id,
                    file_name,
                    file_path,
                    duration_seconds,
                    resolution,
                    thumbnail_path,
                    scene_description,
                    gps_location_name,
                    processed_at
                FROM videos
                WHERE processed_at IS NOT NULL
                ORDER BY processed_at DESC
                LIMIT ?
            """, (limit,))

            videos = [dict(row) for row in cursor.fetchall()]

            return jsonify({"videos": videos})
        except Exception as e:
            current_app.logger.error(f"Error fetching recent videos: {e}")
            return jsonify({"error": str(e)}), 500

    # ═════════════════════════════════════════════════════════════════
    # Clip Export API
    # ═════════════════════════════════════════════════════════════════

    @app.route("/api/clip/export", methods=["POST"])
    def api_clip_export():
        """
        Export a trimmed video clip using FFmpeg.
        
        Expects JSON with:
        - video_id: int
        - start_time: float (seconds)
        - end_time: float (seconds)
        - filename: str (optional, for download)
        
        Returns:
        - download_url: str
        - clip_duration: float
        """
        import subprocess
        import tempfile
        import os
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        video_id = data.get("video_id")
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        filename = data.get("filename", "clip.mp4")
        
        # Validate inputs
        if not video_id:
            return jsonify({"error": "video_id is required"}), 400
        
        try:
            start_time = float(start_time) if start_time is not None else 0
            end_time = float(end_time) if end_time is not None else None
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid start_time or end_time"}), 400
        
        # Get video info
        video = get_video_by_id(video_id)
        if not video:
            return jsonify({"error": "Video not found"}), 404
        
        # Validate file path
        file_path = video["file_path"]
        if file_path.startswith("..") or file_path.startswith("/"):
            return jsonify({"error": "Invalid file path"}), 400
        
        drive = Path(current_app.config["DRIVE_PATH"])
        video_path = (drive / file_path).resolve()
        
        # Security check
        if not str(video_path).startswith(str(drive)):
            return jsonify({"error": "Invalid file path"}), 400
        
        if not video_path.exists():
            return jsonify({"error": "Video file not found"}), 404
        
        # Calculate duration
        duration = video.get("duration_seconds", 0)
        if end_time is None:
            end_time = duration
        
        if start_time < 0 or end_time > duration or start_time >= end_time:
            return jsonify({"error": "Invalid trim range"}), 400
        
        clip_duration = end_time - start_time
        
        # Create temporary file for export
        temp_dir = tempfile.gettempdir()
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        output_path = Path(temp_dir) / safe_filename
        
        try:
            # Build FFmpeg command for lossless trimming (copy codecs)
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file if exists
                "-ss", str(start_time),  # Start time
                "-i", str(video_path),   # Input file
                "-t", str(clip_duration), # Duration
                "-c", "copy",            # Copy codecs (fast, lossless)
                "-avoid_negative_ts", "1", # Ensure timestamps are positive
                "-movflags", "+faststart", # Web-optimized
                str(output_path)
            ]
            
            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                current_app.logger.error(f"FFmpeg error: {result.stderr}")
                return jsonify({"error": "Failed to export clip", "details": result.stderr}), 500
            
            # Return the file as a downloadable response
            return send_file(
                output_path,
                mimetype="video/mp4",
                as_attachment=True,
                download_name=safe_filename
            )
            
        except subprocess.TimeoutExpired:
            return jsonify({"error": "Export timed out"}), 500
        except Exception as e:
            current_app.logger.error(f"Clip export error: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            # Clean up temp file after sending (or if it exists)
            try:
                if output_path.exists():
                    os.remove(output_path)
            except:
                pass

    @app.route("/video-file/<path:file_path>")
    def serve_video_file(file_path):
        """
        Serve a video file directly for preview/hover.
        Security: Only serves files within the configured drive path.
        """
        import os
        import urllib.parse
        from pathlib import Path
        
        # URL decode the file path
        decoded_path = urllib.parse.unquote(file_path)
        drive_path = Path(current_app.config["DRIVE_PATH"])
        
        # Handle both relative and absolute paths stored in database
        if decoded_path.startswith(str(drive_path)):
            # Path already includes drive path (absolute)
            requested_path = Path(decoded_path)
        else:
            # Relative path - prepend drive path
            requested_path = drive_path / decoded_path
        
        # Security check: ensure the requested path is within the drive
        try:
            requested_path.resolve().relative_to(drive_path.resolve())
        except ValueError:
            abort(403, "Access denied")
        
        if not requested_path.exists():
            abort(404, "Video not found")
        
        if not requested_path.is_file():
            abort(403, "Not a file")
        
        return send_file(requested_path, mimetype="video/mp4", conditional=True)

    @app.route("/api/batch/set-location", methods=["POST"])
    def api_batch_set_location():
        """
        Set location for multiple videos in batch.
        Expects: { video_ids: [1, 2, 3], lat: 35.0, lon: 139.0, location_name: "Tokyo" }
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        video_ids = data.get("video_ids", [])
        lat = data.get("lat")
        lon = data.get("lon")
        location_name = data.get("location_name", "").strip()
        
        if not video_ids:
            return jsonify({"error": "No video IDs provided"}), 400
        if lat is None or lon is None:
            return jsonify({"error": "Latitude and longitude required"}), 400
        if not location_name:
            return jsonify({"error": "Location name required"}), 400
        
        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid coordinates"}), 400
        
        db_path = current_app.config["DB_PATH"]
        conn = _get_thread_db_connection(db_path)
        
        try:
            cursor = conn.cursor()
            updated = 0
            
            for video_id in video_ids:
                cursor.execute(
                    "UPDATE videos SET gps_latitude = ?, gps_longitude = ?, gps_location_name = ? WHERE id = ?",
                    (lat, lon, location_name, video_id)
                )
                if cursor.rowcount > 0:
                    updated += 1
            
            conn.commit()
            
            return jsonify({
                "success": True,
                "updated": updated,
                "location_name": location_name,
                "lat": lat,
                "lon": lon
            })
        except Exception as e:
            conn.rollback()
            current_app.logger.error(f"Error setting location: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()

    # ═════════════════════════════════════════════════════════════════
    # Playlist Routes
    # ═════════════════════════════════════════════════════════════════

    @app.route("/playlists")
    def playlists_page():
        """Render the playlists list page."""
        return render_template("playlists.html")

    @app.route("/playlist/<int:playlist_id>")
    def playlist_detail_page(playlist_id: int):
        """Render the playlist detail page."""
        from ..db import Database

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        playlist = db.get_playlist(playlist_id)
        if not playlist:
            abort(404)

        return render_template("playlist_detail.html", playlist=playlist)

    @app.route("/api/playlists", methods=["GET"])
    def api_list_playlists():
        """List all playlists with thumbnails."""
        from ..db import Database

        try:
            db_path = current_app.config["DB_PATH"]
            db = Database(db_path)

            playlists = db.get_all_playlists()

            # Fetch thumbnails for each playlist
            for playlist in playlists:
                items = db.get_playlist_items(playlist["id"])
                thumbnails = []
                for item in items[:4]:  # Get first 4 thumbnails
                    if item.get("thumbnail_path"):
                        thumb_filename = Path(item["thumbnail_path"]).name
                        thumbnails.append(f"/thumbnail/{thumb_filename}")
                playlist["thumbnails"] = thumbnails

            return jsonify({"playlists": playlists})
        except Exception as e:
            current_app.logger.error(f"Error listing playlists: {e}")
            import traceback
            current_app.logger.error(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

    @app.route("/api/playlists", methods=["POST"])
    def api_create_playlist():
        """Create a new playlist."""
        from ..db import Database

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Playlist name is required"}), 400

        description = data.get("description", "").strip()
        color = data.get("color", "#3b82f6").strip()

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        try:
            playlist_id = db.create_playlist(name, description or None, color)
            return jsonify({"success": True, "playlist_id": playlist_id})
        except Exception as e:
            current_app.logger.error(f"Error creating playlist: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/playlists/<int:playlist_id>", methods=["GET"])
    def api_get_playlist(playlist_id: int):
        """Get a single playlist with its videos."""
        from ..db import Database

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        playlist = db.get_playlist(playlist_id)
        if not playlist:
            return jsonify({"error": "Playlist not found"}), 404

        videos = db.get_playlist_items(playlist_id)

        # Add thumbnail URLs to videos
        for video in videos:
            if video.get("thumbnail_path"):
                thumb_filename = Path(video["thumbnail_path"]).name
                video["thumbnail_url"] = f"/thumbnail/{thumb_filename}"
            else:
                video["thumbnail_url"] = None

        return jsonify({"playlist": playlist, "videos": videos})

    @app.route("/api/playlists/<int:playlist_id>", methods=["PUT"])
    def api_update_playlist(playlist_id: int):
        """Update a playlist."""
        from ..db import Database

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        color = data.get("color", "").strip()

        if not name:
            return jsonify({"error": "Playlist name is required"}), 400

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        try:
            db.update_playlist(playlist_id, name, description or None, color or None)
            return jsonify({"success": True})
        except Exception as e:
            current_app.logger.error(f"Error updating playlist: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/playlists/<int:playlist_id>", methods=["DELETE"])
    def api_delete_playlist(playlist_id: int):
        """Delete a playlist."""
        from ..db import Database

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        try:
            db.delete_playlist(playlist_id)
            return jsonify({"success": True})
        except Exception as e:
            current_app.logger.error(f"Error deleting playlist: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/playlists/<int:playlist_id>/items/<int:video_id>", methods=["DELETE"])
    def api_remove_from_playlist(playlist_id: int, video_id: int):
        """Remove a video from a playlist."""
        from ..db import Database

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        try:
            db.remove_video_from_playlist(playlist_id, video_id)
            return jsonify({"success": True})
        except Exception as e:
            current_app.logger.error(f"Error removing video from playlist: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/playlists/<int:playlist_id>/reorder", methods=["POST"])
    def api_reorder_playlist(playlist_id: int):
        """Reorder a video within a playlist."""
        from ..db import Database

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        video_id = data.get("video_id")
        new_position = data.get("new_position")

        if video_id is None or new_position is None:
            return jsonify({"error": "video_id and new_position are required"}), 400

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        try:
            db.reorder_playlist_item(playlist_id, video_id, new_position)
            return jsonify({"success": True})
        except Exception as e:
            current_app.logger.error(f"Error reordering playlist: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/batch/add-to-playlist", methods=["POST"])
    def api_batch_add_to_playlist():
        """Add videos to a playlist (existing or new)."""
        from ..db import Database

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        video_ids = data.get("video_ids", [])
        playlist_id = data.get("playlist_id")
        playlist_name = data.get("playlist_name", "").strip()

        if not video_ids:
            return jsonify({"error": "No video IDs provided"}), 400

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        try:
            # Create new playlist if name provided
            if not playlist_id and playlist_name:
                playlist_id = db.create_playlist(playlist_name)
            elif not playlist_id:
                return jsonify({"error": "playlist_id or playlist_name is required"}), 400

            # Add each video
            added = 0
            for video_id in video_ids:
                if db.add_video_to_playlist(playlist_id, video_id):
                    added += 1

            return jsonify({"success": True, "added": added, "playlist_id": playlist_id})
        except Exception as e:
            current_app.logger.error(f"Error adding to playlist: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/playlists/<int:playlist_id>/export", methods=["GET"])
    def api_export_playlist(playlist_id: int):
        """Export playlist to various formats (json, csv, fcpxml)."""
        import csv
        import io
        from datetime import datetime

        from ..db import Database

        export_format = request.args.get("format", "json").lower()

        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)

        playlist = db.get_playlist(playlist_id)
        if not playlist:
            return jsonify({"error": "Playlist not found"}), 404

        videos = db.get_playlist_items(playlist_id)

        if export_format == "json":
            return jsonify({
                "playlist": playlist,
                "videos": videos,
                "exported_at": datetime.now().isoformat()
            })

        elif export_format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)

            # Header
            writer.writerow([
                "id", "file_name", "file_path", "duration_seconds",
                "resolution", "scene_description", "gps_location_name"
            ])

            # Data rows
            for video in videos:
                writer.writerow([
                    video.get("id"),
                    video.get("file_name", ""),
                    video.get("file_path", ""),
                    video.get("duration_seconds", ""),
                    video.get("resolution", ""),
                    video.get("scene_description", ""),
                    video.get("gps_location_name", "")
                ])

            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode("utf-8")),
                mimetype="text/csv",
                as_attachment=True,
                download_name=f"{playlist['name']}.csv"
            )

        elif export_format == "fcpxml":
            # Generate basic FCPXML for Final Cut Pro
            # This is a simplified version - full implementation would need proper timing
            drive_path = current_app.config["DRIVE_PATH"]

            xml_parts = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<fcpxml version="1.9">',
                '  <resources>',
                '    <format id="r1" name="FFVideoFormat1080p30" width="1920" height="1080" frameDuration="1/30s"/>',
            ]

            # Add format resources for each unique resolution
            formats_added = 0
            for i, video in enumerate(videos):
                res = video.get("resolution", "")
                if "x" in str(res):
                    try:
                        w, h = map(int, res.split("x"))
                        xml_parts.append(f'    <format id="r{i+2}" name="Custom{w}x{h}" width="{w}" height="{h}" frameDuration="1/30s"/>')
                        formats_added += 1
                    except ValueError:
                        pass

            xml_parts.append('  </resources>')
            xml_parts.append('  <library>')
            xml_parts.append('    <event name="{}">'.format(playlist["name"]))
            xml_parts.append('      <project name="{}">'.format(playlist["name"]))
            xml_parts.append('        <sequence format-ref="r1">')
            xml_parts.append('          <spine>')

            # Add clip references
            for i, video in enumerate(videos):
                file_path = video.get("file_path", "")
                file_name = video.get("file_name", "")
                duration = video.get("duration_seconds", 0) or 1

                xml_parts.append(f'            <clip name="{file_name}" duration="{duration}s">')
                xml_parts.append(f'              <note>{video.get("scene_description", "")}</note>')
                xml_parts.append('            </clip>')

            xml_parts.append('          </spine>')
            xml_parts.append('        </sequence>')
            xml_parts.append('      </project>')
            xml_parts.append('    </event>')
            xml_parts.append('  </library>')
            xml_parts.append('</fcpxml>')

            xml_content = "\\n".join(xml_parts)
            return send_file(
                io.BytesIO(xml_content.encode("utf-8")),
                mimetype="text/xml",
                as_attachment=True,
                download_name=f"{playlist['name']}.fcpxml"
            )

        else:
            return jsonify({"error": f"Unknown format: {export_format}"}), 400

    return app
