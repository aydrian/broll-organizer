"""
Flask web application for browsing and searching the b-roll catalog.

Uses plain sqlite3 to avoid sqlite-vec architecture issues on Raspberry Pi.
Implements connection pooling using thread-local storage for improved performance.
"""
from __future__ import annotations

import json
import sqlite3
import threading
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

        file_path = video["file_path"]
        
        # Validate file_path to prevent directory traversal
        if file_path.startswith("..") or file_path.startswith("/"):
            abort(400)
        
        drive = Path(current_app.config["DRIVE_PATH"])
        video_path = (drive / file_path).resolve()
        
        # Verify resolved path is within drive root
        if not str(video_path).startswith(str(drive)):
            abort(400)

        if not video_path.exists():
            abort(404)

        return send_file(
            video_path,
            mimetype="video/mp4",
            conditional=True,
        )

    @app.route("/api/location/search")
    def search_location():
        """
        Search for a location using OpenStreetMap Nominatim API.
        """
        import urllib.request
        import urllib.parse

        query = request.args.get("q", "").strip()
        if not query:
            return jsonify([])

        headers = {"User-Agent": "B-Roll-Organizer/0.2.1"}

        try:
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
                    results.append({
                        "name": item.get("display_name"),
                        "lat": float(item.get("lat")),
                        "lon": float(item.get("lon")),
                        "type": item.get("type", "unknown"),
                    })

                return jsonify(results)

        except Exception as e:
            current_app.logger.error(f"Geocoding error: {e}")
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
    # Timeline Routes & API
    # ═════════════════════════════════════════════════════════════════

    @app.route("/timeline")
    def timeline_page():
        """Render the timeline view page."""
        return render_template("timeline.html")

    @app.route("/timeline/<int:year>")
    def timeline_year(year: int):
        """Render the year view page."""
        return render_template("timeline.html", view="year", year=year)

    @app.route("/timeline/<int:year>/<int:month>")
    def timeline_month(year: int, month: int):
        """Render the month view page."""
        return render_template("timeline.html", view="month", year=year, month=month)

    @app.route("/timeline/<int:year>/<int:month>/<int:day>")
    def timeline_day(year: int, month: int, day: int):
        """Render the day view page."""
        return render_template("timeline.html", view="day", year=year, month=month, day=day)

    @app.route("/api/timeline/years")
    def api_timeline_years():
        """
        Get all years with video counts for the year overview.
        """
        from ..db import Database
        
        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)
        
        try:
            years = db.get_years_with_counts()
            date_range = db.get_date_range()
            
            return jsonify({
                "years": years,
                "date_range": date_range,
                "total": len(years)
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching timeline years: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/timeline/year/<int:year>")
    def api_timeline_year(year: int):
        """
        Get activity data for a specific year (heatmap data).
        """
        from ..db import Database
        
        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)
        
        try:
            activity = db.get_year_activity_heatmap(year)
            
            # Calculate stats
            total_videos = sum(day["count"] for day in activity)
            active_days = len(activity)
            
            return jsonify({
                "year": year,
                "activity": activity,
                "total_videos": total_videos,
                "active_days": active_days
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching year activity: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/timeline/month/<int:year>/<int:month>")
    def api_timeline_month(year: int, month: int):
        """
        Get video counts for each day in a specific month.
        """
        from ..db import Database
        
        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)
        
        try:
            days = db.get_month_grid(year, month)
            
            # Build lookup for quick access
            day_lookup = {d["day"]: d for d in days}
            
            return jsonify({
                "year": year,
                "month": month,
                "days": day_lookup,
                "total_days_with_videos": len(days)
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching month data: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/timeline/day/<int:year>/<int:month>/<int:day>")
    def api_timeline_day(year: int, month: int, day: int):
        """
        Get all videos for a specific date.
        """
        from ..db import Database
        
        db_path = current_app.config["DB_PATH"]
        db = Database(db_path)
        
        try:
            date_str = f"{year}-{month:02d}-{day:02d}"
            videos = db.get_videos_by_date(date_str)
            
            # Add thumbnail URLs
            for video in videos:
                if video.get("file_hash"):
                    video["thumbnail_url"] = f"/thumbnail/{video['file_hash']}"
                else:
                    video["thumbnail_url"] = None
            
            return jsonify({
                "date": date_str,
                "year": year,
                "month": month,
                "day": day,
                "videos": videos,
                "total": len(videos)
            })
        except Exception as e:
            current_app.logger.error(f"Error fetching day videos: {e}")
            return jsonify({"error": str(e)}), 500
        finally:
            db.close()

    @app.route("/api/timeline/on-this-day")
    def api_timeline_on_this_day():
        """
        Get videos from the same month/day across different years.
        Query params: month, day, exclude_year (optional)
        """
        from ..db import Database
        
        try:
            month = request.args.get("month", type=int)
            day = request.args.get("day", type=int)
            exclude_year = request.args.get("exclude_year", type=int)
            
            if month is None or day is None:
                return jsonify({"error": "month and day parameters are required"}), 400
            
            if not (1 <= month <= 12) or not (1 <= day <= 31):
                return jsonify({"error": "Invalid month or day"}), 400
            
            db_path = current_app.config["DB_PATH"]
            db = Database(db_path)
            
            try:
                videos = db.get_on_this_day(month, day, exclude_year)
                
                # Add thumbnail URLs
                for video in videos:
                    if video.get("file_hash"):
                        video["thumbnail_url"] = f"/thumbnail/{video['file_hash']}"
                    else:
                        video["thumbnail_url"] = None
                
                # Group by year
                by_year = {}
                for video in videos:
                    year = video.get("year", "Unknown")
                    if year not in by_year:
                        by_year[year] = []
                    by_year[year].append(video)
                
                return jsonify({
                    "month": month,
                    "day": day,
                    "exclude_year": exclude_year,
                    "videos": videos,
                    "by_year": by_year,
                    "total": len(videos),
                    "year_count": len(by_year)
                })
            finally:
                db.close()
                
        except Exception as e:
            current_app.logger.error(f"Error fetching on-this-day videos: {e}")
            return jsonify({"error": str(e)}), 500

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
    # Playlist Routes & API
    # ═════════════════════════════════════════════════════════════════

    def init_playlists_table():
        """Initialize playlists tables if they don't exist."""
        conn = get_db_conn()
        
        # Main playlists table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#3b82f6',
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
        """)
        
        # Add color column if it doesn't exist (migration)
        try:
            conn.execute("SELECT color FROM playlists LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE playlists ADD COLUMN color TEXT DEFAULT '#3b82f6'")
        
        # Playlist items with proper foreign keys and position
        conn.execute("""
            CREATE TABLE IF NOT EXISTS playlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                added_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE,
                UNIQUE(playlist_id, video_id)
            )
        """)
        
        # Create indexes for performance
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
        
        # Migrate old playlist_videos table if exists
        try:
            conn.execute("SELECT 1 FROM playlist_videos LIMIT 1")
            # Migration: copy data from old table
            conn.execute("""
                INSERT OR IGNORE INTO playlist_items (playlist_id, video_id, position, added_at)
                SELECT playlist_id, video_id, position, added_at FROM playlist_videos
            """)
            conn.execute("DROP TABLE playlist_videos")
        except sqlite3.OperationalError:
            pass  # Old table doesn't exist
            
        conn.commit()

    @app.route("/playlists")
    def playlists_page():
        """Render the playlists list page."""
        return render_template("playlists.html")

    @app.route("/playlist/<int:playlist_id>")
    def playlist_detail_page(playlist_id: int):
        """Render the playlist detail page."""
        conn = get_db_conn()
        row = conn.execute(
            """SELECT p.*, COUNT(pi.id) as video_count 
               FROM playlists p 
               LEFT JOIN playlist_items pi ON p.id = pi.playlist_id 
               WHERE p.id = ? GROUP BY p.id""",
            (playlist_id,)
        ).fetchone()
        if not row:
            abort(404)
        playlist = dict(row)
        return render_template("playlist_detail.html", playlist=playlist)

    @app.route("/api/playlists", methods=["GET"])
    def api_get_playlists():
        """Get all playlists with video counts."""
        conn = get_db_conn()
        rows = conn.execute("""
            SELECT p.id, p.name, p.description, p.color, p.created_at, p.updated_at,
                   COUNT(pi.id) as video_count
            FROM playlists p
            LEFT JOIN playlist_items pi ON p.id = pi.playlist_id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
        """).fetchall()
        return jsonify({
            "playlists": [dict(r) for r in rows]
        })

    @app.route("/api/playlists", methods=["POST"])
    def api_create_playlist():
        """Create a new playlist."""
        data = request.get_json()
        if not data or not data.get("name"):
            return jsonify({"error": "Playlist name is required"}), 400

        conn = get_db_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO playlists (name, description, color) VALUES (?, ?, ?)",
                (data["name"], data.get("description", ""), data.get("color", "#3b82f6"))
            )
            conn.commit()
            return jsonify({
                "success": True,
                "id": cursor.lastrowid,
                "name": data["name"]
            })
        except sqlite3.IntegrityError:
            return jsonify({"error": "Playlist with this name already exists"}), 409

    @app.route("/api/playlists/<int:playlist_id>", methods=["GET"])
    def api_get_playlist(playlist_id: int):
        """Get a single playlist with its videos."""
        conn = get_db_conn()
        
        # Get playlist info
        playlist_row = conn.execute(
            """SELECT p.*, COUNT(pi.id) as video_count 
               FROM playlists p 
               LEFT JOIN playlist_items pi ON p.id = pi.playlist_id 
               WHERE p.id = ? GROUP BY p.id""",
            (playlist_id,)
        ).fetchone()
        
        if not playlist_row:
            return jsonify({"error": "Playlist not found"}), 404
        
        playlist = dict(playlist_row)
        
        # Get videos in playlist
        video_rows = conn.execute(
            """SELECT v.*, pi.position, pi.id as item_id
               FROM playlist_items pi
               JOIN videos v ON pi.video_id = v.id
               WHERE pi.playlist_id = ?
               ORDER BY pi.position""",
            (playlist_id,)
        ).fetchall()
        
        videos = []
        for row in video_rows:
            video = dict(row)
            if video.get("file_hash"):
                video["thumbnail_url"] = f"/thumbnail/{video['file_hash']}"
            videos.append(video)
        
        return jsonify({
            "playlist": playlist,
            "videos": videos
        })

    @app.route("/api/playlists/<int:playlist_id>", methods=["PUT"])
    def api_update_playlist(playlist_id: int):
        """Update a playlist."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        conn = get_db_conn()
        
        # Check if playlist exists
        row = conn.execute("SELECT id FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        if not row:
            return jsonify({"error": "Playlist not found"}), 404
        
        updates = []
        params = []
        
        if "name" in data:
            updates.append("name = ?")
            params.append(data["name"])
        if "description" in data:
            updates.append("description = ?")
            params.append(data["description"])
        if "color" in data:
            updates.append("color = ?")
            params.append(data["color"])
        
        if not updates:
            return jsonify({"error": "No fields to update"}), 400
        
        updates.append("updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")
        params.append(playlist_id)
        
        conn.execute(
            f"UPDATE playlists SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()
        
        return jsonify({"success": True})

    @app.route("/api/playlists/<int:playlist_id>", methods=["DELETE"])
    def api_delete_playlist(playlist_id: int):
        """Delete a playlist."""
        conn = get_db_conn()
        conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        conn.commit()
        return jsonify({"success": True})

    @app.route("/api/playlists/<int:playlist_id>/items", methods=["POST"])
    def api_add_to_playlist(playlist_id: int):
        """Add a video to a playlist."""
        data = request.get_json()
        if not data or "video_id" not in data:
            return jsonify({"error": "video_id is required"}), 400
        
        video_id = data["video_id"]
        position = data.get("position")  # Optional: specific position
        
        conn = get_db_conn()
        
        # Check if playlist exists
        playlist = conn.execute("SELECT id FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        if not playlist:
            return jsonify({"error": "Playlist not found"}), 404
        
        # Check if video exists
        video = conn.execute("SELECT id FROM videos WHERE id = ?", (video_id,)).fetchone()
        if not video:
            return jsonify({"error": "Video not found"}), 404
        
        try:
            if position is not None:
                # Shift existing items at and after this position
                conn.execute(
                    """UPDATE playlist_items 
                       SET position = position + 1 
                       WHERE playlist_id = ? AND position >= ?""",
                    (playlist_id, position)
                )
            else:
                # Get next position
                row = conn.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_items WHERE playlist_id = ?",
                    (playlist_id,)
                ).fetchone()
                position = row[0]
            
            cursor = conn.execute(
                "INSERT INTO playlist_items (playlist_id, video_id, position) VALUES (?, ?, ?)",
                (playlist_id, video_id, position)
            )
            
            # Update playlist timestamp
            conn.execute(
                "UPDATE playlists SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
                (playlist_id,)
            )
            conn.commit()
            
            return jsonify({"success": True, "item_id": cursor.lastrowid, "position": position})
        except sqlite3.IntegrityError:
            return jsonify({"error": "Video already in playlist"}), 409

    @app.route("/api/playlists/<int:playlist_id>/items/<int:video_id>", methods=["DELETE"])
    def api_remove_from_playlist(playlist_id: int, video_id: int):
        """Remove a video from a playlist."""
        conn = get_db_conn()
        
        # Get current position
        row = conn.execute(
            "SELECT position FROM playlist_items WHERE playlist_id = ? AND video_id = ?",
            (playlist_id, video_id)
        ).fetchone()
        
        if not row:
            return jsonify({"error": "Video not in playlist"}), 404
        
        position = row[0]
        
        # Delete the item
        conn.execute(
            "DELETE FROM playlist_items WHERE playlist_id = ? AND video_id = ?",
            (playlist_id, video_id)
        )
        
        # Reorder remaining items to fill the gap
        conn.execute(
            """UPDATE playlist_items 
               SET position = position - 1 
               WHERE playlist_id = ? AND position > ?""",
            (playlist_id, position)
        )
        
        # Update playlist timestamp
        conn.execute(
            "UPDATE playlists SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
            (playlist_id,)
        )
        conn.commit()
        
        return jsonify({"success": True})

    @app.route("/api/playlists/<int:playlist_id>/reorder", methods=["POST"])
    def api_reorder_playlist(playlist_id: int):
        """Reorder videos in a playlist."""
        data = request.get_json()
        if not data or "video_id" not in data or "new_position" not in data:
            return jsonify({"error": "video_id and new_position are required"}), 400
        
        video_id = data["video_id"]
        new_position = data["new_position"]
        
        conn = get_db_conn()
        
        # Get current position
        row = conn.execute(
            "SELECT position FROM playlist_items WHERE playlist_id = ? AND video_id = ?",
            (playlist_id, video_id)
        ).fetchone()
        
        if not row:
            return jsonify({"error": "Video not in playlist"}), 404
        
        old_position = row[0]
        
        if old_position == new_position:
            return jsonify({"success": True})  # No change needed
        
        conn.execute("BEGIN TRANSACTION")
        try:
            if old_position < new_position:
                # Moving down: decrement positions between old and new
                conn.execute(
                    """UPDATE playlist_items
                       SET position = position - 1
                       WHERE playlist_id = ? AND position > ? AND position <= ?""",
                    (playlist_id, old_position, new_position)
                )
            else:
                # Moving up: increment positions between new and old
                conn.execute(
                    """UPDATE playlist_items
                       SET position = position + 1
                       WHERE playlist_id = ? AND position >= ? AND position < ?""",
                    (playlist_id, new_position, old_position)
                )
            
            # Update the moved item
            conn.execute(
                "UPDATE playlist_items SET position = ? WHERE playlist_id = ? AND video_id = ?",
                (new_position, playlist_id, video_id)
            )
            
            # Update playlist timestamp
            conn.execute(
                "UPDATE playlists SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
                (playlist_id,)
            )
            
            conn.commit()
            return jsonify({"success": True})
        except Exception as e:
            conn.execute("ROLLBACK")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/playlists/<int:playlist_id>/export", methods=["GET"])
    def api_export_playlist(playlist_id: int):
        """Export playlist to various formats."""
        from io import StringIO
        import csv
        
        export_format = request.args.get("format", "json").lower()
        
        conn = get_db_conn()
        
        # Get playlist info
        playlist_row = conn.execute(
            """SELECT p.*, COUNT(pi.id) as video_count 
               FROM playlists p 
               LEFT JOIN playlist_items pi ON p.id = pi.playlist_id 
               WHERE p.id = ? GROUP BY p.id""",
            (playlist_id,)
        ).fetchone()
        
        if not playlist_row:
            return jsonify({"error": "Playlist not found"}), 404
        
        playlist = dict(playlist_row)
        
        # Get videos in playlist
        video_rows = conn.execute(
            """SELECT v.*, pi.position
               FROM playlist_items pi
               JOIN videos v ON pi.video_id = v.id
               WHERE pi.playlist_id = ?
               ORDER BY pi.position""",
            (playlist_id,)
        ).fetchall()
        
        videos = [dict(r) for r in video_rows]
        drive = Path(current_app.config["DRIVE_PATH"])
        
        if export_format == "fcpxml":
            # Generate FCPXML
            xml_content = generate_fcpxml(playlist, videos, drive)
            filename = f"{playlist['name'].replace(' ', '_')}.fcpxml"
            return xml_content, 200, {
                "Content-Type": "application/xml",
                "Content-Disposition": f"attachment; filename=\"{filename}\""
            }
        elif export_format == "csv":
            # Generate CSV
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["Position", "Filename", "Description", "Duration", "File Path", "Resolution", "Tags"])
            for video in videos:
                tags = video.get("tags", "")
                try:
                    tags = json.loads(tags) if tags else []
                    tags = ", ".join(tags) if isinstance(tags, list) else tags
                except:
                    pass
                writer.writerow([
                    video["position"],
                    video["file_name"],
                    video.get("scene_description", ""),
                    video.get("duration_seconds", ""),
                    video["file_path"],
                    video.get("resolution", ""),
                    tags
                ])
            filename = f"{playlist['name'].replace(' ', '_')}.csv"
            return output.getvalue(), 200, {
                "Content-Type": "text/csv",
                "Content-Disposition": f"attachment; filename=\"{filename}\""
            }
        else:  # json
            export_data = {
                "playlist": {
                    "id": playlist["id"],
                    "name": playlist["name"],
                    "description": playlist.get("description"),
                    "color": playlist.get("color"),
                    "created_at": playlist["created_at"],
                    "video_count": playlist["video_count"]
                },
                "items": [
                    {
                        "position": video["position"],
                        "video_id": video["id"],
                        "file_name": video["file_name"],
                        "file_path": video["file_path"],
                        "description": video.get("scene_description"),
                        "duration_seconds": video.get("duration_seconds"),
                        "resolution": video.get("resolution"),
                        "tags": video.get("tags"),
                        "gps_location_name": video.get("gps_location_name"),
                        "thumbnail_path": video.get("thumbnail_path")
                    }
                    for video in videos
                ]
            }
            filename = f"{playlist['name'].replace(' ', '_')}.json"
            return jsonify(export_data), 200, {
                "Content-Disposition": f"attachment; filename=\"{filename}\""
            }

    def generate_fcpxml(playlist, videos, drive):
        """Generate FCPXML for Final Cut Pro import."""
        import xml.etree.ElementTree as ET
        from datetime import datetime
        
        # FCPXML 1.10 format
        root = ET.Element("fcpxml", version="1.10")
        
        # Resources
        resources = ET.SubElement(root, "resources")
        
        # Format resource
        format_res = ET.SubElement(resources, "format", {
            "id": "r1",
            "name": "FFVideoFormat1080p30",
            "width": "1920",
            "height": "1080"
        })
        
        # Add asset resources for each video
        for i, video in enumerate(videos):
            asset_id = f"r{i+2}"
            file_path = (drive / video["file_path"]).resolve()
            duration_ms = int(video.get("duration_seconds", 0) * 1000)
            duration = f"{duration_ms}/1000s" if duration_ms > 0 else "0/1s"
            asset = ET.SubElement(resources, "asset", {
                "id": asset_id,
                "name": video["file_name"],
                "src": f"file://{file_path}",
                "duration": duration,
                "hasVideo": "1",
                "hasAudio": "1"
            })
        
        # Library
        library = ET.SubElement(root, "library")
        
        # Event
        event = ET.SubElement(library, "event", {"name": playlist["name"]})
        
        # Project
        project = ET.SubElement(event, "project", {"name": playlist["name"]})
        
        # Sequence
        sequence = ET.SubElement(project, "sequence", {
            "duration": "0/1s",
            "format": "r1"
        })
        
        spine = ET.SubElement(sequence, "spine")
        
        # Add clips to spine
        for i, video in enumerate(videos):
            asset_id = f"r{i+2}"
            duration_ms = int(video.get("duration_seconds", 0) * 1000)
            duration = f"{duration_ms}/1000s" if duration_ms > 0 else "0/1s"
            clip = ET.SubElement(spine, "asset-clip", {
                "ref": asset_id,
                "duration": duration,
                "name": video["file_name"]
            })
        
        # Convert to string
        try:
            ET.indent(root, space="  ")
        except AttributeError:
            pass  # Python < 3.9 doesn't have ET.indent
        xml_str = ET.tostring(root, encoding="unicode")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

    @app.route("/api/videos/<int:video_id>/playlists", methods=["GET"])
    def api_get_video_playlists(video_id: int):
        """Get all playlists that contain a specific video."""
        conn = get_db_conn()
        rows = conn.execute(
            """SELECT p.*, pi.position
               FROM playlists p
               JOIN playlist_items pi ON p.id = pi.playlist_id
               WHERE pi.video_id = ?
               ORDER BY p.name""",
            (video_id,)
        ).fetchall()
        return jsonify({"playlists": [dict(r) for r in rows]})

    @app.route("/api/batch/add-to-playlist", methods=["POST"])
    def api_batch_add_to_playlist():
        """Add multiple videos to a playlist."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        video_ids = data.get("video_ids", [])
        playlist_id = data.get("playlist_id")
        playlist_name = data.get("playlist_name")

        if not video_ids:
            return jsonify({"error": "No video IDs provided"}), 400

        conn = get_db_conn()

        # Create playlist if name provided and not existing
        if playlist_name and not playlist_id:
            try:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO playlists (name, color) VALUES (?, ?)",
                    (playlist_name, "#3b82f6")
                )
                if cursor.lastrowid:
                    playlist_id = cursor.lastrowid
                else:
                    # Get existing playlist ID
                    row = conn.execute(
                        "SELECT id FROM playlists WHERE name = ?", (playlist_name,)
                    ).fetchone()
                    playlist_id = row[0]
            except sqlite3.Error as e:
                return jsonify({"error": f"Failed to create playlist: {e}"}), 500

        if not playlist_id:
            return jsonify({"error": "Playlist ID or name is required"}), 400

        try:
            # Get current max position
            row = conn.execute(
                "SELECT COALESCE(MAX(position), 0) FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,)
            ).fetchone()
            start_pos = row[0] + 1 if row else 1

            added_count = 0
            for idx, video_id in enumerate(video_ids):
                try:
                    conn.execute(
                        "INSERT INTO playlist_items (playlist_id, video_id, position) VALUES (?, ?, ?)",
                        (playlist_id, video_id, start_pos + idx)
                    )
                    added_count += 1
                except sqlite3.IntegrityError:
                    pass  # Video already in playlist, skip

            # Update playlist timestamp
            conn.execute(
                "UPDATE playlists SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
                (playlist_id,)
            )
            conn.commit()

            return jsonify({
                "success": True,
                "added_count": added_count,
                "skipped_count": len(video_ids) - added_count,
                "playlist_id": playlist_id
            })
        except sqlite3.Error as e:
            return jsonify({"error": str(e)}), 500

    # Initialize playlists table on app startup
    with app.app_context():
        try:
            init_playlists_table()
        except Exception as e:
            app.logger.warning(f"Could not initialize playlists table: {e}")

    return app
