#!/usr/bin/env python3
"""
AI DJ System - Radio Free Luna
Main Application Entry Point with TTS Integration and Contextual Awareness
"""

import asyncio
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import List

from fastapi import FastAPI, WebSocket, Request, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
import uvicorn

# Import our modules
from src.core.config import settings
from src.core.database import init_database
from src.core.file_monitor import FileMonitor
from src.analysis.ai_analyzer import MusicAnalysisEngine
from src.analysis.lyrics_fetcher import LyricsFetcher
from src.dj.session_manager import SessionManager
from src.dj.commentary_generator import DJCommentaryGenerator
from src.voice.tts_config import TTSConfig
from src.voice.tts_client import TTSWebUIClient
from src.voice.contextual_voice import ContextualVoiceAdapter
from src.context.context_manager import ContextManager
from src.context.temporal import TemporalAnalyzer
from src.context.weather import WeatherAnalyzer
from src.context.location import LocationAnalyzer
from src.streaming.stream_manager import StreamManager
from src.models import (
    SessionRequest, TestVoiceRequest, CommentaryRequest,
    ValidationError, ValidationHelpers
)

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

class RadioFreeLuna:
    def __init__(self):
        self.app = FastAPI(
            title="Radio Free Luna - AI DJ System",
            description="Intelligent music streaming with AI-powered contextual DJ commentary and voice synthesis",
            version="1.0.0"
        )
        
        # Initialize TTS configuration
        self.tts_config = TTSConfig(
            api_url=settings.tts_webui_url,
            voice_model=settings.tts_voice_model,
            speed=settings.tts_speed,
            quality=settings.tts_quality
        )
        
        # Initialize context analyzers
        self.temporal_analyzer = TemporalAnalyzer()
        self.weather_analyzer = WeatherAnalyzer(
            api_key=settings.weather_api_key,
            location=settings.location
        )
        self.location_analyzer = LocationAnalyzer(
            location=settings.location
        )
        
        # Initialize context manager
        self.context_manager = ContextManager(
            self.weather_analyzer,
            self.location_analyzer,
            self.temporal_analyzer
        )
        
        # Initialize core systems
        self.music_analyzer = None
        self.session_manager = None
        self.commentary_generator = None
        self.tts_client = None
        self.voice_adapter = None
        self.file_monitor = None
        self.stream_manager = None

        # Track background tasks for proper cleanup
        self.background_tasks: List[asyncio.Task] = []

        self.setup_routes()
        self.setup_static_files()
        
    def setup_routes(self):
        """Setup API routes and WebSocket endpoints"""
        
        # Health check
        @self.app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "version": "1.0.0",
                "system": "Radio Free Luna",
                "components": {
                    "database": "connected",
                    "context_manager": "active" if self.context_manager else "inactive",
                    "tts_system": "connected" if self.tts_client else "disconnected",
                    "file_monitor": "active" if self.file_monitor and self.file_monitor.is_running else "inactive",
                    "stream_manager": "active" if self.stream_manager and self.stream_manager.is_initialized else "inactive"
                }
            }
        
        # System status
        @self.app.get("/status")
        async def system_status():
            context = self.context_manager.get_current_context()
            
            return {
                "system": "Radio Free Luna",
                "status": "operational",
                "context": {
                    "description": self.context_manager.generate_context_description(),
                    "themes": self.context_manager.get_contextual_themes(),
                    "last_update": context.get("updated_at").isoformat() if context and context.get("updated_at") else None
                },
                "music_library": {
                    "monitoring": self.file_monitor.is_running if self.file_monitor else False,
                    "directories": settings.music_directories
                },
                "ai_systems": {
                    "analysis_engine": bool(self.music_analyzer),
                    "commentary_generator": bool(self.commentary_generator),
                    "voice_synthesis": bool(self.tts_client)
                },
                "streaming": {
                    "stream_manager": bool(self.stream_manager),
                    "is_streaming": self.stream_manager.audio_server.is_streaming if self.stream_manager else False,
                    "current_session": self.stream_manager.current_session_id if self.stream_manager else None
                }
            }
        
        # Test TTS voice
        @self.app.post("/api/test-voice")
        async def test_voice(text: str = Body(..., description="Text to synthesize (max 1000 chars)")):
            """Test TTS voice generation

            Request body should be the text string to synthesize.

            Returns:
                JSON with synthesis status and audio length
            """
            try:
                # Validate request
                request = TestVoiceRequest(text=text)

                if self.tts_client:
                    audio_data = await self.tts_client.synthesize_speech(request.text)
                    if audio_data:
                        return {
                            "status": "success",
                            "message": "Voice synthesis working",
                            "audio_length": len(audio_data)
                        }
                return {"status": "error", "message": "TTS system not available"}
            except ValidationError as e:
                return {"error": "Validation Failed", "detail": str(e), "status_code": 422}
            except Exception as e:
                logger.error(f"Voice synthesis error: {e}")
                return {"status": "error", "message": str(e)}
        
        # Create a themed session
        @self.app.post("/api/sessions")
        async def create_session(
            theme: str = Body(..., description="Music theme (e.g., 'rainy_day', 'upbeat', 'jazz')"),
            duration_minutes: int = Body(60, description="Session length in minutes (5-480)"),
            start_streaming: bool = Body(False, description="Whether to start audio streaming")
        ):
            """Create a new themed DJ session with optional streaming

            Returns:
                JSON with session details and track list
            """
            try:
                # Validate request
                request = SessionRequest(theme=theme, duration_minutes=duration_minutes)

                if not self.session_manager:
                    return {"error": "Session manager not initialized"}

                context = self.context_manager.get_current_context()
                if not context:
                    return {"error": "Context not available"}

                session = await self.session_manager.create_session(
                    theme=request.theme,
                    duration_minutes=request.duration_minutes,
                    context=context
                )
                
                result = {
                    "session_id": session.session_id,
                    "theme": session.theme,
                    "status": session.status,
                    "track_count": len(session.tracks),
                    "estimated_duration": sum(track.track["duration"] for track in session.tracks),
                    "context": self.context_manager.generate_context_description()
                }
                
                # Start streaming if requested
                if start_streaming and self.stream_manager:
                    stream_session_id = await self.stream_manager.create_and_stream_session(
                        self.session_manager, theme, duration_minutes, context
                    )
                    if stream_session_id:
                        result["streaming"] = True
                        result["stream_session_id"] = stream_session_id
                        result["stream_info"] = self.stream_manager.get_stream_status()
                    else:
                        result["streaming"] = False
                        result["stream_error"] = "Failed to start streaming"
                
                return result

            except ValidationError as e:
                logger.warning(f"Session creation validation error: {e}")
                return {"error": "Validation Failed", "detail": str(e), "status_code": 422}
            except Exception as e:
                logger.error(f"Failed to create session: {e}")
                return {"error": str(e)}
        
        # Generate contextual commentary
        @self.app.post("/api/commentary")
        async def generate_commentary(text_type: str = Body("contextual", description="Type of commentary (contextual, opening, transition, closing)")):
            """Generate contextual DJ commentary

            Returns:
                JSON with generated commentary and duration estimate
            """
            try:
                # Validate request
                request = CommentaryRequest(text_type=text_type)

                if not self.commentary_generator:
                    return {"error": "Commentary generator not initialized"}

                context = self.context_manager.get_current_context()
                if not context:
                    return {"error": "Context not available"}

                if request.text_type == "contextual":
                    commentary = await self.commentary_generator.generate_contextual_interlude(
                        context, "time_transition"
                    )
                else:
                    # Opening commentary
                    commentary = await self.commentary_generator.generate_opening_commentary(
                        "ambient", None, context
                    )

                if commentary:
                    return {
                        "content": commentary.content,
                        "type": commentary.type,
                        "duration_estimate": commentary.duration_estimate,
                        "context": self.context_manager.generate_context_description()
                    }

                return {"error": "Could not generate commentary"}

            except ValidationError as e:
                logger.warning(f"Commentary validation error: {e}")
                return {"error": "Validation Failed", "detail": str(e), "status_code": 422}
            except Exception as e:
                logger.error(f"Failed to generate commentary: {e}")
                return {"error": str(e)}
        
        # Get current context
        @self.app.get("/api/context")
        async def get_context():
            """Get current contextual information"""
            context = self.context_manager.get_current_context()
            
            if not context:
                return {"error": "Context not available"}
            
            return {
                "description": self.context_manager.generate_context_description(),
                "themes": self.context_manager.get_contextual_themes(),
                "music_guidance": self.context_manager.get_contextual_music_guidance(),
                "updated_at": context.get("updated_at").isoformat() if context.get("updated_at") else None
            }
        
        # Root endpoint - serve web interface
        @self.app.get("/")
        async def read_root():
            """Serve the main web interface"""
            index_file = Path("src/web/static/index.html")
            if index_file.exists():
                return FileResponse(str(index_file))
            else:
                # Fallback to JSON response if HTML file doesn't exist
                return {
                    "message": "Radio Free Luna - AI DJ System",
                    "tagline": "Where every song tells a story, and context creates the perfect moment",
                    "docs": "/docs",
                    "api": "/api",
                    "voice_enabled": bool(self.tts_client),
                    "context_aware": bool(self.context_manager),
                    "note": "Web interface not available - HTML files missing"
                }
        
        # API info endpoint for programmatic access
        @self.app.get("/api")
        async def api_info():
            return {
                "message": "Radio Free Luna - AI DJ System API",
                "tagline": "Where every song tells a story, and context creates the perfect moment",
                "docs": "/docs",
                "voice_enabled": bool(self.tts_client),
                "context_aware": bool(self.context_manager),
                "endpoints": {
                    "health": "/health",
                    "status": "/status", 
                    "context": "/api/context",
                    "sessions": "/api/sessions",
                    "commentary": "/api/commentary",
                    "test_voice": "/api/test-voice",
                    "streaming_status": "/api/streaming/status",
                    "streaming_start": "/api/streaming/start",
                    "streaming_stop": "/api/streaming/stop",
                    "streaming_pause": "/api/streaming/pause",
                    "streaming_resume": "/api/streaming/resume",
                    "streaming_skip": "/api/streaming/skip"
                }
            }
    
    def setup_static_files(self):
        """Setup static file serving"""
        static_dir = Path("src/web/static")
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    async def startup(self):
        """Initialize all system components"""
        logger.info("🎵 Starting Radio Free Luna - AI DJ System...")
        
        # Initialize database
        logger.info("📊 Initializing database...")
        await init_database(settings.database_url)
        
        # Initialize AI systems
        logger.info("🧠 Initializing AI analysis systems...")
        self.music_analyzer = MusicAnalysisEngine(settings.openai_api_key)
        self.session_manager = SessionManager(settings.database_url, settings.openai_api_key)
        self.commentary_generator = DJCommentaryGenerator(settings.openai_api_key)
        
        # Initialize context monitoring
        logger.info("🌍 Starting contextual awareness monitoring...")
        await self.context_manager.update_context()  # Initial context update

        # Create monitoring task with proper exception handling
        context_task = asyncio.create_task(self.context_manager.start_monitoring())
        self.background_tasks.append(context_task)

        def _handle_context_task_exception(task: asyncio.Task):
            """Handle exceptions from background context monitoring task"""
            try:
                task.result()
            except asyncio.CancelledError:
                logger.info("Context monitoring task cancelled")
            except Exception as e:
                logger.error(f"Context monitoring task failed: {e}", exc_info=True)

        context_task.add_done_callback(_handle_context_task_exception)
        
        # Initialize TTS voice system
        logger.info("🎤 Initializing voice synthesis system...")
        try:
            self.tts_client = TTSWebUIClient(self.tts_config)
            await self.tts_client.initialize()

            # Test TTS connection
            if await self.tts_client.test_connection():
                logger.info("✅ TTS voice system ready")
                self.voice_adapter = ContextualVoiceAdapter(self.tts_client)
            else:
                logger.warning("⚠️  TTS-WebUI not available, continuing without voice synthesis")
                await self.tts_client.shutdown()
                self.tts_client = None
        except Exception as e:
            logger.error(f"❌ Failed to initialize TTS system: {e}")
            logger.info("Continuing without voice synthesis...")
            self.tts_client = None
        
        # Start file monitoring
        if settings.music_directories:
            logger.info(f"📁 Starting file monitoring for: {settings.music_directories}")
            self.file_monitor = FileMonitor(
                settings.music_directories,
                settings.database_url
            )
            
            # Perform initial scan
            logger.info("🔍 Performing initial library scan...")
            self.file_monitor.initial_scan()
            
            # Start monitoring
            self.file_monitor.start()
        else:
            logger.warning("⚠️  No music directories configured")
        
        # Initialize streaming system
        logger.info("🎵 Initializing audio streaming system...")
        self.stream_manager = StreamManager(
            host=settings.icecast_host,
            port=settings.icecast_port,
            mount=settings.stream_mount,
            password=settings.icecast_password  # Validated by Pydantic config
        )
        
        try:
            await self.stream_manager.initialize()
            logger.info("✅ Audio streaming system ready")
        except Exception as e:
            logger.error(f"❌ Failed to initialize streaming system: {e}")
            logger.info("Continuing without streaming capabilities...")
            self.stream_manager = None
        
        logger.info("🎉 Radio Free Luna startup complete!")
        logger.info("🎯 The AI DJ is now aware of context and ready to create perfect musical moments")
        
        if self.stream_manager:
            logger.info(f"📻 Streaming available at: http://{settings.icecast_host}:{settings.icecast_port}{settings.stream_mount}")
        else:
            logger.info("📻 Streaming not available - check configuration")
    
    async def shutdown(self):
        """Cleanup system components"""
        logger.info("🛑 Shutting down Radio Free Luna...")

        # Cancel all background tasks gracefully
        if self.background_tasks:
            logger.info(f"Cancelling {len(self.background_tasks)} background tasks...")
            for task in self.background_tasks:
                if not task.done():
                    task.cancel()

            # Wait for cancellation with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.background_tasks, return_exceptions=True),
                    timeout=5.0
                )
                logger.info("All background tasks cancelled")
            except asyncio.TimeoutError:
                logger.warning("Some background tasks did not complete within timeout")

        if self.file_monitor:
            logger.info("📁 Stopping file monitor...")
            self.file_monitor.stop()
        
        if self.context_manager:
            logger.info("🌍 Stopping context monitoring...")
            await self.context_manager.stop_monitoring()
        
        if self.tts_client:
            logger.info("🎤 Stopping TTS client...")
            await self.tts_client.shutdown()
        
        if self.stream_manager:
            logger.info("📻 Stopping streaming system...")
            await self.stream_manager.shutdown()
        
        logger.info("👋 Radio Free Luna shutdown complete!")

# Global application instance with thread-safe access
_app_lock = threading.Lock()
app_instance = None


def create_app():
    """Factory function to create the FastAPI application (thread-safe)"""
    global app_instance
    with _app_lock:
        if app_instance is None:
            app_instance = RadioFreeLuna()
        return app_instance.app


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully (thread-safe)"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    global app_instance

    with _app_lock:
        if app_instance:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(app_instance.shutdown())
            except RuntimeError:
                # No event loop running - this is in signal handler context
                logger.warning("Could not schedule async shutdown (no event loop)")
        else:
            logger.warning("App instance not initialized")

    # Don't exit immediately - let the app finish gracefully
    # The uvicorn server will handle the actual shutdown

async def main():
    """Main application entry point"""
    global app_instance
    
    # Setup signal handlers (must be before creating app_instance so shutdown handler can access it)
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Create application (thread-safe)
    with _app_lock:
        app_instance = RadioFreeLuna()
        app_ref = app_instance

    # Startup
    await app_ref.startup()
    
    # Run server
    config = uvicorn.Config(
        app_ref.app,
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info"
    )

    server = uvicorn.Server(config)

    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await app_ref.shutdown()

if __name__ == "__main__":
    asyncio.run(main())