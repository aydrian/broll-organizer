"""
Health check and validation utilities for the b-roll catalog.

Provides diagnostics for finding inconsistencies between the database
and the filesystem, missing thumbnails, hash mismatches, duplicates, etc.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .config import VIDEO_EXTENSIONS, THUMBS_DIRNAME, get_thumbs_dir

if TYPE_CHECKING:
    from .db import Database


@dataclass
class HealthIssue:
    """Represents a single health check issue."""
    type: str
    description: str
    details: dict = field(default_factory=dict)
    fixable: bool = False


@dataclass
class HealthReport:
    """Complete health check report with all issues found."""
    issues: list[HealthIssue] = field(default_factory=list)
    healthy: bool = True
    
    # Issue counts by type
    missing_files: int = 0
    files_not_in_db: int = 0
    missing_thumbnails: int = 0
    hash_mismatches: int = 0
    duplicates: int = 0
    missing_metadata: int = 0
    orphaned_thumbnails: int = 0
    
    def add_issue(self, issue: HealthIssue) -> None:
        """Add an issue to the report."""
        self.issues.append(issue)
        self.healthy = False
        
        # Update counters
        if issue.type == "missing_file":
            self.missing_files += 1
        elif issue.type == "file_not_in_db":
            self.files_not_in_db += 1
        elif issue.type == "missing_thumbnail":
            self.missing_thumbnails += 1
        elif issue.type == "hash_mismatch":
            self.hash_mismatches += 1
        elif issue.type == "duplicate":
            self.duplicates += 1
        elif issue.type == "missing_metadata":
            self.missing_metadata += 1
        elif issue.type == "orphaned_thumbnail":
            self.orphaned_thumbnails += 1


def _get_video_files_on_drive(drive_path: Path) -> dict[str, Path]:
    """Scan drive and return dict of {relative_path: absolute_path} for video files."""
    video_files = {}
    for dirpath, dirnames, filenames in os.walk(drive_path):
        # Skip hidden/system directories
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {
            "__pycache__", ".git", ".broll_thumbs", ".Spotlight-V100", 
            ".fseventsd", ".Trashes"
        }]
        
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in {ext.lower() for ext in VIDEO_EXTENSIONS}:
                if not path.name.startswith("._"):  # Skip macOS resource forks
                    try:
                        relative = str(path.relative_to(drive_path))
                        video_files[relative] = path
                    except ValueError:
                        continue
    return video_files


def _get_thumbnails_on_drive(thumbs_dir: Path) -> set[str]:
    """Get set of all thumbnail filenames in the thumbs directory."""
    if not thumbs_dir.exists():
        return set()
    
    thumbnails = set()
    for filename in os.listdir(thumbs_dir):
        if filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
            thumbnails.add(filename)
    return thumbnails


def _compute_file_hash(filepath: str | Path) -> str:
    """Fast partial hash for comparison."""
    import hashlib
    chunk_size = 65536
    size = os.path.getsize(filepath)
    
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        h.update(f.read(chunk_size))
        if size > chunk_size * 2:
            f.seek(-chunk_size, 2)
            h.update(f.read(chunk_size))
    h.update(str(size).encode())
    return h.hexdigest()


def check_missing_files(db: Database, drive_path: Path) -> list[HealthIssue]:
    """Find database records pointing to files that no longer exist."""
    issues = []
    all_videos = db.get_all_videos(limit=1000000)  # Get all
    
    for video in all_videos:
        relative_path = video.get("file_path")
        if not relative_path:
            continue
            
        absolute_path = drive_path / relative_path
        if not absolute_path.exists():
            issues.append(HealthIssue(
                type="missing_file",
                description=f"Missing file: {relative_path}",
                details={
                    "video_id": video.get("id"),
                    "file_path": relative_path,
                    "absolute_path": str(absolute_path),
                },
                fixable=True,
            ))
    
    return issues


def check_files_not_in_db(db: Database, drive_path: Path) -> list[HealthIssue]:
    """Find video files on the drive that are not in the database."""
    issues = []
    existing_paths = set()
    
    # Get all paths from DB
    all_videos = db.get_all_videos(limit=1000000)
    for video in all_videos:
        if video.get("file_path"):
            existing_paths.add(video.get("file_path"))
    
    # Scan drive for videos
    video_files = _get_video_files_on_drive(drive_path)
    
    for relative_path in video_files:
        if relative_path not in existing_paths:
            issues.append(HealthIssue(
                type="file_not_in_db",
                description=f"File not cataloged: {relative_path}",
                details={
                    "file_path": relative_path,
                    "absolute_path": str(video_files[relative_path]),
                },
                fixable=False,  # Requires processing to add to DB
            ))
    
    return issues


def check_missing_thumbnails(db: Database, drive_path: Path) -> list[HealthIssue]:
    """Find videos in DB that should have thumbnails but don't."""
    issues = []
    thumbs_dir = get_thumbs_dir(drive_path)
    all_videos = db.get_all_videos(limit=1000000)
    
    for video in all_videos:
        # Skip videos that weren't fully processed (scan-only mode)
        scene_desc = video.get("scene_description", "")
        if not scene_desc or scene_desc.startswith("ERROR"):
            continue
        
        thumbnail_path = video.get("thumbnail_path")
        if not thumbnail_path:
            # Should have thumbnail but doesn't
            issues.append(HealthIssue(
                type="missing_thumbnail",
                description=f"Missing thumbnail: {video.get('file_name', 'unknown')}",
                details={
                    "video_id": video.get("id"),
                    "file_path": video.get("file_path"),
                },
                fixable=True,
            ))
        else:
            # Check if thumbnail file actually exists
            full_thumb_path = thumbs_dir / Path(thumbnail_path).name
            if not full_thumb_path.exists():
                issues.append(HealthIssue(
                    type="missing_thumbnail",
                    description=f"Thumbnail file missing: {thumbnail_path}",
                    details={
                        "video_id": video.get("id"),
                        "file_path": video.get("file_path"),
                        "thumbnail_path": thumbnail_path,
                    },
                    fixable=True,
                ))
    
    return issues


