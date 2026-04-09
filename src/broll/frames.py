# src/broll/frames.py
"""
Keyframe extraction from video files using ffmpeg.

For DJI Pocket 3 footage, prefers the low-resolution .LRF preview file
for faster extraction — the LLM only needs small frames anyway.
"""
from __future__ import annotations

import subprocess
import json
from pathlib import Path

from .config import NUM_KEYFRAMES


def get_video_duration(file_path: str) -> float | None:
    """Get video duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return None

        probe = json.loads(result.stdout)
        duration = probe.get("format", {}).get("duration")
        return float(duration) if duration else None

    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return None

def _get_stream_duration(file_path: str) -> float | None:
    """
    Fallback duration detection using stream-level info.
    Some corrupted or unusual files have duration in the stream
    but not in the format/container level.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_entries", "stream=duration,nb_frames,r_frame_rate",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return None

        probe = json.loads(result.stdout)
        for stream in probe.get("streams", []):
            d = stream.get("duration")
            if d:
                return float(d)
        return None

    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return None

def extract_keyframes(
    video_info: dict,
    num_frames: int = NUM_KEYFRAMES,
    thumb_dir: str | Path | None = None,
) -> list[bytes]:
    """
    Extract evenly-spaced keyframes from a video as JPEG bytes.

    If the video has an associated LRF file (DJI footage), that is used
    instead for much faster extraction.

    Falls back to fixed-interval extraction if duration is unknown
    (e.g. corrupted/unfinalized recordings).
    """
    source_path = video_info.get("lrf_path") or video_info["absolute_path"]

    duration = get_video_duration(source_path)

    if duration is None or duration < 0.5:
        source_path = video_info["absolute_path"]
        duration = get_video_duration(source_path)

    if duration is None or duration < 0.5:
        duration = _get_stream_duration(source_path)

    frames: list[bytes] = []

    if duration and duration >= 0.5:
        # Normal path: evenly-spaced timestamps
        for i in range(num_frames):
            timestamp = duration * (i + 1) / (num_frames + 1)
            try:
                frame_bytes = _extract_single_frame(source_path, timestamp)
                if frame_bytes:
                    frames.append(frame_bytes)
            except Exception:
                continue
    else:
        # Fallback for unknown duration: try fixed timestamps
        print(f"    Duration unknown, trying fixed timestamps...")
        fallback_timestamps = [0.5, 3.0, 8.0, 15.0, 30.0]
        for ts in fallback_timestamps:
            try:
                frame_bytes = _extract_single_frame(source_path, ts)
                if frame_bytes:
                    frames.append(frame_bytes)
                    if len(frames) >= num_frames:
                        break
            except Exception:
                # Hit past the end of the file or other error, stop trying
                break

    if not frames:
        raise ValueError(f"Could not extract any frames from {video_info['file_name']}")

    # Save thumbnail
    if thumb_dir and frames:
        _save_thumbnail(frames[0], video_info["file_hash"], thumb_dir)
        thumb_path = str(Path(thumb_dir) / f"{video_info['file_hash']}.jpg")
        video_info["thumbnail_path"] = thumb_path

    return frames


