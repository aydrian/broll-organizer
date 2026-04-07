"""Tests for project CLI commands."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def cli_runner():
    """Create a Click CLI test runner."""
    return CliRunner()


def _run_with_mocked_db(cli_runner, args, mock_db):
    """Helper to run CLI with properly mocked Database."""
    from broll.cli import cli

    with patch("broll.cli.get_db_path") as mock_get_db:
        with patch("broll.cli.Database") as MockDB:
            MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
            MockDB.return_value.__exit__ = MagicMock(return_value=False)
            return cli_runner.invoke(cli, args)


class TestProjectCreate:
    """Tests for project create command."""

    def test_project_create_requires_name(self, cli_runner):
        """Creating a project requires a name argument."""
        from broll.cli import cli

        result = cli_runner.invoke(cli, ["project", "create"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_project_create_requires_drive(self, cli_runner):
        """Creating a project requires a drive option."""
        from broll.cli import cli

        result = cli_runner.invoke(cli, ["project", "create", "Test Project"])
        assert result.exit_code != 0
        assert "--drive" in result.output or "required" in result.output.lower()

    def test_project_create_basic(self, cli_runner, tmp_path):
        """Create a project with minimal options."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.create_project.return_value = 123

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                # Create the db file so it "exists"
                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "create", "Test Project",
                    "--drive", str(drive_path)
                ])

        assert result.exit_code == 0
        mock_db.create_project.assert_called_once()
        call_kwargs = mock_db.create_project.call_args[1]
        assert call_kwargs["name"] == "Test Project"
        assert call_kwargs["status"] == "planning"
        assert "Created project 'Test Project' (ID: 123)" in result.output

    def test_project_create_with_all_options(self, cli_runner, tmp_path):
        """Create a project with all options specified."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.create_project.return_value = 456

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "create", "Full Project",
                    "--drive", str(drive_path),
                    "--description", "A test description",
                    "--aspect", "9:16",
                    "--duration", "60",
                    "--status", "gathering"
                ])

        assert result.exit_code == 0
        mock_db.create_project.assert_called_once()
        call_kwargs = mock_db.create_project.call_args[1]
        assert call_kwargs["name"] == "Full Project"
        assert call_kwargs["description"] == "A test description"
        assert call_kwargs["aspect_ratio"] == "9:16"
        assert call_kwargs["target_duration_seconds"] == 60
        assert call_kwargs["status"] == "gathering"


class TestProjectList:
    """Tests for project list command."""

    def test_project_list_empty(self, cli_runner, tmp_path):
        """List projects when none exist."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.list_projects.return_value = []

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "list",
                    "--drive", str(drive_path)
                ])

        assert result.exit_code == 0
        assert "No projects found" in result.output

    def test_project_list_with_projects(self, cli_runner, tmp_path):
        """List projects with data."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.list_projects.return_value = [
            {"id": 1, "name": "Project A", "status": "planning", "aspect_ratio": "9:16", "target_duration_seconds": 60},
            {"id": 2, "name": "Project B", "status": "ready", "aspect_ratio": "16:9", "target_duration_seconds": None},
        ]

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "list",
                    "--drive", str(drive_path)
                ])

        assert result.exit_code == 0
        assert "Project A" in result.output
        assert "Project B" in result.output
        assert "planning" in result.output
        assert "ready" in result.output
        assert "9:16" in result.output
        assert "16:9" in result.output

    def test_project_list_with_filters(self, cli_runner, tmp_path):
        """List projects with status and aspect filters."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.list_projects.return_value = [
            {"id": 1, "name": "Vertical Project", "status": "planning", "aspect_ratio": "9:16"},
        ]

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "list",
                    "--drive", str(drive_path),
                    "--status", "planning",
                    "--aspect", "9:16"
                ])

        assert result.exit_code == 0
        mock_db.list_projects.assert_called_once_with(status="planning", aspect_ratio="9:16")

    def test_project_list_json_output(self, cli_runner, tmp_path):
        """List projects in JSON format."""
        from broll.cli import cli
        import json

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.list_projects.return_value = [
            {"id": 1, "name": "Project A", "status": "planning"},
        ]

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "list",
                    "--drive", str(drive_path),
                    "--format", "json"
                ])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "Project A"


