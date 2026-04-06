"""Update location_cache schema with search_key and display_name

Revision ID: 2026_04_05_update_location_cache
Revises: 2026_04_05_add_proxy_path
Create Date: 2026-04-05 20:30:00.000000+00:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2026_04_05_update_location_cache'
down_revision = '2026_04_05_add_proxy_path'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Recreate location_cache table with new schema.
    Old: location_name TEXT UNIQUE, lat, lon, cached_at
    New: search_key TEXT UNIQUE, display_name TEXT, location_name TEXT, lat, lon, cached_at
    """
    # Drop the old table (it's just cache data, safe to lose)
    op.drop_table('location_cache')

    # Create new table with proper columns
    op.create_table(
        'location_cache',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('search_key', sa.Text(), nullable=False, unique=True),
        sa.Column('display_name', sa.Text(), nullable=False),
        sa.Column('location_name', sa.Text(), nullable=True),
        sa.Column('lat', sa.REAL(), nullable=False),
        sa.Column('lon', sa.REAL(), nullable=False),
        sa.Column('cached_at', sa.Text(),
                  server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"))
    )


def downgrade() -> None:
    """
    Revert to old location_cache schema.
    """
    op.drop_table('location_cache')

    op.create_table(
        'location_cache',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('location_name', sa.Text(), nullable=False, unique=True),
        sa.Column('lat', sa.REAL(), nullable=False),
        sa.Column('lon', sa.REAL(), nullable=False),
        sa.Column('cached_at', sa.Text(),
                  server_default=sa.text("strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"))
    )