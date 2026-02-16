# src/broll/scanner.py
"""
Filesystem scanner — discovers video files, detects source devices,
maps DJI LRF previews to their full-resolution counterparts, and
identifies new/changed files by comparing against the database.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .config import VIDEO_EXTENSIONS, LRF_EXTENSION, DB_FILENAME, THUMBS_DIRNAME


# Directories we should never descend into
SKIP_DIRS: set[str] = {
    ".broll_thumbs",
    ".Spotlight-V100",
    ".fseventsd",
    ".Trashes",
    ".DocumentRevisions-V100",
    "__pycache__",
    ".git",
}


def compute_file_hash(filepath: str | Path, chunk_size: int = 65536) -> str:
    """
    Fast partial hash — reads first + last 64KB and includes file size.
    This is sufficient for change detection without reading multi-GB files fully.
    """
    filepath = str(filepath)
    h = hashlib.md5()
    size = os.path.getsize(filepath)

    with open(filepath, "rb") as f:
        h.update(f.read(chunk_size))
        if size > chunk_size * 2:
            f.seek(-chunk_size, 2)
            h.update(f.read(chunk_size))

    # Include file size to differentiate files with identical headers
    h.update(str(size).encode())
    return h.hexdigest()


def _is_video_file(path: Path) -> bool:
    """Check if a file is a video we should process."""
    return path.suffix.lower() in {ext.lower() for ext in VIDEO_EXTENSIONS}


def _is_lrf_file(path: Path) -> bool:
    """Check if a file is a DJI low-resolution preview."""
    return path.suffix.lower() == LRF_EXTENSION.lower()


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped during scanning."""
    return dirname in SKIP_DIRS or dirname.startswith(".")


def detect_source_device(path: Path) -> str:
    """
    Heuristic detection of source device from filename patterns.

    DJI Osmo Pocket 3:  DJI_20240115143022_0001_D.mp4
    iPhone:             IMG_1234.MOV, IMG_1234.MP4, RPReplay_Final1234.MP4
    """
    name = path.stem.upper()

    if name.startswith("DJI_"):
        return "dji_pocket3"
    elif name.startswith("IMG_") or name.startswith("RPREPLAY"):
        return "iphone"

    # Check parent directory names for clues
    parts = [p.upper() for p in path.parts]
    if any("DJI" in p for p in parts):
        return "dji_pocket3"
    if any("DCIM" in p for p in parts):
        return "iphone"

    return "unknown"


def _build_lrf_map(root: Path) -> dict[str, str]:
    """
    Walk the drive and build a mapping of video stems to their LRF file paths.

    DJI names its files consistently:
        DJI_20240115143022_0001_D.mp4
        DJI_20240115143022_0001_D.LRF

    So we can match by stem (filename without extension).
    """
    lrf_map: dict[str, str] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune directories we don't want to enter
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for filename in filenames:
            path = Path(dirpath) / filename
            if path.name.startswith("._"):
                continue
            if _is_lrf_file(path):
                lrf_map[path.stem] = str(path)

    return lrf_map


def scan_drive(
    root_path: str | Path,
    existing_hashes: dict[str, str],
    force: bool = False,
) -> list[dict]:
    """
    Walk the directory tree looking for video files.
    Compare against existing database entries to find new/changed files.

    Args:
        root_path: Root of the external drive to scan.
        existing_hashes: Dict of {relative_path: file_hash} from the database.
        force: If True, return all files regardless of whether they've been processed.

    Returns:
        List of dicts describing each new/changed video file.
    """
    root = Path(root_path).resolve()
    new_files: list[dict] = []

    # First pass: collect all LRF files for quick lookup
    lrf_map = _build_lrf_map(root)

    # Second pass: find video files
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune system/hidden directories
        dirnames[:] = sorted(d for d in dirnames if not _should_skip_dir(d))

        for filename in sorted(filenames):
            path = Path(dirpath) / filename

            if not _is_video_file(path):
                continue

            # Skip macOS resource fork files (._filename)
            if path.name.startswith("._"):
                continue

            # Skip the database and thumbnail files
            if path.name == DB_FILENAME:
                continue

            relative = str(path.relative_to(root))

            # Compute hash for change detection
            try:
                file_hash = compute_file_hash(path)
            except OSError as e:
                print(f"  ⚠️  Could not read {relative}: {e}")
                continue

            # Skip if already processed and unchanged (unless --force)
            if not force:
                if relative in existing_hashes and existing_hashes[relative] == file_hash:
                    continue

            # Check for matching LRF file (same stem)
            lrf_path = lrf_map.get(path.stem)

            # Detect source device
            source = detect_source_device(path)

            new_files.append(
                {
                    "absolute_path": str(path),
                    "file_path": relative,
                    "file_name": filename,
                    "file_size": path.stat().st_size,
                    "file_hash": file_hash,
                    "source_device": source,
                    "lrf_path": lrf_path,
                }
            )

    return new_files
