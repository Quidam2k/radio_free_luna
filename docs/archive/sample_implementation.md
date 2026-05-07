# Sample Implementation Files

This document contains key implementation files to get you started quickly with Claude Code.

## requirements.txt

```txt
# TTS Integration
python-tts-webui-client==0.1.0  # Custom client for TTS-WebUI
aiohttp==3.9.1
pydub==0.25.1

# Voice Processing
librosa==0.10.1
soundfile==0.12.1
scipy==1.11.4

# Development
pytest==7.4.3
pytest-asyncio==0.21.1
black==23.11.0
flake8==6.1.0
```

## main.py

```python
#!/usr/bin/env python3
"""
AI DJ System - Main Application Entry Point with TTS Integration
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from dotenv import load_dotenv

# Import our modules
from src.core.config import Settings
from src.core.database import init_database
from src.core.file_monitor import FileMonitor
from src.web.api import router as api_router
from src.web.websocket_manager import WebSocketManager
from src.dj.voiced_dj_engine import VoicedDJEngine
from src.analysis.background_processor import BackgroundProcessor
from src.voice.tts_config import TTSConfig
from src.context.context_manager import ContextManager
from src.context.temporal import TemporalAnalyzer
from src.context.weather import WeatherAnalyzer
from src.context.location import LocationAnalyzer

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ai_dj.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class AIdjApplication:
    def __init__(self):
        self.settings = Settings()
        self.app = FastAPI(
            title="AI DJ System with Voice",
            description="Intelligent music streaming with AI-powered DJ commentary and voice synthesis",
            version="1.0.0"
        )
        
        # Initialize TTS configuration
        self.tts_config = TTSConfig(
            api_url=os.getenv("TTS_WEBUI_URL", "http://localhost:7860"),
            voice_model=os.getenv("TTS_VOICE_MODEL", "male_conversational"),
            speed=float(os.getenv("TTS_SPEED", "1.0")),
            pitch=float(os.getenv("TTS_PITCH", "1.0")),
            emotion=os.getenv("TTS_EMOTION", "conversational")
        )
        
        # Initialize context managers
        self.temporal_analyzer = TemporalAnalyzer()
        self.weather_analyzer = WeatherAnalyzer(
            api_key=os.getenv("WEATHER_API_KEY"),
            location=os.getenv("LOCATION", "Denver, CO")
        )
        self.location_analyzer = LocationAnalyzer(
            location=os.getenv("LOCATION", "Denver, CO")
        )
        
        self.context_manager = ContextManager(
            self.weather_analyzer,
            self.location_analyzer,
            self.temporal_analyzer
        )
        
        # Initialize components
        self.websocket_manager = WebSocketManager()
        self.session_manager = SessionManager(self.settings.database_url)
        self.file_monitor = None
        self.background_processor = None
        
        self.setup_routes()
        self.setup_static_files()
        
    def setup_routes(self):
        """Setup API routes and WebSocket endpoints"""
        
        # Include API router
        self.app.include_router(api_router, prefix="/api")
        
        # WebSocket endpoint
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.websocket_manager.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_text()
                    await self.websocket_manager.handle_message(websocket, data)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self.websocket_manager.disconnect(websocket)
        
        # Health check
        @self.app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "version": "1.0.0",
                "components": {
                    "database": "connected",
                    "file_monitor": "active" if self.file_monitor else "inactive",
                    "background_processor": "running" if self.background_processor else "stopped"
                }
            }
        
        # Root endpoint - serve main web interface
        @self.app.get("/")
        async def read_root():
            return {"message": "AI DJ System", "docs": "/docs", "api": "/api"}
    
    def setup_static_files(self):
        """Setup static file serving"""
        static_dir = Path("src/web/static")
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    async def startup(self):
        """Initialize all system components"""
        logger.info("Starting AI DJ System...")
        
        # Initialize database
        logger.info("Initializing database...")
        await init_database(self.settings.database_url)
        
        # Start file monitoring
        if self.settings.music_directories:
            logger.info(f"Starting file monitor for: {self.settings.music_directories}")
            self.file_monitor = FileMonitor(
                self.settings.music_directories,
                self.settings.database_url
            )
            self.file_monitor.start()
        
        # Start background processing
        logger.info("Starting background analysis processor...")
        self.background_processor = BackgroundProcessor(
            self.settings.database_url,
            self.settings.openai_api_key
        )
        await self.background_processor.start()
        
        logger.info("AI DJ System startup complete!")
    
    async def shutdown(self):
        """Cleanup system components"""
        logger.info("Shutting down AI DJ System...")
        
        if self.file_monitor:
            logger.info("Stopping file monitor...")
            self.file_monitor.stop()
        
        if self.background_processor:
            logger.info("Stopping background processor...")
            await self.background_processor.stop()
        
        logger.info("AI DJ System shutdown complete!")

# Global application instance
app_instance = None

def create_app():
    """Factory function to create the FastAPI application"""
    global app_instance
    app_instance = AIdjApplication()
    return app_instance.app

def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    if app_instance:
        asyncio.create_task(app_instance.shutdown())
    sys.exit(0)

async def main():
    """Main application entry point"""
    global app_instance
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Create application
    app_instance = AIdjApplication()
    
    # Startup
    await app_instance.startup()
    
    # Run server
    config = uvicorn.Config(
        app_instance.app,
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info"
    )
    
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
```

