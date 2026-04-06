"""
Tests for project database operations.
"""
from __future__ import annotations

import pytest
from broll.db import Database


class TestProjectCreate:
    """Tests for project creation."""

    def test_create_project_basic(self, empty_project_db):
        """Create a project with minimal fields."""
        db = empty_project_db
        project_id = db.create_project(name="Test Project")

        assert project_id > 0
        project = db.get_project(project_id)
        assert project is not None
        assert project["name"] == "Test Project"
        assert project["status"] == "active"  # default
        assert project["updated_at"] is not None

    def test_create_project_all_fields(self, empty_project_db):
        """Create a project with all fields specified."""
        db = empty_project_db
        project_id = db.create_project(
            name="Full Project",
            description="A test description",
            status="planning",
            aspect_ratio="16:9",
            target_duration_seconds=120.0,
            canva_link="https://www.canva.com/design/abc123"
        )

        project = db.get_project(project_id)
        assert project["name"] == "Full Project"
        assert project["description"] == "A test description"
        assert project["status"] == "planning"
        assert project["aspect_ratio"] == "16:9"
        assert project["target_duration_seconds"] == 120.0
        assert project["canva_link"] == "https://www.canva.com/design/abc123"


class TestProjectList:
    """Tests for listing projects."""

    def test_list_all_projects(self, empty_project_db):
        """List all projects ordered by updated_at DESC."""
        db = empty_project_db

        # Create projects
        db.create_project(name="Project A")
        db.create_project(name="Project B")
        db.create_project(name="Project C")

        projects = db.list_projects()

        assert len(projects) == 3
        # Should be ordered by updated_at DESC (most recent first)
        assert projects[0]["name"] == "Project C"
        assert projects[1]["name"] == "Project B"
        assert projects[2]["name"] == "Project A"

    def test_list_projects_with_filters(self, empty_project_db):
        """List projects filtered by status and aspect_ratio."""
        db = empty_project_db

        # Create projects with different attributes
        db.create_project(name="Active 16:9", status="active", aspect_ratio="16:9")
        db.create_project(name="Archived 16:9", status="archived", aspect_ratio="16:9")
        db.create_project(name="Active 9:16", status="active", aspect_ratio="9:16")

        # Filter by status only
        active_projects = db.list_projects(status="active")
        assert len(active_projects) == 2
        assert all(p["status"] == "active" for p in active_projects)

        # Filter by aspect ratio only
        ratio_16_9 = db.list_projects(aspect_ratio="16:9")
        assert len(ratio_16_9) == 2
        assert all(p["aspect_ratio"] == "16:9" for p in ratio_16_9)

        # Filter by both
        filtered = db.list_projects(status="active", aspect_ratio="16:9")
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Active 16:9"


class TestProjectUpdateDelete:
    """Tests for updating and deleting projects."""

    def test_update_project_fields(self, empty_project_db):
        """Update specific project fields."""
        db = empty_project_db

        project_id = db.create_project(name="Original Name")
        original_project = db.get_project(project_id)
        original_updated_at = original_project["updated_at"]

        # Update fields
        db.update_project(project_id, {"name": "Updated Name", "status": "archived"})

        updated_project = db.get_project(project_id)
        assert updated_project["name"] == "Updated Name"
        assert updated_project["status"] == "archived"
        # updated_at should be refreshed
        assert updated_project["updated_at"] != original_updated_at

    def test_update_project_preserves_other_fields(self, empty_project_db):
        """Update only affects specified fields."""
        db = empty_project_db

        project_id = db.create_project(
            name="Test",
            description="Original description",
            aspect_ratio="16:9"
        )

        # Update only name
        db.update_project(project_id, {"name": "New Name"})

        project = db.get_project(project_id)
        assert project["name"] == "New Name"
        assert project["description"] == "Original description"
        assert project["aspect_ratio"] == "16:9"

    def test_delete_project_removes_clips(self, empty_project_db):
        """Deleting a project removes all its clips."""
        db = empty_project_db

        # Create a project
        project_id = db.create_project(name="To Delete")

        # Add a video to the database first
        conn = db.connect()
        conn.execute(
            """
            INSERT INTO videos (file_path, file_name, file_size, file_hash)
            VALUES (?, ?, ?, ?)
            """,
            ("test.mp4", "test.mp4", 1000, "hash123")
        )
        conn.commit()
        video_row = conn.execute("SELECT id FROM videos WHERE file_path = ?", ("test.mp4",)).fetchone()
        video_id = video_row[0]

        # Add a clip to the project
        clip_id = db.add_project_clip(project_id, video_id, position=1)
        assert clip_id > 0

        # Verify clip exists
        clips = db.get_project_clips(project_id)
        assert len(clips) == 1

        # Delete the project
        result = db.delete_project(project_id)
        assert result is True

        # Project should be gone
        assert db.get_project(project_id) is None

        # Clips should be gone too
        clips = db.get_project_clips(project_id)
        assert len(clips) == 0

    def test_delete_nonexistent_project_returns_false(self, empty_project_db):
        """Deleting a non-existent project returns False."""
        db = empty_project_db
        result = db.delete_project(99999)
        assert result is False


