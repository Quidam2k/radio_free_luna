"""
Pytest configuration and fixtures for Radio Free Luna tests
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import the application
from main import RadioFreeLuna
from src.core.database import Base


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db_file.close()

    db_url = f"sqlite:///{temp_db_file.name}"
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)

    yield db_url

    # Cleanup - dispose engine connections before deleting file
    engine.dispose()

    # Try to delete the file; on Windows it may be locked, so use try/except
    try:
        os.unlink(temp_db_file.name)
    except PermissionError:
        # File is still in use, will be cleaned up by OS
        pass


@pytest.fixture
def temp_music_dir():
    """Create a temporary directory with test music files."""
    temp_dir = tempfile.mkdtemp()
    
    # Create mock music files
    test_files = [
        "test_song_1.mp3",
        "test_song_2.flac", 
        "test_song_3.wav"
    ]
    
    for filename in test_files:
        file_path = Path(temp_dir) / filename
        file_path.write_bytes(b"fake audio data")
    
    yield temp_dir
    
    # Cleanup handled by tempfile


@pytest.fixture
def mock_openai():
    """Mock OpenAI API responses."""
    return AsyncMock()


@pytest.fixture
def mock_tts_client():
    """Mock TTS client."""
    mock_client = AsyncMock()
    mock_client.test_connection.return_value = True
    mock_client.synthesize_speech.return_value = b"fake audio data"
    return mock_client


@pytest.fixture
def app_config(temp_db, temp_music_dir):
    """Test application configuration."""
    return {
        "database_url": temp_db,
        "music_directories": [temp_music_dir],
        "openai_api_key": "test_key",
        "tts_webui_url": "http://localhost:7860",
        "location": "Test City, TS",
        "weather_api_key": None
    }


@pytest.fixture
def app(app_config, mock_openai, mock_tts_client, monkeypatch):
    """Create test application instance.

    Deliberately does NOT run RadioFreeLuna.startup(): the constructor wires
    every route, and startup would hit real services (TTS retries, weather,
    file scanning) that API tests mock anyway. Components the route handlers
    reference are attached as mocks instead.
    """
    # monkeypatch auto-restores these after the test — plain os.environ
    # mutation here leaks into later tests' Settings() instances.
    monkeypatch.setenv("DATABASE_URL", app_config["database_url"])
    monkeypatch.setenv("MUSIC_DIRECTORIES", ",".join(app_config["music_directories"]))
    monkeypatch.setenv("OPENAI_API_KEY", app_config["openai_api_key"])
    monkeypatch.setenv("TTS_WEBUI_URL", app_config["tts_webui_url"])
    monkeypatch.setenv("LOCATION", app_config["location"])

    radio_app = RadioFreeLuna()

    # Attach components in place of startup(). session_manager and
    # commentary_generator are REAL instances (cheap to construct, no
    # network) so tests can @patch their class methods.
    from src.dj.session_manager import SessionManager
    from src.dj.commentary_generator import DJCommentaryGenerator

    radio_app.music_analyzer = mock_openai
    radio_app.tts_client = mock_tts_client
    radio_app.session_manager = SessionManager(app_config["database_url"], "test_key")
    radio_app.commentary_generator = DJCommentaryGenerator("test_key")

    # Weather and location are keyless (Open-Meteo) — force them offline so
    # tests serve mock/fallback data instead of hitting the network.
    radio_app.weather_analyzer.offline = True
    radio_app.location_analyzer.offline = True

    yield radio_app
    # Nothing was started, so nothing to shut down.


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app.app)


@pytest.fixture
def sample_context():
    """Sample context data for testing."""
    from datetime import datetime
    return {
        "weather": {
            "condition": "sunny",
            "temperature": 72,
            "mood": "upbeat"
        },
        "temporal": {
            "time_of_day": "afternoon",
            "day_of_week": "friday",
            "season": "spring"
        },
        "location": {
            "city": "Test City",
            "music_scene": "indie_rock"
        },
        # Routes call .isoformat() on this — must be a datetime, not a string
        "updated_at": datetime(2024, 1, 1, 12, 0, 0)
    }


@pytest.fixture
def sample_tracks():
    """Sample track data for testing."""
    return [
        {
            "id": 1,
            "title": "Test Song 1",
            "artist": "Test Artist 1",
            "album": "Test Album 1",
            "duration": 240,
            "genre": "rock",
            "file_path": "/test/path/song1.mp3",
            "themes": ["upbeat", "guitar_driven"]
        },
        {
            "id": 2,
            "title": "Test Song 2", 
            "artist": "Test Artist 2",
            "album": "Test Album 2",
            "duration": 180,
            "genre": "indie",
            "file_path": "/test/path/song2.flac",
            "themes": ["contemplative", "indie_folk"]
        }
    ]