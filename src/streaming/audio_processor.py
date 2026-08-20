"""
Audio Processor for Radio Free Luna
Handles basic audio processing, normalization, and effects
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

try:
    from pydub import AudioSegment
    from pydub.effects import normalize, compress_dynamic_range
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False
    AudioSegment = None

logger = logging.getLogger(__name__)


class AudioProcessor:
    """
    Basic audio processor for Radio Free Luna streaming.
    
    Provides audio normalization, format conversion, and basic effects.
    """
    
    def __init__(self):
        self.target_sample_rate = 44100
        self.target_channels = 2
        self.target_bit_depth = 16
        self.normalize_audio = True
        self.apply_compression = False
        
        # Audio processing settings
        self.normalization_target_dbfs = -20.0
        self.compression_threshold = -20.0
        self.compression_ratio = 4.0
        
    async def process_audio_file(self, file_path: str, 
                               normalize: bool = True,
                               target_format: Optional[Dict[str, Any]] = None) -> Optional[AudioSegment]:
        """
        Process an audio file for streaming.
        
        Args:
            file_path: Path to audio file
            normalize: Whether to normalize audio levels
            target_format: Target audio format specifications
            
        Returns:
            Optional[AudioSegment]: Processed audio or None if failed
        """
        if not HAS_PYDUB:
            logger.warning("pydub not available - cannot process audio files")
            return None

        # Decoding and pydub processing are CPU/disk bound and would stall the
        # event loop (and the live stream) for seconds per track if run inline.
        return await asyncio.to_thread(
            self._process_audio_file_sync, file_path, normalize, target_format
        )

    def _process_audio_file_sync(self, file_path: str,
                                 normalize: bool = True,
                                 target_format: Optional[Dict[str, Any]] = None) -> Optional[AudioSegment]:
        try:
            if not Path(file_path).exists():
                logger.error(f"Audio file not found: {file_path}")
                return None

            logger.debug(f"Processing audio file: {file_path}")

            # Load the audio file
            audio = AudioSegment.from_file(file_path)

            # Apply format conversion
            audio = self._convert_format(audio, target_format)

            # Apply normalization if requested
            if normalize and self.normalize_audio:
                audio = self._normalize_audio(audio)

            # Apply compression if enabled
            if self.apply_compression:
                audio = self._apply_compression(audio)

            # Apply any additional processing
            audio = self._apply_additional_processing(audio)

            logger.debug(f"Successfully processed audio: {len(audio)}ms duration")
            return audio

        except Exception as e:
            logger.error(f"Error processing audio file {file_path}: {e}")
            return None
    
    def _convert_format(self, audio: AudioSegment, 
                       target_format: Optional[Dict[str, Any]] = None) -> AudioSegment:
        """Convert audio to target format."""
        try:
            if target_format is None:
                target_format = {
                    "sample_rate": self.target_sample_rate,
                    "channels": self.target_channels,
                    "bit_depth": self.target_bit_depth
                }
            
            # Convert sample rate
            target_sample_rate = target_format.get("sample_rate", self.target_sample_rate)
            if audio.frame_rate != target_sample_rate:
                audio = audio.set_frame_rate(target_sample_rate)
                logger.debug(f"Converted sample rate to {target_sample_rate}Hz")
            
            # Convert channels
            target_channels = target_format.get("channels", self.target_channels)
            if audio.channels != target_channels:
                if target_channels == 1:
                    audio = audio.set_channels(1)  # Convert to mono
                elif target_channels == 2:
                    audio = audio.set_channels(2)  # Convert to stereo
                logger.debug(f"Converted to {target_channels} channel(s)")
            
            # Convert bit depth
            target_bit_depth = target_format.get("bit_depth", self.target_bit_depth)
            target_sample_width = target_bit_depth // 8
            if audio.sample_width != target_sample_width:
                audio = audio.set_sample_width(target_sample_width)
                logger.debug(f"Converted bit depth to {target_bit_depth} bits")
            
            return audio
            
        except Exception as e:
            logger.error(f"Error converting audio format: {e}")
            return audio
    
    def _normalize_audio(self, audio: AudioSegment) -> AudioSegment:
        """Normalize audio levels."""
        try:
            # Use pydub's normalize function
            normalized = normalize(audio, headroom=abs(self.normalization_target_dbfs))
            logger.debug(f"Normalized audio to {self.normalization_target_dbfs} dBFS")
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing audio: {e}")
            return audio
    
    def _apply_compression(self, audio: AudioSegment) -> AudioSegment:
        """Apply dynamic range compression."""
        try:
            # Use pydub's compression function
            compressed = compress_dynamic_range(
                audio, 
                threshold=self.compression_threshold,
                ratio=self.compression_ratio
            )
            logger.debug(f"Applied compression: threshold={self.compression_threshold}dB, ratio={self.compression_ratio}:1")
            return compressed
            
        except Exception as e:
            logger.error(f"Error applying compression: {e}")
            return audio
    
    def _apply_additional_processing(self, audio: AudioSegment) -> AudioSegment:
        """Apply any additional audio processing."""
        try:
            # Apply gentle high-pass filter to remove low-frequency noise
            # This is a simple implementation - more sophisticated filtering
            # would require additional libraries like scipy
            
            # For now, we'll just apply a very gentle fade-in/out to smooth edges
            fade_duration = min(100, len(audio) // 10)  # 100ms or 10% of track, whichever is smaller
            
            if fade_duration > 0:
                audio = audio.fade_in(fade_duration).fade_out(fade_duration)
                logger.debug(f"Applied {fade_duration}ms fade in/out")
            
            return audio
            
        except Exception as e:
            logger.error(f"Error applying additional processing: {e}")
            return audio
    
    async def batch_process_files(self, file_paths: List[str], 
                                 normalize: bool = True,
                                 target_format: Optional[Dict[str, Any]] = None) -> List[Optional[AudioSegment]]:
        """
        Process multiple audio files in batch.
        
        Args:
            file_paths: List of audio file paths
            normalize: Whether to normalize audio levels
            target_format: Target audio format specifications
            
        Returns:
            List[Optional[AudioSegment]]: List of processed audio segments
        """
        logger.info(f"Batch processing {len(file_paths)} audio files")
        
        processed_audio = []
        
        for file_path in file_paths:
            audio = await self.process_audio_file(file_path, normalize, target_format)
            processed_audio.append(audio)
        
        successful_count = sum(1 for audio in processed_audio if audio is not None)
        logger.info(f"Successfully processed {successful_count}/{len(file_paths)} audio files")
        
        return processed_audio
    
    def analyze_audio_properties(self, audio: AudioSegment) -> Dict[str, Any]:
        """
        Analyze properties of an audio segment.
        
        Args:
            audio: Audio segment to analyze
            
        Returns:
            Dict[str, Any]: Audio properties
        """
        if not HAS_PYDUB:
            return {"error": "pydub not available"}
        
        try:
            properties = {
                "duration_ms": len(audio),
                "duration_seconds": len(audio) / 1000.0,
                "sample_rate": audio.frame_rate,
                "channels": audio.channels,
                "sample_width": audio.sample_width,
                "bit_depth": audio.sample_width * 8,
                "frame_count": audio.frame_count(),
                "max_possible_amplitude": audio.max_possible_amplitude,
                "dBFS": audio.dBFS,
                "rms": audio.rms
            }
            
            # Calculate additional metrics
            properties["estimated_bitrate"] = (
                properties["sample_rate"] * 
                properties["bit_depth"] * 
                properties["channels"]
            )
            
            return properties
            
        except Exception as e:
            logger.error(f"Error analyzing audio properties: {e}")
            return {"error": str(e)}
    
    def get_audio_format_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get format information for an audio file without loading it.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Dict[str, Any]: Format information
        """
        try:
            if not Path(file_path).exists():
                return {"error": "File not found"}
            
            # Get basic file info
            file_size = Path(file_path).stat().st_size
            file_extension = Path(file_path).suffix.lower()
            
            info = {
                "file_path": file_path,
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "file_extension": file_extension,
                "supported": file_extension in ['.mp3', '.flac', '.wav', '.m4a', '.ogg', '.wma']
            }
            
            if HAS_PYDUB:
                try:
                    # Try to get more detailed info by loading just metadata
                    audio = AudioSegment.from_file(file_path)
                    info.update({
                        "duration_ms": len(audio),
                        "duration_seconds": len(audio) / 1000.0,
                        "sample_rate": audio.frame_rate,
                        "channels": audio.channels,
                        "bit_depth": audio.sample_width * 8,
                        "estimated_bitrate": (
                            audio.frame_rate * audio.sample_width * 8 * audio.channels
                        )
                    })
                except Exception as e:
                    info["metadata_error"] = str(e)
            else:
                info["note"] = "pydub not available - limited format info"
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting audio format info: {e}")
            return {"error": str(e)}
    
    def create_silence(self, duration_ms: int, 
                      sample_rate: Optional[int] = None,
                      channels: Optional[int] = None) -> Optional[AudioSegment]:
        """
        Create a silent audio segment.
        
        Args:
            duration_ms: Duration in milliseconds
            sample_rate: Sample rate (uses default if None)
            channels: Number of channels (uses default if None)
            
        Returns:
            Optional[AudioSegment]: Silent audio segment
        """
        if not HAS_PYDUB:
            logger.warning("pydub not available - cannot create silence")
            return None
        
        try:
            sample_rate = sample_rate or self.target_sample_rate
            channels = channels or self.target_channels
            
            silence = AudioSegment.silent(
                duration=duration_ms,
                frame_rate=sample_rate
            )
            
            if channels == 2:
                silence = silence.set_channels(2)
            
            logger.debug(f"Created {duration_ms}ms of silence")
            return silence
            
        except Exception as e:
            logger.error(f"Error creating silence: {e}")
            return None