## Enhanced .env Configuration

```env
# Core Configuration
DATABASE_URL=sqlite:///ai_dj.db
OPENAI_API_KEY=your_openai_api_key_here
GENIUS_API_TOKEN=your_genius_token_here

# Music Library
MUSIC_DIRECTORIES=/path/to/music1,/path/to/music2

# TTS-WebUI Configuration
TTS_WEBUI_URL=http://localhost:7860
TTS_VOICE_MODEL=male_conversational
TTS_SPEED=1.0
TTS_PITCH=1.0
TTS_EMOTION=conversational
TTS_QUALITY=high

# Context Services
WEATHER_API_KEY=your_weather_api_key
LOCATION=Denver, CO

# Audio Streaming
ICECAST_HOST=localhost
ICECAST_PORT=8000
ICECAST_PASSWORD=your_icecast_password
STREAM_MOUNT=/ai_dj_stream

# DJ Personality
DJ_PERSONALITY=conversational
KNOWLEDGE_DEPTH=deep
TRIVIA_FREQUENCY=moderate
CONTEXT_AWARENESS=true

# Voice Scheduling (JSON format)
VOICE_SCHEDULE={"morning": "morning_energy", "afternoon": "classic_radio", "evening": "chris_in_the_morning", "late_night": "late_night_host"}

# Performance
MAX_ANALYSIS_WORKERS=3
BATCH_SIZE=50
CACHE_SIZE_MB=256
```

## Enhanced Configuration Class

```python
# src/core/config.py - Updated with TTS settings
"""
Configuration management for AI DJ System with TTS Integration
"""

import os
import json
from typing import List, Optional, Dict
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    database_url: str = Field(
        default="sqlite:///ai_dj.db",
        description="Database connection URL"
    )
    
    # API Keys
    openai_api_key: str = Field(
        description="OpenAI API key for AI analysis"
    )
    genius_api_token: Optional[str] = Field(
        default=None,
        description="Genius API token for lyrics fetching"
    )
    weather_api_key: Optional[str] = Field(
        default=None,
        description="Weather API key for contextual awareness"
    )
    
    # Location and Context
    location: str = Field(
        default="Denver, CO",
        description="Geographic location for context awareness"
    )
    
    # Music Library
    music_directories: List[str] = Field(
        default_factory=list,
        description="Comma-separated list of music directories to monitor"
    )
    
    # TTS-WebUI Configuration
    tts_webui_url: str = Field(
        default="http://localhost:7860",
        description="TTS-WebUI API endpoint"
    )
    tts_voice_model: str = Field(
        default="male_conversational",
        description="Default TTS voice model"
    )
    tts_speed: float = Field(
        default=1.0,
        description="Default speech speed multiplier"
    )
    tts_pitch: float = Field(
        default=1.0,
        description="Default speech pitch multiplier"
    )
    tts_emotion: str = Field(
        default="conversational",
        description="Default speech emotion/style"
    )
    tts_quality: str = Field(
        default="high",
        description="TTS audio quality setting"
    )
    
    # Voice Scheduling
    voice_schedule: Dict[str, str] = Field(
        default_factory=dict,
        description="Time-based voice scheduling"
    )
    
    # Audio Processing
    supported_formats: List[str] = Field(
        default=[".mp3", ".flac", ".wav", ".m4a", ".ogg"],
        description="Supported audio file formats"
    )
    
    # Streaming
    icecast_host: str = Field(default="localhost")
    icecast_port: int = Field(default=8000)
    icecast_password: str = Field(default="hackme")
    stream_mount: str = Field(default="/ai_dj_stream")
    
    # AI Configuration
    dj_personality: str = Field(
        default="conversational",
        description="DJ personality style: conversational, professional, poetic"
    )
    knowledge_depth: str = Field(
        default="deep",
        description="Knowledge depth: surface, moderate, deep"
    )
    trivia_frequency: str = Field(
        default="moderate",
        description="Trivia frequency: rare, moderate, frequent"
    )
    context_awareness: bool = Field(
        default=True,
        description="Enable contextual awareness features"
    )
    
    # Performance
    max_analysis_workers: int = Field(default=3)
    batch_size: int = Field(default=50)
    cache_size_mb: int = Field(default=256)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
        @classmethod
        def parse_env_var(cls, field_name: str, raw_val: str):
            if field_name == "music_directories":
                return [path.strip() for path in raw_val.split(",") if path.strip()]
            elif field_name == "voice_schedule":
                try:
                    return json.loads(raw_val)
                except json.JSONDecodeError:
                    return {}
            return cls.json_loads(raw_val)

# Global settings instance
settings = Settings()
```