class TestProjectUpdate:
    """Tests for project update command."""

    def test_project_update_not_found(self, cli_runner, tmp_path):
        """Update a project that doesn't exist."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.get_project.return_value = None

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "update", "999",
                    "--drive", str(drive_path),
                    "--name", "New Name"
                ])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_project_update_no_changes(self, cli_runner, tmp_path):
        """Update with no changes specified."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.get_project.return_value = {"id": 1, "name": "Original"}

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "update", "1",
                    "--drive", str(drive_path)
                ])

        assert result.exit_code == 1
        assert "No updates specified" in result.output

    def test_project_update_success(self, cli_runner, tmp_path):
        """Successfully update a project."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.get_project.return_value = {"id": 1, "name": "Original"}

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "update", "1",
                    "--drive", str(drive_path),
                    "--name", "Updated Name",
                    "--status", "ready"
                ])

        assert result.exit_code == 0
        mock_db.update_project.assert_called_once()
        call_args = mock_db.update_project.call_args
        assert call_args[0][0] == 1  # project_id
        assert call_args[0][1]["name"] == "Updated Name"
        assert call_args[0][1]["status"] == "ready"


class TestProjectDelete:
    """Tests for project delete command."""

    def test_project_delete_not_found(self, cli_runner, tmp_path):
        """Delete a project that doesn't exist."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.get_project.return_value = None

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "delete", "999",
                    "--drive", str(drive_path),
                    "--yes"  # Bypass confirmation
                ])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_project_delete_success(self, cli_runner, tmp_path):
        """Successfully delete a project."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.get_project.return_value = {"id": 1, "name": "To Delete"}
        mock_db.delete_project.return_value = True

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "delete", "1",
                    "--drive", str(drive_path),
                    "--yes"  # Bypass confirmation
                ])

        assert result.exit_code == 0
        mock_db.delete_project.assert_called_once_with(1)
        assert "Deleted project 'To Delete'" in result.output


class TestProjectShow:
    """Tests for project show command."""

    def test_project_show_not_found(self, cli_runner, tmp_path):
        """Show a project that doesn't exist."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.get_project.return_value = None

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "show", "999",
                    "--drive", str(drive_path)
                ])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_project_show_with_clips(self, cli_runner, tmp_path):
        """Show project with clips."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.get_project.return_value = {
            "id": 1,
            "name": "Test Project",
            "status": "planning",
            "aspect_ratio": "9:16",
            "target_duration_seconds": 60,
            "created_at": "2026-04-06T10:00:00Z",
            "updated_at": "2026-04-06T11:00:00Z"
        }
        mock_db.get_project_clips.return_value = [
            {"position": 1, "video_id": 101, "marker_label": "Opening", "in_seconds": 5.0, "out_seconds": 10.0},
            {"position": 2, "video_id": 102, "marker_label": None, "in_seconds": None, "out_seconds": None},
        ]

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "show", "1",
                    "--drive", str(drive_path)
                ])

        assert result.exit_code == 0
        assert "Test Project" in result.output
        assert "planning" in result.output
        assert "9:16" in result.output
        assert "Opening" in result.output  # Marker label
        assert "Clips (2)" in result.output


class TestProjectAddClip:
    """Tests for project add-clip command."""

    def test_add_clip_with_video(self, cli_runner, tmp_path):
        """Add a whole video as a clip."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.add_project_clip.return_value = 789
        mock_db.get_project.return_value = {"id": 123, "name": "Test Project"}

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "add-clip", "123",
                    "--drive", str(drive_path),
                    "--video", "456"
                ])

        assert result.exit_code == 0
        mock_db.add_project_clip.assert_called_once()
        call_args = mock_db.add_project_clip.call_args
        assert call_args[0][0] == 123  # project_id is positional
        assert call_args[1]["video_id"] == 456

    def test_add_clip_requires_video_or_marker(self, cli_runner, tmp_path):
        """Must specify either --video or --marker."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.get_project.return_value = {"id": 123, "name": "Test Project"}

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "add-clip", "123",
                    "--drive", str(drive_path)
                ])

        assert result.exit_code == 1
        assert "required" in result.output.lower() or "--video" in result.output or "--marker" in result.output

    def test_add_clip_project_not_found(self, cli_runner, tmp_path):
        """Adding to non-existent project fails."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.get_project.return_value = None

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "add-clip", "123",
                    "--drive", str(drive_path),
                    "--video", "456"
                ])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestProjectRemoveClip:
    """Tests for project remove-clip command."""

    def test_remove_clip_success(self, cli_runner, tmp_path):
        """Successfully remove a clip from a project."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.remove_project_clip.return_value = True

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "remove-clip", "123",
                    "--drive", str(drive_path),
                    "--clip-id", "456",
                    "--yes"
                ])

        assert result.exit_code == 0
        mock_db.remove_project_clip.assert_called_once_with(123, 456)
        assert "Removed clip" in result.output

    def test_remove_clip_not_found(self, cli_runner, tmp_path):
        """Removing non-existent clip fails."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()
        mock_db.remove_project_clip.return_value = False

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "remove-clip", "123",
                    "--drive", str(drive_path),
                    "--clip-id", "999",
                    "--yes"
                ])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestProjectReorder:
    """Tests for project reorder command."""

    def test_reorder_clips_success(self, cli_runner, tmp_path):
        """Successfully reorder clips."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "reorder", "123",
                    "--drive", str(drive_path),
                    "--clips", "5,2,8,1"
                ])

        assert result.exit_code == 0
        mock_db.reorder_project_clips.assert_called_once_with(123, [5, 2, 8, 1])
        assert "Reordered" in result.output

    def test_reorder_invalid_clip_ids(self, cli_runner, tmp_path):
        """Reorder with invalid clip IDs fails."""
        from broll.cli import cli

        drive_path = tmp_path / "drive"
        drive_path.mkdir()

        mock_db = MagicMock()

        with patch("broll.cli.get_db_path", return_value=tmp_path / "test.db"):
            with patch("broll.cli.Database") as MockDB:
                MockDB.return_value.__enter__ = MagicMock(return_value=mock_db)
                MockDB.return_value.__exit__ = MagicMock(return_value=False)

                (tmp_path / "test.db").touch()

                result = cli_runner.invoke(cli, [
                    "project", "reorder", "123",
                    "--drive", str(drive_path),
                    "--clips", "invalid"
                ])

        assert result.exit_code == 1
        assert "integers" in result.output.lower() or "invalid" in result.output.lower()
