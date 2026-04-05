"""
Alembic environment configuration for broll-organizer.

This env.py supports dynamic database URLs based on drive path passed via CLI.
Usage: alembic -x drive_path=/path/to/drive upgrade head
"""
from __future__ import annotations

import sqlite3
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool, MetaData, Table, Column, Integer, Text, Float, REAL, event

from alembic import context

# Import project modules for schema reflection
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.broll.config import EMBEDDING_DIMENSIONS


def load_sqlite_vec(dbapi_conn, connection_record):
    """Load sqlite-vec extension on connection."""
    import sqlite_vec
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_db_url() -> str:
    """
    Get database URL from CLI arguments or config.
    
    Supports -x drive_path=/path/to/drive to dynamically construct
    the SQLite URL for the external drive.
    """
    # Try to get drive path from command line arguments (-x drive_path=...)
    cmd_line = config.cmd_opts
    if cmd_line is not None and hasattr(cmd_line, 'x') and cmd_line.x:
        for arg in cmd_line.x:
            if arg.startswith('drive_path='):
                drive_path = arg.split('=', 1)[1]
                # Import config here to get correct DB_FILENAME
                sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
                from broll.config import DB_FILENAME
                db_path = Path(drive_path) / '.broll' / DB_FILENAME
                return f"sqlite:///{db_path.absolute()}"
    
    # Fallback to config option
    db_url = config.get_main_option("sqlalchemy.url")
    if db_url and not db_url.endswith('placeholder.db'):
        return db_url
    
    raise ValueError(
        "No database URL configured. Use -x drive_path=/path/to/drive "
        "or set sqlalchemy.url in alembic.ini"
    )


def get_target_metadata() -> MetaData:
    """
    Construct SQLAlchemy metadata reflecting the current database schema.
    
    This provides the target schema for autogenerate support.
    """
    metadata = MetaData()
    
    # Main videos table
    Table(
        'videos',
        metadata,
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('file_path', Text, unique=True, nullable=False),
        Column('file_name', Text, nullable=False),
        Column('file_size', Integer),
        Column('file_hash', Text, nullable=False),
        Column('source_device', Text),
        Column('lrf_path', Text),
        # Technical metadata
        Column('duration_seconds', REAL),
        Column('resolution', Text),
        Column('width', Integer),
        Column('height', Integer),
        Column('fps', REAL),
        Column('codec', Text),
        Column('creation_date', Text),
        # GPS metadata
        Column('gps_latitude', REAL),
        Column('gps_longitude', REAL),
        Column('gps_location_name', Text),
        Column('gps_accuracy', REAL),
        Column('folder_location', Text),
        Column('location_source', Text, server_default='folder'),
        # LLM-generated analysis
        Column('scene_description', Text),
        Column('tags', Text),
        Column('mood', Text),
        Column('camera_movement', Text),
        Column('time_of_day', Text),
        # Housekeeping
        Column('thumbnail_path', Text),
        Column('processed_at', Text),
        Column('created_at', Text, server_default="(strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"),
    )
    
    # FTS5 virtual table - created manually in migration, not reflected here
    # as FTS5 has special syntax that SQLAlchemy doesn't directly support
    
    # Vector table - created manually in migration
    # sqlite-vec is an extension table
    
    # Location cache table
    Table(
        'location_cache',
        metadata,
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('location_name', Text, unique=True, nullable=False),
        Column('lat', REAL, nullable=False),
        Column('lon', REAL, nullable=False),
        Column('cached_at', Text, server_default="(strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"),
    )
    
    return metadata


# Set up target metadata for autogenerate
target_metadata = get_target_metadata()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    
    This configures the context with just a URL and not an Engine.
    """
    url = get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite specific render options
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    
    In this scenario we create an Engine and associate a connection.
    """
    url = get_db_url()
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
        # Enable loading SQLite extensions (for sqlite-vec)
        connect_args={'check_same_thread': False},
    )
    
    # Register event to load sqlite-vec extension on connect
    event.listen(connectable, "connect", load_sqlite_vec)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite batch mode for ALTER support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
