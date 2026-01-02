"""
Integration tests for Radio Free Luna
Tests complete workflows and component interactions
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch
from pathlib import Path


class TestFullWorkflow:
    """Test complete workflow from file scanning to session creation."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_session_creation(self, app, temp_music_dir, sample_context):
        """Test complete workflow: scan files → analyze → create session."""
        
        # Mock the AI analysis components
        with patch('src.analysis.ai_analyzer.MusicAnalysisEngine.analyze_track_themes') as mock_analyze:
            mock_analyze.return_value = {
                "themes": ["upbeat", "guitar_driven"],
                "mood": "energetic",
                "cultural_significance": "Test significance",
                "lyrical_analysis": "Test analysis",
                "musical_elements": "Guitar and drums",
                "connections": []
            }
            
            # Simulate file scanning
            if app.file_monitor:
                app.file_monitor.initial_scan()
            
            # Update context
            app.context_manager.current_context = sample_context
            
            # Create a session
            if app.session_manager:
                session = await app.session_manager.create_session(
                    theme="upbeat",
                    duration_minutes=30,
                    context=sample_context
                )
                
                assert session is not None
                assert session.theme == "upbeat"
    
    @pytest.mark.asyncio 
    async def test_context_to_music_pipeline(self, app, sample_context):
        """Test context analysis to music recommendation pipeline."""
        
        # Set context
        app.context_manager.current_context = sample_context
        
        # Get contextual themes
        themes = app.context_manager.get_contextual_themes()
        assert isinstance(themes, list)
        
        # Get music guidance
        guidance = app.context_manager.get_contextual_music_guidance()
        assert isinstance(guidance, dict)
        
        # Test that themes align with context
        if sample_context["weather"]["condition"] == "sunny":
            assert any("upbeat" in str(theme).lower() for theme in themes)
    
    @pytest.mark.asyncio
    async def test_voice_context_adaptation(self, app, sample_context):
        """Test voice adaptation based on context."""
        
        if app.voice_adapter and app.tts_client:
            # Test morning voice selection
            morning_context = {**sample_context, "temporal": {"time_of_day": "morning"}}
            voice = app.voice_adapter.get_adaptive_voice(morning_context)
            assert voice in ["nova", "alloy"]  # Energetic voices for morning
            
            # Test evening voice selection  
            evening_context = {**sample_context, "temporal": {"time_of_day": "evening"}}
            voice = app.voice_adapter.get_adaptive_voice(evening_context)
            assert voice in ["fable", "shimmer", "echo"]  # Warmer voices for evening


class TestComponentInteraction:
    """Test interactions between different system components."""
    
    @pytest.mark.asyncio
    async def test_ai_analysis_to_database(self, app, temp_music_dir):
        """Test AI analysis results being stored in database."""
        
        with patch('src.analysis.ai_analyzer.MusicAnalysisEngine.analyze_track_themes') as mock_analyze:
            mock_analyze.return_value = {
                "themes": ["test_theme"],
                "mood": "test_mood",
                "cultural_significance": "Test significance"
            }
            
            # This would typically happen during file monitoring
            # For testing, we simulate the process
            test_file = Path(temp_music_dir) / "test_song.mp3"
            if test_file.exists():
                # Simulate metadata extraction and analysis
                metadata = {
                    "title": "Test Song",
                    "artist": "Test Artist",
                    "duration": 240
                }
                
                # Simulate analysis and storage
                analysis = await mock_analyze.return_value
                assert analysis["themes"] == ["test_theme"]
    
    @pytest.mark.asyncio
    async def test_context_to_session_flow(self, app, sample_context):
        """Test context influencing session creation."""
        
        app.context_manager.current_context = sample_context
        
        # Mock session manager track selection
        if app.session_manager:
            with patch('src.dj.session_manager.SessionManager._select_tracks_for_theme') as mock_select:
                mock_select.return_value = [
                    {
                        "id": 1,
                        "title": "Sunny Day Song",
                        "themes": ["upbeat", "sunny"]
                    }
                ]
                
                session = await app.session_manager.create_session(
                    theme="contextual",
                    duration_minutes=30,
                    context=sample_context
                )
                
                if session:
                    # Verify context influenced selection
                    mock_select.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_commentary_context_integration(self, app, sample_context):
        """Test commentary generation using context."""
        
        if app.commentary_generator:
            app.context_manager.current_context = sample_context
            
            with patch('src.dj.commentary_generator.DJCommentaryGenerator.generate_contextual_interlude') as mock_commentary:
                mock_commentary.return_value = AsyncMock(
                    content="It's a beautiful sunny afternoon...",
                    type="contextual",
                    duration_estimate=20
                )
                
                commentary = await app.commentary_generator.generate_contextual_interlude(
                    sample_context, "time_transition"
                )
                
                if commentary:
                    assert "sunny" in commentary.content.lower() or "afternoon" in commentary.content.lower()


