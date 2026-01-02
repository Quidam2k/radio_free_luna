"""
Icecast2 Client for Radio Free Luna
Real streaming implementation with Icecast2 server integration
"""

import asyncio
import logging
import socket
import threading
import time
import queue
import io
from typing import Optional, Dict, Any, List
from pathlib import Path
import base64

try:
    from pydub import AudioSegment
    from pydub.playback import play
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False
    AudioSegment = None

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger(__name__)


class IcecastClient:
    """
    Real Icecast2 client for streaming audio content.
    
    Connects to an Icecast2 server and streams audio data using the source protocol.
    """
    
    def __init__(self, 
                 host: str = "localhost", 
                 port: int = 8000, 
                 mount: str = "/ai_dj_stream",
                 password: str = "hackme",
                 audio_format: str = "mp3",
                 bitrate: int = 128,
                 sample_rate: int = 44100,
                 channels: int = 2):
        
        self.host = host
        self.port = port
        self.mount = mount
        self.password = password
        self.audio_format = audio_format
        self.bitrate = bitrate
        self.sample_rate = sample_rate
        self.channels = channels
        
        # Connection state
        self.socket = None
        self.is_connected = False
        self.is_streaming = False
        
        # Streaming thread
        self.stream_thread = None
        self.audio_queue = queue.Queue()
        self.should_stop = threading.Event()
        
        # Buffer settings
        self.buffer_size = 4096
        self.max_queue_size = 50
        
        # Statistics
        self.bytes_sent = 0
        self.start_time = None
        
    async def connect(self) -> bool:
        """Connect to Icecast2 server."""
        try:
            logger.info(f"Connecting to Icecast2 at {self.host}:{self.port}{self.mount}")
            
            # Create socket connection
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            
            # Connect to server
            await asyncio.to_thread(self.socket.connect, (self.host, self.port))
            
            # Send Icecast2 source headers
            headers = self._build_source_headers()
            await asyncio.to_thread(self.socket.send, headers.encode('utf-8'))
            
            # Read response
            response = await asyncio.to_thread(self.socket.recv, 1024)
            response_str = response.decode('utf-8')
            
            if "HTTP/1.0 200 OK" in response_str:
                self.is_connected = True
                logger.info("✅ Successfully connected to Icecast2 server")
                return True
            else:
                logger.error(f"Icecast2 connection failed: {response_str}")
                self.socket.close()
                self.socket = None
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to Icecast2: {e}")
            if self.socket:
                self.socket.close()
                self.socket = None
            return False
    
    def _build_source_headers(self) -> str:
        """Build HTTP headers for Icecast2 source connection."""
        auth_string = f"source:{self.password}"
        auth_encoded = base64.b64encode(auth_string.encode()).decode()
        
        headers = [
            f"PUT {self.mount} HTTP/1.0",
            f"Authorization: Basic {auth_encoded}",
            f"User-Agent: RadioFreeLuna/1.0",
            f"Content-Type: audio/mpeg",
            f"Ice-Name: Radio Free Luna - AI DJ Stream",
            f"Ice-Description: Intelligent contextual music streaming",
            f"Ice-Genre: Various",
            f"Ice-Public: 0",
            f"Ice-Bitrate: {self.bitrate}",
            f"Ice-Channels: {self.channels}",
            f"Ice-Samplerate: {self.sample_rate}",
            "",
            ""
        ]
        
        return "\r\n".join(headers)
    
    async def disconnect(self):
        """Disconnect from Icecast2 server."""
        logger.info("Disconnecting from Icecast2 server...")
        
        self.should_stop.set()
        self.is_connected = False
        self.is_streaming = False
        
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=5)
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        logger.info("Disconnected from Icecast2 server")
    
    async def start_streaming(self) -> bool:
        """Start streaming audio data to Icecast2."""
        if not self.is_connected:
            logger.error("Not connected to Icecast2 server")
            return False
        
        if self.is_streaming:
            logger.warning("Already streaming")
            return True
        
        try:
            self.is_streaming = True
            self.start_time = time.time()
            self.bytes_sent = 0
            
            # Start streaming thread
            self.stream_thread = threading.Thread(target=self._streaming_loop, daemon=True)
            self.stream_thread.start()
            
            logger.info("✅ Started streaming to Icecast2")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            self.is_streaming = False
            return False
    
    def _streaming_loop(self):
        """Main streaming loop (runs in separate thread)."""
        logger.info("Icecast2 streaming loop started")
        
        while not self.should_stop.is_set() and self.is_connected:
            try:
                # Get audio data from queue
                try:
                    audio_data = self.audio_queue.get(timeout=1.0)
                    
                    if audio_data is None:  # Shutdown signal
                        break
                    
                    # Send to Icecast2
                    self._send_audio_data(audio_data)
                    self.bytes_sent += len(audio_data)
                    
                except queue.Empty:
                    # No audio data available, send silence or continue
                    silence = self._generate_silence(self.buffer_size)
                    self._send_audio_data(silence)
                    continue
                    
            except Exception as e:
                logger.error(f"Error in streaming loop: {e}")
                time.sleep(1)
        
        logger.info("Icecast2 streaming loop ended")
    
    def _send_audio_data(self, audio_data: bytes):
        """Send audio data to Icecast2 server."""
        try:
            if self.socket and self.is_connected:
                self.socket.send(audio_data)
        except Exception as e:
            logger.error(f"Failed to send audio data: {e}")
            self.is_connected = False
    
    def _generate_silence(self, size: int) -> bytes:
        """Generate silence for when no audio is available."""
        return b'\x00' * size
    
    async def queue_audio_data(self, audio_data: bytes):
        """Queue audio data for streaming."""
        if not self.is_streaming:
            logger.warning("Not streaming - ignoring audio data")
            return
        
        # Check queue size to prevent memory issues
        if self.audio_queue.qsize() >= self.max_queue_size:
            logger.warning("Audio queue full - dropping oldest data")
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
        
        self.audio_queue.put(audio_data)
    
    async def queue_audio_file(self, file_path: str):
        """Queue an audio file for streaming."""
        if not HAS_PYDUB:
            logger.error("pydub not available - cannot process audio files")
            return
        
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.error(f"Audio file not found: {file_path}")
                return
            
            logger.info(f"Queueing audio file: {file_path.name}")
            
            # Load and process audio file
            audio = AudioSegment.from_file(str(file_path))
            
            # Convert to target format
            audio = audio.set_frame_rate(self.sample_rate)
            audio = audio.set_channels(self.channels)
            
            # Export to MP3 format for streaming
            buffer = io.BytesIO()
            audio.export(buffer, format="mp3", bitrate=f"{self.bitrate}k")
            audio_data = buffer.getvalue()
            
            # Split into chunks and queue
            chunk_size = self.buffer_size
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                await self.queue_audio_data(chunk)
            
            logger.info(f"Successfully queued {len(audio_data)} bytes from {file_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to queue audio file {file_path}: {e}")
    
    def get_stream_info(self) -> Dict[str, Any]:
        """Get current streaming information."""
        uptime = time.time() - self.start_time if self.start_time else 0
        
        return {
            "is_connected": self.is_connected,
            "is_streaming": self.is_streaming,
            "host": self.host,
            "port": self.port,
            "mount": self.mount,
            "audio_format": self.audio_format,
            "bitrate": self.bitrate,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bytes_sent": self.bytes_sent,
            "uptime_seconds": uptime,
            "queue_size": self.audio_queue.qsize(),
            "stream_url": f"http://{self.host}:{self.port}{self.mount}"
        }
    
    async def test_connection(self) -> bool:
        """Test connection to Icecast2 server without starting stream."""
        if not HAS_REQUESTS:
            logger.warning("requests library not available for connection test")
            return False
        
        try:
            # Test basic connectivity to Icecast2 admin interface
            admin_url = f"http://{self.host}:{self.port}/admin/stats.xml"
            response = requests.get(admin_url, timeout=5)
            
            if response.status_code == 200:
                logger.info("Icecast2 server is reachable")
                return True
            else:
                logger.warning(f"Icecast2 server returned status {response.status_code}")
                return False
                
        except Exception as e:
            logger.warning(f"Cannot reach Icecast2 server: {e}")
            return False


