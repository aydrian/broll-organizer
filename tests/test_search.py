"""
Tests for search module filter functionality.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from broll.search import hybrid_search, keyword_search, semantic_search


class TestHybridSearchWithFilters:
    """Tests for hybrid_search with filters parameter."""

    def test_with_duration_filter(self, sample_videos_database):
        """Hybrid search should apply duration filters."""
        # Mock the FTS and vector searches to return specific IDs
        with patch.object(sample_videos_database, 'search_fts', return_value=[
            {"video_id": 1, "rank": -1.0},
            {"video_id": 2, "rank": -2.0},
            {"video_id": 3, "rank": -3.0},
            {"video_id": 4, "rank": -4.0},
        ]):
            with patch.object(sample_videos_database, 'vector_search', return_value=[]):
                results = hybrid_search(
                    "test",
                    sample_videos_database,
                    limit=10,
                    filters={"duration_min": 15.0}  # video2 (25s) and video4 (120s)
                )
                # Only video2 (25s) and video4 (120s) match duration filter
                result_ids = [r["id"] for r in results]
                assert sorted(result_ids) == [2, 4]

    def test_with_resolution_filter(self, sample_videos_database):
        """Hybrid search should apply resolution filters."""
        with patch.object(sample_videos_database, 'search_fts', return_value=[
            {"video_id": 1, "rank": -1.0},  # 3840 width
            {"video_id": 2, "rank": -2.0},  # 1920 width
            {"video_id": 3, "rank": -3.0},  # 1080 width
        ]):
            with patch.object(sample_videos_database, 'vector_search', return_value=[]):
                results = hybrid_search(
                    "test",
                    sample_videos_database,
                    limit=10,
                    filters={"min_width": 1920}  # video1 and video2
                )
                result_ids = [r["id"] for r in results]
                assert sorted(result_ids) == [1, 2]

    def test_no_query_only_filters(self, sample_videos_database):
        """Search with no query should return filtered results only."""
        results = hybrid_search(
            None,
            sample_videos_database,
            limit=10,
            filters={"mood": "calm"}
        )
        result_ids = [r["id"] for r in results]
        # video1 and video3 are calm
        assert sorted(result_ids) == [1, 3]
        # Should have search_score assigned
        for r in results:
            assert r.get("search_score") is not None

    def test_no_query_no_filters_returns_empty(self, sample_videos_database):
        """Search with neither query nor filters should return empty."""
        results = hybrid_search(None, sample_videos_database, limit=10)
        assert results == []

    def test_multiple_filters_intersection(self, sample_videos_database):
        """Multiple filters should be combined with AND logic."""
        with patch.object(sample_videos_database, 'search_fts', return_value=[
            {"video_id": 1, "rank": -1.0},
            {"video_id": 2, "rank": -2.0},
            {"video_id": 3, "rank": -3.0},
        ]):
            with patch.object(sample_videos_database, 'vector_search', return_value=[]):
                results = hybrid_search(
                    "test",
                    sample_videos_database,
                    limit=10,
                    filters={
                        "mood": "calm",  # video1 and video3
                        "min_width": 2000,  # Only video1 (3840)
                    }
                )
                # Intersection: only video1
                assert len(results) == 1
                assert results[0]["id"] == 1

    def test_filter_no_matches_returns_empty(self, sample_videos_database):
        """If filters match no videos, search should return empty."""
        with patch.object(sample_videos_database, 'search_fts', return_value=[
            {"video_id": 1, "rank": -1.0},
            {"video_id": 2, "rank": -2.0},
        ]):
            with patch.object(sample_videos_database, 'vector_search', return_value=[]):
                results = hybrid_search(
                    "test",
                    sample_videos_database,
                    limit=10,
                    filters={"mood": "nonexistent"}
                )
                assert results == []


class TestKeywordSearchWithFilters:
    """Tests for keyword_search with filters parameter."""

    def test_with_location_filter(self, sample_videos_database):
        """Keyword search should apply location filters."""
        with patch.object(sample_videos_database, 'search_fts', return_value=[
            {"video_id": 1, "rank": -1.0},  # Tokyo
            {"video_id": 2, "rank": -2.0},  # Kusatsu
            {"video_id": 3, "rank": -3.0},  # New York
        ]):
            results = keyword_search(
                "test",
                sample_videos_database,
                limit=10,
                filters={"location": "Japan"}
            )
            # Tokyo and Kusatsu are in Japan
            result_ids = [r["id"] for r in results]
            assert sorted(result_ids) == [1, 2]

    def test_no_query_only_filters(self, sample_videos_database):
        """Keyword search with no query should return filtered results."""
        results = keyword_search(
            None,
            sample_videos_database,
            limit=10,
            filters={"time_of_day": "night"}  # video2
        )
        assert len(results) == 1
        assert results[0]["id"] == 2

    def test_search_results_filtered_then_limited(self, sample_videos_database):
        """Results should be filtered then limited."""
        with patch.object(sample_videos_database, 'search_fts', return_value=[
            {"video_id": 1, "rank": -1.0},
            {"video_id": 2, "rank": -2.0},
            {"video_id": 3, "rank": -3.0},
            {"video_id": 4, "rank": -4.0},
        ]):
            results = keyword_search(
                "test",
                sample_videos_database,
                limit=2,  # Only want 2 results
                filters={"duration_max": 100}  # Excludes video4 (120s)
            )
            # All except video4, then take first 2
            assert len(results) == 2


class TestSemanticSearchWithFilters:
    """Tests for semantic_search with filters parameter."""

    def test_with_mood_filter(self, sample_videos_database):
        """Semantic search should apply mood filters."""
        with patch("broll.search.generate_embedding", return_value=[0.0] * 768):
            with patch.object(sample_videos_database, 'vector_search', return_value=[
                (1, 0.1),
                (2, 0.2),
                (3, 0.3),
                (4, 0.4),
            ]):
                results = semantic_search(
                    "test",
                    sample_videos_database,
                    limit=10,
                    filters={"mood": "energetic"}  # video2
                )
                assert len(results) == 1
                assert results[0]["id"] == 2

    def test_no_query_only_filters(self, sample_videos_database):
        """Semantic search with no query should return filtered results."""
        results = semantic_search(
            None,
            sample_videos_database,
            limit=10,
            filters={"movement": "static"}  # video1 and video4
        )
        result_ids = [r["id"] for r in results]
        assert sorted(result_ids) == [1, 4]


class TestSearchResultMetadata:
    """Tests for search result metadata fields."""

    def test_results_have_search_score(self, sample_videos_database):
        """Results should have search_score field."""
        with patch.object(sample_videos_database, 'search_fts', return_value=[
            {"video_id": 1, "rank": -1.0},
        ]):
            with patch.object(sample_videos_database, 'vector_search', return_value=[]):
                results = hybrid_search("test", sample_videos_database, limit=10)
                assert all("search_score" in r for r in results)

    def test_results_have_in_fts_and_in_vec(self, sample_videos_database):
        """Results should have in_fts and in_vec flags."""
        with patch("broll.search.generate_embedding", return_value=[0.0] * 768):
            with patch.object(sample_videos_database, 'search_fts', return_value=[
                {"video_id": 1, "rank": -1.0},
            ]):
                with patch.object(sample_videos_database, 'vector_search', return_value=[
                    (1, 0.1),
                ]):
                    results = hybrid_search("test", sample_videos_database, limit=10)
                    assert results[0]["in_fts"] is True
                    assert results[0]["in_vec"] is True

    def test_filter_only_results_have_defaults(self, sample_videos_database):
        """Filter-only results should have default metadata."""
        results = keyword_search(
            None,
            sample_videos_database,
            limit=10,
            filters={"mood": "calm"}
        )
        for r in results:
            assert r["search_score"] == 1.0
            assert r["in_fts"] is False
            assert r["in_vec"] is False