## Docker Compose with TTS-WebUI

```yaml
# docker-compose.yml - Updated with TTS-WebUI service
version: '3.8'

services:
  ai-dj:
    build: .
    container_name: ai-dj-main
    ports:
      - "8080:8080"
    volumes:
      - ./music:/app/music:ro
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GENIUS_API_TOKEN=${GENIUS_API_TOKEN}
      - WEATHER_API_KEY=${WEATHER_API_KEY}
      - DATABASE_URL=postgresql://ai_dj_user:${DB_PASSWORD}@postgres:5432/ai_dj
      - MUSIC_DIRECTORIES=/app/music
      - TTS_WEBUI_URL=http://tts-webui:7860
      - LOCATION=${LOCATION:-Denver, CO}
      - DJ_PERSONALITY=conversational
      - KNOWLEDGE_DEPTH=deep
    depends_on:
      - postgres
      - redis
      - icecast
      - tts-webui
    restart: unless-stopped
    networks:
      - ai-dj-network

  tts-webui:
    image: rsxdalv/tts-webui:latest
    container_name: ai-dj-tts
    ports:
      - "7860:7860"
    volumes:
      - ./tts_models:/app/models
      - ./tts_config:/app/config
    environment:
      - GRADIO_SERVER_NAME=0.0.0.0
      - GRADIO_SERVER_PORT=7860
      - API_ENABLED=true
    command: ["python", "server.py", "--api"]
    restart: unless-stopped
    networks:
      - ai-dj-network
    # Optional GPU support
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

  postgres:
    image: postgres:15-alpine
    container_name: ai-dj-postgres
    environment:
      - POSTGRES_DB=ai_dj
      - POSTGRES_USER=ai_dj_user
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped
    networks:
      - ai-dj-network

  redis:
    image: redis:7-alpine
    container_name: ai-dj-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    networks:
      - ai-dj-network

  icecast:
    image: moul/icecast
    container_name: ai-dj-icecast
    ports:
      - "8000:8000"
    environment:
      - ICECAST_SOURCE_PASSWORD=${ICECAST_PASSWORD}
      - ICECAST_ADMIN_PASSWORD=${ICECAST_ADMIN_PASSWORD}
      - ICECAST_RELAY_PASSWORD=${ICECAST_RELAY_PASSWORD}
      - ICECAST_HOSTNAME=localhost
    volumes:
      - ./icecast.xml:/etc/icecast2/icecast.xml
    restart: unless-stopped
    networks:
      - ai-dj-network

volumes:
  postgres_data:
  redis_data:

networks:
  ai-dj-network:
    driver: bridge
```

Perfect! Now your AI DJ system has complete TTS-WebUI integration. Here's what this adds:

## **Complete Voice Integration Features:**

### **Adaptive Voice Personality**
- Voice changes throughout the day (energetic morning, intimate late night)
- Context-aware speech patterns (contemplative during rain, upbeat when sunny)
- Emotional expression matching the music and moment

### **Real-Time Voice Streaming**
- Queue-based commentary system for smooth playback
- Background voice generation that doesn't interrupt music
- Emergency interrupt capability for urgent commentary

### **Contextual Speech Enhancement**
- SSML-like markers for natural delivery
- Automatic emphasis on key words
- Breathing pauses for longer commentary
- Speed and pitch adjustments based on time/weather

### **TTS-WebUI Integration**
- Full API integration with your existing Chatterbox setup
- Support for multiple voice models and characters
- High-quality audio generation
- Streaming speech synthesis for real-time response

### **Smart Voice Scheduling**
- Different voice personalities for different times of day
- Automatic adaptation to context (weather, holidays, local events)
- Voice testing endpoints for configuration

Now your AI DJ can truly come alive with a voice that adapts to every moment - speaking softly during late-night hours, energetically during morning shows, and contemplatively during rainy afternoons, all while maintaining the personality and intelligence of Chris in the Morning!

