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


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db_file.close()
    
    db_url = f"sqlite:///{temp_db_file.name}"
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    
    yield db_url
    
    # Cleanup
    os.unlink(temp_db_file.name)


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
async def app(app_config, mock_openai, mock_tts_client):
    """Create test application instance."""
    # Patch environment variables
    os.environ.update({
        "DATABASE_URL": app_config["database_url"],
        "MUSIC_DIRECTORIES": ",".join(app_config["music_directories"]),
        "OPENAI_API_KEY": app_config["openai_api_key"],
        "TTS_WEBUI_URL": app_config["tts_webui_url"],
        "LOCATION": app_config["location"]
    })
    
    radio_app = RadioFreeLuna()
    
    # Mock the AI and TTS systems
    radio_app.music_analyzer = mock_openai
    radio_app.tts_client = mock_tts_client
    
    await radio_app.startup()
    
    yield radio_app
    
    await radio_app.shutdown()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app.app)


@pytest.fixture
def sample_context():
    """Sample context data for testing."""
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
        "updated_at": "2024-01-01T12:00:00Z"
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