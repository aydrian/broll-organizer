"""Add transcription columns to videos table

Revision ID: 2026_04_09_add_transcription_columns
Revises: 2026_04_06_add_projects_and_clip_usage
Create Date: 2026-04-09 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2026_04_09_add_transcription_columns'
down_revision: Union[str, Sequence[str], None] = '2026_04_06_add_projects_and_clip_usage'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add transcript columns and update FTS5 triggers."""
    # Add transcript columns to videos table
    op.add_column('videos', sa.Column('transcript', sa.Text, nullable=True))
    op.add_column('videos', sa.Column('transcript_model', sa.Text, nullable=True))

    # Drop existing FTS5 triggers (will recreate with transcript)
    op.execute('DROP TRIGGER IF EXISTS videos_ai')
    op.execute('DROP TRIGGER IF EXISTS videos_ad')
    op.execute('DROP TRIGGER IF EXISTS videos_au')

    # Recreate FTS5 triggers with transcript column included
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS videos_ai AFTER INSERT ON videos BEGIN
            INSERT INTO videos_fts(
                rowid, file_name, scene_description, tags,
                mood, camera_movement, time_of_day, gps_location_name, transcript
            ) VALUES (
                new.id, new.file_name, new.scene_description, new.tags,
                new.mood, new.camera_movement, new.time_of_day,
                new.gps_location_name, new.transcript
            );
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS videos_ad AFTER DELETE ON videos BEGIN
            INSERT INTO videos_fts(
                videos_fts, rowid, file_name, scene_description, tags,
                mood, camera_movement, time_of_day, gps_location_name, transcript
            ) VALUES (
                'delete', old.id, old.file_name, old.scene_description,
                old.tags, old.mood, old.camera_movement, old.time_of_day,
                old.gps_location_name, old.transcript
            );
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS videos_au AFTER UPDATE ON videos BEGIN
            INSERT INTO videos_fts(
                videos_fts, rowid, file_name, scene_description, tags,
                mood, camera_movement, time_of_day, gps_location_name, transcript
            ) VALUES (
                'delete', old.id, old.file_name, old.scene_description,
                old.tags, old.mood, old.camera_movement, old.time_of_day,
                old.gps_location_name, old.transcript
            );
            INSERT INTO videos_fts(
                rowid, file_name, scene_description, tags,
                mood, camera_movement, time_of_day, gps_location_name, transcript
            ) VALUES (
                new.id, new.file_name, new.scene_description, new.tags,
                new.mood, new.camera_movement, new.time_of_day,
                new.gps_location_name, new.transcript
            );
        END
    """)


def downgrade() -> None:
    """Remove transcript columns and restore original FTS5 triggers."""
    # Drop updated FTS5 triggers
    op.execute('DROP TRIGGER IF EXISTS videos_au')
    op.execute('DROP TRIGGER IF EXISTS videos_ad')
    op.execute('DROP TRIGGER IF EXISTS videos_ai')

    # Remove transcript columns
    op.drop_column('videos', 'transcript_model')
    op.drop_column('videos', 'transcript')

    # Restore original FTS5 triggers (without transcript)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS videos_ai AFTER INSERT ON videos BEGIN
            INSERT INTO videos_fts(
                rowid, file_name, scene_description, tags,
                mood, camera_movement, time_of_day, gps_location_name
            ) VALUES (
                new.id, new.file_name, new.scene_description, new.tags,
                new.mood, new.camera_movement, new.time_of_day,
                new.gps_location_name
            );
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS videos_ad AFTER DELETE ON videos BEGIN
            INSERT INTO videos_fts(
                videos_fts, rowid, file_name, scene_description, tags,
                mood, camera_movement, time_of_day, gps_location_name
            ) VALUES (
                'delete', old.id, old.file_name, old.scene_description,
                old.tags, old.mood, old.camera_movement, old.time_of_day,
                old.gps_location_name
            );
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS videos_au AFTER UPDATE ON videos BEGIN
            INSERT INTO videos_fts(
                videos_fts, rowid, file_name, scene_description, tags,
                mood, camera_movement, time_of_day, gps_location_name
            ) VALUES (
                'delete', old.id, old.file_name, old.scene_description,
                old.tags, old.mood, old.camera_movement, old.time_of_day,
                old.gps_location_name
            );
            INSERT INTO videos_fts(
                rowid, file_name, scene_description, tags,
                mood, camera_movement, time_of_day, gps_location_name
            ) VALUES (
                new.id, new.file_name, new.scene_description, new.tags,
                new.mood, new.camera_movement, new.time_of_day,
                new.gps_location_name
            );
        END
    """)
