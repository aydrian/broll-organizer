# src/broll/metadata.py
"""
Metadata extraction from video files.

- Technical metadata (duration, resolution, fps, codec) via ffprobe
- GPS coordinates via exiftool
- Reverse geocoding via the reverse_geocoder library
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from typing import Any


def extract_technical_metadata(file_path: str) -> dict[str, Any]:
    """
    Extract technical video metadata using ffprobe.

    Returns dict with: duration_seconds, resolution, width, height, fps, codec, creation_date
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {}

        probe = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"  ⚠️  ffprobe error for {file_path}: {e}")
        return {}

    metadata: dict[str, Any] = {}

    # Find the video stream (skip audio, subtitle, data streams)
    video_stream = None
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if video_stream:
        # Resolution
        width = video_stream.get("width")
        height = video_stream.get("height")
        metadata["width"] = width
        metadata["height"] = height
        if width and height:
            metadata["resolution"] = f"{width}x{height}"

        # Codec
        metadata["codec"] = video_stream.get("codec_name")

        # Frame rate (e.g. "30000/1001" → 29.97)
        fps_str = video_stream.get("r_frame_rate", "")
        if fps_str and "/" in fps_str:
            try:
                num, den = fps_str.split("/")
                metadata["fps"] = round(float(num) / float(den), 2)
            except (ValueError, ZeroDivisionError):
                metadata["fps"] = None
        elif fps_str:
            try:
                metadata["fps"] = round(float(fps_str), 2)
            except ValueError:
                metadata["fps"] = None

    # Duration (from format, more reliable than stream)
    fmt = probe.get("format", {})
    duration = fmt.get("duration")
    if duration:
        try:
            metadata["duration_seconds"] = round(float(duration), 2)
        except ValueError:
            pass

    # Creation date — check multiple possible tag locations
    creation_date = _extract_creation_date(probe)
    if creation_date:
        metadata["creation_date"] = creation_date

    return metadata


def _extract_creation_date(probe: dict) -> str | None:
    """
    Try to find the creation date from ffprobe output.
    Different devices store this in different places.
    """
    # Check format-level tags first
    fmt_tags = probe.get("format", {}).get("tags", {})
    # Check stream-level tags as fallback
    stream_tags = {}
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            stream_tags = stream.get("tags", {})
            break

    # Try common tag names (case-insensitive search)
    for tags in [fmt_tags, stream_tags]:
        # Normalize keys to lowercase for comparison
        lower_tags = {k.lower(): v for k, v in tags.items()}

        for key in ["creation_time", "date", "com.apple.quicktime.creationdate"]:
            value = lower_tags.get(key)
            if value:
                return _normalize_datetime(value)

    return None


def _normalize_datetime(dt_string: str) -> str:
    """
    Normalize various datetime formats to ISO 8601.
    Handles formats like:
        2024-01-15T14:30:22.000000Z
        2024-01-15 14:30:22
        2024:01:15 14:30:22
    """
    dt_string = dt_string.strip()

    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(dt_string, fmt)
            return dt.isoformat()
        except ValueError:
            continue

    # If nothing parses, return the original string
    return dt_string


def extract_gps(file_path: str) -> dict[str, Any]:
    """
    Extract GPS coordinates from video metadata using exiftool.

    Works with:
    - iPhone .mp4/.mov files (GPS stored in QuickTime metadata)
    - DJI Osmo Pocket 3 .mp4 files (GPS in XMP/QuickTime tags)

    Returns dict with: gps_latitude, gps_longitude (as floats, or None)
    """
    try:
        cmd = [
            "exiftool",
            "-json",
            "-n",  # Numeric output (decimal degrees, not DMS)
            "-GPSLatitude",
            "-GPSLongitude",
            "-GPSAltitude",
            "-GPSCoordinates",
            # Also check QuickTime-specific location tags
            "-Keys:GPSCoordinates",
            "-UserData:GPSCoordinates",
            "-ItemList:GPSCoordinates",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if result.returncode != 0 or not result.stdout.strip():
            return {"gps_latitude": None, "gps_longitude": None}

        data = json.loads(result.stdout)
        if not data:
            return {"gps_latitude": None, "gps_longitude": None}

        info = data[0]

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"  ⚠️  exiftool error for {file_path}: {e}")
        return {"gps_latitude": None, "gps_longitude": None}

    lat = info.get("GPSLatitude")
    lon = info.get("GPSLongitude")

    # Some devices store coordinates as a combined string "lat lon"
    if lat is None or lon is None:
        gps_coords = info.get("GPSCoordinates")
        if gps_coords and isinstance(gps_coords, str):
            parts = gps_coords.replace(",", " ").split()
            if len(parts) >= 2:
                try:
                    lat = float(parts[0])
                    lon = float(parts[1])
                except ValueError:
                    pass

    # Validate coordinates are reasonable
    if lat is not None and lon is not None:
        try:
            lat = float(lat)
            lon = float(lon)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                lat, lon = None, None
        except (ValueError, TypeError):
            lat, lon = None, None

    return {
        "gps_latitude": lat,
        "gps_longitude": lon,
    }


def reverse_geocode(lat: float, lon: float) -> str | None:
    """
    Convert GPS coordinates to a human-readable place name.
    Uses the offline reverse_geocoder library (no API calls needed).

    Returns a string like "San Francisco, US" or None on failure.
    """
    try:
        import reverse_geocoder as rg

        results = rg.search((lat, lon))
        if results:
            place = results[0]
            city = place.get("name", "")
            country = place.get("cc", "")
            admin1 = place.get("admin1", "")  # State/province

            if city and country:
                if admin1:
                    return f"{city}, {admin1}, {country}"
                return f"{city}, {country}"
    except Exception:
        pass

    return None


def extract_all_metadata(file_path: str) -> dict[str, Any]:
    """
    Convenience function — runs all metadata extraction in one call.

    Returns a combined dict with all technical + GPS + location metadata.
    """
    metadata: dict[str, Any] = {}

    # Technical metadata from ffprobe
    technical = extract_technical_metadata(file_path)
    metadata.update(technical)

    # GPS from exiftool
    gps = extract_gps(file_path)
    metadata.update(gps)

    # Reverse geocode if we have coordinates
    lat = gps.get("gps_latitude")
    lon = gps.get("gps_longitude")
    if lat is not None and lon is not None:
        location_name = reverse_geocode(lat, lon)
        metadata["gps_location_name"] = location_name

    return metadata