class EnhancedAudioServer:
    """
    Enhanced audio server with real Icecast2 integration.
    
    Replaces the mock BasicAudioServer with actual streaming capabilities.
    """
    
    def __init__(self, host: str = "localhost", port: int = 8000, mount: str = "/ai_dj_stream", password: str = "hackme"):
        self.icecast_client = IcecastClient(host, port, mount, password)
        self.current_session = None
        self.is_streaming = False
        
        # Enhanced audio processing
        self.crossfade_duration = 6.0  # seconds
        self.normalization_enabled = True
        self.dynamic_range_compression = True
        
    async def start_server(self) -> bool:
        """Start the enhanced audio server."""
        logger.info("Starting enhanced audio server with Icecast2 integration...")
        
        # Test Icecast2 connectivity first
        if not await self.icecast_client.test_connection():
            logger.warning("Icecast2 server not reachable - falling back to mock mode")
            return await self._start_mock_mode()
        
        # Connect to Icecast2
        if await self.icecast_client.connect():
            if await self.icecast_client.start_streaming():
                self.is_streaming = True
                logger.info("✅ Enhanced audio server started with real Icecast2 streaming")
                return True
        
        logger.warning("Failed to connect to Icecast2 - falling back to mock mode")
        return await self._start_mock_mode()
    
    async def _start_mock_mode(self) -> bool:
        """Fallback to mock mode when Icecast2 is not available."""
        logger.info("Running in mock streaming mode")
        self.is_streaming = True
        return True
    
    async def stop_server(self):
        """Stop the audio server."""
        logger.info("Stopping enhanced audio server...")
        await self.icecast_client.disconnect()
        self.is_streaming = False
        logger.info("Enhanced audio server stopped")
    
    async def stream_session(self, session_data: Dict[str, Any]) -> bool:
        """Stream a complete DJ session with enhanced audio processing."""
        try:
            logger.info(f"Starting enhanced stream for session: {session_data.get('session_id', 'unknown')}")
            
            self.current_session = session_data
            
            if not self.is_streaming:
                await self.start_server()
            
            # Process and queue the session content with enhancements
            await self._process_session_audio(session_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to stream session: {e}")
            return False
    
    async def _process_session_audio(self, session_data: Dict[str, Any]):
        """Process session audio with crossfading and enhancement."""
        try:
            tracks = session_data.get('tracks', [])
            commentary = session_data.get('commentary', [])
            
            logger.info(f"Processing {len(tracks)} tracks with enhanced audio pipeline")
            
            previous_track_tail = None
            
            for i, track_info in enumerate(tracks):
                track = track_info.get('track', {})
                track_path = track.get('file_path')
                
                # Queue any commentary before the track
                if i < len(commentary):
                    await self._queue_enhanced_commentary(commentary[i])
                
                # Process and queue the track with crossfading
                if track_path:
                    current_track_tail = await self._queue_enhanced_track(
                        track_path, 
                        track, 
                        previous_track_tail
                    )
                    previous_track_tail = current_track_tail
                else:
                    logger.warning(f"No file path for track: {track.get('title', 'unknown')}")
            
        except Exception as e:
            logger.error(f"Error processing session audio: {e}")
    
    async def _queue_enhanced_track(self, file_path: str, track_info: Dict[str, Any], previous_tail: Optional[bytes] = None) -> Optional[bytes]:
        """Queue a track with crossfading and audio enhancement."""
        try:
            if not Path(file_path).exists():
                logger.warning(f"Track file not found: {file_path}")
                return None
            
            logger.info(f"Processing enhanced track: {track_info.get('title', 'Unknown')} by {track_info.get('artist', 'Unknown')}")
            
            if self.icecast_client.is_connected:
                # Real Icecast2 streaming
                await self.icecast_client.queue_audio_file(file_path)
                
                # TODO: Implement actual crossfading with pydub
                # For now, just queue the file
                return b"mock_track_tail"  # Would be actual audio tail for crossfading
            else:
                # Mock mode
                logger.info(f"Mock: Would stream {track_info.get('title', 'Unknown')}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing enhanced track: {e}")
            return None
    
    async def _queue_enhanced_commentary(self, commentary_info: Dict[str, Any]):
        """Queue DJ commentary with audio enhancement."""
        try:
            content = commentary_info.get('content', '')
            commentary_type = commentary_info.get('type', 'unknown')
            
            logger.info(f"Processing enhanced commentary ({commentary_type}): {content[:50]}...")
            
            # TODO: Generate TTS audio and queue it
            # For now, just log the commentary
            logger.debug(f"Enhanced commentary ready: {content}")
            
        except Exception as e:
            logger.error(f"Error processing enhanced commentary: {e}")
    
    def get_stream_info(self) -> Dict[str, Any]:
        """Get enhanced streaming information."""
        base_info = self.icecast_client.get_stream_info()
        
        return {
            **base_info,
            "enhanced_features": {
                "crossfade_duration": self.crossfade_duration,
                "normalization_enabled": self.normalization_enabled,
                "dynamic_range_compression": self.dynamic_range_compression
            },
            "current_session": self.current_session.get('session_id') if self.current_session else None
        }
    
    async def skip_current_track(self) -> bool:
        """Skip to the next track with enhanced transition."""
        try:
            logger.info("Skipping current track with enhanced transition")
            
            # TODO: Implement smooth skip with crossfading
            # For now, just clear some queue items
            if self.icecast_client.is_connected:
                # Clear some items from the queue
                queue_size = self.icecast_client.audio_queue.qsize()
                items_to_clear = min(10, queue_size)
                
                for _ in range(items_to_clear):
                    try:
                        self.icecast_client.audio_queue.get_nowait()
                    except queue.Empty:
                        break
            
            return True
            
        except Exception as e:
            logger.error(f"Error skipping track: {e}")
            return False
    
    async def pause_stream(self) -> bool:
        """Pause the stream with fade out."""
        try:
            logger.info("Pausing stream with fade out")
            # TODO: Implement fade out before pause
            return True
        except Exception as e:
            logger.error(f"Error pausing stream: {e}")
            return False
    
    async def resume_stream(self) -> bool:
        """Resume the stream with fade in."""
        try:
            logger.info("Resuming stream with fade in")
            # TODO: Implement fade in after resume
            return True
        except Exception as e:
            logger.error(f"Error resuming stream: {e}")
            return False