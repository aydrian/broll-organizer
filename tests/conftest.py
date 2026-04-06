"""
Shared test fixtures for broll-organizer tests.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from broll.db import Database


@pytest.fixture
def temp_db_path():
    """Create a temporary database file path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def empty_database(temp_db_path):
    """Create an initialized but empty database."""
    db = Database(temp_db_path)
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def sample_videos_database(temp_db_path):
    """Create a database with sample video records for testing."""
    db = Database(temp_db_path)
    db.initialize()

    # Insert sample videos with various metadata
    sample_videos = [
        {
            "file_path": "video1.mp4",
            "file_name": "sunset_beach.mp4",
            "file_size": 1000000,
            "file_hash": "hash1",
            "duration_seconds": 10.0,
            "width": 3840,
            "height": 2160,
            "resolution": "3840x2160",
            "creation_date": "2025-06-15T18:30:00Z",
            "gps_location_name": "Tokyo, Japan",
            "mood": "calm",
            "camera_movement": "static",
            "time_of_day": "golden_hour",
            "source_device": "dji_pocket3",
        },
        {
            "file_path": "video2.mp4",
            "file_name": "night_city.mp4",
            "file_size": 2000000,
            "file_hash": "hash2",
            "duration_seconds": 25.0,
            "width": 1920,
            "height": 1080,
            "resolution": "1920x1080",
            "creation_date": "2025-08-20T22:00:00Z",
            "gps_location_name": "Kusatsu, Japan",
            "mood": "energetic",
            "camera_movement": "gimbal",
            "time_of_day": "night",
            "source_device": "dji_pocket3",
        },
        {
            "file_path": "video3.mp4",
            "file_name": "morning_portrait.mp4",
            "file_size": 500000,
            "file_hash": "hash3",
            "duration_seconds": 5.0,
            "width": 1080,
            "height": 1920,
            "resolution": "1080x1920",
            "creation_date": "2025-01-10T08:00:00Z",
            "gps_location_name": "New York, USA",
            "mood": "calm",
            "camera_movement": "pan",
            "time_of_day": "morning",
            "source_device": "iphone",
        },
        {
            "file_path": "video4.mp4",
            "file_name": "long_clip.mp4",
            "file_size": 3000000,
            "file_hash": "hash4",
            "duration_seconds": 120.0,
            "width": 720,
            "height": 480,
            "resolution": "720x480",
            "creation_date": "2025-12-25T12:00:00Z",
            "mood": "mysterious",
            "camera_movement": "static",
            "time_of_day": "afternoon",
        },
    ]

    conn = db.connect()
    for video in sample_videos:
        columns = ", ".join(video.keys())
        placeholders = ", ".join("?" * len(video))
        sql = f"INSERT INTO videos ({columns}) VALUES ({placeholders})"
        conn.execute(sql, tuple(video.values()))

    conn.commit()
    yield db
    db.close()


@pytest.fixture
def mock_embeddings(monkeypatch):
    """Mock the embedding generation to avoid API calls during tests."""
    def mock_generate_embedding(text: str) -> list[float]:
        # Return a deterministic fake embedding (768 dimensions of zeros)
        return [0.0] * 768

    monkeypatch.setattr("broll.embeddings.generate_embedding", mock_generate_embedding)


@pytest.fixture
def mock_vector_search(monkeypatch):
    """Mock the vector search to return predictable results."""
    def mock_vector_search_impl(embedding, limit=20):
        # Return empty list by default - tests can override if needed
        return []

    monkeypatch.setattr(
        "broll.db.Database.vector_search", lambda self, emb, limit: mock_vector_search_impl(emb, limit)
    )
