"""
API endpoint tests for Radio Free Luna
"""

import pytest
import json
from unittest.mock import AsyncMock, patch


class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    def test_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"
        assert data["system"] == "Radio Free Luna"
        assert "components" in data
    
    def test_system_status(self, client):
        """Test system status endpoint."""
        response = client.get("/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["system"] == "Radio Free Luna"
        assert data["status"] == "operational"
        assert "context" in data
        assert "music_library" in data
        assert "ai_systems" in data
    
    def test_root_endpoint(self, client):
        """Root serves the web interface (HTML) when static files exist."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Radio Free Luna" in response.text

    def test_api_info_endpoint(self, client):
        """JSON API info lives at /api."""
        response = client.get("/api")
        assert response.status_code == 200

        data = response.json()
        assert data["message"] == "Radio Free Luna - AI DJ System API"
        assert "tagline" in data
        assert "endpoints" in data


class TestContextAPI:
    """Test context-related API endpoints."""
    
    @patch('src.context.context_manager.ContextManager.get_current_context')
    def test_get_context(self, mock_get_context, client, sample_context):
        """Test context retrieval endpoint."""
        mock_get_context.return_value = sample_context
        
        response = client.get("/api/context")
        assert response.status_code == 200
        
        data = response.json()
        assert "description" in data
        assert "themes" in data
        assert "music_guidance" in data
        assert "updated_at" in data
    
    @patch('src.context.context_manager.ContextManager.get_current_context')
    def test_get_context_unavailable(self, mock_get_context, client):
        """Test context endpoint when context is unavailable."""
        mock_get_context.return_value = None
        
        response = client.get("/api/context")
        assert response.status_code == 200
        
        data = response.json()
        assert "error" in data
        assert data["error"] == "Context not available"


class TestSessionAPI:
    """Test session management API endpoints."""
    
    @patch('src.dj.session_manager.SessionManager.create_session')
    @patch('src.context.context_manager.ContextManager.get_current_context')
    def test_create_session(self, mock_get_context, mock_create_session, client, sample_context):
        """Test session creation endpoint."""
        mock_get_context.return_value = sample_context
        
        # Mock session object
        mock_session = AsyncMock()
        mock_session.session_id = "test_session_123"
        mock_session.theme = "rainy_day"
        mock_session.status = "created"
        mock_session.tracks = [
            AsyncMock(track={"duration": 240}),
            AsyncMock(track={"duration": 180})
        ]
        mock_create_session.return_value = mock_session
        
        response = client.post(
            "/api/sessions",
            json={"theme": "rainy_day", "duration_minutes": 60}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["session_id"] == "test_session_123"
        assert data["theme"] == "rainy_day"
        assert data["status"] == "created"
        assert data["track_count"] == 2
        assert data["estimated_duration"] == 420
    
    @patch('src.context.context_manager.ContextManager.get_current_context')
    def test_create_session_no_context(self, mock_get_context, client):
        """Test session creation when context is unavailable."""
        mock_get_context.return_value = None
        
        response = client.post(
            "/api/sessions",
            json={"theme": "rainy_day", "duration_minutes": 60}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "error" in data
        assert data["error"] == "Context not available"


class TestCommentaryAPI:
    """Test commentary generation API endpoints."""
    
    @patch('src.dj.commentary_generator.DJCommentaryGenerator.generate_contextual_interlude')
    @patch('src.context.context_manager.ContextManager.get_current_context')
    def test_generate_contextual_commentary(self, mock_get_context, mock_generate_commentary, client, sample_context):
        """Test contextual commentary generation."""
        mock_get_context.return_value = sample_context
        
        # Mock commentary object
        mock_commentary = AsyncMock()
        mock_commentary.content = "Test commentary content"
        mock_commentary.type = "contextual"
        mock_commentary.duration_estimate = 30
        mock_generate_commentary.return_value = mock_commentary
        
        response = client.post(
            "/api/commentary",
            json={"text_type": "contextual"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["content"] == "Test commentary content" 
        assert data["type"] == "contextual"
        assert data["duration_estimate"] == 30
        assert "context" in data
    
    @patch('src.dj.commentary_generator.DJCommentaryGenerator.generate_opening_commentary')
    @patch('src.context.context_manager.ContextManager.get_current_context')
    def test_generate_opening_commentary(self, mock_get_context, mock_generate_commentary, client, sample_context):
        """Test opening commentary generation."""
        mock_get_context.return_value = sample_context
        
        # Mock commentary object
        mock_commentary = AsyncMock()
        mock_commentary.content = "Welcome to Radio Free Luna"
        mock_commentary.type = "opening"
        mock_commentary.duration_estimate = 45
        mock_generate_commentary.return_value = mock_commentary
        
        response = client.post(
            "/api/commentary",
            json={"text_type": "opening"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["content"] == "Welcome to Radio Free Luna"
        assert data["type"] == "opening"
        assert data["duration_estimate"] == 45


class TestVoiceAPI:
    """Test voice synthesis API endpoints."""
    
    @patch('src.voice.tts_client.TTSWebUIClient.synthesize_speech')
    def test_voice_synthesis(self, mock_synthesize, client):
        """Test voice synthesis endpoint."""
        mock_synthesize.return_value = b"fake audio data"
        
        response = client.post(
            "/api/test-voice",
            json={"text": "Hello from Radio Free Luna"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert data["message"] == "Voice synthesis working"
        assert "audio_length" in data
    
    def test_voice_synthesis_unavailable(self, client):
        """Test voice synthesis when TTS is unavailable."""
        # This test assumes TTS client is None or unavailable
        response = client.post(
            "/api/test-voice",
            json={"text": "Hello from Radio Free Luna"}
        )
        
        # Should handle gracefully even when TTS is unavailable
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestAPIErrorHandling:
    """Test API error handling and edge cases."""
    
    def test_invalid_endpoints(self, client):
        """Test handling of invalid endpoints."""
        response = client.get("/api/nonexistent")
        assert response.status_code == 404
    
    def test_malformed_requests(self, client):
        """Test handling of malformed requests."""
        # Test with invalid JSON
        response = client.post(
            "/api/sessions",
            data="invalid json",
            headers={"content-type": "application/json"}
        )
        # Should handle gracefully - exact status code depends on FastAPI handling
        assert response.status_code in [400, 422]
    
    def test_missing_parameters(self, client):
        """Test endpoints with missing required parameters."""
        response = client.post("/api/sessions")
        # Should handle missing parameters gracefully
        assert response.status_code in [200, 400, 422]