class TestProjectClipAdd:
    """Tests for adding clips to projects."""

    def test_add_project_clip_with_marker(self, empty_project_db):
        """Add a clip with a video marker."""
        db = empty_project_db

        # Setup
        project_id = db.create_project(name="Test Project")

        conn = db.connect()
        conn.execute(
            """
            INSERT INTO videos (file_path, file_name, file_size, file_hash)
            VALUES (?, ?, ?, ?)
            """,
            ("test.mp4", "test.mp4", 1000, "hash123")
        )
        video_row = conn.execute("SELECT id FROM videos WHERE file_path = ?", ("test.mp4",)).fetchone()
        video_id = video_row[0]

        # Create a marker
        marker_id = db.create_marker(video_id, "Good Part", 5.0, 10.0)

        # Add clip with marker
        clip_id = db.add_project_clip(
            project_id, video_id, video_marker_id=marker_id,
            position=1, notes="Use this part"
        )

        assert clip_id > 0
        clips = db.get_project_clips(project_id)
        assert len(clips) == 1
        assert clips[0]["video_marker_id"] == marker_id
        assert clips[0]["marker_label"] == "Good Part"
        assert clips[0]["marker_in"] == 5.0
        assert clips[0]["marker_out"] == 10.0
        assert clips[0]["notes"] == "Use this part"

    def test_add_project_clip_without_marker(self, empty_project_db):
        """Add a clip without a video marker (full clip)."""
        db = empty_project_db

        # Setup
        project_id = db.create_project(name="Test Project")

        conn = db.connect()
        conn.execute(
            """
            INSERT INTO videos (file_path, file_name, file_size, file_hash)
            VALUES (?, ?, ?, ?)
            """,
            ("test.mp4", "test.mp4", 1000, "hash123")
        )
        video_row = conn.execute("SELECT id FROM videos WHERE file_path = ?", ("test.mp4",)).fetchone()
        video_id = video_row[0]

        # Add clip without marker
        clip_id = db.add_project_clip(project_id, video_id, notes="Full video")

        clips = db.get_project_clips(project_id)
        assert len(clips) == 1
        assert clips[0]["video_marker_id"] is None
        assert clips[0]["marker_label"] is None
        assert clips[0]["notes"] == "Full video"

    def test_add_project_clip_records_usage(self, empty_project_db):
        """Adding a clip records clip usage."""
        db = empty_project_db

        # Setup
        project_id = db.create_project(name="Test Project")

        conn = db.connect()
        conn.execute(
            """
            INSERT INTO videos (file_path, file_name, file_size, file_hash)
            VALUES (?, ?, ?, ?)
            """,
            ("test.mp4", "test.mp4", 1000, "hash123")
        )
        video_row = conn.execute("SELECT id FROM videos WHERE file_path = ?", ("test.mp4",)).fetchone()
        video_id = video_row[0]

        # Create marker
        marker_id = db.create_marker(video_id, "Highlight", 2.0, 5.0)

        # Add clip
        db.add_project_clip(project_id, video_id, video_marker_id=marker_id)

        # Check usage was recorded
        usage = db.get_clip_usage(video_id, marker_id)
        assert len(usage) == 1
        assert usage[0]["video_id"] == video_id
        assert usage[0]["video_marker_id"] == marker_id
        assert usage[0]["project_id"] == project_id
        assert usage[0]["project_name"] == "Test Project"

        # Check count
        count = db.get_clip_usage_count(video_id, marker_id)
        assert count == 1