def check_hash_mismatches(db: Database, drive_path: Path) -> list[HealthIssue]:
    """Find videos where the stored hash doesn't match the current file hash."""
    issues = []
    all_videos = db.get_all_videos(limit=1000000)
    
    for video in all_videos:
        relative_path = video.get("file_path")
        stored_hash = video.get("file_hash")
        
        if not relative_path or not stored_hash:
            continue
        
        absolute_path = drive_path / relative_path
        if not absolute_path.exists():
            continue  # Missing files handled separately
        
        try:
            current_hash = _compute_file_hash(absolute_path)
            if current_hash != stored_hash:
                issues.append(HealthIssue(
                    type="hash_mismatch",
                    description=f"Hash mismatch: {relative_path}",
                    details={
                        "video_id": video.get("id"),
                        "file_path": relative_path,
                        "stored_hash": stored_hash,
                        "current_hash": current_hash,
                    },
                    fixable=True,
                ))
        except OSError:
            continue  # File access error, skip
    
    return issues


def check_duplicates(db: Database) -> list[HealthIssue]:
    """Find potential duplicate entries (same hash, different paths)."""
    issues = []
    all_videos = db.get_all_videos(limit=1000000)
    
    # Group videos by hash
    by_hash = defaultdict(list)
    for video in all_videos:
        file_hash = video.get("file_hash")
        if file_hash:
            by_hash[file_hash].append(video)
    
    # Find hashes with multiple videos
    for file_hash, videos in by_hash.items():
        if len(videos) > 1:
            paths = [v.get("file_path") for v in videos]
            ids = [v.get("id") for v in videos]
            issues.append(HealthIssue(
                type="duplicate",
                description=f"Duplicate entries ({len(videos)} files with same hash)",
                details={
                    "hash": file_hash,
                    "video_ids": ids,
                    "file_paths": paths,
                },
                fixable=True,
            ))
    
    return issues


