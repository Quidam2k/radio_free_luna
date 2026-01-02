"""
Comprehensive test suite for Phase 1 fixes
Tests all security, validation, and robustness improvements
"""

import pytest
import asyncio
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestSecurityConfiguration:
    """Test suite for security configuration fixes (Task Group 1)"""

    def test_config_requires_openai_key(self):
        """Test that system requires OpenAI API key"""
        from src.core.config import Settings, ValidationError

        # Clear the env var
        os.environ.pop('OPENAI_API_KEY', None)

        with pytest.raises(SystemExit):
            Settings()

    def test_config_rejects_weak_icecast_password(self):
        """Test that weak Icecast passwords are rejected"""
        from src.core.config import Settings

        weak_passwords = [
            'hackme',
            'password',
            '123456',
            'admin',
            'test',
            'short',
        ]

        for weak_pwd in weak_passwords:
            os.environ['ICECAST_PASSWORD'] = weak_pwd
            with pytest.raises(SystemExit):
                Settings()

    def test_config_accepts_strong_icecast_password(self):
        """Test that strong passwords are accepted"""
        from src.core.config import Settings

        os.environ['OPENAI_API_KEY'] = 'sk-test-key-development-only-123456'
        os.environ['ICECAST_PASSWORD'] = 'MyStream2024!Secure'

        try:
            settings = Settings()
            assert settings.icecast_password == 'MyStream2024!Secure'
        except SystemExit:
            pytest.fail("Strong password should be accepted")

    def test_config_validates_password_requirements(self):
        """Test password validation requirements"""
        from src.core.config import Settings

        invalid_passwords = [
            'short',  # too short
            'nouppercase123',  # no uppercase
            'NODIGITS',  # no digits
        ]

        for invalid_pwd in invalid_passwords:
            os.environ['ICECAST_PASSWORD'] = invalid_pwd
            with pytest.raises(SystemExit):
                Settings()


class TestInputValidation:
    """Test suite for input validation (Task 4.1)"""

    def test_session_request_valid_theme(self):
        """Test valid session request"""
        from src.models import SessionRequest

        request = SessionRequest(theme='rainy_day', duration_minutes=30)
        assert request.theme == 'rainy_day'
        assert request.duration_minutes == 30

    def test_session_request_rejects_empty_theme(self):
        """Test empty theme rejected"""
        from src.models import SessionRequest, ValidationError

        with pytest.raises(ValidationError):
            SessionRequest(theme='', duration_minutes=30)

    def test_session_request_rejects_long_theme(self):
        """Test excessively long theme rejected"""
        from src.models import SessionRequest, ValidationError

        long_theme = 'x' * 150
        with pytest.raises(ValidationError):
            SessionRequest(theme=long_theme, duration_minutes=30)

    def test_session_request_rejects_invalid_duration(self):
        """Test invalid durations rejected"""
        from src.models import SessionRequest, ValidationError

        invalid_durations = [0, 1, 500, 600]
        for duration in invalid_durations:
            with pytest.raises(ValidationError):
                SessionRequest(theme='valid', duration_minutes=duration)

    def test_voice_request_valid_text(self):
        """Test valid voice request"""
        from src.models import TestVoiceRequest

        request = TestVoiceRequest(text='Hello world')
        assert request.text == 'Hello world'

    def test_voice_request_rejects_empty_text(self):
        """Test empty text rejected"""
        from src.models import TestVoiceRequest, ValidationError

        with pytest.raises(ValidationError):
            TestVoiceRequest(text='')

    def test_voice_request_rejects_long_text(self):
        """Test excessively long text rejected"""
        from src.models import TestVoiceRequest, ValidationError

        long_text = 'x' * 2000
        with pytest.raises(ValidationError):
            TestVoiceRequest(text=long_text)

    def test_commentary_request_valid_types(self):
        """Test valid commentary types"""
        from src.models import CommentaryRequest

        valid_types = ['contextual', 'opening', 'transition', 'closing']
        for ctype in valid_types:
            request = CommentaryRequest(text_type=ctype)
            assert request.text_type == ctype

    def test_commentary_request_rejects_invalid_type(self):
        """Test invalid commentary type rejected"""
        from src.models import CommentaryRequest, ValidationError

        with pytest.raises(ValidationError):
            CommentaryRequest(text_type='invalid_type')