The system is now complete and ready for Claude Code to build into a fully functional AI radio station with contextual intelligence and natural voice synthesis.Manager()
        self.dj_engine = VoicedDJEngine(
            self.settings.database_url,
            self.settings.openai_api_key,
            self.context_manager,
            self.tts_config
        )
        self.file_monitor = None
        self.background_processor = None
        
        self.setup_routes()
        self.setup_static_files()
        
    def setup_routes(self):
        """Setup API routes and WebSocket endpoints"""
        
        # Include API router
        self.app.include_router(api_router, prefix="/api")
        
        # WebSocket endpoint
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.websocket_manager.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_text()
                    await self.websocket_manager.handle_message(websocket, data)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self.websocket_manager.disconnect(websocket)
        
        # Health check with TTS status
        @self.app.get("/health")
        async def health_check():
            tts_status = "connected" if self.dj_engine.tts_client else "disconnected"
            return {
                "status": "healthy",
                "version": "1.0.0",
                "components": {
                    "database": "connected",
                    "file_monitor": "active" if self.file_monitor else "inactive",
                    "background_processor": "running" if self.background_processor else "stopped",
                    "tts_system": tts_status,
                    "context_manager": "active" if self.context_manager else "inactive"
                }
            }
        
        # TTS test endpoint
        @self.app.post("/api/test-voice")
        async def test_voice(text: str = "Hello, this is your AI DJ testing the voice system"):
            """Test TTS voice generation"""
            try:
                if self.dj_engine.tts_client:
                    audio_data = await self.dj_engine.tts_client.synthesize_speech(text)
                    if audio_data:
                        return {"status": "success", "audio_length": len(audio_data)}
                return {"status": "error", "message": "TTS system not available"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        
        # Root endpoint - serve main web interface
        @self.app.get("/")
        async def read_root():
            return {
                "message": "AI DJ System with Voice", 
                "docs": "/docs", 
                "api": "/api",
                "voice_enabled": self.tts_config.api_url is not None
            }
    
    def setup_static_files(self):
        """Setup static file serving"""
        static_dir = Path("src/web/static")
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    async def startup(self):
        """Initialize all system components including TTS"""
        logger.info("Starting AI DJ System with Voice...")
        
        # Initialize database
        logger.info("Initializing database...")
        await init_database(self.settings.database_url)
        
        # Initialize context monitoring
        logger.info("Starting context monitoring...")
        asyncio.create_task(self.context_manager.start_monitoring())
        
        # Initialize TTS voice system
        logger.info("Initializing TTS voice system...")
        try:
            await self.dj_engine.initialize_voice_system()
            logger.info("TTS voice system ready")
        except Exception as e:
            logger.error(f"Failed to initialize TTS system: {e}")
            logger.info("Continuing without voice synthesis...")
        
        # Start file monitoring
        if self.settings.music_directories:
            logger.info(f"Starting file monitor for: {self.settings.music_directories}")
            self.file_monitor = FileMonitor(
                self.settings.music_directories,
                self.settings.database_url
            )
            self.file_monitor.start()
        
        # Start background processing
        logger.info("Starting background analysis processor...")
        self.background_processor = BackgroundProcessor(
            self.settings.database_url,
            self.settings.openai_api_key
        )
        await self.background_processor.start()
        
        logger.info("AI DJ System startup complete!")
    
    async def shutdown(self):
        """Cleanup system components"""
        logger.info("Shutting down AI DJ System...")
        
        if self.file_monitor:
            logger.info("Stopping file monitor...")
            self.file_monitor.stop()
        
        if self.background_processor:
            logger.info("Stopping background processor...")
            await self.background_processor.stop()
        
        if self.dj_engine.tts_client:
            logger.info("Stopping TTS client...")
            await self.dj_engine.tts_client.__aexit__(None, None, None)
        
        if self.dj_engine.voice_streamer:
            logger.info("Stopping voice streamer...")
            self.dj_engine.voice_streamer.stop_streaming()
        
        logger.info("AI DJ System shutdown complete!")

# Global application instance
app_instance = NoneManager()
        self.session_manager = SessionManager(self.settings.database_url)
        self.file_monitor = None
        self.background_processor = None
        
        self.setup_routes()
        self.setup_static_files()
        
    def setup_routes(self):
        """Setup API routes and WebSocket endpoints"""
        
        # Include API router
        self.app.include_router(api_router, prefix="/api")
        
        # WebSocket endpoint
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.websocket_manager.connect(websocket)
            try:
                while True:
                    data = await websocket.receive_text()
                    await self.websocket_manager.handle_message(websocket, data)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self.websocket_manager.disconnect(websocket)
        
        # Health check
        @self.app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "version": "1.0.0",
                "components": {
                    "database": "connected",
                    "file_monitor": "active" if self.file_monitor else "inactive",
                    "background_processor": "running" if self.background_processor else "stopped"
                }
            }
        
        # Root endpoint - serve main web interface
        @self.app.get("/")
        async def read_root():
            return {"message": "AI DJ System", "docs": "/docs", "api": "/api"}
    
    def setup_static_files(self):
        """Setup static file serving"""
        static_dir = Path("src/web/static")
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    async def startup(self):
        """Initialize all system components"""
        logger.info("Starting AI DJ System...")
        
        # Initialize database
        logger.info("Initializing database...")
        await init_database(self.settings.database_url)
        
        # Start file monitoring
        if self.settings.music_directories:
            logger.info(f"Starting file monitor for: {self.settings.music_directories}")
            self.file_monitor = FileMonitor(
                self.settings.music_directories,
                self.settings.database_url
            )
            self.file_monitor.start()
        
        # Start background processing
        logger.info("Starting background analysis processor...")
        self.background_processor = BackgroundProcessor(
            self.settings.database_url,
            self.settings.openai_api_key
        )
        await self.background_processor.start()
        
        logger.info("AI DJ System startup complete!")
    
    async def shutdown(self):
        """Cleanup system components"""
        logger.info("Shutting down AI DJ System...")
        
        if self.file_monitor:
            logger.info("Stopping file monitor...")
            self.file_monitor.stop()
        
        if self.background_processor:
            logger.info("Stopping background processor...")
            await self.background_processor.stop()
        
        logger.info("AI DJ System shutdown complete!")