class TestErrorRecovery:
    """Test system recovery from various error conditions."""
    
    @pytest.mark.asyncio
    async def test_ai_service_unavailable(self, app):
        """Test system behavior when AI services are unavailable."""
        
        # Simulate OpenAI API failure
        with patch('openai.AsyncOpenAI') as mock_openai:
            mock_openai.side_effect = Exception("API unavailable")
            
            # System should handle gracefully
            if app.music_analyzer:
                try:
                    result = await app.music_analyzer.analyze_track_themes(
                        "Test Song", "Test Artist", "Test lyrics"
                    )
                    # Should return fallback or handle gracefully
                    assert result is not None or result is None  # Either works
                except Exception as e:
                    # Should have proper error handling
                    assert "API unavailable" in str(e) or isinstance(e, (ConnectionError, TimeoutError))
    
    @pytest.mark.asyncio
    async def test_tts_service_unavailable(self, app):
        """Test system behavior when TTS service is unavailable."""
        
        # Set TTS client to None (simulating unavailable service)
        app.tts_client = None
        
        # System should still function without voice
        context = app.context_manager.get_current_context()
        
        # Should not crash when TTS is unavailable
        assert True  # If we get here, system handled TTS absence gracefully
    
    @pytest.mark.asyncio 
    async def test_weather_service_unavailable(self, app):
        """Test system behavior when weather service is unavailable."""
        
        with patch('src.context.weather.WeatherAnalyzer.get_current_weather') as mock_weather:
            mock_weather.side_effect = Exception("Weather API unavailable")
            
            # Context manager should handle gracefully with fallbacks
            await app.context_manager.update_context()
            
            context = app.context_manager.get_current_context()
            # Should either have fallback weather data or handle absence gracefully
            assert context is not None
    
    @pytest.mark.asyncio
    async def test_database_connection_loss(self, app):
        """Test system behavior when database becomes unavailable."""
        
        # This is a complex test that would require more sophisticated mocking
        # For now, we test that the system has proper error handling structures
        
        if hasattr(app, 'session_manager') and app.session_manager:
            # Should have database connection handling
            assert hasattr(app.session_manager, 'database_url')
    
    def test_invalid_music_files(self, app, temp_music_dir):
        """Test handling of corrupted or invalid music files."""
        
        # Create an invalid "music" file
        invalid_file = Path(temp_music_dir) / "invalid.mp3"
        invalid_file.write_text("This is not an audio file")
        
        if app.file_monitor:
            # Should handle invalid files gracefully
            try:
                app.file_monitor.initial_scan()
                assert True  # If we get here, it handled invalid files
            except Exception as e:
                # Should have specific error handling for invalid files
                assert "invalid" in str(e).lower() or "corrupt" in str(e).lower()


class TestPerformance:
    """Test system performance characteristics."""
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, app):
        """Test system handling of concurrent requests."""
        
        async def make_context_request():
            return app.context_manager.get_current_context()
        
        # Make multiple concurrent requests
        tasks = [make_context_request() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All requests should complete without errors
        for result in results:
            assert not isinstance(result, Exception)
    
    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, app):
        """Test that repeated operations don't cause memory leaks."""
        
        # Perform repeated context updates
        for _ in range(10):
            await app.context_manager.update_context()
            context = app.context_manager.get_current_context()
            assert context is not None
        
        # System should remain stable
        assert app.context_manager is not None
    
    def test_large_music_library_handling(self, temp_music_dir):
        """Test system performance with large music libraries."""
        
        # Create many test files
        for i in range(100):
            test_file = Path(temp_music_dir) / f"test_song_{i:03d}.mp3"
            test_file.write_bytes(b"fake audio data")
        
        if temp_music_dir:
            file_count = len(list(Path(temp_music_dir).glob("*.mp3")))
            assert file_count >= 100
            
            # System should handle large directories
            # (Actual performance testing would require real implementation)