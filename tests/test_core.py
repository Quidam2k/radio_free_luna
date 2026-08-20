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
    
    def test_default_settings(self, monkeypatch):
        """Test default configuration values."""
        monkeypatch.setenv('OPENAI_API_KEY', 'test_key')
        monkeypatch.setenv('MUSIC_DIRECTORIES', '/test/path')

        settings = Settings()

        assert settings.openai_api_key == "test_key"
        assert settings.location == "Denver, CO"
        assert settings.tts_webui_url == "http://localhost:7860"
        assert settings.tts_voice_model == "alloy"
    
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
    


class TestMusicAnalysisEngine:
    """Test AI music analysis functionality (no network)."""

    @pytest.fixture
    def analysis_engine(self):
        """Create music analysis engine for testing."""
        return MusicAnalysisEngine("test_api_key")

    def test_parse_analysis_response(self, analysis_engine):
        """Well-formed JSON from the model parses into an AnalysisResult."""
        response = """
        Here is the analysis you requested:
        {
            "themes": ["love", "loss"],
            "mood_analysis": {"valence": 0.5, "energy": 0.7, "danceability": 0.4},
            "summary": "A moving ballad.",
            "cultural_context": "An 80s staple.",
            "notable_elements": ["synth lead"]
        }
        """
        result = analysis_engine._parse_analysis_response(response)

        assert result.themes == ["love", "loss"]
        assert result.mood_valence == 0.5
        assert result.energy_level == 0.7
        assert result.summary == "A moving ballad."

    def test_parse_malformed_response_raises(self, analysis_engine):
        with pytest.raises(Exception):
            analysis_engine._parse_analysis_response("not json at all")

    def test_fallback_analysis_uses_genre(self, analysis_engine):
        """When AI is unavailable, fallback themes come from the genre."""
        from src.core.database import Track
        track = Track(title="Test", artist="Artist", genre="jazz", duration=200)

        result = analysis_engine._create_fallback_analysis(track)

        assert "sophistication" in result.themes
        assert result.energy_level == 0.5

    @pytest.mark.asyncio
    async def test_analyze_track_falls_back_when_api_fails(self, analysis_engine):
        """API failure must degrade to a fallback analysis, not raise."""
        from src.core.database import Track

        class FailingClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        raise ConnectionError("no API today")

        analysis_engine.client = FailingClient()
        track = Track(id=999999, title="T", artist="A", genre="rock",
                      duration=100, file_hash="h")

        result = await analysis_engine.analyze_track_comprehensive(track)

        assert result is not None
        assert "energy" in result.themes  # rock fallback themes


class TestContextManager:
    """Test contextual awareness with REAL analyzers (all offline):
    weather serves mock data, location falls back to string parsing,
    temporal is pure computation."""

    @pytest.fixture
    def context_manager(self):
        from src.context.weather import WeatherAnalyzer
        from src.context.location import LocationAnalyzer
        from src.context.temporal import TemporalAnalyzer

        return ContextManager(
            WeatherAnalyzer(location="Nashville, TN", offline=True),
            LocationAnalyzer(location="Nashville, TN", offline=True),
            TemporalAnalyzer()
        )

    @pytest.mark.asyncio
    async def test_context_update(self, context_manager):
        """Full context update populates all three sources."""
        await context_manager.update_context()

        context = context_manager.get_current_context()
        assert context is not None
        assert context["temporal"] is not None
        assert context["weather"] is not None
        assert context["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_contextual_themes(self, context_manager):
        """Theme generation produces a non-empty deduplicated list."""
        await context_manager.update_context()

        themes = context_manager.get_contextual_themes()

        assert isinstance(themes, list)
        assert len(themes) > 0
        assert len(themes) == len(set(themes))

    @pytest.mark.asyncio
    async def test_music_guidance(self, context_manager):
        """Guidance dict has the documented structure."""
        await context_manager.update_context()

        guidance = context_manager.get_contextual_music_guidance()

        assert isinstance(guidance, dict)
        assert "themes" in guidance
        assert "energy_guidance" in guidance
        assert "mood_guidance" in guidance

    @pytest.mark.asyncio
    async def test_context_description_is_readable(self, context_manager):
        await context_manager.update_context()

        description = context_manager.generate_context_description()

        assert isinstance(description, str)
        assert len(description) > 0
        assert description != "Context information not available"


class TestSessionManager:
    """Test DJ session management."""


    @pytest.fixture
    def session_manager(self, temp_db):
        """Create session manager for testing."""
        return SessionManager(temp_db, "test_api_key")


    @pytest.mark.asyncio
    @patch('src.dj.session_manager.SessionManager.store_session', new_callable=AsyncMock)
    @patch('src.dj.session_manager.SessionManager.generate_session_commentary', new_callable=AsyncMock)
    @patch('src.dj.session_manager.SessionManager.find_tracks_for_theme', new_callable=AsyncMock)
    async def test_create_session(
        self,
        mock_find_tracks,
        mock_generate_commentary,
        mock_store_session,
        session_manager,
        sample_tracks
    ):
        """Session creation sequences the candidate tracks for real."""
        mock_find_tracks.return_value = sample_tracks
        mock_generate_commentary.return_value = []

        session = await session_manager.create_session(
            theme="rainy_day",
            duration_minutes=60,
            context={}
        )

        assert session is not None
        assert session.theme == "rainy_day"
        assert session.session_id
        assert len(session.tracks) == len(sample_tracks)
        assert session.tracks[0].position == 1
        mock_store_session.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('src.dj.session_manager.SessionManager.find_tracks_for_theme', new_callable=AsyncMock)
    async def test_create_session_empty_library_raises(self, mock_find_tracks, session_manager):
        mock_find_tracks.return_value = []

        with pytest.raises(ValueError):
            await session_manager.create_session("rainy_day", 60, {})

    def test_context_relevance_scoring(self, session_manager, sample_tracks):
        """Theme match contributes to relevance; mismatch scores zero."""
        track = sample_tracks[0]  # themes: ["upbeat", "guitar_driven"]

        match = session_manager.calculate_context_relevance(track, {}, "upbeat")
        miss = session_manager.calculate_context_relevance(track, {}, "jazz")

        assert match == pytest.approx(0.4)
        assert miss == 0.0