def check_missing_metadata(db: Database) -> list[HealthIssue]:
    """Find videos lacking AI-generated descriptions or tags."""
    issues = []
    all_videos = db.get_all_videos(limit=1000000)
    
    for video in all_videos:
        scene_desc = video.get("scene_description")
        tags = video.get("tags")
        
        # Check if metadata is missing or was an error
        is_error = scene_desc and scene_desc.startswith("ERROR")
        
        if not scene_desc or is_error or not tags:
            issues.append(HealthIssue(
                type="missing_metadata",
                description=f"Missing metadata: {video.get('file_name', 'unknown')}",
                details={
                    "video_id": video.get("id"),
                    "file_path": video.get("file_path"),
                    "has_description": bool(scene_desc and not is_error),
                    "has_tags": bool(tags),
                    "is_error": is_error,
                },
                fixable=True,  # Can be fixed by reprocessing
            ))
    
    return issues


def check_orphaned_thumbnails(db: Database, drive_path: Path) -> list[HealthIssue]:
    """Find thumbnail files that don't correspond to any video in the database."""
    issues = []
    thumbs_dir = get_thumbs_dir(drive_path)
    
    if not thumbs_dir.exists():
        return issues
    
    # Get all video IDs that have thumbnails
    all_videos = db.get_all_videos(limit=1000000)
    valid_thumbnail_stems = set()
    
    for video in all_videos:
        video_id = video.get("id")
        if video_id is not None:
            # Thumbnails are typically named like: {video_id}_frame_*.jpg
            # Or could be stored with the video filename
            valid_thumbnail_stems.add(str(video_id))
    
    # Also track expected thumbnail names based on stored paths
    expected_thumbnails = set()
    for video in all_videos:
        thumb_path = video.get("thumbnail_path")
        if thumb_path:
            expected_thumbnails.add(Path(thumb_path).name)
    
    # Scan actual thumbnail files
    for filename in os.listdir(thumbs_dir):
        if not filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        
        # Check if this thumbnail corresponds to any known video
        # Thumbnail naming convention: {video_id}_frame_{frame_num}.jpg
        is_orphaned = True
        
        # Check if filename starts with a valid video ID
        for vid_id in valid_thumbnail_stems:
            if filename.startswith(f"{vid_id}_") or filename == expected_thumbnails.get(vid_id):
                is_orphaned = False
                break
        
        # Also check by full expected filename
        if filename in expected_thumbnails:
            is_orphaned = False
        
        if is_orphaned:
            issues.append(HealthIssue(
                type="orphaned_thumbnail",
                description=f"Orphaned thumbnail: {filename}",
                details={
                    "filename": filename,
                    "path": str(thumbs_dir / filename),
                },
                fixable=True,
            ))
    
    return issues


def run_health_check(
    db: Database,
    drive_path: Path,
    check_thumbnails: bool = True,
    check_orphaned: bool = True,
    check_hashes: bool = True,
    check_all: bool = True,
) -> HealthReport:
    """Run comprehensive health check on the catalog."""
    report = HealthReport()
    
    # Always run basic checks
    for issue in check_missing_files(db, drive_path):
        report.add_issue(issue)
    
    for issue in check_files_not_in_db(db, drive_path):
        report.add_issue(issue)
    
    for issue in check_duplicates(db):
        report.add_issue(issue)
    
    for issue in check_missing_metadata(db):
        report.add_issue(issue)
    
    # Conditional checks
    if check_thumbnails:
        for issue in check_missing_thumbnails(db, drive_path):
            report.add_issue(issue)
    
    if check_orphaned:
        for issue in check_orphaned_thumbnails(db, drive_path):
            report.add_issue(issue)
    
    if check_hashes:
        for issue in check_hash_mismatches(db, drive_path):
            report.add_issue(issue)
    
    return report