def extract_keyframes_optimized(
    video_info: dict,
    num_frames: int = NUM_KEYFRAMES,
    thumb_dir: str | Path | None = None,
) -> list[bytes]:
    """
    Extract evenly-spaced keyframes from a video using optimized single FFmpeg invocation.

    Uses FFmpeg's select filter to extract all frames in one pass,
    reducing subprocess overhead compared to multiple _extract_single_frame calls.

    Args:
        video_info: Video info dict with 'absolute_path', 'file_name', etc.
        num_frames: Number of frames to extract
        thumb_dir: Optional thumbnail directory

    Returns:
        List of JPEG bytes for each frame
    """
    source_path = video_info.get("lrf_path") or video_info["absolute_path"]

    duration = get_video_duration(source_path)

    if duration is None or duration < 0.5:
        source_path = video_info["absolute_path"]
        duration = get_video_duration(source_path)

    if duration is None or duration < 0.5:
        duration = _get_stream_duration(source_path)

    if duration is None or duration < 0.5:
        raise ValueError(f"Could not determine duration for {video_info['file_name']}")

    # Build select filter for evenly-spaced frames
    # select='not(mod(n,INTERVAL))' picks every INTERVALth frame
    # We need to calculate interval based on duration and frame rate
    # Instead, use select='isnan(prev_selected_t)+gte(t,timestamp)' for timestamp-based selection

    timestamps = [duration * (i + 1) / (num_frames + 1) for i in range(num_frames)]

    # Build select expression: pick first frame at or after each timestamp
    # Using isequal(t,timestamp) won't work due to frame boundaries
    # Better: use between() for a small window around each timestamp

    # Create multiple outputs using split and select filters
    # This is complex - simpler approach: use thumbnail filter with multiple outputs

    # Actually, use a simpler approach: pipe all frames from select filter
    # and parse them on the fly

    # Use scene-based selection: pick the frame closest to each target timestamp
    select_expr = "+".join([f"isnan(prev_selected_t)+gte(t,{ts:.3f})" for ts in timestamps])

    cmd = [
        "ffmpeg",
        "-i", source_path,
        "-vf", f"select='{select_expr}',scale=720:-2",
        "-vsync", "vfr",
        "-q:v", "3",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-loglevel", "error",
        "pipe:1",
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=60)

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        # Fallback to original method on failure
        raise RuntimeError(f"Optimized FFmpeg failed: {stderr[:200]}")

    # Parse the output - image2pipe produces concatenated JPEGs
    # Each JPEG starts with \xff\xd8 and ends with \xff\xd9
    frames = _parse_mjpeg_stream(result.stdout)

    if len(frames) < num_frames:
        # Not enough frames extracted, fallback to original method
        raise RuntimeError(f"Only extracted {len(frames)}/{num_frames} frames")

    # Save thumbnail (first frame)
    if thumb_dir and frames:
        _save_thumbnail(frames[0], video_info["file_hash"], thumb_dir)
        thumb_path = str(Path(thumb_dir) / f"{video_info['file_hash']}.jpg")
        video_info["thumbnail_path"] = thumb_path

    return frames[:num_frames]


def _parse_mjpeg_stream(data: bytes) -> list[bytes]:
    """
    Parse concatenated JPEG frames from image2pipe output.

    Each JPEG starts with SOI marker (\xff\xd8) and ends with EOI marker (\xff\xd9).
    """
    frames = []
    start = 0

    # Find all JPEG start markers
    while True:
        # Find next SOI marker
        soi = data.find(b"\xff\xd8", start)
        if soi == -1:
            break

        # Find corresponding EOI marker
        eoi = data.find(b"\xff\xd9", soi + 2)
        if eoi == -1:
            break

        # Extract frame (including both markers)
        frame = data[soi : eoi + 2]
        if len(frame) > 100:  # Sanity check - must be a real JPEG
            frames.append(frame)

        start = eoi + 2

    return frames


def _extract_single_frame(source_path: str, timestamp: float) -> bytes | None:
    """
    Extract a single frame at the given timestamp using ffmpeg.

    Scales the output to 720px wide (maintaining aspect ratio) to keep
    things efficient for the LLM — it doesn't need 4K frames.
    """
    cmd = [
        "ffmpeg",
        "-ss", str(timestamp),          # Seek to timestamp (fast seek before input)
        "-i", source_path,
        "-vframes", "1",                # Extract exactly one frame
        "-vf", "scale=720:-2",          # Scale to 720px wide, maintain aspect ratio
        "-q:v", "3",                    # JPEG quality (2-5 is good, lower = better)
        "-f", "image2",                 # Output format
        "-vcodec", "mjpeg",             # JPEG codec
        "-y",                           # Overwrite output (needed for pipe)
        "-loglevel", "error",           # Suppress noisy output
        "pipe:1",                       # Output to stdout
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=30)

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"ffmpeg error: {stderr[:200]}")

    if not result.stdout:
        return None

    return result.stdout


def _save_thumbnail(frame_bytes: bytes, file_hash: str, thumb_dir: str | Path):
    """Save a frame as a JPEG thumbnail for the web UI."""
    thumb_dir = Path(thumb_dir)
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / f"{file_hash}.jpg"
    thumb_path.write_bytes(frame_bytes)
