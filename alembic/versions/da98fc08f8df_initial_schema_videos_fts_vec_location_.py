"""Initial schema: videos, fts, vec, location_cache

Revision ID: da98fc08f8df
Revises: 
Create Date: 2026-04-05 15:54:25.615680

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da98fc08f8df'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema."""
    # ---- Main videos table ----
    op.create_table(
        'videos',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('file_path', sa.Text, unique=True, nullable=False),
        sa.Column('file_name', sa.Text, nullable=False),
        sa.Column('file_size', sa.Integer),
        sa.Column('file_hash', sa.Text, nullable=False),
        sa.Column('source_device', sa.Text),
        sa.Column('lrf_path', sa.Text),
        # Technical metadata
        sa.Column('duration_seconds', sa.REAL),
        sa.Column('resolution', sa.Text),
        sa.Column('width', sa.Integer),
        sa.Column('height', sa.Integer),
        sa.Column('fps', sa.REAL),
        sa.Column('codec', sa.Text),
        sa.Column('creation_date', sa.Text),
        # GPS metadata
        sa.Column('gps_latitude', sa.REAL),
        sa.Column('gps_longitude', sa.REAL),
        sa.Column('gps_location_name', sa.Text),
        sa.Column('gps_accuracy', sa.REAL),
        sa.Column('folder_location', sa.Text),
        sa.Column('location_source', sa.Text, server_default='folder'),
        # LLM-generated analysis
        sa.Column('scene_description', sa.Text),
        sa.Column('tags', sa.Text),
        sa.Column('mood', sa.Text),
        sa.Column('camera_movement', sa.Text),
        sa.Column('time_of_day', sa.Text),
        # Housekeeping
        sa.Column('thumbnail_path', sa.Text),
        sa.Column('processed_at', sa.Text),
        sa.Column('created_at', sa.Text, server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
    )
    
    # ---- Index for fast hash lookups during scanning ----
    op.create_index(
        'idx_videos_file_hash',
        'videos',
        ['file_path', 'file_hash']
    )
    
    # ---- Full-text search index (FTS5) for keyword search ----
    # FTS5 uses special syntax, execute raw SQL
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS videos_fts USING fts5(
            file_name,
            scene_description,
            tags,
            mood,
            camera_movement,
            time_of_day,
            gps_location_name,
            content='videos',
            content_rowid='id'
        )
    """)
    
    # ---- Triggers to keep FTS5 index in sync with the videos table ----
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
    
    # ---- Vector table for semantic search (sqlite-vec) ----
    # Get embedding dimensions from config (768 for Fireworks nomic-embed-text-v2-moe)
    EMBEDDING_DIMENSIONS = 768
    op.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS videos_vec USING vec0(
            video_id INTEGER PRIMARY KEY,
            description_embedding FLOAT[{EMBEDDING_DIMENSIONS}]
        )
    """)
    
    # ---- Location cache table for geocoding results ----
    op.create_table(
        'location_cache',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('location_name', sa.Text, unique=True, nullable=False),
        sa.Column('lat', sa.REAL, nullable=False),
        sa.Column('lon', sa.REAL, nullable=False),
        sa.Column('cached_at', sa.Text, server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')")),
    )


def downgrade() -> None:
    """Revert to empty database."""
    # Drop tables in reverse order of dependencies
    op.drop_table('location_cache')
    op.execute('DROP TABLE IF EXISTS videos_vec')
    op.execute('DROP TRIGGER IF EXISTS videos_au')
    op.execute('DROP TRIGGER IF EXISTS videos_ad')
    op.execute('DROP TRIGGER IF EXISTS videos_ai')
    op.execute('DROP TABLE IF EXISTS videos_fts')
    op.drop_index('idx_videos_file_hash', table_name='videos')
    op.drop_table('videos')

