#!/usr/bin/env python3
"""Simple configuration for testing without complex pydantic settings"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SimpleSettings:
    def __init__(self):
        # Required settings
        self.openai_api_key = os.getenv('OPENAI_API_KEY', 'sk-test-key')
        self.database_url = os.getenv('DATABASE_URL', 'sqlite:///data/radio_free_luna.db')
        
        # Music directories (parse comma-separated)
        music_dirs_str = os.getenv('MUSIC_DIRECTORIES', '')
        self.music_directories = [path.strip() for path in music_dirs_str.split(",") if path.strip()]
        
        # Optional settings with defaults
        self.location = os.getenv('LOCATION', 'Denver, CO')
        self.dj_personality = os.getenv('DJ_PERSONALITY', 'conversational')
        self.knowledge_depth = os.getenv('KNOWLEDGE_DEPTH', 'moderate')
        self.tts_webui_url = os.getenv('TTS_WEBUI_URL', 'http://localhost:7860')
        
        # Audio settings
        self.supported_formats = [".mp3", ".flac", ".wav", ".m4a", ".ogg"]
        
        # Streaming settings  
        self.icecast_host = os.getenv('ICECAST_HOST', 'localhost')
        self.icecast_port = int(os.getenv('ICECAST_PORT', '8000'))
        self.icecast_password = os.getenv('ICECAST_PASSWORD', 'change_this_password_in_production')
        self.stream_mount = os.getenv('STREAM_MOUNT', '/ai_dj_stream')
        
        # Voice settings
        self.tts_voice_model = os.getenv('TTS_VOICE_MODEL', 'alloy')
        self.tts_speed = float(os.getenv('TTS_SPEED', '1.0'))
        self.tts_quality = os.getenv('TTS_QUALITY', 'tts-1')
        
        # Performance
        self.max_analysis_workers = int(os.getenv('MAX_ANALYSIS_WORKERS', '3'))
        self.batch_size = int(os.getenv('BATCH_SIZE', '50'))
        
        # Optional API keys
        self.genius_api_token = os.getenv('GENIUS_API_TOKEN')
        self.weather_api_key = os.getenv('WEATHER_API_KEY')
        
    def __repr__(self):
        return f"SimpleSettings(openai_key={'set' if self.openai_api_key else 'missing'}, music_dirs={len(self.music_directories)} dirs)"

# Create settings instance  
settings = SimpleSettings()

if __name__ == "__main__":
    print("Simple Configuration Test")
    print(f"Settings: {settings}")
    print(f"Music directories: {settings.music_directories}")
    print(f"Database URL: {settings.database_url}")
    print(f"OpenAI key: {'SET' if settings.openai_api_key else 'MISSING'}")