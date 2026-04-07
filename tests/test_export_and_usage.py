"""Tests for project export and search with usage."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest


class TestProjectExport:
    """Tests for project export functionality."""

    def test_export_project_not_found(self, empty_project_db, tmp_path):
        """Export a project that doesn't exist."""
        db = empty_project_db
        output_path = tmp_path / "export.zip"

        with pytest.raises(ValueError, match="Project not found"):
            db.export_project(123, output_path, tmp_path)

    def test_export_project_no_clips(self, empty_project_db, tmp_path):
        """Export a project with no clips."""
        db = empty_project_db
        project_id = db.create_project("Test Project")
        output_path = tmp_path / "export.zip"

        with pytest.raises(ValueError, match="Project has no clips"):
            db.export_project(project_id, output_path, tmp_path)


class TestSearchWithUsage:
    """Tests for search with usage filtering."""

    def test_search_with_usage_count(self, empty_project_db):
        """Search returns usage count when show_usage is True."""
        db = empty_project_db

        # Create videos
        conn = db.connect()
        conn.execute(
            "INSERT INTO videos (file_path, file_name, file_size, file_hash, duration_seconds, width, height) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test1.mp4", "test1.mp4", 1000, "hash1", 60.0, 1920, 1080)
        )
        conn.commit()

        # Use in two projects
        p1 = db.create_project("Project 1")
        p2 = db.create_project("Project 2")
        db.add_project_clip(p1, video_id=1, position=1)
        db.add_project_clip(p2, video_id=1, position=1)

        # Search with usage
        results = db.search_with_usage_filter("test1", show_usage=True)

        # Find result for video 1
        video_results = [r for r in results if r["video_id"] == 1]
        assert len(video_results) > 0
        assert video_results[0]["usage_count"] == 2

    def test_search_exclude_used_in_project(self, empty_project_db):
        """Search can exclude clips used in a specific project."""
        db = empty_project_db

        # Create videos
        conn = db.connect()
        conn.execute(
            "INSERT INTO videos (file_path, file_name, file_size, file_hash, duration_seconds, width, height) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test1.mp4", "test1.mp4", 1000, "hash1", 60.0, 1920, 1080)
        )
        conn.commit()

        # Use in one project
        p1 = db.create_project("Project 1")
        db.add_project_clip(p1, video_id=1, position=1)

        # Search excluding used clips
        results = db.search_with_usage_filter("test1", exclude_used_in_project=p1)

        # Should not find video 1 since it's used in project p1
        video_results = [r for r in results if r.get("video_id") == 1]
        assert len(video_results) == 0
