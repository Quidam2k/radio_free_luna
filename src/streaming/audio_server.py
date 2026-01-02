"""
Audio Server for Radio Free Luna
Handles streaming audio to clients with Icecast2 integration and fallback to mock mode
"""

import asyncio
import logging
import threading
import queue
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
import io

try:
    from pydub import AudioSegment
    from pydub.playback import play
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False
    AudioSegment = None

from .icecast_client import EnhancedAudioServer

logger = logging.getLogger(__name__)


class BasicAudioServer:
    """
    Basic audio server for streaming music sessions.
    
    This is a simplified implementation that demonstrates the streaming concept.
    For production use, this should be replaced with proper Icecast2 integration.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8000, mount: str = "/ai_dj_stream", password: str = None):
        self.host = host
        self.port = port
        self.mount = mount
        self.password = password
        self.is_streaming = False
        self.current_session = None
        self.audio_queue = queue.Queue()
        self.clients = []
        self.stream_thread = None

        # Audio settings
        self.sample_rate = 44100
        self.channels = 2
        self.bit_depth = 16

        # Enhanced streaming integration
        self.enhanced_server = None
        self.mock_mode = False  # Will auto-detect and fallback to mock if needed

        # Validate password is provided
        if not password:
            logger.error("❌ Audio server password is required and must be configured via ICECAST_PASSWORD environment variable")
            raise ValueError("Icecast password must be provided and validated via configuration")
        
    async def start_server(self) -> bool:
        """Start the audio streaming server with enhanced capabilities."""
        try:
            logger.info(f"Starting audio server on {self.host}:{self.port}{self.mount}")
            
            # Try to initialize enhanced server first
            self.enhanced_server = EnhancedAudioServer(
                host=self.host,
                port=self.port,
                mount=self.mount,
                password=self.password  # Already validated in __init__
            )
            
            # Attempt to start enhanced server
            if await self.enhanced_server.start_server():
                self.is_streaming = True
                logger.info("✅ Audio server started with enhanced Icecast2 streaming")
                return True
            else:
                # Fallback to basic mock mode
                logger.warning("Enhanced server failed, falling back to basic mode")
                return await self._start_basic_mode()
            
        except Exception as e:
            logger.error(f"Failed to start enhanced server: {e}")
            return await self._start_basic_mode()
    
    async def _start_basic_mode(self) -> bool:
        """Fallback to basic/mock streaming mode."""
        try:
            logger.info("Starting in basic/mock streaming mode")
            self.mock_mode = True
            self.is_streaming = True
            self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
            self.stream_thread.start()
            
            logger.info("✅ Audio server started in basic mode")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start basic audio server: {e}")
            return False
    
    async def stop_server(self):
        """Stop the audio streaming server."""
        logger.info("Stopping audio server...")
        self.is_streaming = False
        
        # Stop enhanced server if running
        if self.enhanced_server:
            await self.enhanced_server.stop_server()
            self.enhanced_server = None
        
        # Stop basic streaming thread if running
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=5)
        
        logger.info("Audio server stopped")
    
    def _stream_loop(self):
        """Main streaming loop (runs in separate thread)."""
        logger.info("Audio streaming loop started")
        
        while self.is_streaming:
            try:
                # Get next audio chunk from queue
                try:
                    audio_data = self.audio_queue.get(timeout=1.0)
                    
                    if audio_data is None:  # Shutdown signal
                        break
                    
                    # In real implementation, this would send to Icecast
                    self._send_to_clients(audio_data)
                    
                except queue.Empty:
                    # No audio data available, send silence or continue
                    continue
                    
            except Exception as e:
                logger.error(f"Error in streaming loop: {e}")
                time.sleep(1)
        
        logger.info("Audio streaming loop ended")
    
    def _send_to_clients(self, audio_data: bytes):
        """Send audio data to connected clients (mock implementation)."""
        if self.mock_mode:
            # Just log that we would send data
            logger.debug(f"Would send {len(audio_data)} bytes to {len(self.clients)} clients")
        else:
            # TODO: Implement actual client streaming
            pass
    
    async def stream_session(self, session_data: Dict[str, Any]) -> bool:
        """
        Stream a complete DJ session with enhanced capabilities.
        
        Args:
            session_data: Session information including tracks and commentary
            
        Returns:
            bool: True if streaming started successfully
        """
        try:
            logger.info(f"Starting to stream session: {session_data.get('session_id', 'unknown')}")
            
            self.current_session = session_data
            
            if not self.is_streaming:
                await self.start_server()
            
            # Use enhanced server if available
            if self.enhanced_server:
                return await self.enhanced_server.stream_session(session_data)
            else:
                # Fallback to basic session queuing
                await self._queue_session_audio(session_data)
                return True
            
        except Exception as e:
            logger.error(f"Failed to stream session: {e}")
            return False
    
    async def _queue_session_audio(self, session_data: Dict[str, Any]):
        """Queue audio content for streaming."""
        try:
            tracks = session_data.get('tracks', [])
            commentary = session_data.get('commentary', [])
            
            logger.info(f"Queueing {len(tracks)} tracks for streaming")
            
            # For each track, queue the audio
            for i, track_info in enumerate(tracks):
                track = track_info.get('track', {})
                track_path = track.get('file_path')
                
                # Queue any commentary before the track
                if i < len(commentary):
                    await self._queue_commentary(commentary[i])
                
                # Queue the track
                if track_path:
                    await self._queue_track(track_path, track)
                else:
                    logger.warning(f"No file path for track: {track.get('title', 'unknown')}")
            
            # Queue any remaining commentary
            for j in range(len(tracks), len(commentary)):
                await self._queue_commentary(commentary[j])
                
        except Exception as e:
            logger.error(f"Error queueing session audio: {e}")
    
    async def _queue_track(self, file_path: str, track_info: Dict[str, Any]):
        """Queue a music track for streaming."""
        try:
            if not Path(file_path).exists():
                logger.warning(f"Track file not found: {file_path}")
                return
            
            logger.info(f"Queueing track: {track_info.get('title', 'Unknown')} by {track_info.get('artist', 'Unknown')}")
            
            if self.mock_mode:
                # In mock mode, just simulate queueing
                mock_audio_data = b"mock_audio_data_for_track"
                self.audio_queue.put(mock_audio_data)
                return
            
            if not HAS_PYDUB:
                logger.warning("pydub not available - cannot process audio files")
                return
                
            # Load and process the audio file
            try:
                audio = AudioSegment.from_file(file_path)
                
                # Convert to standard format
                audio = audio.set_frame_rate(self.sample_rate)
                audio = audio.set_channels(self.channels)
                audio = audio.set_sample_width(self.bit_depth // 8)
                
                # Convert to raw audio data
                audio_data = audio.raw_data
                self.audio_queue.put(audio_data)
                
                logger.debug(f"Queued {len(audio_data)} bytes for track: {track_info.get('title')}")
                
            except Exception as e:
                logger.error(f"Failed to process audio file {file_path}: {e}")
                
        except Exception as e:
            logger.error(f"Error queueing track: {e}")
    
    async def _queue_commentary(self, commentary_info: Dict[str, Any]):
        """Queue DJ commentary for streaming."""
        try:
            content = commentary_info.get('content', '')
            commentary_type = commentary_info.get('type', 'unknown')
            
            logger.info(f"Queueing commentary ({commentary_type}): {content[:50]}...")
            
            if self.mock_mode:
                # In mock mode, just simulate queueing
                mock_commentary_data = b"mock_commentary_audio_data"
                self.audio_queue.put(mock_commentary_data)
                return
            
            # TODO: Generate audio from commentary using TTS
            # This would integrate with the TTS system
            # For now, we'll just log the commentary
            
            logger.debug(f"Would generate TTS audio for: {content}")
            
        except Exception as e:
            logger.error(f"Error queueing commentary: {e}")
    
    def get_stream_info(self) -> Dict[str, Any]:
        """Get current streaming information."""
        base_info = {
            "is_streaming": self.is_streaming,
            "host": self.host,
            "port": self.port,
            "mount": self.mount,
            "current_session": self.current_session.get('session_id') if self.current_session else None,
            "clients_connected": len(self.clients),
            "queue_size": self.audio_queue.qsize(),
            "mock_mode": self.mock_mode,
            "audio_settings": {
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "bit_depth": self.bit_depth
            }
        }
        
        # Add enhanced server info if available
        if self.enhanced_server:
            enhanced_info = self.enhanced_server.get_stream_info()
            base_info.update({
                "enhanced_streaming": True,
                "icecast_info": enhanced_info
            })
        else:
            base_info["enhanced_streaming"] = False
        
        return base_info
    
    async def skip_current_track(self) -> bool:
        """Skip to the next track in the queue."""
        try:
            if self.enhanced_server:
                return await self.enhanced_server.skip_current_track()
            else:
                # Basic skip implementation
                logger.info("Skipping current track (basic mode)")
                
                # Clear current audio buffer and move to next item
                if not self.audio_queue.empty():
                    # Remove some items from queue to simulate skip
                    for _ in range(min(5, self.audio_queue.qsize())):
                        try:
                            self.audio_queue.get_nowait()
                        except queue.Empty:
                            break
                
                return True
            
        except Exception as e:
            logger.error(f"Error skipping track: {e}")
            return False
    
    async def pause_stream(self) -> bool:
        """Pause the current stream."""
        try:
            if self.enhanced_server:
                return await self.enhanced_server.pause_stream()
            else:
                logger.info("Pausing stream (basic mode)")
                # Basic pause implementation would go here
                return True
        except Exception as e:
            logger.error(f"Error pausing stream: {e}")
            return False
    
    async def resume_stream(self) -> bool:
        """Resume the paused stream."""
        try:
            if self.enhanced_server:
                return await self.enhanced_server.resume_stream()
            else:
                logger.info("Resuming stream (basic mode)")
                # Basic resume implementation would go here
                return True
        except Exception as e:
            logger.error(f"Error resuming stream: {e}")
            return False


class StreamingSession:
    """Represents an active streaming session."""
    
    def __init__(self, session_id: str, session_data: Dict[str, Any]):
        self.session_id = session_id
        self.session_data = session_data
        self.start_time = time.time()
        self.current_track_index = 0
        self.is_paused = False
        
    def get_current_track(self) -> Optional[Dict[str, Any]]:
        """Get information about the currently playing track."""
        tracks = self.session_data.get('tracks', [])
        if 0 <= self.current_track_index < len(tracks):
            return tracks[self.current_track_index]
        return None
    
    def get_session_progress(self) -> Dict[str, Any]:
        """Get current session progress information."""
        tracks = self.session_data.get('tracks', [])
        current_track = self.get_current_track()
        
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "elapsed_time": time.time() - self.start_time,
            "current_track_index": self.current_track_index,
            "total_tracks": len(tracks),
            "current_track": current_track.get('track') if current_track else None,
            "is_paused": self.is_paused,
            "progress_percentage": (self.current_track_index / len(tracks) * 100) if tracks else 0
        }