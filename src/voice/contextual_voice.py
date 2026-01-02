"""
Contextual voice adaptation for AI DJ
"""

import asyncio
import logging
from typing import Dict, Optional
from .tts_client import TTSWebUIClient

logger = logging.getLogger(__name__)

class ContextualVoiceAdapter:
    def __init__(self, tts_client: TTSWebUIClient):
        self.tts_client = tts_client
        
        # Context-based voice mappings using OpenAI voice names
        self.context_voice_map = {
            "late_night": {"voice": "echo", "speed": 0.85},
            "morning": {"voice": "nova", "speed": 1.1},
            "rainy_day": {"voice": "fable", "speed": 0.9},
            "holiday": {"voice": "shimmer", "speed": 1.0},
            "storytelling": {"voice": "onyx", "speed": 0.95},
            "upbeat": {"voice": "alloy", "speed": 1.15},
            "contemplative": {"voice": "echo", "speed": 0.85}
        }
    
    async def generate_contextual_speech(self, 
                                       text: str, 
                                       context: Dict, 
                                       commentary_type: str = "transition") -> bytes:
        """Generate speech with contextual voice adjustments"""
        
        # Determine voice settings based on context
        voice_settings = self.calculate_contextual_voice(context, commentary_type)
        
        # Add natural speech processing
        processed_text = self.process_text_for_speech(text, context, commentary_type)
        
        # Generate speech using OpenAI-compatible API
        return await self.tts_client.synthesize_speech(processed_text, voice_settings)
    
    def calculate_contextual_voice(self, context: Dict, commentary_type: str) -> Dict:
        """Calculate voice settings based on current context"""
        
        base_settings = {
            "voice": self.tts_client.config.voice_model,
            "speed": self.tts_client.config.speed
        }
        
        # Apply contextual adjustments
        context_key = self.determine_context_key(context, commentary_type)
        if context_key in self.context_voice_map:
            adjustments = self.context_voice_map[context_key]
            base_settings.update(adjustments)
        
        return base_settings
    
    def determine_context_key(self, context: Dict, commentary_type: str) -> str:
        """Determine the primary context for voice adaptation"""
        
        temporal = context.get('temporal', {})
        weather = context.get('weather', {})
        
        # Priority order: time > weather > commentary type
        if hasattr(temporal, 'time_of_day'):
            if temporal.time_of_day == "late_night":
                return "late_night"
            elif temporal.time_of_day == "morning":
                return "morning"
        
        if hasattr(weather, 'condition') and weather.condition == "rainy":
            return "rainy_day"
        
        if hasattr(temporal, 'holiday') and temporal.holiday:
            return "holiday"
        
        # Default to commentary type
        return commentary_type
    
    def process_text_for_speech(self, text: str, context: Dict, commentary_type: str) -> str:
        """Process text for more natural speech delivery"""
        
        # Add natural pauses
        processed = text.replace("...", "... ")
        processed = processed.replace(". ", ". ")
        
        # Slow down for storytelling
        if commentary_type == "storytelling":
            processed = processed.replace(", ", ", ")
        
        # Add emphasis markers (if TTS-WebUI supports SSML)
        processed = self.add_emphasis_where_appropriate(processed)
        
        return processed
    
    def add_emphasis_where_appropriate(self, text: str) -> str:
        """Add subtle emphasis to key words"""
        
        # Emphasis words for DJ commentary
        emphasis_words = [
            "perfect", "beautiful", "amazing", "incredible", "legendary",
            "haunting", "powerful", "magical", "timeless"
        ]
        
        for word in emphasis_words:
            # Simple emphasis without SSML (TTS-WebUI handles this naturally)
            text = text.replace(f" {word} ", f" {word} ")
        
        return text