class MockAudioProcessor:
    """
    Mock audio processor for testing when pydub is not available.
    """
    
    def __init__(self):
        self.target_sample_rate = 44100
        self.target_channels = 2
        self.target_bit_depth = 16
        logger.info("Using mock audio processor - no actual audio processing")
    
    async def process_audio_file(self, file_path, normalize=True, target_format=None):
        """Mock audio file processing."""
        logger.debug(f"Mock processing: {file_path}")
        return None
    
    async def batch_process_files(self, file_paths, normalize=True, target_format=None):
        """Mock batch processing."""
        logger.debug(f"Mock batch processing: {len(file_paths)} files")
        return [None] * len(file_paths)
    
    def analyze_audio_properties(self, audio):
        """Mock audio analysis."""
        return {"error": "Mock processor - no analysis available"}
    
    def get_audio_format_info(self, file_path):
        """Mock format info."""
        return {
            "file_path": file_path,
            "supported": True,
            "note": "Mock processor - limited info available"
        }
    
    def create_silence(self, duration_ms, sample_rate=None, channels=None):
        """Mock silence creation."""
        logger.debug(f"Mock silence: {duration_ms}ms")
        return None


# Factory function to get appropriate audio processor
def get_audio_processor():
    """Get appropriate audio processor based on available dependencies."""
    if HAS_PYDUB:
        return AudioProcessor()
    else:
        return MockAudioProcessor()