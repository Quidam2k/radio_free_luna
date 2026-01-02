"""
Core component tests for Radio Free Luna
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.core.config import Settings
from src.core.file_monitor import FileMonitor
from src.analysis.ai_analyzer import MusicAnalysisEngine
from src.context.context_manager import ContextManager
from src.dj.session_manager import SessionManager


class TestSettings:
    """Test configuration management."""
    
    def test_default_settings(self):
        """Test default configuration values."""
        settings = Settings(
            openai_api_key="test_key",
            music_directories=["/test/path"]
        )
        
        assert settings.database_url == "sqlite:///ai_dj.db"
        assert settings.location == "Denver, CO"
        assert settings.tts_webui_url == "http://localhost:7860"
        assert settings.tts_voice_model == "alloy"
        assert settings.dj_personality == "conversational"
    
    def test_environment_variable_parsing(self):
        """Test parsing of environment variables."""
        # Test music directories parsing
        with patch.dict('os.environ', {
            'MUSIC_DIRECTORIES': '/path1,/path2, /path3 ',
            'OPENAI_API_KEY': 'test_key'
        }):
            settings = Settings()
            assert settings.music_directories == ['/path1', '/path2', '/path3']


class TestFileMonitor:
    """Test file monitoring functionality."""
    
    def test_file_monitor_initialization(self, temp_music_dir, temp_db):
        """Test file monitor initialization."""
        monitor = FileMonitor([temp_music_dir], temp_db)
        
        assert monitor.directories == [temp_music_dir]
        assert monitor.database_url == temp_db
        assert not monitor.is_running
    
    @patch('src.core.file_monitor.FileMonitor.scan_directory')
    def test_initial_scan(self, mock_scan, temp_music_dir, temp_db):
        """Test initial directory scan."""
        monitor = FileMonitor([temp_music_dir], temp_db)
        mock_scan.return_value = []
        
        monitor.initial_scan()
        
        mock_scan.assert_called_once()
    
    def test_supported_formats(self, temp_music_dir, temp_db):
        """Test supported audio format detection."""
        monitor = FileMonitor([temp_music_dir], temp_db)
        
        # Test supported formats
        assert monitor._is_supported_audio_file(Path("test.mp3"))
        assert monitor._is_supported_audio_file(Path("test.flac"))
        assert monitor._is_supported_audio_file(Path("test.wav"))
        
        # Test unsupported formats
        assert not monitor._is_supported_audio_file(Path("test.txt"))
        assert not monitor._is_supported_audio_file(Path("test.jpg"))


class TestMusicAnalysisEngine:
    """Test AI music analysis functionality."""
    
    @pytest.fixture
    def analysis_engine(self):
        """Create music analysis engine for testing."""
        return MusicAnalysisEngine("test_api_key")
    
    @patch('openai.AsyncOpenAI')
    async def test_analyze_track(self, mock_openai, analysis_engine, sample_tracks):
        """Test track analysis functionality."""
        # Mock OpenAI response
        mock_response = AsyncMock()
        mock_response.choices[0].message.content = """
        {
            "themes": ["upbeat", "guitar_driven"],
            "mood": "energetic",
            "cultural_significance": "Representative of indie rock movement",
            "lyrical_analysis": "Themes of freedom and self-expression",
            "musical_elements": "Driven by guitar riffs and steady drumbeat",
            "connections": ["Similar to alternative rock from the 90s"]
        }
        """
        mock_openai.return_value.chat.completions.create.return_value = mock_response
        
        track = sample_tracks[0]
        result = await analysis_engine.analyze_track_themes(
            track["title"], track["artist"], "Sample lyrics"
        )
        
        assert "themes" in result
        assert "mood" in result
        assert "cultural_significance" in result
    
    @patch('openai.AsyncOpenAI')
    async def test_find_connections(self, mock_openai, analysis_engine, sample_tracks):
        """Test track connection discovery."""
        # Mock OpenAI response
        mock_response = AsyncMock()
        mock_response.choices[0].message.content = """
        {
            "connections": [
                {
                    "type": "thematic",
                    "strength": 0.8,
                    "reason": "Both explore themes of urban alienation"
                }
            ]
        }
        """
        mock_openai.return_value.chat.completions.create.return_value = mock_response
        
        connections = await analysis_engine.find_track_connections(
            sample_tracks[0], sample_tracks
        )
        
        assert isinstance(connections, list)
        if connections:  # If connections found
            assert "type" in connections[0]
            assert "strength" in connections[0]


class TestContextManager:
    """Test contextual awareness functionality."""
    
    @pytest.fixture
    def context_manager(self):
        """Create context manager for testing."""
        weather_analyzer = MagicMock()
        location_analyzer = MagicMock()
        temporal_analyzer = MagicMock()
        
        return ContextManager(
            weather_analyzer,
            location_analyzer, 
            temporal_analyzer
        )
    
    async def test_context_update(self, context_manager):
        """Test context update functionality."""
        # Mock analyzer responses
        context_manager.weather_analyzer.get_current_weather.return_value = {
            "condition": "sunny",
            "temperature": 75,
            "mood": "upbeat"
        }
        
        context_manager.temporal_analyzer.get_current_temporal_context.return_value = {
            "time_of_day": "afternoon",
            "season": "spring"
        }
        
        context_manager.location_analyzer.get_location_context.return_value = {
            "city": "Test City",
            "music_scene": "indie_rock"
        }
        
        await context_manager.update_context()
        
        context = context_manager.get_current_context()
        assert context is not None
        assert "weather" in context
        assert "temporal" in context
        assert "location" in context
    
    def test_contextual_themes(self, context_manager, sample_context):
        """Test contextual theme generation."""
        context_manager.current_context = sample_context
        
        themes = context_manager.get_contextual_themes()
        
        assert isinstance(themes, list)
        assert len(themes) > 0
    
    def test_music_guidance(self, context_manager, sample_context):
        """Test contextual music guidance."""
        context_manager.current_context = sample_context
        
        guidance = context_manager.get_contextual_music_guidance()
        
        assert isinstance(guidance, dict)
        assert "energy_level" in guidance
        assert "mood_preference" in guidance


class TestSessionManager:
    """Test DJ session management."""
    
    @pytest.fixture
    async def session_manager(self, temp_db):
        """Create session manager for testing."""
        return SessionManager(temp_db, "test_api_key")
    
    @patch('src.dj.session_manager.SessionManager._select_tracks_for_theme')
    @patch('src.dj.session_manager.SessionManager._generate_session_commentary')
    async def test_create_session(
        self, 
        mock_generate_commentary,
        mock_select_tracks,
        session_manager,
        sample_context,
        sample_tracks
    ):
        """Test session creation."""
        # Mock track selection
        mock_select_tracks.return_value = sample_tracks
        
        # Mock commentary generation
        mock_generate_commentary.return_value = [
            {"type": "opening", "content": "Welcome to this session"},
            {"type": "transition", "content": "Next up we have..."}
        ]
        
        session = await session_manager.create_session(
            theme="rainy_day",
            duration_minutes=60,
            context=sample_context
        )
        
        assert session is not None
        assert session.theme == "rainy_day"
        assert hasattr(session, 'session_id')
        assert hasattr(session, 'tracks')
    
    def test_theme_scoring(self, session_manager, sample_tracks, sample_context):
        """Test track scoring for themes."""
        track = sample_tracks[0]
        score = session_manager._score_track_for_context(track, sample_context)
        
        assert isinstance(score, (int, float))
        assert score >= 0