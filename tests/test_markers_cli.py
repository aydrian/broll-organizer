"""
Tests for marker CLI commands (clip in/out points).
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from broll.cli import cli


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

    # Mock video lookup
    mock_video = {
        "id": 1,
        "file_name": "test_video.mp4",
        "file_path": "test_video.mp4",
        "duration_seconds": 60.0
    }
    mock_db.get_video_by_id.return_value = mock_video

    # Mock marker methods
    mock_db.create_marker.return_value = 1
    mock_db.update_marker.return_value = None
    mock_db.get_video_markers.return_value = []
    mock_db.get_marker.return_value = None
    mock_db.delete_marker.return_value = None

    return db_path, db_file, mock_db


class TestMarkerSet:
    """Tests for marker set command."""

    def test_marker_set_requires_video_id(self, cli_runner):
        """Marker set requires a video_id argument."""
        result = cli_runner.invoke(cli, ["marker", "set"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "VIDEO_ID" in result.output

    def test_marker_set_requires_drive(self, cli_runner):
        """Marker set requires --drive option."""
        result = cli_runner.invoke(cli, ["marker", "set", "1"])
        assert result.exit_code != 0
        assert "--drive" in result.output

    def test_marker_set_requires_in_option(self, cli_runner, tmp_path):
        """Marker set requires --in option."""
        db_path = tmp_path / "test_drive"
        db_path.mkdir()

        result = cli_runner.invoke(cli, [
            "marker", "set", "1",
            "--drive", str(db_path),
            "--out", "10"
        ])
        assert result.exit_code != 0
        assert "--in" in result.output or "in" in result.output.lower()

    def test_marker_set_requires_out_option(self, cli_runner, tmp_path):
        """Marker set requires --out option."""
        db_path = tmp_path / "test_drive"
        db_path.mkdir()

        result = cli_runner.invoke(cli, [
            "marker", "set", "1",
            "--drive", str(db_path),
            "--in", "5"
        ])
        assert result.exit_code != 0
        assert "--out" in result.output or "out" in result.output.lower()

    def test_marker_set_requires_label(self, cli_runner, tmp_path):
        """Marker set requires --label option."""
        db_path = tmp_path / "test_drive"
        db_path.mkdir()

        result = cli_runner.invoke(cli, [
            "marker", "set", "1",
            "--drive", str(db_path),
            "--in", "5",
            "--out", "10"
        ])
        assert result.exit_code != 0
        assert "--label" in result.output

    def test_marker_set_rejects_in_ge_out(self, cli_runner, tmp_path):
        """Marker set rejects in >= out."""
        db_path = tmp_path / "test_drive"
        db_path.mkdir()

        result = cli_runner.invoke(cli, [
            "marker", "set", "1",
            "--drive", str(db_path),
            "--in", "10",
            "--out", "5",
            "--label", "test"
        ])
        assert result.exit_code != 0
        assert "in" in result.output.lower()

    def test_marker_set_creates_marker(self, cli_runner, mock_database):
        """Marker set creates a new marker when label doesn't exist."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "set", "1",
                    "--drive", str(db_path),
                    "--in", "5",
                    "--out", "10",
                    "--label", "money shot"
                ])

                assert result.exit_code == 0
                mock_db.create_marker.assert_called_once()
                call_args = mock_db.create_marker.call_args[0]
                assert call_args[0] == 1  # video_id
                assert call_args[1] == "money shot"  # label
                assert call_args[2] == 5.0  # in_seconds
                assert call_args[3] == 10.0  # out_seconds

    def test_marker_set_updates_existing(self, cli_runner, mock_database):
        """Marker set updates existing marker when label exists."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        # Set up existing marker with same label
        existing_marker = {
            "id": 5,
            "video_id": 1,
            "label": "money shot",
            "in_seconds": 3.0,
            "out_seconds": 7.0,
            "color": "#3b82f6"
        }
        mock_db.get_video_markers.return_value = [existing_marker]

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "set", "1",
                    "--drive", str(db_path),
                    "--in", "5",
                    "--out", "10",
                    "--label", "money shot"
                ])

                assert result.exit_code == 0
                mock_db.update_marker.assert_called_once()
                call_args = mock_db.update_marker.call_args[0]
                assert call_args[0] == 5  # marker_id

    def test_marker_set_validates_video_exists(self, cli_runner, mock_database):
        """Marker set fails when video doesn't exist."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()
        mock_db.get_video_by_id.return_value = None

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "set", "999",
                    "--drive", str(db_path),
                    "--in", "5",
                    "--out", "10",
                    "--label", "test"
                ])

                assert result.exit_code == 1
                assert "not found" in result.output.lower()

    def test_marker_set_with_custom_color(self, cli_runner, mock_database):
        """Marker set accepts custom color."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "set", "1",
                    "--drive", str(db_path),
                    "--in", "5",
                    "--out", "10",
                    "--label", "intro",
                    "--color", "#ef4444"
                ])

                assert result.exit_code == 0
                call_args = mock_db.create_marker.call_args[0]
                assert call_args[4] == "#ef4444"  # color


class TestMarkerList:
    """Tests for marker list command."""

    def test_marker_list_requires_video_id(self, cli_runner):
        """Marker list requires a video_id argument."""
        result = cli_runner.invoke(cli, ["marker", "list"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "VIDEO_ID" in result.output

    def test_marker_list_requires_drive(self, cli_runner):
        """Marker list requires --drive option."""
        result = cli_runner.invoke(cli, ["marker", "list", "1"])
        assert result.exit_code != 0
        assert "--drive" in result.output

    def test_marker_list_shows_markers(self, cli_runner, mock_database):
        """Marker list displays markers in table format."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        mock_markers = [
            {"id": 1, "label": "intro", "in_seconds": 0.0, "out_seconds": 5.0, "color": "#3b82f6"},
            {"id": 2, "label": "money shot", "in_seconds": 12.5, "out_seconds": 18.3, "color": "#ef4444"}
        ]
        mock_db.get_video_markers.return_value = mock_markers

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "list", "1",
                    "--drive", str(db_path)
                ])

                assert result.exit_code == 0
                assert "intro" in result.output
                assert "money shot" in result.output
                assert "12.5" in result.output or "12" in result.output
                assert "18.3" in result.output or "18" in result.output

    def test_marker_list_json_output(self, cli_runner, mock_database):
        """Marker list supports JSON output format."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        mock_markers = [
            {"id": 1, "label": "intro", "in_seconds": 0.0, "out_seconds": 5.0, "color": "#3b82f6"}
        ]
        mock_db.get_video_markers.return_value = mock_markers

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "list", "1",
                    "--drive", str(db_path),
                    "--format", "json"
                ])

                assert result.exit_code == 0
                import json
                data = json.loads(result.output)
                assert len(data) == 1
                assert data[0]["label"] == "intro"

    def test_marker_list_shows_empty_message(self, cli_runner, mock_database):
        """Marker list shows message when no markers exist."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()
        mock_db.get_video_markers.return_value = []

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "list", "1",
                    "--drive", str(db_path)
                ])

                assert result.exit_code == 0
                assert "no markers" in result.output.lower()

    def test_marker_list_validates_video_exists(self, cli_runner, mock_database):
        """Marker list fails when video doesn't exist."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()
        mock_db.get_video_by_id.return_value = None

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "list", "999",
                    "--drive", str(db_path)
                ])

                assert result.exit_code == 1
                assert "not found" in result.output.lower()


class TestMarkerDelete:
    """Tests for marker delete command."""

    def test_marker_delete_requires_marker_id(self, cli_runner):
        """Marker delete requires a marker_id argument."""
        result = cli_runner.invoke(cli, ["marker", "delete"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "MARKER_ID" in result.output

    def test_marker_delete_requires_drive(self, cli_runner):
        """Marker delete requires --drive option."""
        result = cli_runner.invoke(cli, ["marker", "delete", "1"])
        assert result.exit_code != 0
        assert "--drive" in result.output

    def test_marker_delete_success(self, cli_runner, mock_database):
        """Marker delete removes marker successfully."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        mock_db.get_marker.return_value = {
            "id": 1,
            "video_id": 1,
            "label": "test marker",
            "in_seconds": 5.0,
            "out_seconds": 10.0
        }

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "delete", "1",
                    "--drive", str(db_path)
                ], input="y\n")

                assert result.exit_code == 0
                mock_db.delete_marker.assert_called_once_with(1)
                assert "deleted" in result.output.lower()

    def test_marker_delete_not_found(self, cli_runner, mock_database):
        """Marker delete fails when marker doesn't exist."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()
        mock_db.get_marker.return_value = None

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "delete", "999",
                    "--drive", str(db_path)
                ], input="y\n")

                assert result.exit_code == 1
                assert "not found" in result.output.lower()


class TestMarkerExport:
    """Tests for marker export command."""

    def test_marker_export_requires_marker_id(self, cli_runner):
        """Marker export requires a marker_id argument."""
        result = cli_runner.invoke(cli, ["marker", "export"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "MARKER_ID" in result.output

    def test_marker_export_requires_drive(self, cli_runner):
        """Marker export requires --drive option."""
        result = cli_runner.invoke(cli, ["marker", "export", "1", "--output", "test.mp4"])
        assert result.exit_code != 0
        assert "--drive" in result.output

    def test_marker_export_requires_output(self, cli_runner, tmp_path):
        """Marker export requires --output option."""
        db_path = tmp_path / "test_drive"
        db_path.mkdir()

        result = cli_runner.invoke(cli, [
            "marker", "export", "1",
            "--drive", str(db_path)
        ])
        assert result.exit_code != 0
        assert "--output" in result.output

    def test_marker_export_not_found(self, cli_runner, mock_database):
        """Marker export fails when marker doesn't exist."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()
        mock_db.get_marker.return_value = None

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                result = cli_runner.invoke(cli, [
                    "marker", "export", "999",
                    "--drive", str(db_path),
                    "--output", "test.mp4"
                ])

                assert result.exit_code == 1
                assert "not found" in result.output.lower()

    def test_marker_export_ffmpeg_called(self, cli_runner, mock_database):
        """Marker export calls FFmpeg with correct parameters."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        # Create video file
        test_video = db_path / "test_video.mp4"
        test_video.touch()

        mock_db.get_marker.return_value = {
            "id": 1,
            "video_id": 1,
            "label": "money shot",
            "in_seconds": 12.5,
            "out_seconds": 18.3,
            "color": "#3b82f6"
        }

        output_path = db_path / "output.mp4"

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.cli.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stderr="")

                    result = cli_runner.invoke(cli, [
                        "marker", "export", "1",
                        "--drive", str(db_path),
                        "--output", str(output_path)
                    ])

                    # FFmpeg should be called
                    mock_run.assert_called_once()
                    call_args = mock_run.call_args[0][0]
                    assert "ffmpeg" in call_args[0].lower() or "ffmpeg" in str(call_args[0])

    def test_marker_export_ffmpeg_error(self, cli_runner, mock_database):
        """Marker export handles FFmpeg errors."""
        db_path, db_file, mock_db = mock_database
        db_file.touch()

        test_video = db_path / "test_video.mp4"
        test_video.touch()

        mock_db.get_marker.return_value = {
            "id": 1,
            "video_id": 1,
            "label": "money shot",
            "in_seconds": 12.5,
            "out_seconds": 18.3
        }

        output_path = db_path / "output.mp4"

        with patch("broll.cli.get_db_path", return_value=db_file):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                with patch("broll.cli.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=1, stderr="FFmpeg error")

                    result = cli_runner.invoke(cli, [
                        "marker", "export", "1",
                        "--drive", str(db_path),
                        "--output", str(output_path)
                    ])

                    assert result.exit_code == 1