# Global application instance
app_instance = None

def create_app():
    """Factory function to create the FastAPI application"""
    global app_instance
    app_instance = AIdjApplication()
    return app_instance.app

def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    if app_instance:
        asyncio.create_task(app_instance.shutdown())
    sys.exit(0)

async def main():
    """Main application entry point"""
    global app_instance
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Create application
    app_instance = AIdjApplication()
    
    # Startup
    await app_instance.startup()
    
    # Run server
    config = uvicorn.Config(
        app_instance.app,
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info"
    )
    
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
```

## src/core/config.py

```python
"""
Configuration management for AI DJ System
"""

import os
from typing import List, Optional
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    database_url: str = Field(
        default="sqlite:///ai_dj.db",
        description="Database connection URL"
    )
    
    # API Keys
    openai_api_key: str = Field(
        description="OpenAI API key for AI analysis"
    )
    genius_api_token: Optional[str] = Field(
        default=None,
        description="Genius API token for lyrics fetching"
    )
    
    # Music Library
    music_directories: List[str] = Field(
        default_factory=list,
        description="Comma-separated list of music directories to monitor"
    )
    
    # Audio Processing
    supported_formats: List[str] = Field(
        default=[".mp3", ".flac", ".wav", ".m4a", ".ogg"],
        description="Supported audio file formats"
    )
    
    # Streaming
    icecast_host: str = Field(default="localhost")
    icecast_port: int = Field(default=8000)
    icecast_password: str = Field(default="hackme")
    stream_mount: str = Field(default="/ai_dj_stream")
    
    # AI Configuration
    dj_personality: str = Field(
        default="conversational",
        description="DJ personality style: conversational, professional, poetic"
    )
    knowledge_depth: str = Field(
        default="deep",
        description="Knowledge depth: surface, moderate, deep"
    )
    trivia_frequency: str = Field(
        default="moderate",
        description="Trivia frequency: rare, moderate, frequent"
    )
    
    # Performance
    max_analysis_workers: int = Field(default=3)
    batch_size: int = Field(default=50)
    cache_size_mb: int = Field(default=256)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
        @classmethod
        def parse_env_var(cls, field_name: str, raw_val: str):
            if field_name == "music_directories":
                return [path.strip() for path in raw_val.split(",") if path.strip()]
            return cls.json_loads(raw_val)

# Global settings instance
settings = Settings()
```

## src/core/database.py

```python
"""
Database models and connection management
"""

import asyncio
from datetime import datetime
from typing import Optional, List
import json

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, 
    DateTime, Boolean, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.sqlite import JSON
import sqlite3

Base = declarative_base()