def fix_missing_files(db: Database, issues: list[HealthIssue], dry_run: bool = False) -> int:
    """Remove database entries for missing files. Returns count of fixed issues."""
    fixed = 0
    for issue in issues:
        if issue.type != "missing_file":
            continue
        
        video_id = issue.details.get("video_id")
        if video_id:
            if not dry_run:
                db.delete_video(video_id)
            fixed += 1
    
    return fixed


def fix_orphaned_thumbnails(issues: list[HealthIssue], drive_path: Path, dry_run: bool = False) -> int:
    """Delete orphaned thumbnail files. Returns count of fixed issues."""
    fixed = 0
    thumbs_dir = get_thumbs_dir(drive_path)
    
    for issue in issues:
        if issue.type != "orphaned_thumbnail":
            continue
        
        thumb_path = issue.details.get("path")
        if thumb_path:
            path = Path(thumb_path)
            if path.exists():
                if not dry_run:
                    path.unlink()
                fixed += 1
    
    return fixed


def format_text_report(report: HealthReport, drive_path: Path) -> str:
    """Format health report as human-readable text."""
    lines = []
    
    lines.append(f"\n{'=' * 60}")
    lines.append("B-Roll Catalog Health Report")
    lines.append(f"Drive: {drive_path}")
    lines.append(f"{'=' * 60}")
    
    if report.healthy:
        lines.append("\n✅ Catalog is healthy! No issues found.")
    else:
        lines.append(f"\n⚠️  Found {len(report.issues)} issue(s):")
        lines.append("")
        
        # Group by type
        by_type = defaultdict(list)
        for issue in report.issues:
            by_type[issue.type].append(issue)
        
        for issue_type, issues in sorted(by_type.items()):
            lines.append(f"  {issue_type.replace('_', ' ').title()} ({len(issues)}):")
            for issue in issues[:5]:  # Show first 5
                lines.append(f"    - {issue.description}")
            if len(issues) > 5:
                lines.append(f"    ... and {len(issues) - 5} more")
            lines.append("")
    
    # Summary
    lines.append(f"{'-' * 60}")
    lines.append("Summary:")
    if report.missing_files:
        lines.append(f"  Missing files:          {report.missing_files}")
    if report.files_not_in_db:
        lines.append(f"  Files not in DB:        {report.files_not_in_db}")
    if report.missing_thumbnails:
        lines.append(f"  Missing thumbnails:     {report.missing_thumbnails}")
    if report.hash_mismatches:
        lines.append(f"  Hash mismatches:        {report.hash_mismatches}")
    if report.duplicates:
        lines.append(f"  Duplicate entries:      {report.duplicates}")
    if report.missing_metadata:
        lines.append(f"  Missing metadata:       {report.missing_metadata}")
    if report.orphaned_thumbnails:
        lines.append(f"  Orphaned thumbnails:    {report.orphaned_thumbnails}")
    
    if report.healthy:
        lines.append("  All checks passed!")
    
    lines.append(f"{'=' * 60}")
    
    return "\n".join(lines)


def format_json_report(report: HealthReport, drive_path: Path) -> str:
    """Format health report as JSON."""
    data = {
        "healthy": report.healthy,
        "drive_path": str(drive_path),
        "total_issues": len(report.issues),
        "counts": {
            "missing_files": report.missing_files,
            "files_not_in_db": report.files_not_in_db,
            "missing_thumbnails": report.missing_thumbnails,
            "hash_mismatches": report.hash_mismatches,
            "duplicates": report.duplicates,
            "missing_metadata": report.missing_metadata,
            "orphaned_thumbnails": report.orphaned_thumbnails,
        },
        "issues": [
            {
                "type": issue.type,
                "description": issue.description,
                "details": issue.details,
                "fixable": issue.fixable,
            }
            for issue in report.issues
        ],
    }
    return json.dumps(data, indent=2)