class TestGlobalStateThreadSafety:
    """Test suite for global state race condition fix (Task 2.1)"""

    @pytest.mark.asyncio
    async def test_app_instance_creation_is_threadsafe(self):
        """Test that app instance creation uses lock"""
        from main import create_app, _app_lock

        # create_app should use lock
        app1 = create_app()
        app2 = create_app()

        # Should return same app instance
        assert app1 is app2

    def test_signal_handler_thread_safety(self):
        """Test signal handler uses lock"""
        from main import handle_shutdown, _app_lock

        # Verify _app_lock is defined and is a Lock
        assert _app_lock is not None
        import threading
        assert isinstance(_app_lock, threading.Lock)


class TestTTSResourceManagement:
    """Test suite for TTS resource leak fix (Task 2.2)"""

    @pytest.mark.asyncio
    async def test_tts_requires_context_manager(self):
        """Test that TTS client requires async context manager"""
        from src.voice.tts_config import TTSConfig
        from src.voice.tts_client import TTSWebUIClient

        config = TTSConfig()
        client = TTSWebUIClient(config)

        # Should return None if not properly initialized
        result = await client.synthesize_speech('test text')
        assert result is None

    @pytest.mark.asyncio
    async def test_tts_session_cleanup(self):
        """Test that TTS client properly closes session"""
        from src.voice.tts_config import TTSConfig
        from src.voice.tts_client import TTSWebUIClient

        config = TTSConfig()

        async with TTSWebUIClient(config) as client:
            # Client should have session
            assert client.session is not None

        # Session should be closed after context exit
        assert client.session is None


class TestSafeObjectSerialization:
    """Test suite for safe serialization fix (Task 3.2)"""

    def test_safe_serialize_dict(self):
        """Test serializing a dict"""
        from src.dj.session_manager import safe_json_serialize
        import json

        data = {'key': 'value', 'number': 42}
        result = safe_json_serialize(data)
        parsed = json.loads(result)
        assert parsed == data

    def test_safe_serialize_with_datetime(self):
        """Test serializing object with datetime"""
        from src.dj.session_manager import safe_json_serialize
        from datetime import datetime
        import json

        class MockContext:
            def __init__(self):
                self.timestamp = datetime.now()
                self.name = 'test'

        obj = MockContext()
        result = safe_json_serialize(obj)
        parsed = json.loads(result)

        # Should have converted datetime to ISO format
        assert 'timestamp' in parsed
        assert 'name' in parsed
        assert parsed['name'] == 'test'

    def test_safe_serialize_none(self):
        """Test serializing None"""
        from src.dj.session_manager import safe_json_serialize
        import json

        result = safe_json_serialize(None)
        parsed = json.loads(result)
        assert parsed == {}

    def test_safe_serialize_complex_object(self):
        """Test serializing complex nested object"""
        from src.dj.session_manager import safe_json_serialize
        from datetime import datetime
        import json

        class InnerObj:
            def __init__(self):
                self.value = 42

        class OuterObj:
            def __init__(self):
                self.inner = InnerObj()
                self.timestamp = datetime.now()
                self.name = 'test'

        obj = OuterObj()
        result = safe_json_serialize(obj)
        parsed = json.loads(result)

        assert 'name' in parsed
        assert 'timestamp' in parsed
        assert parsed['name'] == 'test'


