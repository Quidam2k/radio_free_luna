"""
Advanced Crossfader for Radio Free Luna
Handles sophisticated audio transitions, normalization, and dynamic processing
"""

import asyncio
import logging
from typing import Optional, Tuple, List, Dict, Any
import math

try:
    from pydub import AudioSegment
    from pydub.effects import normalize, compress_dynamic_range
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False
    AudioSegment = None
    normalize = None
    compress_dynamic_range = None

logger = logging.getLogger(__name__)


class BasicCrossfader:
    """
    Advanced crossfader for smooth transitions between audio tracks.
    
    Provides sophisticated fade-in/fade-out transitions, smart crossfading,
    audio normalization, and dynamic range compression.
    """
    
    def __init__(self, fade_duration_ms: int = 6000):
        self.fade_duration_ms = fade_duration_ms
        self.default_crossfade_type = "smart"  # linear, exponential, logarithmic, smart, sine
        
        # Advanced audio processing options
        self.normalize_audio = True
        self.dynamic_compression = True
        self.auto_gain_control = True
        
        # Smart crossfading analysis cache
        self.analysis_cache = {}
        
    def create_crossfade(self, track1: AudioSegment, track2: AudioSegment,
                        fade_duration_ms: Optional[int] = None,
                        crossfade_type: str = "linear") -> AudioSegment:
        """
        Create a crossfade between two audio tracks.

        Args:
            track1: First audio track (will fade out)
            track2: Second audio track (will fade in)
            fade_duration_ms: Duration of crossfade in milliseconds
            crossfade_type: Type of crossfade (linear, sine, logarithmic, smart)

        Returns:
            AudioSegment: Combined audio with crossfade
        """
        if not HAS_PYDUB:
            logger.warning("pydub not available - returning track2")
            return track2

        try:
            fade_duration = fade_duration_ms or self.fade_duration_ms

            # Ensure fade duration doesn't exceed track lengths
            fade_duration = min(fade_duration, len(track1), len(track2))

            if fade_duration <= 0:
                logger.warning("Invalid fade duration, concatenating tracks")
                return track1 + track2

            # Get the fade portions
            track1_fade_out = track1[-fade_duration:]
            track2_fade_in = track2[:fade_duration]

            # Apply fades based on type
            if crossfade_type == "linear":
                faded_out = self._apply_linear_fade_out(track1_fade_out)
                faded_in = self._apply_linear_fade_in(track2_fade_in)
            elif crossfade_type == "sine":
                faded_out = self._apply_sine_fade_out(track1_fade_out)
                faded_in = self._apply_sine_fade_in(track2_fade_in)
            elif crossfade_type == "smart":
                # Analyze tracks and choose best crossfade method
                optimal_type = self._analyze_optimal_crossfade(track1_fade_out, track2_fade_in)
                if optimal_type == "smart":  # guard against analysis recursing forever
                    optimal_type = "linear"
                logger.debug(f"Smart crossfade selected: {optimal_type}")
                return self.create_crossfade(track1, track2, fade_duration_ms, optimal_type)
            else:  # logarithmic or fallback
                faded_out = self._apply_logarithmic_fade_out(track1_fade_out)
                faded_in = self._apply_logarithmic_fade_in(track2_fade_in)
            
            # Mix the fade sections
            crossfaded_section = faded_out.overlay(faded_in)
            
            # Combine: track1 (without fade section) + crossfaded section + track2 (without fade section)
            result = track1[:-fade_duration] + crossfaded_section + track2[fade_duration:]
            
            logger.debug(f"Created {crossfade_type} crossfade of {fade_duration}ms")
            return result
            
        except Exception as e:
            logger.error(f"Error creating crossfade: {e}")
            # Fallback to simple concatenation
            return track1 + track2
    
    def _apply_linear_fade_out(self, audio: AudioSegment) -> AudioSegment:
        """Apply linear fade out to audio segment."""
        return audio.fade_out(len(audio))
    
    def _apply_linear_fade_in(self, audio: AudioSegment) -> AudioSegment:
        """Apply linear fade in to audio segment."""
        return audio.fade_in(len(audio))
    
    def _apply_logarithmic_fade_out(self, audio: AudioSegment) -> AudioSegment:
        """Apply logarithmic fade out (linear ramp in dB, exponential in amplitude)."""
        if not HAS_PYDUB:
            return audio

        duration_ms = len(audio)
        result = audio

        for i in range(0, duration_ms, 100):  # Process in 100ms chunks for efficiency
            progress = i / duration_ms
            gain_db = progress * -60.0  # ramp 0 dB -> -60 dB

            chunk_start = i
            chunk_end = min(i + 100, duration_ms)
            chunk = result[chunk_start:chunk_end].apply_gain(gain_db)
            result = result[:chunk_start] + chunk + result[chunk_end:]

        return result

    def _apply_logarithmic_fade_in(self, audio: AudioSegment) -> AudioSegment:
        """Apply logarithmic fade in (linear ramp in dB, exponential in amplitude)."""
        if not HAS_PYDUB:
            return audio

        duration_ms = len(audio)
        result = audio

        for i in range(0, duration_ms, 100):  # Process in 100ms chunks for efficiency
            progress = i / duration_ms
            gain_db = (1.0 - progress) * -60.0  # ramp -60 dB -> 0 dB

            chunk_start = i
            chunk_end = min(i + 100, duration_ms)
            chunk = result[chunk_start:chunk_end].apply_gain(gain_db)
            result = result[:chunk_start] + chunk + result[chunk_end:]

        return result
    
    def _apply_sine_fade_out(self, audio: AudioSegment) -> AudioSegment:
        """Apply sine wave fade out for smooth S-curve transition."""
        if not HAS_PYDUB:
            return audio
        
        duration_ms = len(audio)
        result = audio
        
        # Apply sine wave volume curve
        for i in range(0, duration_ms, 100):  # Process in 100ms chunks for efficiency
            progress = i / duration_ms
            volume_factor = math.cos(progress * math.pi / 2)  # Sine curve for fade out
            
            if volume_factor > 0:
                gain_db = 20 * math.log10(volume_factor)
                chunk_start = i
                chunk_end = min(i + 100, duration_ms)
                chunk = result[chunk_start:chunk_end].apply_gain(gain_db)
                result = result[:chunk_start] + chunk + result[chunk_end:]
        
        return result
    
    def _apply_sine_fade_in(self, audio: AudioSegment) -> AudioSegment:
        """Apply sine wave fade in for smooth S-curve transition."""
        if not HAS_PYDUB:
            return audio
        
        duration_ms = len(audio)
        result = audio
        
        # Apply sine wave volume curve
        for i in range(0, duration_ms, 100):  # Process in 100ms chunks for efficiency
            progress = i / duration_ms
            volume_factor = math.sin(progress * math.pi / 2)  # Sine curve for fade in
            
            if volume_factor > 0:
                gain_db = 20 * math.log10(volume_factor)
                chunk_start = i
                chunk_end = min(i + 100, duration_ms)
                chunk = result[chunk_start:chunk_end].apply_gain(gain_db)
                result = result[:chunk_start] + chunk + result[chunk_end:]
        
        return result
    
    def _analyze_optimal_crossfade(self, track1_segment: AudioSegment, track2_segment: AudioSegment) -> str:
        """Analyze audio segments to determine optimal crossfade type."""
        if not HAS_PYDUB:
            return "linear"
        
        try:
            # Get segment characteristics
            track1_analysis = self._analyze_segment(track1_segment)
            track2_analysis = self._analyze_segment(track2_segment)
            
            # Calculate differences
            energy_diff = abs(track1_analysis["energy"] - track2_analysis["energy"])
            dynamics_diff = abs(track1_analysis["dynamics"] - track2_analysis["dynamics"])
            
            # Decision logic for optimal crossfade
            if dynamics_diff > 0.3:
                # Different dynamics - use sine for smooth S-curve transition
                return "sine"
            elif energy_diff < 0.1 and dynamics_diff < 0.1:
                # Very similar tracks - use linear for clean transition
                return "linear"
            else:
                # Moderate / large energy differences - logarithmic feels natural
                return "logarithmic"
                
        except Exception as e:
            logger.warning(f"Crossfade analysis failed: {e}")
            return "linear"
    
    def _analyze_segment(self, segment: AudioSegment) -> Dict[str, Any]:
        """Analyze audio segment for crossfade optimization."""
        try:
            # Basic audio analysis
            rms = segment.rms
            max_amplitude = segment.max
            
            # Normalize energy to 0-1 scale
            energy = min(1.0, rms / (max_amplitude + 1)) if max_amplitude > 0 else 0.0
            
            # Calculate dynamics (difference between loud and quiet parts)
            # Sample a few points and calculate range
            sample_points = 5
            sample_size = len(segment) // sample_points
            volumes = []
            
            for i in range(sample_points):
                start = i * sample_size
                end = min(start + sample_size, len(segment))
                if end > start:
                    sample = segment[start:end]
                    volumes.append(sample.rms)
            
            dynamics = (max(volumes) - min(volumes)) / (max(volumes) + 1) if volumes else 0.0
            
            return {
                "energy": energy,
                "dynamics": dynamics,
                "rms": rms,
                "max_amplitude": max_amplitude
            }
            
        except Exception as e:
            logger.warning(f"Segment analysis failed: {e}")
            return {"energy": 0.5, "dynamics": 0.5, "rms": 0, "max_amplitude": 0}
    
    def enhance_audio_quality(self, audio: AudioSegment) -> AudioSegment:
        """Apply audio enhancement processing."""
        if not HAS_PYDUB or not audio:
            return audio
        
        try:
            result = audio
            
            # Apply normalization if enabled
            if self.normalize_audio and normalize:
                result = normalize(result)
                logger.debug("Applied audio normalization")
            
            # Apply dynamic range compression if enabled
            if self.dynamic_compression and compress_dynamic_range:
                result = compress_dynamic_range(result)
                logger.debug("Applied dynamic range compression")
            
            # Apply auto gain control if enabled
            if self.auto_gain_control:
                result = self._apply_auto_gain_control(result)
                logger.debug("Applied auto gain control")
            
            return result
            
        except Exception as e:
            logger.warning(f"Audio enhancement failed: {e}")
            return audio
    
    def _apply_auto_gain_control(self, audio: AudioSegment) -> AudioSegment:
        """Apply automatic gain control to maintain consistent volume."""
        try:
            target_rms = 1000  # Target RMS level
            current_rms = audio.rms
            
            if current_rms > 0:
                # Calculate gain adjustment needed
                gain_ratio = target_rms / current_rms
                gain_db = 20 * math.log10(gain_ratio)
                
                # Limit gain to reasonable range
                gain_db = max(-20, min(20, gain_db))
                
                if abs(gain_db) > 1:  # Only adjust if significant
                    audio = audio.apply_gain(gain_db)
                    logger.debug(f"Applied auto gain: {gain_db:.1f}dB")
            
            return audio
            
        except Exception as e:
            logger.warning(f"Auto gain control failed: {e}")
            return audio
    
    def create_gapless_transition(self, tracks: List[AudioSegment]) -> AudioSegment:
        """
        Create gapless transitions between multiple tracks.
        
        Args:
            tracks: List of audio tracks to chain together
            
        Returns:
            AudioSegment: Combined audio with smooth transitions
        """
        if not tracks:
            return AudioSegment.empty()
        
        if len(tracks) == 1:
            return tracks[0]
        
        try:
            result = tracks[0]
            
            for i in range(1, len(tracks)):
                result = self.create_crossfade(result, tracks[i])
            
            logger.info(f"Created gapless transition for {len(tracks)} tracks")
            return result
            
        except Exception as e:
            logger.error(f"Error creating gapless transition: {e}")
            # Fallback to simple concatenation
            result = AudioSegment.empty()
            for track in tracks:
                result += track
            return result
    
    def create_enhanced_gapless_transition(self, tracks: List[AudioSegment]) -> AudioSegment:
        """
        Create enhanced gapless transitions using smart crossfading and audio analysis.
        
        Args:
            tracks: List of audio tracks to chain together
            
        Returns:
            AudioSegment: Combined audio with sophisticated transitions
        """
        if not tracks:
            return AudioSegment.empty()
        
        if len(tracks) == 1:
            return self.enhance_audio_quality(tracks[0])
        
        try:
            result = self.enhance_audio_quality(tracks[0])
            
            for i in range(1, len(tracks)):
                current_track = self.enhance_audio_quality(tracks[i])
                
                # Use smart crossfading for each transition
                result = self.create_crossfade(
                    result, 
                    current_track,
                    crossfade_type="smart"
                )
                
                logger.debug(f"Applied smart crossfade for track {i+1}/{len(tracks)}")
            
            logger.info(f"Created enhanced gapless transition for {len(tracks)} tracks with smart crossfading")
            return result
            
        except Exception as e:
            logger.error(f"Error creating enhanced gapless transition: {e}")
            # Fallback to basic gapless transition
            return self.create_gapless_transition(tracks)
    
    def mix_with_commentary(self, music: AudioSegment, commentary: AudioSegment, 
                          commentary_position: str = "beginning", 
                          music_duck_level: float = 0.3) -> AudioSegment:
        """
        Mix music with DJ commentary.
        
        Args:
            music: Background music track
            commentary: Commentary audio
            commentary_position: Where to place commentary (beginning, middle, end)
            music_duck_level: How much to reduce music volume during commentary (0.0-1.0)
            
        Returns:
            AudioSegment: Mixed audio with commentary
        """
        if not HAS_PYDUB:
            logger.warning("pydub not available - returning music")
            return music
        
        try:
            commentary_duration = len(commentary)
            music_duration = len(music)
            
            # Determine commentary position
            if commentary_position == "beginning":
                overlay_position = 0
            elif commentary_position == "middle":
                overlay_position = (music_duration - commentary_duration) // 2
            elif commentary_position == "end":
                overlay_position = music_duration - commentary_duration
            else:  # Custom position (assume it's a number in ms)
                try:
                    overlay_position = int(commentary_position)
                except (ValueError, TypeError):
                    overlay_position = 0
            
            # Ensure position is valid
            overlay_position = max(0, min(overlay_position, music_duration - commentary_duration))
            
            # Create ducked music section
            ducked_section_start = overlay_position
            ducked_section_end = overlay_position + commentary_duration
            
            # Split music into sections
            before_duck = music[:ducked_section_start]
            duck_section = music[ducked_section_start:ducked_section_end]
            after_duck = music[ducked_section_end:]
            
            # Apply ducking (reduce volume). apply_gain with the (negative)
            # dB value — pydub's `-` operator lowers gain by the operand, so
            # subtracting the negative log would boost the music instead.
            duck_gain_db = 20 * math.log10(music_duck_level) if music_duck_level > 0 else -60.0
            ducked_music = duck_section.apply_gain(duck_gain_db)
            
            # Mix commentary with ducked music
            mixed_section = ducked_music.overlay(commentary)
            
            # Recombine
            result = before_duck + mixed_section + after_duck
            
            logger.debug(f"Mixed commentary at position {commentary_position} with duck level {music_duck_level}")
            return result
            
        except Exception as e:
            logger.error(f"Error mixing commentary: {e}")
            # Fallback to just playing commentary first
            return commentary + music
    
    async def process_session_audio(self, session_tracks: List[dict], 
                                   commentary_segments: List[dict]) -> Optional[AudioSegment]:
        """
        Process an entire session with tracks and commentary.
        
        Args:
            session_tracks: List of track information dicts
            commentary_segments: List of commentary information dicts
            
        Returns:
            Optional[AudioSegment]: Complete session audio or None if failed
        """
        if not HAS_PYDUB:
            logger.warning("pydub not available - cannot process session audio")
            return None
        
        try:
            logger.info(f"Processing session with {len(session_tracks)} tracks and {len(commentary_segments)} commentary segments")
            
            processed_segments = []
            
            # Process each track with its associated commentary
            for i, track_info in enumerate(session_tracks):
                track_path = track_info.get('file_path')
                if not track_path:
                    continue
                
                try:
                    # Load the track
                    track_audio = AudioSegment.from_file(track_path)
                    
                    # Apply audio enhancement
                    enhanced_audio = self.enhance_audio_quality(track_audio)
                    
                    # Find any commentary for this track
                    track_commentary = None
                    for commentary in commentary_segments:
                        if commentary.get('track_index') == i:
                            # TODO: Generate audio from commentary text using TTS
                            # For now, we'll skip this and just use the track
                            pass
                    
                    # Add the track (with optional commentary mixing)
                    if track_commentary:
                        mixed_audio = self.mix_with_commentary(enhanced_audio, track_commentary)
                        processed_segments.append(mixed_audio)
                    else:
                        processed_segments.append(enhanced_audio)
                    
                except Exception as e:
                    logger.error(f"Error processing track {track_path}: {e}")
                    continue
            
            if not processed_segments:
                logger.warning("No audio segments to process")
                return None
            
            # Create gapless transitions between all segments using smart crossfading
            if len(processed_segments) > 1:
                session_audio = self.create_enhanced_gapless_transition(processed_segments)
            else:
                session_audio = processed_segments[0] if processed_segments else AudioSegment.empty()
            
            logger.info(f"Successfully processed session audio: {len(session_audio)}ms total duration")
            return session_audio
            
        except Exception as e:
            logger.error(f"Error processing session audio: {e}")
            return None


