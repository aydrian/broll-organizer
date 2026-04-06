"""
Video proxy generation for smooth web playback.

Generates low-bitrate H.264 transcoded versions of videos for use in
hover previews and main video player to avoid stuttering with
high-bitrate source files.
"""

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Optional

from broll.config import get_proxy_dir

logger = logging.getLogger(__name__)


def generate_proxy(
    source_path: Path,
    proxy_path: Path,
    target_height: int = 480,
    crf: int = 28,
) -> bool:
    """
    Generate a low-bitrate proxy video using FFmpeg.

    Args:
        source_path: Path to the original video file
        proxy_path: Path where the proxy should be saved
        target_height: Target height in pixels (width auto-calculated to maintain aspect)
        crf: Constant Rate Factor (lower = better quality, higher = smaller file)
             23 is default, 28 is good for proxies

    Returns:
        True if successful, False otherwise
    """
    proxy_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite if exists
        "-i", str(source_path),
        "-vf", f"scale=-2:{target_height}",  # Maintain aspect ratio, fit to height
        "-c:v", "libx264",
        "-preset", "fast",  # Balance between speed and compression
        "-crf", str(crf),  # Quality level (28 = ~800-1200kbps for 480p)
        "-pix_fmt", "yuv420p",  # Ensure browser compatibility
        "-c:a", "aac",
        "-b:a", "64k",  # Low audio bitrate (preview doesn't need high quality audio)
        "-movflags", "+faststart",  # Web-optimized (moov atom at front)
        "-loglevel", "error",  # Only show errors
        str(proxy_path),
    ]

    try:
        logger.info(f"Generating proxy: {source_path.name} -> {proxy_path}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stderr:
            logger.debug(f"FFmpeg stderr: {result.stderr}")

        # Verify the file was created and has content
        if not proxy_path.exists() or proxy_path.stat().st_size == 0:
            logger.error(f"Proxy file not created or empty: {proxy_path}")
            return False

        # Log size reduction
        orig_size = source_path.stat().st_size
        proxy_size = proxy_path.stat().st_size
        ratio = proxy_size / orig_size if orig_size > 0 else 0
        logger.info(
            f"Proxy created: {orig_size / (1024*1024):.1f}MB -> "
            f"{proxy_size / (1024*1024):.1f}MB ({ratio:.1%})"
        )

        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed: {e.stderr}")
        # Clean up partial file
        if proxy_path.exists():
            proxy_path.unlink()
        return False
    except Exception as e:
        logger.error(f"Failed to generate proxy: {e}")
        if proxy_path.exists():
            proxy_path.unlink()
        return False


def get_proxy_path(
    file_hash: str,
    drive_root: Path,
    proxy_dir: Optional[Path] = None,
) -> Path:
    """
    Get the path where a proxy should be stored.

    Args:
        file_hash: Hash of the source video (used as filename)
        drive_root: Root path of the drive
        proxy_dir: Optional custom proxy directory (uses config default if not provided)

    Returns:
        Path to the proxy file location
    """
    if proxy_dir is None:
        proxy_dir = get_proxy_dir(drive_root)
    return proxy_dir / f"{file_hash}.mp4"


def proxy_exists(
    file_hash: str,
    drive_root: Path,
    proxy_dir: Optional[Path] = None,
) -> bool:
    """
    Check if a proxy already exists for the given file hash.

    Args:
        file_hash: Hash of the source video
        drive_root: Root path of the drive
        proxy_dir: Optional custom proxy directory

    Returns:
        True if proxy exists and is non-empty
    """
    proxy_path = get_proxy_path(file_hash, drive_root, proxy_dir)
    return proxy_path.exists() and proxy_path.stat().st_size > 0


def delete_proxy(
    file_hash: str,
    drive_root: Path,
    proxy_dir: Optional[Path] = None,
) -> bool:
    """
    Delete a proxy file if it exists.

    Args:
        file_hash: Hash of the source video
        drive_root: Root path of the drive
        proxy_dir: Optional custom proxy directory

    Returns:
        True if proxy was deleted (or didn't exist), False on error
    """
    proxy_path = get_proxy_path(file_hash, drive_root, proxy_dir)
    if not proxy_path.exists():
        return True

    try:
        proxy_path.unlink()
        logger.info(f"Deleted proxy: {proxy_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete proxy: {e}")
        return False