class Track(Base):
    __tablename__ = "tracks"
    
    id = Column(Integer, primary_key=True)
    file_path = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, index=True)
    artist = Column(String, index=True)
    album = Column(String, index=True)
    year = Column(Integer, index=True)
    genre = Column(String, index=True)
    duration = Column(Integer)  # seconds
    file_size = Column(Integer)
    file_hash = Column(String, index=True)
    bitrate = Column(Integer)
    sample_rate = Column(Integer)
    
    # Playback statistics
    play_count = Column(Integer, default=0)
    last_played = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    analysis = relationship("TrackAnalysis", back_populates="track", uselist=False)
    connections_from = relationship("TrackConnection", foreign_keys="TrackConnection.track_id_1")
    connections_to = relationship("TrackConnection", foreign_keys="TrackConnection.track_id_2")

class Artist(Base):
    __tablename__ = "artists"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    biography = Column(Text)
    formed_year = Column(Integer)
    origin_country = Column(String)
    genres = Column(Text)  # JSON array
    wikipedia_url = Column(String)
    image_url = Column(String)
    
    # Statistics
    track_count = Column(Integer, default=0)
    play_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TrackAnalysis(Base):
    __tablename__ = "track_analysis"
    
    track_id = Column(Integer, ForeignKey("tracks.id"), primary_key=True)
    lyrics = Column(Text)
    themes = Column(Text)  # JSON array
    
    # Mood analysis
    mood_valence = Column(Float)  # -1 to 1
    energy_level = Column(Float)  # 0 to 1
    danceability = Column(Float)  # 0 to 1
    
    # Musical analysis
    key_signature = Column(String)
    tempo = Column(Integer)  # BPM
    time_signature = Column(String)
    loudness = Column(Float)  # dB
    
    # AI Analysis
    summary = Column(Text)
    cultural_context = Column(Text)
    notable_elements = Column(Text)  # JSON array
    
    analysis_date = Column(DateTime, default=datetime.utcnow)
    analysis_version = Column(String, default="1.0")
    
    # Relationships
    track = relationship("Track", back_populates="analysis")

class TrackConnection(Base):
    __tablename__ = "track_connections"
    
    id = Column(Integer, primary_key=True)
    track_id_1 = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    track_id_2 = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    connection_type = Column(String, nullable=False, index=True)  # 'thematic', 'harmonic', 'temporal', 'lyrical'
    strength = Column(Float, nullable=False, index=True)  # 0 to 1
    description = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Ensure no duplicate connections
    __table_args__ = (
        UniqueConstraint('track_id_1', 'track_id_2', 'connection_type'),
        Index('idx_track_connections_strength', 'strength'),
    )

class DJSession(Base):
    __tablename__ = "dj_sessions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    theme = Column(String, index=True)
    status = Column(String, default="created", index=True)  # created, generating, ready, playing, completed, error
    
    # Configuration
    duration_minutes = Column(Integer)
    parameters = Column(Text)  # JSON configuration
    
    # Content
    track_sequence = Column(Text)  # JSON array of track IDs
    commentary = Column(Text)  # JSON array of commentary segments
    
    # Playback
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    current_position = Column(Integer, default=0)
    
    # Statistics
    listener_count = Column(Integer, default=0)
    total_plays = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Theme(Base):
    __tablename__ = "themes"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text)
    keywords = Column(Text)  # JSON array
    
    # Mood criteria
    mood_criteria = Column(Text)  # JSON object
    genre_preferences = Column(Text)  # JSON array
    exclude_genres = Column(Text)  # JSON array
    
    # Statistics
    track_count = Column(Integer, default=0)
    session_count = Column(Integer, default=0)
    
    is_custom = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Database connection management
