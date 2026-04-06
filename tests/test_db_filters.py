"""
Tests for database filter query building functionality.
"""
from __future__ import annotations

import pytest


class TestBuildFilteredQuery:
    """Tests for Database.build_filtered_query method."""

    def test_empty_filters_returns_true(self, sample_videos_database):
        """Empty filters should return '1=1' (always true)."""
        where_clause, params = sample_videos_database.build_filtered_query({})
        assert where_clause == "1=1"
        assert params == []

    def test_duration_min_filter(self, sample_videos_database):
        """Test minimum duration filter."""
        filters = {"duration_min": 5.0}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "duration_seconds >= ?" in where_clause
        assert params == [5.0]

    def test_duration_max_filter(self, sample_videos_database):
        """Test maximum duration filter."""
        filters = {"duration_max": 30.0}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "duration_seconds <= ?" in where_clause
        assert params == [30.0]

    def test_duration_range_filter(self, sample_videos_database):
        """Test both min and max duration filters combined."""
        filters = {"duration_min": 5.0, "duration_max": 30.0}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "duration_seconds >= ?" in where_clause
        assert "duration_seconds <= ?" in where_clause
        assert " AND " in where_clause
        assert params == [5.0, 30.0]

    def test_min_width_filter(self, sample_videos_database):
        """Test minimum width filter."""
        filters = {"min_width": 1920}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "width >= ?" in where_clause
        assert params == [1920]

    def test_min_height_filter(self, sample_videos_database):
        """Test minimum height filter."""
        filters = {"min_height": 1080}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "height >= ?" in where_clause
        assert params == [1080]

    def test_aspect_ratio_filter(self, sample_videos_database):
        """Test aspect ratio filter with 5% tolerance."""
        filters = {"aspect_ratio": "16:9"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "CAST(width AS REAL) / height BETWEEN ? AND ?" in where_clause
        # 16/9 = 1.777..., 5% tolerance = 0.0888...
        assert len(params) == 2
        assert abs(params[0] - 1.689) < 0.01  # 1.777 - 0.088
        assert abs(params[1] - 1.866) < 0.01  # 1.777 + 0.088

    def test_invalid_aspect_ratio_skipped(self, sample_videos_database):
        """Invalid aspect ratio should be skipped gracefully."""
        filters = {"aspect_ratio": "invalid"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert where_clause == "1=1"
        assert params == []

    def test_portrait_orientation(self, sample_videos_database):
        """Test portrait orientation filter."""
        filters = {"orientation": "portrait"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "height > width" in where_clause

    def test_landscape_orientation(self, sample_videos_database):
        """Test landscape orientation filter."""
        filters = {"orientation": "landscape"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "width > height" in where_clause

    def test_square_orientation(self, sample_videos_database):
        """Test square orientation filter."""
        filters = {"orientation": "square"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "width = height" in where_clause

    def test_date_from_filter(self, sample_videos_database):
        """Test date from filter."""
        filters = {"date_from": "2025-01-01"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "creation_date >= ?" in where_clause
        assert params == ["2025-01-01"]

    def test_date_to_filter(self, sample_videos_database):
        """Test date to filter."""
        filters = {"date_to": "2025-12-31"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "creation_date <= ?" in where_clause
        assert params == ["2025-12-31"]

    def test_mood_filter(self, sample_videos_database):
        """Test mood filter."""
        filters = {"mood": "calm"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "mood = ?" in where_clause
        assert params == ["calm"]

    def test_movement_filter(self, sample_videos_database):
        """Test camera movement filter."""
        filters = {"movement": "pan"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "camera_movement = ?" in where_clause
        assert params == ["pan"]

    def test_time_of_day_filter(self, sample_videos_database):
        """Test time of day filter."""
        filters = {"time_of_day": "night"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "time_of_day = ?" in where_clause
        assert params == ["night"]

    def test_location_filter(self, sample_videos_database):
        """Test location filter with LIKE pattern."""
        filters = {"location": "Tokyo"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "gps_location_name LIKE ?" in where_clause
        assert params == ["%Tokyo%"]

    def test_device_filter(self, sample_videos_database):
        """Test source device filter."""
        filters = {"device": "dji_pocket3"}
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "source_device = ?" in where_clause
        assert params == ["dji_pocket3"]

    def test_multiple_filters_combined_with_and(self, sample_videos_database):
        """Multiple filters should be combined with AND."""
        filters = {
            "duration_min": 5.0,
            "duration_max": 30.0,
            "mood": "calm",
        }
        where_clause, params = sample_videos_database.build_filtered_query(filters)
        assert "duration_seconds >= ?" in where_clause
        assert "duration_seconds <= ?" in where_clause
        assert "mood = ?" in where_clause
        # Should have AND between conditions
        assert where_clause.count("AND") == 2
        assert params == [5.0, 30.0, "calm"]


class TestGetFilteredIds:
    """Tests for Database.get_filtered_ids method."""

    def test_duration_filter_returns_correct_ids(self, sample_videos_database):
        """Filter by duration should return matching video IDs."""
        filters = {"duration_min": 15.0}
        ids = sample_videos_database.get_filtered_ids(filters)
        # video2 (25s) and video4 (120s) match
        assert len(ids) == 2
        # IDs are 1-indexed after insertion
        assert sorted(ids) == [2, 4]

    def test_resolution_filter_returns_correct_ids(self, sample_videos_database):
        """Filter by minimum width should return matching videos."""
        filters = {"min_width": 1920}
        ids = sample_videos_database.get_filtered_ids(filters)
        # video1 (3840) and video2 (1920) match
        assert len(ids) == 2
        assert sorted(ids) == [1, 2]

    def test_orientation_portrait_returns_correct_ids(self, sample_videos_database):
        """Portrait orientation should return only portrait videos."""
        filters = {"orientation": "portrait"}
        ids = sample_videos_database.get_filtered_ids(filters)
        # video3 is 1080x1920 (portrait)
        assert ids == [3]

    def test_location_filter_uses_like_matching(self, sample_videos_database):
        """Location filter should use partial matching."""
        filters = {"location": "Japan"}
        ids = sample_videos_database.get_filtered_ids(filters)
        # video1 (Tokyo, Japan) and video2 (Kusatsu, Japan) match
        assert len(ids) == 2
        assert sorted(ids) == [1, 2]

    def test_mood_filter_returns_correct_ids(self, sample_videos_database):
        """Mood filter should return exact matches."""
        filters = {"mood": "calm"}
        ids = sample_videos_database.get_filtered_ids(filters)
        # video1 and video3 are calm
        assert len(ids) == 2
        assert sorted(ids) == [1, 3]

    def test_combined_filters(self, sample_videos_database):
        """Multiple filters should return intersection."""
        filters = {
            "mood": "calm",
            "min_width": 1920,
        }
        ids = sample_videos_database.get_filtered_ids(filters)
        # video1: calm + 3840 width (matches)
        # video3: calm but 1080 width (doesn't match)
        assert ids == [1]

    def test_no_matching_filters_returns_empty(self, sample_videos_database):
        """Filters with no matches should return empty list."""
        filters = {"mood": "nonexistent_mood"}
        ids = sample_videos_database.get_filtered_ids(filters)
        assert ids == []


class TestGetVideosByFilters:
    """Tests for Database.get_videos_by_filters method."""

    def test_returns_full_video_records(self, sample_videos_database):
        """Should return full video dicts, not just IDs."""
        filters = {"mood": "calm"}
        videos = sample_videos_database.get_videos_by_filters(filters)
        assert len(videos) == 2
        # Check that full records are returned
        for video in videos:
            assert "id" in video
            assert "file_name" in video
            assert "mood" in video

    def test_respects_limit(self, sample_videos_database):
        """Should respect the limit parameter."""
        filters = {"duration_min": 0}  # All videos match
        videos = sample_videos_database.get_videos_by_filters(filters, limit=2)
        assert len(videos) == 2

    def test_respects_offset(self, sample_videos_database):
        """Should support pagination via offset."""
        filters = {"duration_min": 0}
        videos_page1 = sample_videos_database.get_videos_by_filters(filters, limit=2, offset=0)
        videos_page2 = sample_videos_database.get_videos_by_filters(filters, limit=2, offset=2)
        # Different results for different offsets
        assert videos_page1[0]["id"] != videos_page2[0]["id"]
