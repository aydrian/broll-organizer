"""Add projects and clip_usage tables

Revision ID: 2026_04_06_add_projects_and_clip_usage
Revises: 2026_04_06_add_video_markers
Create Date: 2026-04-06 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2026_04_06_add_projects_and_clip_usage'
down_revision: Union[str, Sequence[str], None] = '2026_04_06_add_video_markers'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create projects, project_clips, and clip_usage tables."""
    # ---- Projects table ----
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('status', sa.Text, server_default='active'),
        sa.Column('aspect_ratio', sa.Text),
        sa.Column('target_duration_seconds', sa.REAL),
        sa.Column('canva_link', sa.Text),
        sa.Column('created_at', sa.Text,
                  server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
        sa.Column('updated_at', sa.Text,
                  server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
    )

    # ---- Project clips table ----
    op.create_table(
        'project_clips',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.Integer, nullable=False),
        sa.Column('video_id', sa.Integer, nullable=False),
        sa.Column('video_marker_id', sa.Integer),
        sa.Column('position', sa.Integer, nullable=False),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.Text,
                  server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
    )

    # ---- Clip usage tracking table ----
    op.create_table(
        'clip_usage',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('video_id', sa.Integer, nullable=False),
        sa.Column('project_id', sa.Integer),
        sa.Column('video_marker_id', sa.Integer),
        sa.Column('used_at', sa.Text,
                  server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
    )

    # ---- Indexes for projects ----
    op.create_index(
        'idx_projects_status',
        'projects',
        ['status']
    )
    op.create_index(
        'idx_projects_updated_at',
        'projects',
        ['updated_at', 'DESC']
    )

    # ---- Indexes for project_clips ----
    op.create_index(
        'idx_project_clips_project_id',
        'project_clips',
        ['project_id']
    )
    op.create_index(
        'idx_project_clips_project_position',
        'project_clips',
        ['project_id', 'position']
    )
    op.create_index(
        'idx_project_clips_video_id',
        'project_clips',
        ['video_id']
    )

    # ---- Indexes for clip_usage ----
    op.create_index(
        'idx_clip_usage_video',
        'clip_usage',
        ['video_id', 'video_marker_id']
    )
    op.create_index(
        'idx_clip_usage_project',
        'clip_usage',
        ['project_id']
    )

    # ---- Foreign key triggers for project_clips ----
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS project_clips_insert_project_fk
        BEFORE INSERT ON project_clips
        FOR EACH ROW
        BEGIN
            SELECT CASE
                WHEN (SELECT id FROM projects WHERE id = NEW.project_id) IS NULL
                THEN RAISE(ABORT, 'Foreign key violation: project_id does not exist')
            END;
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS project_clips_insert_video_fk
        BEFORE INSERT ON project_clips
        FOR EACH ROW
        BEGIN
            SELECT CASE
                WHEN (SELECT id FROM videos WHERE id = NEW.video_id) IS NULL
                THEN RAISE(ABORT, 'Foreign key violation: video_id does not exist')
            END;
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS project_clips_insert_marker_fk
        BEFORE INSERT ON project_clips
        FOR EACH ROW
        WHEN NEW.video_marker_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT id FROM video_markers WHERE id = NEW.video_marker_id) IS NULL
                THEN RAISE(ABORT, 'Foreign key violation: video_marker_id does not exist')
            END;
        END
    """)

    # ---- Cascade delete trigger for project deletion ----
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS project_clips_delete_project_cascade
        BEFORE DELETE ON projects
        FOR EACH ROW
        BEGIN
            DELETE FROM project_clips WHERE project_id = OLD.id;
        END
    """)

    # ---- Cascade delete trigger for video deletion ----
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS project_clips_delete_video_cascade
        BEFORE DELETE ON videos
        FOR EACH ROW
        BEGIN
            DELETE FROM project_clips WHERE video_id = OLD.id;
        END
    """)

    # ---- Foreign key triggers for clip_usage ----
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS clip_usage_insert_video_fk
        BEFORE INSERT ON clip_usage
        FOR EACH ROW
        BEGIN
            SELECT CASE
                WHEN (SELECT id FROM videos WHERE id = NEW.video_id) IS NULL
                THEN RAISE(ABORT, 'Foreign key violation: video_id does not exist')
            END;
        END
    """)

    op.execute("""
        CREATE TRIGGER IF NOT EXISTS clip_usage_insert_project_fk
        BEFORE INSERT ON clip_usage
        FOR EACH ROW
        WHEN NEW.project_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT id FROM projects WHERE id = NEW.project_id) IS NULL
                THEN RAISE(ABORT, 'Foreign key violation: project_id does not exist')
            END;
        END
    """)



def downgrade() -> None:
    """Remove projects, project_clips, and clip_usage tables."""
    # Drop triggers first
    op.execute('DROP TRIGGER IF EXISTS clip_usage_insert_project_fk')
    op.execute('DROP TRIGGER IF EXISTS clip_usage_insert_video_fk')
    op.execute('DROP TRIGGER IF EXISTS project_clips_delete_video_cascade')
    op.execute('DROP TRIGGER IF EXISTS project_clips_delete_project_cascade')
    op.execute('DROP TRIGGER IF EXISTS project_clips_insert_marker_fk')
    op.execute('DROP TRIGGER IF EXISTS project_clips_insert_video_fk')
    op.execute('DROP TRIGGER IF EXISTS project_clips_insert_project_fk')

    # Drop indexes
    op.drop_index('idx_clip_usage_project', table_name='clip_usage')
    op.drop_index('idx_clip_usage_video', table_name='clip_usage')
    op.drop_index('idx_project_clips_video_id', table_name='project_clips')
    op.drop_index('idx_project_clips_project_position', table_name='project_clips')
    op.drop_index('idx_project_clips_project_id', table_name='project_clips')
    op.drop_index('idx_projects_updated_at', table_name='projects')
    op.drop_index('idx_projects_status', table_name='projects')

    # Drop tables
    op.drop_table('clip_usage')
    op.drop_table('project_clips')
    op.drop_table('projects')
