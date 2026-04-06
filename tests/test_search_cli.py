"""
Tests for search CLI command with filter options.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from broll.cli import cli, RESOLUTION_MAP


@pytest.fixture
def cli_runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def mock_database(tmp_path):
    """Create a mock database setup for CLI tests."""
    # Create a mock db path in a temp directory
    db_path = tmp_path / "test_drive"
    db_path.mkdir()
    db_file = db_path / "broll.db"

    # Create a mock Database context manager
    mock_db = MagicMock()
    mock_db.get_catalog_stats.return_value = {"total_videos": 100}
    mock_db.get_filtered_ids.return_value = []

    return db_path, db_file, mock_db


class TestSearchWithFilters:
    """Tests for search command with various filter options."""

    def test_search_requires_drive_or_query_or_filter(self, cli_runner):
        """Search requires at least a drive and either query or filters."""
        # No drive, no query, no filters
        result = cli_runner.invoke(cli, ["search"])
        assert result.exit_code != 0

    def test_search_requires_drive(self, cli_runner):
        """Search requires --drive option."""
        result = cli_runner.invoke(cli, ["search", "sunset"])
        assert result.exit_code != 0
        assert "--drive" in result.output

    def test_search_with_query_only(self, cli_runner, tmp_path, mock_database):
        """Search with just a query and drive should work."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()  # Create empty db file to satisfy exists check

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search", return_value=[]) as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path)
                    ])
                    # Should succeed even with no results
                    assert result.exit_code == 0
                    # Verify search was called
                    mock_search.assert_called_once()

    def test_search_with_duration_range(self, cli_runner, tmp_path, mock_database):
        """Search with --duration option should parse range."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--duration", "5-30"
                    ])
                    assert result.exit_code == 0
                    # Verify search was called with filters
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("duration_min") == 5.0
                    assert filters.get("duration_max") == 30.0

    def test_search_with_min_max_duration(self, cli_runner, tmp_path, mock_database):
        """Search with --min-duration and --max-duration should work."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--min-duration", "10",
                        "--max-duration", "60"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("duration_min") == 10.0
                    assert filters.get("duration_max") == 60.0

    def test_search_with_resolution_name(self, cli_runner, tmp_path, mock_database):
        """Search with --resolution 4K should map to min_width."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--resolution", "4K"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("min_width") == 3840

    def test_search_with_resolution_number(self, cli_runner, tmp_path, mock_database):
        """Search with --resolution as number should use as min_width."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--resolution", "2000"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("min_width") == 2000

    def test_search_with_aspect_ratio(self, cli_runner, tmp_path, mock_database):
        """Search with --aspect option should set aspect_ratio filter."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--aspect", "16:9"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("aspect_ratio") == "16:9"

    def test_search_with_portrait_flag(self, cli_runner, tmp_path, mock_database):
        """Search with --portrait flag should set orientation filter."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--portrait"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("orientation") == "portrait"

    def test_search_with_landscape_flag(self, cli_runner, tmp_path, mock_database):
        """Search with --landscape flag should set orientation filter."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--landscape"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("orientation") == "landscape"

    def test_search_with_date_range(self, cli_runner, tmp_path, mock_database):
        """Search with --date range should parse dates."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--date", "2025-01-01..2025-12-31"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("date_from") == "2025-01-01"
                    assert filters.get("date_to") == "2025-12-31"

    def test_search_with_since_until(self, cli_runner, tmp_path, mock_database):
        """Search with --since and --until should set date filters."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--since", "2025-01-01",
                        "--until", "2025-06-30"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("date_from") == "2025-01-01"
                    assert filters.get("date_to") == "2025-06-30"

    def test_search_with_mood_filter(self, cli_runner, tmp_path, mock_database):
        """Search with --mood should set mood filter."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--mood", "calm"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("mood") == "calm"

    def test_search_with_movement_filter(self, cli_runner, tmp_path, mock_database):
        """Search with --movement should set camera movement filter."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--movement", "static"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("movement") == "static"

    def test_search_with_time_filter(self, cli_runner, tmp_path, mock_database):
        """Search with --time should set time_of_day filter."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--time", "night"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("time_of_day") == "night"

    def test_search_with_location_filter(self, cli_runner, tmp_path, mock_database):
        """Search with --location should set location filter."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--location", "Tokyo"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("location") == "Tokyo"

    def test_search_with_device_filter(self, cli_runner, tmp_path, mock_database):
        """Search with --device should set source_device filter."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--device", "dji_pocket3"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("device") == "dji_pocket3"


class TestSearchWithoutQuery:
    """Tests for filter-only search (no query argument)."""

    def test_search_without_query_with_filters(self, cli_runner, tmp_path, mock_database):
        """Search should work with only filters (no query)."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search",
                        "--drive", str(db_path),
                        "--location", "Tokyo",
                        "--time", "night"
                    ])
                    assert result.exit_code == 0
                    # Verify query was passed as None
                    call_args = mock_search.call_args
                    assert call_args[0][0] is None  # query argument

    def test_search_without_query_or_filters_fails(self, cli_runner, tmp_path, mock_database):
        """Search without query or filters should fail with helpful message."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "search",
                    "--drive", str(db_path)
                ])
                assert result.exit_code == 1
                assert "Provide a search query or at least one filter" in result.output


class TestSearchModes:
    """Tests for different search modes with filters."""

    def test_keyword_mode_with_filters(self, cli_runner, tmp_path, mock_database):
        """Keyword search mode should support filters."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.keyword_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--mode", "keyword",
                        "--mood", "calm"
                    ])
                    assert result.exit_code == 0
                    mock_search.assert_called_once()

    def test_semantic_mode_with_filters(self, cli_runner, tmp_path, mock_database):
        """Semantic search mode should support filters."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.semantic_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--mode", "semantic",
                        "--resolution", "4K"
                    ])
                    assert result.exit_code == 0
                    mock_search.assert_called_once()


class TestMultipleFilters:
    """Tests for combining multiple filters."""

    def test_multiple_filters_combined(self, cli_runner, tmp_path, mock_database):
        """Multiple filters should be combined in filters dict."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--duration", "5-30",
                        "--resolution", "4K",
                        "--mood", "calm",
                        "--movement", "static"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    assert filters.get("duration_min") == 5.0
                    assert filters.get("duration_max") == 30.0
                    assert filters.get("min_width") == 3840
                    assert filters.get("mood") == "calm"
                    assert filters.get("movement") == "static"

    def test_min_width_resolution_combination(self, cli_runner, tmp_path, mock_database):
        """--min-width should combine with --resolution (take max)."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.search.hybrid_search") as mock_search:
                    # 4K = 3840, but min-width = 4000, so result should be 4000
                    result = cli_runner.invoke(cli, [
                        "search", "sunset",
                        "--drive", str(db_path),
                        "--resolution", "4K",  # 3840
                        "--min-width", "4000"
                    ])
                    assert result.exit_code == 0
                    call_args = mock_search.call_args
                    filters = call_args[1].get("filters", {})
                    # max(3840, 4000) = 4000
                    assert filters.get("min_width") == 4000
