"""
Configuration management for Radio Free Luna AI DJ System

Provides environment-based configuration with validation.
All configuration comes from .env file. Critical settings require
valid values and will cause startup to fail if misconfigured.
"""

import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Production-grade configuration with validation and security checks"""

    def __init__(self):
        # =========================================================================
        # REQUIRED SETTINGS - System will not start without these
        # =========================================================================

        self.openai_api_key = self._get_required_env(
            'OPENAI_API_KEY',
            'OpenAI API key for AI analysis and commentary'
        )

        # Optional override for any OpenAI-compatible endpoint (LM Studio, Ollama, etc.).
        # When unset, the openai SDK uses api.openai.com.
        openai_base_url = os.getenv('OPENAI_BASE_URL', '').strip()
        self.openai_base_url: Optional[str] = openai_base_url or None

        # =========================================================================
        # SECURITY SETTINGS - Validated for production use
        # =========================================================================

        self.icecast_password = self._get_validated_password(
            os.getenv('ICECAST_PASSWORD', ''),
            'Icecast password'
        )

        # =========================================================================
        # DATABASE CONFIGURATION
        # =========================================================================

        self.database_url = os.getenv(
            'DATABASE_URL',
            'sqlite:///data/radio_free_luna.db'
        )

        # =========================================================================
        # API KEYS - Optional with fallbacks
        # =========================================================================

        self.genius_api_token = os.getenv('GENIUS_API_TOKEN')
        self.weather_api_key = os.getenv('WEATHER_API_KEY')

        # =========================================================================
        # LOCATION & CONTEXT
        # =========================================================================

        self.location = os.getenv('LOCATION', 'Denver, CO')
        self.timezone = os.getenv('TIMEZONE', 'America/Denver')

        # =========================================================================
        # MUSIC LIBRARY
        # =========================================================================

        music_dirs_str = os.getenv('MUSIC_DIRECTORIES', '')
        self.music_directories = [
            path.strip() for path in music_dirs_str.split(",") if path.strip()
        ]
        self.supported_formats = ['.mp3', '.flac', '.wav', '.m4a', '.ogg']

        # =========================================================================
        # TTS-WEBUI CONFIGURATION
        # =========================================================================

        self.tts_webui_url = os.getenv('TTS_WEBUI_URL', 'http://localhost:7860')
        self.tts_voice_model = os.getenv('TTS_VOICE_MODEL', 'alloy')

        try:
            self.tts_speed = float(os.getenv('TTS_SPEED', '1.0'))
            self.tts_pitch = float(os.getenv('TTS_PITCH', '0.0'))
        except ValueError:
            self.tts_speed = 1.0
            self.tts_pitch = 0.0

        self.tts_emotion = os.getenv('TTS_EMOTION', 'conversational')
        self.tts_quality = os.getenv('TTS_QUALITY', 'tts-1')

        # =========================================================================
        # AI PERSONALITY CONFIGURATION
        # =========================================================================

        self.dj_personality = os.getenv('DJ_PERSONALITY', 'conversational')
        self.knowledge_depth = os.getenv('KNOWLEDGE_DEPTH', 'moderate')
        self.trivia_frequency = os.getenv('TRIVIA_FREQUENCY', 'moderate')
        self.context_awareness = True

        # =========================================================================
        # STREAMING CONFIGURATION
        # =========================================================================

        self.icecast_host = os.getenv('ICECAST_HOST', 'localhost')

        try:
            self.icecast_port = int(os.getenv('ICECAST_PORT', '8000'))
        except ValueError:
            self.icecast_port = 8000

        self.stream_mount = os.getenv('STREAM_MOUNT', '/ai_dj_stream')

        try:
            self.stream_bitrate_kbps = int(os.getenv('STREAM_BITRATE_KBPS', '128'))
        except ValueError:
            self.stream_bitrate_kbps = 128

        # =========================================================================
        # PERFORMANCE CONFIGURATION
        # =========================================================================

        try:
            self.max_analysis_workers = int(os.getenv('MAX_ANALYSIS_WORKERS', '3'))
            self.batch_size = int(os.getenv('BATCH_SIZE', '50'))
            self.cache_size_mb = int(os.getenv('CACHE_SIZE_MB', '256'))
        except ValueError:
            self.max_analysis_workers = 3
            self.batch_size = 50
            self.cache_size_mb = 256

        # =========================================================================
        # REDIS CONFIGURATION
        # =========================================================================

        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_enabled = os.getenv('REDIS_ENABLED', 'false').lower() == 'true'

        # =========================================================================
        # SERVER CONFIGURATION
        # =========================================================================

        self.host = os.getenv('HOST', '0.0.0.0')

        try:
            self.port = int(os.getenv('PORT', '8080'))
        except ValueError:
            self.port = 8080

        self.debug = os.getenv('DEBUG', 'false').lower() == 'true'

        # =========================================================================
        # LOGGING CONFIGURATION
        # =========================================================================

        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.log_file = os.getenv('LOG_FILE', 'logs/radio_free_luna.log')

    def _get_required_env(self, key: str, description: str) -> str:
        """Get a required environment variable or fail"""
        value = os.getenv(key, '').strip()

        if not value:
            print("\n" + "=" * 70)
            print(f"CONFIGURATION ERROR: Missing {key}")
            print("=" * 70)
            print(f"Radio Free Luna requires {description}.")
            print(f"\nSet up your configuration:")
            print(f"  1. Copy .env.example to .env")
            print(f"  2. Add your {key}: {key}=...")
            print(f"  3. Start the system again")
            print("=" * 70 + "\n")
            raise ValueError(f"{key} is required but not set")

        return value

    def _get_validated_password(self, value: str, description: str) -> str:
        """Validate a password meets security requirements"""
        value = value.strip()
        if not value:
            print("\n" + "=" * 70)
            print("CONFIGURATION ERROR: Missing Icecast Password")
            print("=" * 70)
            print("Icecast password is required and must be configured.")
            print("\nSet ICECAST_PASSWORD in .env file with a strong password:")
            print("  - At least 12 characters")
            print("  - Must contain uppercase letters")
            print("  - Must contain digits")
            print("  - Example: MyStream2024!Secure")
            print("=" * 70 + "\n")
            raise ValueError("ICECAST_PASSWORD is required")

        # Check for dangerous test values
        dangerous_values = [
            'hackme',
            'change_this_password_in_production',
            'password',
            '123456',
            'admin',
            'test',
            'your_secure_icecast_password_here',
        ]

        if value.lower() in dangerous_values:
            print("\n" + "=" * 70)
            print("CONFIGURATION ERROR: Invalid Icecast Password")
            print("=" * 70)
            print(f"Password cannot be '{value}'.")
            print("Use a strong password with uppercase letters, lowercase, and numbers.")
            print("  Example: MyStream2024!Secure")
            print("=" * 70 + "\n")
            raise ValueError(f"Icecast password is too weak: '{value}'")

        # Require minimum length
        if len(value) < 12:
            raise ValueError(
                f"Icecast password too short (min 12 chars, got {len(value)})"
            )

        # Require uppercase
        if not any(c.isupper() for c in value):
            raise ValueError(
                "Icecast password must contain at least one uppercase letter"
            )

        # Require digit
        if not any(c.isdigit() for c in value):
            raise ValueError(
                "Icecast password must contain at least one digit"
            )

        return value


def get_settings() -> Settings:
    """Get validated settings instance"""
    try:
        return Settings()
    except ValueError as e:
        print(f"Failed to load configuration: {e}")
        exit(1)


# Create global settings instance - fails on startup if config invalid
settings = get_settings()