class TestProjectClipRemoveReorder:
    """Tests for removing and reordering clips."""

    def test_remove_project_clip_renumbers(self, empty_project_db):
        """Removing a clip renumbers remaining positions."""
        db = empty_project_db

        # Setup
        project_id = db.create_project(name="Test Project")

        conn = db.connect()
        conn.execute(
            """
            INSERT INTO videos (file_path, file_name, file_size, file_hash)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            ("test1.mp4", "test1.mp4", 1000, "hash1",
             "test2.mp4", "test2.mp4", 1000, "hash2")
        )
        video1_id = conn.execute("SELECT id FROM videos WHERE file_path = ?", ("test1.mp4",)).fetchone()[0]
        video2_id = conn.execute("SELECT id FROM videos WHERE file_path = ?", ("test2.mp4",)).fetchone()[0]

        # Add 3 clips with specific positions
        clip1_id = db.add_project_clip(project_id, video1_id, position=1)
        clip2_id = db.add_project_clip(project_id, video2_id, position=2)
        clip3_id = db.add_project_clip(project_id, video1_id, position=3)

        # Verify initial positions
        clips = db.get_project_clips(project_id)
        assert [(c["id"], c["position"]) for c in clips] == [(clip1_id, 1), (clip2_id, 2), (clip3_id, 3)]

        # Remove middle clip
        result = db.remove_project_clip(project_id, clip2_id)
        assert result is True

        # Verify positions renumbered
        clips = db.get_project_clips(project_id)
        assert len(clips) == 2
        assert [(c["id"], c["position"]) for c in clips] == [(clip1_id, 1), (clip3_id, 2)]

    def test_reorder_project_clips(self, empty_project_db):
        """Reorder clips in a project."""
        db = empty_project_db

        # Setup
        project_id = db.create_project(name="Test Project")

        conn = db.connect()
        conn.execute(
            """
            INSERT INTO videos (file_path, file_name, file_size, file_hash)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            ("test1.mp4", "test1.mp4", 1000, "hash1",
             "test2.mp4", "test2.mp4", 1000, "hash2",
             "test3.mp4", "test3.mp4", 1000, "hash3")
        )
        video1_id = conn.execute("SELECT id FROM videos WHERE file_path = ?", ("test1.mp4",)).fetchone()[0]
        video2_id = conn.execute("SELECT id FROM videos WHERE file_path = ?", ("test2.mp4",)).fetchone()[0]
        video3_id = conn.execute("SELECT id FROM videos WHERE file_path = ?", ("test3.mp4",)).fetchone()[0]

        # Add clips
        clip1_id = db.add_project_clip(project_id, video1_id)  # pos 1
        clip2_id = db.add_project_clip(project_id, video2_id)  # pos 2
        clip3_id = db.add_project_clip(project_id, video3_id)  # pos 3

        # Reorder: reverse order
        db.reorder_project_clips(project_id, [clip3_id, clip2_id, clip1_id])

        # Verify new order
        clips = db.get_project_clips(project_id)
        assert [(c["id"], c["position"]) for c in clips] == [(clip3_id, 1), (clip2_id, 2), (clip1_id, 3)]

    def test_remove_nonexistent_clip_returns_false(self, empty_project_db):
        """Removing a non-existent clip returns False."""
        db = empty_project_db

        project_id = db.create_project(name="Test Project")
        result = db.remove_project_clip(project_id, 99999)
        assert result is False
