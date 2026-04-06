"""Add proxy_path column to videos table

Revision ID: 2026_04_05_add_proxy_path
Revises: 1a2b3c4d5e6f
Create Date: 2026-04-05 21:00:00

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2026_04_05_add_proxy_path'
down_revision = '1a2b3c4d5e6f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add proxy_path column to videos table
    op.add_column('videos', sa.Column('proxy_path', sa.String(), nullable=True))

    # Create index for faster lookups
    op.create_index(
        'idx_videos_proxy_path',
        'videos',
        ['proxy_path'],
        unique=False
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index('idx_videos_proxy_path', table_name='videos')

    # Drop column
    op.drop_column('videos', 'proxy_path')
