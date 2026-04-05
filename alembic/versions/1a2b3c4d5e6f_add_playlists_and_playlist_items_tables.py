"""Add playlists and playlist_items tables

Revision ID: 1a2b3c4d5e6f
Revises: da98fc08f8df
Create Date: 2026-04-05 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, Sequence[str], None] = 'da98fc08f8df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create playlists and playlist_items tables."""
    # ---- Playlists table ----
    op.create_table(
        'playlists',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('created_at', sa.Text, server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
        sa.Column('updated_at', sa.Text, server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
    )
    
    # ---- Playlist items table (junction table) ----
    op.create_table(
        'playlist_items',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('playlist_id', sa.Integer, nullable=False),
        sa.Column('video_id', sa.Integer, nullable=False),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('added_at', sa.Text, server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
    )
    
    # ---- Indexes for performance ----
    op.create_index(
        'idx_playlist_items_playlist_id',
        'playlist_items',
        ['playlist_id']
    )
    
    op.create_index(
        'idx_playlist_items_video_id',
        'playlist_items',
        ['video_id']
    )
    
    op.create_index(
        'idx_playlist_items_sort_order',
        'playlist_items',
        ['playlist_id', 'sort_order']
    )
    
    # ---- Unique constraint to prevent duplicate videos in a playlist ----
    op.create_index(
        'idx_playlist_items_unique',
        'playlist_items',
        ['playlist_id', 'video_id'],
        unique=True
    )
    
    # ---- Foreign key constraints ----
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS playlist_items_insert_fk 
        BEFORE INSERT ON playlist_items
        FOR EACH ROW
        BEGIN
            SELECT CASE
                WHEN (SELECT id FROM playlists WHERE id = NEW.playlist_id) IS NULL
                THEN RAISE(ABORT, 'Foreign key violation: playlist_id does not exist')
            END;
            SELECT CASE
                WHEN (SELECT id FROM videos WHERE id = NEW.video_id) IS NULL
                THEN RAISE(ABORT, 'Foreign key violation: video_id does not exist')
            END;
        END
    """)
    
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS playlist_items_delete_video_cascade
        BEFORE DELETE ON videos
        FOR EACH ROW
        BEGIN
            DELETE FROM playlist_items WHERE video_id = OLD.id;
        END
    """)
    
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS playlist_items_delete_playlist_cascade
        BEFORE DELETE ON playlists
        FOR EACH ROW
        BEGIN
            DELETE FROM playlist_items WHERE playlist_id = OLD.id;
        END
    """)


def downgrade() -> None:
    """Remove playlists and playlist_items tables."""
    op.execute('DROP TRIGGER IF EXISTS playlist_items_delete_playlist_cascade')
    op.execute('DROP TRIGGER IF EXISTS playlist_items_delete_video_cascade')
    op.execute('DROP TRIGGER IF EXISTS playlist_items_insert_fk')
    op.drop_index('idx_playlist_items_unique', table_name='playlist_items')
    op.drop_index('idx_playlist_items_sort_order', table_name='playlist_items')
    op.drop_index('idx_playlist_items_video_id', table_name='playlist_items')
    op.drop_index('idx_playlist_items_playlist_id', table_name='playlist_items')
    op.drop_table('playlist_items')
    op.drop_table('playlists')