class MockCrossfader:
    """
    Mock crossfader for testing when pydub is not available.
    """
    
    def __init__(self, fade_duration_ms: int = 3000):
        self.fade_duration_ms = fade_duration_ms
        logger.info("Using mock crossfader - no actual audio processing")
    
    def create_crossfade(self, track1, track2, fade_duration_ms=None, crossfade_type="linear"):
        """Mock crossfade - just returns track2."""
        logger.debug(f"Mock crossfade: {crossfade_type}, duration: {fade_duration_ms or self.fade_duration_ms}ms")
        return track2
    
    def create_gapless_transition(self, tracks):
        """Mock gapless transition."""
        logger.debug(f"Mock gapless transition for {len(tracks)} tracks")
        return tracks[-1] if tracks else None
    
    def mix_with_commentary(self, music, commentary, commentary_position="beginning", music_duck_level=0.3):
        """Mock commentary mixing."""
        logger.debug(f"Mock commentary mix at {commentary_position} with duck level {music_duck_level}")
        return music
    
    async def process_session_audio(self, session_tracks, commentary_segments):
        """Mock session audio processing."""
        logger.debug(f"Mock session processing: {len(session_tracks)} tracks, {len(commentary_segments)} commentary")
        return None


# Factory function to get appropriate crossfader
def get_crossfader(fade_duration_ms: int = 3000):
    """Get appropriate crossfader based on available dependencies."""
    if HAS_PYDUB:
        return BasicCrossfader(fade_duration_ms)
    else:
        return MockCrossfader(fade_duration_ms)