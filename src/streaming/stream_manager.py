"""
Stream Manager for Radio Free Luna
Manages streaming sessions and coordinates with audio server
"""

import asyncio
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime
import uuid

from .audio_server import BasicAudioServer, StreamingSession

logger = logging.getLogger(__name__)


class StreamManager:
    """
    Manages audio streaming sessions for Radio Free Luna.
    
    Coordinates between session creation, audio server, and client connections.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8000, mount: str = "/ai_dj_stream", password: str = None):
        if not password:
            raise ValueError("Icecast password is required for StreamManager initialization")
        self.audio_server = BasicAudioServer(host, port, mount, password=password)
        self.active_sessions: Dict[str, StreamingSession] = {}
        self.current_session_id: Optional[str] = None
        self.is_initialized = False
        
    async def initialize(self) -> bool:
        """Initialize the stream manager and audio server."""
        try:
            logger.info("Initializing Stream Manager...")
            
            # Start the audio server
            success = await self.audio_server.start_server()
            if not success:
                logger.error("Failed to start audio server")
                return False
            
            self.is_initialized = True
            logger.info("✅ Stream Manager initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Stream Manager: {e}")
            return False
    
    async def shutdown(self):
        """Shutdown the stream manager and cleanup resources."""
        logger.info("Shutting down Stream Manager...")
        
        # Stop all active sessions
        for session_id in list(self.active_sessions.keys()):
            await self.stop_session(session_id)
        
        # Stop the audio server
        await self.audio_server.stop_server()
        
        self.is_initialized = False
        logger.info("Stream Manager shutdown complete")
    
    async def start_session_stream(self, session_data: Dict[str, Any]) -> Optional[str]:
        """
        Start streaming a DJ session.
        
        Args:
            session_data: Complete session data including tracks and commentary
            
        Returns:
            Optional[str]: Session ID if successful, None otherwise
        """
        try:
            if not self.is_initialized:
                logger.error("Stream Manager not initialized")
                return None
            
            session_id = session_data.get('session_id', str(uuid.uuid4()))
            
            logger.info(f"Starting stream for session: {session_id}")
            
            # Stop current session if running
            if self.current_session_id:
                await self.stop_session(self.current_session_id)
            
            # Create streaming session
            streaming_session = StreamingSession(session_id, session_data)
            self.active_sessions[session_id] = streaming_session
            self.current_session_id = session_id
            
            # Start streaming the session
            success = await self.audio_server.stream_session(session_data)
            if not success:
                logger.error(f"Failed to start streaming session {session_id}")
                await self.stop_session(session_id)
                return None
            
            logger.info(f"✅ Successfully started streaming session: {session_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Error starting session stream: {e}")
            return None
    
    async def stop_session(self, session_id: str) -> bool:
        """
        Stop a streaming session.
        
        Args:
            session_id: ID of the session to stop
            
        Returns:
            bool: True if successful
        """
        try:
            if session_id not in self.active_sessions:
                logger.warning(f"Session {session_id} not found in active sessions")
                return False
            
            logger.info(f"Stopping streaming session: {session_id}")
            
            # Remove from active sessions
            del self.active_sessions[session_id]
            
            # Clear current session if it's this one
            if self.current_session_id == session_id:
                self.current_session_id = None
            
            # TODO: Implement actual session stopping in audio server
            logger.info(f"✅ Successfully stopped session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping session: {e}")
            return False
    
    async def pause_current_session(self) -> bool:
        """Pause the currently streaming session."""
        try:
            if not self.current_session_id:
                logger.warning("No current session to pause")
                return False
            
            session = self.active_sessions.get(self.current_session_id)
            if not session:
                logger.error("Current session not found in active sessions")
                return False
            
            session.is_paused = True
            success = await self.audio_server.pause_stream()
            
            if success:
                logger.info(f"Paused session: {self.current_session_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error pausing current session: {e}")
            return False
    
    async def resume_current_session(self) -> bool:
        """Resume the currently paused session."""
        try:
            if not self.current_session_id:
                logger.warning("No current session to resume")
                return False
            
            session = self.active_sessions.get(self.current_session_id)
            if not session:
                logger.error("Current session not found in active sessions")
                return False
            
            session.is_paused = False
            success = await self.audio_server.resume_stream()
            
            if success:
                logger.info(f"Resumed session: {self.current_session_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error resuming current session: {e}")
            return False
    
    async def skip_track(self) -> bool:
        """Skip to the next track in the current session."""
        try:
            if not self.current_session_id:
                logger.warning("No current session for track skip")
                return False
            
            session = self.active_sessions.get(self.current_session_id)
            if not session:
                logger.error("Current session not found for track skip")
                return False
            
            # Update session track index
            tracks = session.session_data.get('tracks', [])
            if session.current_track_index < len(tracks) - 1:
                session.current_track_index += 1
                logger.info(f"Skipped to track {session.current_track_index + 1} of {len(tracks)}")
            else:
                logger.info("Already at last track")
            
            # Skip in audio server
            return await self.audio_server.skip_current_track()
            
        except Exception as e:
            logger.error(f"Error skipping track: {e}")
            return False
    
    def get_current_session_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the currently streaming session."""
        if not self.current_session_id:
            return None
        
        session = self.active_sessions.get(self.current_session_id)
        if not session:
            return None
        
        session_progress = session.get_session_progress()
        stream_info = self.audio_server.get_stream_info()
        
        return {
            **session_progress,
            "stream_info": stream_info,
            "session_theme": session.session_data.get('theme', 'unknown'),
            "total_duration": session.session_data.get('estimated_duration', 0)
        }
    
    def get_all_sessions_info(self) -> List[Dict[str, Any]]:
        """Get information about all active sessions."""
        sessions_info = []
        
        for session_id, session in self.active_sessions.items():
            session_info = {
                "session_id": session_id,
                "is_current": session_id == self.current_session_id,
                **session.get_session_progress()
            }
            sessions_info.append(session_info)
        
        return sessions_info
    
    def get_stream_status(self) -> Dict[str, Any]:
        """Get overall streaming status."""
        return {
            "is_initialized": self.is_initialized,
            "is_streaming": self.audio_server.is_streaming,
            "current_session_id": self.current_session_id,
            "active_sessions_count": len(self.active_sessions),
            "stream_info": self.audio_server.get_stream_info(),
            "current_session": self.get_current_session_info()
        }
    
    async def create_and_stream_session(self, session_manager, theme: str, duration_minutes: int, context: Dict[str, Any]) -> Optional[str]:
        """
        Create a new DJ session and immediately start streaming it.
        
        Args:
            session_manager: The DJ session manager instance
            theme: Theme for the session
            duration_minutes: Duration in minutes
            context: Current context information
            
        Returns:
            Optional[str]: Session ID if successful
        """
        try:
            logger.info(f"Creating and streaming session with theme: {theme}")
            
            # Create the session using the session manager
            session = await session_manager.create_session(
                theme=theme,
                duration_minutes=duration_minutes,
                context=context
            )
            
            if not session:
                logger.error("Failed to create session")
                return None
            
            # Convert session to streaming format
            session_data = {
                "session_id": session.session_id,
                "theme": session.theme,
                "tracks": [{"track": track.track} for track in session.tracks] if hasattr(session, 'tracks') else [],
                "commentary": session.commentary if hasattr(session, 'commentary') else [],
                "estimated_duration": sum(track.track.get("duration", 0) for track in session.tracks) if hasattr(session, 'tracks') else 0,
                "context": context
            }
            
            # Start streaming
            stream_session_id = await self.start_session_stream(session_data)
            
            if stream_session_id:
                logger.info(f"✅ Successfully created and started streaming session: {stream_session_id}")
            else:
                logger.error("Failed to start streaming session")
            
            return stream_session_id
            
        except Exception as e:
            logger.error(f"Error creating and streaming session: {e}")
            return None