class DatabaseManager:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def get_session(self):
        """Get a database session"""
        return self.SessionLocal()
    
    def init_database(self):
        """Initialize database tables"""
        Base.metadata.create_all(bind=self.engine)
        
        # Create default themes
        session = self.get_session()
        try:
            self._create_default_themes(session)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def _create_default_themes(self, session):
        """Create default theme categories"""
        default_themes = [
            {
                "name": "love",
                "description": "Songs about romantic love, relationships, and heartbreak",
                "keywords": ["love", "romance", "heart", "relationship", "dating", "heartbreak"],
                "mood_criteria": {"valence": [-1.0, 1.0], "energy": [0.0, 1.0]}
            },
            {
                "name": "upbeat",
                "description": "High-energy, positive songs perfect for motivation",
                "keywords": ["happy", "energetic", "dance", "party", "celebration"],
                "mood_criteria": {"valence": [0.3, 1.0], "energy": [0.6, 1.0]}
            },
            {
                "name": "relaxing",
                "description": "Calm, soothing music for relaxation and unwinding",
                "keywords": ["calm", "peaceful", "chill", "relaxing", "ambient"],
                "mood_criteria": {"valence": [-0.2, 0.8], "energy": [0.0, 0.5]}
            },
            {
                "name": "nostalgic",
                "description": "Songs that evoke memories and contemplation of the past",
                "keywords": ["memory", "past", "childhood", "nostalgia", "remember"],
                "mood_criteria": {"valence": [-0.5, 0.5], "energy": [0.2, 0.7]}
            },
            {
                "name": "driving",
                "description": "Perfect road trip and driving music",
                "keywords": ["road", "highway", "journey", "travel", "freedom"],
                "mood_criteria": {"valence": [-0.2, 0.8], "energy": [0.4, 0.9]}
            }
        ]
        
        for theme_data in default_themes:
            existing = session.query(Theme).filter_by(name=theme_data["name"]).first()
            if not existing:
                theme = Theme(
                    name=theme_data["name"],
                    description=theme_data["description"],
                    keywords=json.dumps(theme_data["keywords"]),
                    mood_criteria=json.dumps(theme_data["mood_criteria"]),
                    is_custom=False
                )
                session.add(theme)

# Global database manager instance
db_manager = None

async def init_database(database_url: str):
    """Initialize the database"""
    global db_manager
    db_manager = DatabaseManager(database_url)
    db_manager.init_database()
    return db_manager

def get_db():
    """Dependency to get database session"""
    return db_manager.get_session()
```

## src/core/file_monitor.py

```python
"""
File system monitoring for automatic music library updates
"""

import os
import time
import hashlib
import logging
from pathlib import Path
from typing import List, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from mutagen import File as MutagenFile
from sqlalchemy.orm import Session

from .database import get_db, Track
from .config import settings

logger = logging.getLogger(__name__)

