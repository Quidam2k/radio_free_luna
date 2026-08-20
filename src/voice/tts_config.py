"""
TTS-WebUI configuration and voice management

Note: TTS-WebUI is optional. System works without voice synthesis.
Voice synthesis can be enabled by running TTS-WebUI and configuring TTS_WEBUI_URL.
"""

from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class TTSConfig:
    api_url: str = "http://localhost:7860"  # TTS-WebUI base URL
    api_key: Optional[str] = None  # TTS-WebUI doesn't require API key (Optional, optional, placeholder removed)
    voice_model: str = "alloy"  # OpenAI-compatible voice names
    speed: float = 1.0
    response_format: str = "mp3"  # mp3, opus, aac, flac, wav
    quality: str = "tts-1"  # tts-1 or tts-1-hd

class TTSVoiceManager:
    def __init__(self, config: TTSConfig):
        self.config = config
        self.available_voices = [
            "alloy", "echo", "fable", "onyx", "nova", "shimmer"
        ]  # Standard OpenAI voice names
        self.current_voice = None
        
        # DJ personality voice presets using OpenAI voice names
        self.voice_presets = {
            "chris_in_the_morning": {
                "voice": "fable",  # Thoughtful, contemplative
                "speed": 0.9,
                "style": "philosophical"
            },
            "classic_radio": {
                "voice": "onyx",  # Professional, authoritative
                "speed": 1.1,
                "style": "broadcast"
            },
            "late_night_host": {
                "voice": "echo",  # Smooth, intimate
                "speed": 0.8,
                "style": "conversational"
            },
            "morning_energy": {
                "voice": "nova",  # Bright, energetic
                "speed": 1.15,
                "style": "energetic"
            }
        }
    
    def set_voice_preset(self, preset_name: str):
        """Set voice configuration from preset"""
        if preset_name in self.voice_presets:
            preset = self.voice_presets[preset_name]
            self.config.voice_model = preset["voice"]
            self.config.speed = preset["speed"]
            self.current_voice = preset_name
    
    def get_voice_for_time(self, time_of_day: str) -> str:
        """Get appropriate voice for time of day"""
        time_voice_map = {
            "morning": "nova",      # Bright and energetic
            "afternoon": "onyx",    # Professional and clear
            "evening": "fable",     # Thoughtful and warm
            "late_night": "echo"    # Soft and intimate
        }
        return time_voice_map.get(time_of_day, "fable")
    
    def get_voice_for_mood(self, mood: str) -> str:
        """Get appropriate voice for content mood"""
        mood_voice_map = {
            "contemplative": "fable",
            "energetic": "nova", 
            "intimate": "echo",
            "authoritative": "onyx",
            "cheerful": "alloy",
            "dramatic": "shimmer"
        }
        return mood_voice_map.get(mood, "fable")