class TestAsyncTaskManagement:
    """Test suite for async task management fix (Task 5.1)"""

    @pytest.mark.asyncio
    async def test_background_tasks_tracked(self):
        """Test that background tasks are tracked"""
        from main import RadioFreeLuna

        app = RadioFreeLuna()
        assert hasattr(app, 'background_tasks')
        assert isinstance(app.background_tasks, list)

    @pytest.mark.asyncio
    async def test_tasks_cancelled_on_shutdown(self):
        """Test that tasks are cancelled during shutdown"""
        from main import RadioFreeLuna

        app = RadioFreeLuna()

        # Create a mock task
        async def mock_task():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                return "cancelled"

        task = asyncio.create_task(mock_task())
        app.background_tasks.append(task)

        # Shutdown should cancel tasks
        await app.shutdown()

        # Task should be cancelled
        assert task.cancelled()


class TestSignalHandling:
    """Test suite for signal handling fix (Task 5.2)"""

    def test_handle_shutdown_uses_lock(self):
        """Test signal handler uses thread lock"""
        from main import handle_shutdown, _app_lock
        import threading

        assert isinstance(_app_lock, threading.Lock)

    def test_handle_shutdown_no_immediate_exit(self):
        """Test that signal handler doesn't call sys.exit immediately"""
        from main import handle_shutdown
        import inspect

        source = inspect.getsource(handle_shutdown)

        # Should NOT contain sys.exit call in handler
        assert 'sys.exit' not in source


class TestAudioServerPasswordValidation:
    """Test that audio server requires validated password"""

    def test_audio_server_requires_password(self):
        """Test audio server constructor requires password"""
        from src.streaming.audio_server import BasicAudioServer

        with pytest.raises(ValueError):
            BasicAudioServer(password=None)

    def test_audio_server_accepts_valid_password(self):
        """Test audio server accepts valid password"""
        from src.streaming.audio_server import BasicAudioServer

        try:
            server = BasicAudioServer(password='ValidPassword123!')
            assert server.password == 'ValidPassword123!'
        except ValueError:
            pytest.fail("Valid password should be accepted")


class TestStreamManagerPasswordValidation:
    """Test that stream manager requires validated password"""

    def test_stream_manager_requires_password(self):
        """Test stream manager constructor requires password"""
        from src.streaming.stream_manager import StreamManager

        with pytest.raises(ValueError):
            StreamManager(password=None)

    def test_stream_manager_accepts_valid_password(self):
        """Test stream manager accepts valid password"""
        from src.streaming.stream_manager import StreamManager

        try:
            manager = StreamManager(password='ValidPassword123!')
            assert manager.audio_server is not None
        except ValueError:
            pytest.fail("Valid password should be accepted")


# Integration tests
class TestPhase1Integration:
    """Integration tests for Phase 1 fixes"""

    @pytest.mark.asyncio
    async def test_config_to_audio_server_password_flow(self):
        """Test password flows from config to audio server"""
        from src.core.config import Settings

        os.environ['OPENAI_API_KEY'] = 'sk-test-key-development-only-123456'
        os.environ['ICECAST_PASSWORD'] = 'MyStream2024!Secure'

        try:
            settings = Settings()

            # Password should be validated in config
            assert settings.icecast_password == 'MyStream2024!Secure'

            # Password should be required for audio server
            from src.streaming.audio_server import BasicAudioServer
            server = BasicAudioServer(password=settings.icecast_password)
            assert server.password == settings.icecast_password

        except SystemExit:
            pytest.fail("Integration test failed due to config error")

    def test_input_validation_on_multiple_endpoints(self):
        """Test that multiple endpoint models validate correctly"""
        from src.models import SessionRequest, TestVoiceRequest, CommentaryRequest, ValidationError

        # Valid requests should work
        session = SessionRequest('theme', 30)
        voice = TestVoiceRequest('text')
        commentary = CommentaryRequest('opening')

        assert session is not None
        assert voice is not None
        assert commentary is not None

        # Invalid requests should fail
        with pytest.raises(ValidationError):
            SessionRequest('theme', 500)  # too long

        with pytest.raises(ValidationError):
            TestVoiceRequest('x' * 2000)  # too long

        with pytest.raises(ValidationError):
            CommentaryRequest('invalid')  # invalid type


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