class MusicFileHandler(FileSystemEventHandler):
    """Handle file system events for music files"""
    
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.audio_extensions = set(settings.supported_formats)
        self.processing_queue = set()
        
    def on_created(self, event):
        """Handle new file creation"""
        if not event.is_directory and self.is_audio_file(event.src_path):
            logger.info(f"New audio file detected: {event.src_path}")
            self.process_audio_file(event.src_path)
    
    def on_modified(self, event):
        """Handle file modification"""
        if not event.is_directory and self.is_audio_file(event.src_path):
            # Avoid processing the same file multiple times rapidly
            if event.src_path not in self.processing_queue:
                logger.info(f"Audio file modified: {event.src_path}")
                self.process_audio_file(event.src_path)
    
    def on_deleted(self, event):
        """Handle file deletion"""
        if not event.is_directory and self.is_audio_file(event.src_path):
            logger.info(f"Audio file deleted: {event.src_path}")
            self.remove_track_from_db(event.src_path)
    
    def is_audio_file(self, file_path: str) -> bool:
        """Check if file is a supported audio format"""
        return Path(file_path).suffix.lower() in self.audio_extensions
    
    def process_audio_file(self, file_path: str):
        """Process a single audio file"""
        try:
            self.processing_queue.add(file_path)
            
            # Wait a moment for file to be fully written
            time.sleep(0.5)
            
            if not os.path.exists(file_path):
                logger.warning(f"File disappeared during processing: {file_path}")
                return
            
            # Extract metadata
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                logger.warning(f"Could not read audio metadata: {file_path}")
                return
            
            # Calculate file hash for duplicate detection
            file_hash = self.calculate_file_hash(file_path)
            
            # Store in database
            track_id = self.store_track_metadata(file_path, audio_file, file_hash)
            
            if track_id:
                logger.info(f"Successfully processed track {track_id}: {file_path}")
                # Queue for AI analysis (would be handled by background processor)
                # self.queue_for_analysis(track_id)
            
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
        finally:
            self.processing_queue.discard(file_path)
    
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of file for duplicate detection"""
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return ""
    
    def store_track_metadata(self, file_path: str, audio_file, file_hash: str) -> int:
        """Store track metadata in database"""
        session = self.db_session_factory()
        try:
            # Check if track already exists
            existing_track = session.query(Track).filter_by(file_path=file_path).first()
            
            # Extract metadata with fallbacks
            metadata = self.extract_metadata(audio_file)
            
            if existing_track:
                # Update existing track
                for key, value in metadata.items():
                    setattr(existing_track, key, value)
                existing_track.file_hash = file_hash
                existing_track.file_size = os.path.getsize(file_path)
                track_id = existing_track.id
            else:
                # Create new track
                track = Track(
                    file_path=file_path,
                    file_hash=file_hash,
                    file_size=os.path.getsize(file_path),
                    **metadata
                )
                session.add(track)
                session.flush()  # Get the ID
                track_id = track.id
            
            session.commit()
            return track_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Database error storing track {file_path}: {e}")
            return None
        finally:
            session.close()
    
    def extract_metadata(self, audio_file) -> dict:
        """Extract metadata from audio file"""
        # Different audio formats store metadata differently
        # This handles the most common formats
        
        def safe_get(key_variants, default="Unknown"):
            for key in key_variants:
                if key in audio_file:
                    value = audio_file[key]
                    if isinstance(value, list) and value:
                        return str(value[0])
                    elif value:
                        return str(value)
            return default
        
        # Extract basic metadata
        title = safe_get(['TIT2', 'TITLE', '\xa9nam'])
        artist = safe_get(['TPE1', 'ARTIST', '\xa9ART'])
        album = safe_get(['TALB', 'ALBUM', '\xa9alb'])
        genre = safe_get(['TCON', 'GENRE', '\xa9gen'])
        
        # Extract year
        year = safe_get(['TDRC', 'DATE', '\xa9day'])
        try:
            if year and year != "Unknown":
                year = int(str(year)[:4])  # Extract just the year part
        except (ValueError, TypeError):
            year = None
        
        # Extract audio properties
        duration = 0
        bitrate = 0
        sample_rate = 0
        
        if hasattr(audio_file, 'info') and audio_file.info:
            duration = int(getattr(audio_file.info, 'length', 0))
            bitrate = int(getattr(audio_file.info, 'bitrate', 0))
            sample_rate = int(getattr(audio_file.info, 'sample_rate', 0))
        
        return {
            'title': title,
            'artist': artist,
            'album': album,
            'year': year,
            'genre': genre,
            'duration': duration,
            'bitrate': bitrate,
            'sample_rate': sample_rate
        }
    
    def remove_track_from_db(self, file_path: str):
        """Remove track from database when file is deleted"""
        session = self.db_session_factory()
        try:
            track = session.query(Track).filter_by(file_path=file_path).first()
            if track:
                session.delete(track)
                session.commit()
                logger.info(f"Removed track from database: {file_path}")
        except Exception as e:
            session.rollback()
            logger.error(f"Error removing track from database: {e}")
        finally:
            session.close()

class FileMonitor:
    """Main file monitoring system"""
    
    def __init__(self, directories: List[str], database_url: str):
        self.directories = directories
        self.database_url = database_url
        self.observer = Observer()
        self.handler = MusicFileHandler(get_db)
        self.is_running = False
        
    def start(self):
        """Start monitoring specified directories"""
        if self.is_running:
            logger.warning("File monitor is already running")
            return
        
        # Add watches for each directory
        for directory in self.directories:
            if os.path.exists(directory):
                self.observer.schedule(
                    self.handler, 
                    directory, 
                    recursive=True
                )
                logger.info(f"Started monitoring: {directory}")
            else:
                logger.warning(f"Directory does not exist: {directory}")
        
        self.observer.start()
        self.is_running = True
        logger.info("File monitor started successfully")
    
    def stop(self):
        """Stop file monitoring"""
        if not self.is_running:
            return
        
        self.observer.stop()
        self.observer.join()
        self.is_running = False
        logger.info("File monitor stopped")
    
    def initial_scan(self):
        """Perform initial scan of all directories"""
        logger.info("Starting initial library scan...")
        
        total_files = 0
        processed_files = 0
        
        for directory in self.directories:
            if not os.path.exists(directory):
                logger.warning(f"Skipping non-existent directory: {directory}")
                continue
            
            logger.info(f"Scanning directory: {directory}")
            
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    total_files += 1
                    
                    if self.handler.is_audio_file(file_path):
                        try:
                            self.handler.process_audio_file(file_path)
                            processed_files += 1
                            
                            if processed_files % 100 == 0:
                                logger.info(f"Processed {processed_files} audio files...")
                                
                        except Exception as e:
                            logger.error(f"Error processing {file_path}: {e}")
        
        logger.info(f"Initial scan complete: {processed_files} audio files processed out of {total_files} total files")
```

This comprehensive set of implementation files provides a solid foundation for building the AI DJ system. The code includes:

1. **Main application entry point** with proper async handling and graceful shutdown
2. **Configuration management** using Pydantic for type safety and environment variable loading
3. **Database models** with SQLAlchemy for all the core data structures
4. **File monitoring system** that watches for changes and automatically processes new music files

These files give Claude Code everything needed to start building the core infrastructure, with clear extension points for adding the AI analysis, DJ commentary generation, and streaming components in subsequent development phases.