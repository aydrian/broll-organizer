"""Add video_markers table

Revision ID: 2026_04_06_add_video_markers
Revises: 2026_04_05_update_location_cache
Create Date: 2026-04-06 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2026_04_06_add_video_markers'
down_revision: Union[str, Sequence[str], None] = '2026_04_05_update_location_cache'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create video_markers table for clip in/out points."""
    # ---- Video markers table ----
    op.create_table(
        'video_markers',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('video_id', sa.Integer, nullable=False),
        sa.Column('label', sa.Text, nullable=False),
        sa.Column('in_seconds', sa.REAL, nullable=False),
        sa.Column('out_seconds', sa.REAL, nullable=False),
        sa.Column('color', sa.Text, server_default='#3b82f6'),
        sa.Column('created_at', sa.Text,
                  server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
    )

    # ---- Indexes for performance ----
    op.create_index(
        'idx_video_markers_video_id',
        'video_markers',
        ['video_id']
    )

    op.create_index(
        'idx_video_markers_label',
        'video_markers',
        ['video_id', 'label'],
        unique=True
    )

    # ---- Foreign key trigger ----
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS video_markers_insert_fk
        BEFORE INSERT ON video_markers
        FOR EACH ROW
        BEGIN
            SELECT CASE
                WHEN (SELECT id FROM videos WHERE id = NEW.video_id) IS NULL
                THEN RAISE(ABORT, 'Foreign key violation: video_id does not exist')
            END;
        END
    """)

    # ---- Cascade delete trigger ----
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS video_markers_delete_video_cascade
        BEFORE DELETE ON videos
        FOR EACH ROW
        BEGIN
            DELETE FROM video_markers WHERE video_id = OLD.id;
        END
    """)


def downgrade() -> None:
    """Remove video_markers table."""
    op.execute('DROP TRIGGER IF EXISTS video_markers_delete_video_cascade')
    op.execute('DROP TRIGGER IF EXISTS video_markers_insert_fk')
    op.drop_index('idx_video_markers_label', table_name='video_markers')
    op.drop_index('idx_video_markers_video_id', table_name='video_markers')
    op.drop_table('video_markers')
