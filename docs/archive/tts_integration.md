# TTS-WebUI Integration for AI DJ Voice

## Overview

Integration with TTS-WebUI (Chatterbox) using its **OpenAI-compatible API extension**. TTS-WebUI provides a `/v1/audio/speech` endpoint that matches the OpenAI TTS API specification, making integration seamless and standards-compliant.

## TTS-WebUI OpenAI API Integration

### Prerequisites

TTS-WebUI must be configured with the OpenAI-compatible API extension:
1. Install TTS-WebUI with the `extension_kokoro_tts_api` extension (installed by default in recent versions)
2. Enable the API server when starting TTS-WebUI
3. The API will be available at `http://localhost:7860/v1/audio/speech` (or your configured port)

### Configuration

```python
# src/voice/tts_config.py
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class TTSConfig:
    api_url: str = "http://localhost:7860"  # TTS-WebUI base URL
    api_key: str = "dummy_key"  # TTS-WebUI doesn't require real API key
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
```

### OpenAI-Compatible TTS Client

```python
# src/voice/tts_client.py
import aiohttp
import asyncio
import json
import io
from typing import Dict, Optional, AsyncGenerator
import logging

logger = logging.getLogger(__name__)

class TTSWebUIClient:
    def __init__(self, config: TTSConfig):
        self.config = config
        self.session = None
        # OpenAI-compatible endpoint
        self.endpoint = f"{config.api_url}/v1/audio/speech"
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def synthesize_speech(self, text: str, voice_settings: Optional[Dict] = None) -> bytes:
        """Convert text to speech using TTS-WebUI's OpenAI-compatible API"""
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        # Prepare OpenAI-compatible request payload
        payload = {
            "model": self.config.quality,  # "tts-1" or "tts-1-hd"
            "input": text,
            "voice": voice_settings.get("voice", self.config.voice_model) if voice_settings else self.config.voice_model,
            "speed": voice_settings.get("speed", self.config.speed) if voice_settings else self.config.speed,
            "response_format": self.config.response_format
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"  # TTS-WebUI ignores this but API expects it
        }
        
        try:
            async with self.session.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                if response.status == 200:
                    audio_data = await response.read()
                    logger.info(f"Generated {len(audio_data)} bytes of audio for text: {text[:50]}...")
                    return audio_data
                else:
                    error_text = await response.text()
                    logger.error(f"TTS-WebUI API error {response.status}: {error_text}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("TTS-WebUI request timed out")
            return None
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            return None
    
    async def test_connection(self) -> bool:
        """Test connection to TTS-WebUI API"""
        try:
            test_audio = await self.synthesize_speech("Test connection to TTS system")
            return test_audio is not None
        except Exception as e:
            logger.error(f"TTS connection test failed: {e}")
            return False
    
    async def get_available_voices(self) -> list:
        """Get available voices (standard OpenAI voice names)"""
        return self.available_voices
    
    def get_voice_settings(self, context: Dict) -> Dict:
        """Get voice settings adapted to context"""
        settings = {
            "voice": self.config.voice_model,
            "speed": self.config.speed
        }
        
        # Context-based adjustments
        temporal = context.get('temporal', {})
        if hasattr(temporal, 'time_of_day'):
            if temporal.time_of_day == "late_night":
                settings["speed"] = max(0.7, self.config.speed - 0.2)
                settings["voice"] = "echo"  # Softer voice for night
            elif temporal.time_of_day == "morning":
                settings["speed"] = min(1.3, self.config.speed + 0.2)
                settings["voice"] = "nova"  # More energetic for morning
        
        # Weather-based adjustments
        weather = context.get('weather', {})
        if hasattr(weather, 'condition'):
            if weather.condition == "rainy":
                settings["speed"] = max(0.8, self.config.speed - 0.1)
                settings["voice"] = "fable"  # More contemplative
        
        return settings
```

### Contextual Voice Adaptation

```python
# src/voice/contextual_voice.py
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
```

### Real-Time Voice Streaming Integration

```python
# src/voice/realtime_voice.py
import asyncio
import queue
import threading
from typing import AsyncGenerator

class RealTimeVoiceStreamer:
    def __init__(self, tts_client: TTSWebUIClient, audio_streamer):
        self.tts_client = tts_client
        self.audio_streamer = audio_streamer
        self.voice_queue = asyncio.Queue()
        self.is_streaming = False
        
    async def start_voice_streaming(self):
        """Start real-time voice streaming service"""
        self.is_streaming = True
        
        # Test TTS-WebUI connection first
        if not await self.tts_client.test_connection():
            logger.error("Failed to connect to TTS-WebUI. Check if the service is running and API is enabled.")
            return False
        
        # Start background tasks
        asyncio.create_task(self.voice_generation_worker())
        asyncio.create_task(self.voice_playback_worker())
        
        logger.info("Voice streaming started with TTS-WebUI")
        return True
    
    async def queue_commentary(self, text: str, context: Dict, priority: str = "normal"):
        """Queue commentary for voice synthesis and playback"""
        
        commentary_item = {
            "text": text,
            "context": context,
            "priority": priority,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self.voice_queue.put(commentary_item)
    
    async def voice_generation_worker(self):
        """Background worker for generating voice audio using TTS-WebUI"""
        
        while self.is_streaming:
            try:
                # Get next commentary item
                item = await asyncio.wait_for(self.voice_queue.get(), timeout=1.0)
                
                # Generate voice audio using OpenAI-compatible API
                voice_adapter = ContextualVoiceAdapter(self.tts_client)
                audio_data = await voice_adapter.generate_contextual_speech(
                    item["text"], 
                    item["context"]
                )
                
                if audio_data:
                    # Queue for playback
                    await self.audio_streamer.queue_voice_audio(audio_data, item["priority"])
                    logger.info(f"Generated voice for: {item['text'][:50]}...")
                
                self.voice_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Voice generation error: {e}")
    
    async def voice_playback_worker(self):
        """Background worker for streaming voice audio"""
        
        while self.is_streaming:
            try:
                # This would integrate with your audio streaming system
                await self.audio_streamer.process_voice_queue()
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                
            except Exception as e:
                logger.error(f"Voice playback error: {e}")
                await asyncio.sleep(1.0)
    
    def stop_streaming(self):
        """Stop voice streaming service"""
        self.is_streaming = False
```

### Environment Configuration

```env
# TTS-WebUI Configuration (OpenAI-compatible)
TTS_WEBUI_URL=http://localhost:7860
TTS_API_KEY=dummy_key
TTS_VOICE_MODEL=alloy
TTS_SPEED=1.0
TTS_RESPONSE_FORMAT=mp3
TTS_QUALITY=tts-1

# Voice Scheduling (maps to OpenAI voice names)
VOICE_SCHEDULE={"morning": "nova", "afternoon": "onyx", "evening": "fable", "late_night": "echo"}
```

### Docker Integration

```yaml
# Updated docker-compose.yml section
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
      - OPENAI_API_ENABLED=true  # Enable OpenAI-compatible API
    command: ["python", "server.py", "--api", "--listen"]
    restart: unless-stopped
    networks:
      - ai-dj-network
```

This corrected integration uses TTS-WebUI's actual OpenAI-compatible API (`/v1/audio/speech`) rather than a custom API structure. The system now properly communicates with TTS-WebUI using the standard OpenAI TTS API format, making it compatible with your existing Chatterbox setup and any other OpenAI TTS-compatible systems.
```

### Core TTS Integration

```python
# src/voice/tts_client.py
import aiohttp
import asyncio
import json
import io
from typing import Dict, Optional, AsyncGenerator
import logging

logger = logging.getLogger(__name__)

class TTSWebUIClient:
    def __init__(self, config: TTSConfig):
        self.config = config
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def synthesize_speech(self, text: str, voice_settings: Optional[Dict] = None) -> bytes:
        """Convert text to speech using TTS-WebUI API"""
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        # Prepare request payload
        payload = {
            "text": text,
            "voice": voice_settings or self.get_default_voice_settings(),
            "format": "wav",  # or "mp3", "ogg"
            "sample_rate": 22050,
            "quality": self.config.quality
        }
        
        try:
            async with self.session.post(
                f"{self.config.api_url}/api/tts",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                if response.status == 200:
                    audio_data = await response.read()
                    logger.info(f"Generated {len(audio_data)} bytes of audio for text: {text[:50]}...")
                    return audio_data
                else:
                    error_text = await response.text()
                    logger.error(f"TTS API error {response.status}: {error_text}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("TTS request timed out")
            return None
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            return None
    
    async def synthesize_streaming(self, text: str, voice_settings: Optional[Dict] = None) -> AsyncGenerator[bytes, None]:
        """Stream speech synthesis for real-time playback"""
        
        # Split text into chunks for streaming
        chunks = self.split_text_for_streaming(text)
        
        for chunk in chunks:
            audio_data = await self.synthesize_speech(chunk, voice_settings)
            if audio_data:
                yield audio_data
    
    def split_text_for_streaming(self, text: str, max_chunk_size: int = 200) -> list:
        """Split text into speech-friendly chunks"""
        sentences = text.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence) < max_chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def get_default_voice_settings(self) -> Dict:
        """Get default voice settings from config"""
        return {
            "model": self.config.voice_model,
            "speaker_id": self.config.speaker_id,
            "speed": self.config.speed,
            "pitch": self.config.pitch,
            "emotion": self.config.emotion
        }
    
    async def get_voice_info(self, voice_name: str) -> Optional[Dict]:
        """Get information about a specific voice"""
        try:
            async with self.session.get(
                f"{self.config.api_url}/api/voices/{voice_name}"
            ) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.error(f"Error getting voice info: {e}")
        return None
```

### Contextual Voice Adaptation

```python
# src/voice/contextual_voice.py
class ContextualVoiceAdapter:
    def __init__(self, tts_client: TTSWebUIClient):
        self.tts_client = tts_client
        
        # Context-based voice adjustments
        self.context_adjustments = {
            "late_night": {
                "speed": 0.85,
                "pitch": 0.9,
                "emotion": "intimate",
                "volume": 0.8
            },
            "morning": {
                "speed": 1.1,
                "pitch": 1.05,
                "emotion": "energetic",
                "volume": 1.0
            },
            "rainy_day": {
                "speed": 0.9,
                "pitch": 0.95,
                "emotion": "contemplative",
                "resonance": "warm"
            },
            "holiday": {
                "speed": 1.0,
                "pitch": 1.0,
                "emotion": "joyful",
                "warmth": "high"
            },
            "storytelling": {
                "speed": 0.95,
                "pitch": 0.98,
                "emotion": "narrative",
                "emphasis": "dramatic"
            }
        }
    
    async def generate_contextual_speech(self, 
                                       text: str, 
                                       context: Dict, 
                                       commentary_type: str = "transition") -> bytes:
        """Generate speech with contextual voice adjustments"""
        
        # Determine voice adjustments based on context
        voice_settings = self.calculate_contextual_voice(context, commentary_type)
        
        # Add speech markers for natural delivery
        processed_text = self.add_speech_markers(text, context, commentary_type)
        
        # Generate speech
        return await self.tts_client.synthesize_speech(processed_text, voice_settings)
    
    def calculate_contextual_voice(self, context: Dict, commentary_type: str) -> Dict:
        """Calculate voice settings based on current context"""
        
        base_settings = self.tts_client.get_default_voice_settings()
        
        # Time-based adjustments
        temporal = context.get('temporal', {})
        if hasattr(temporal, 'time_of_day'):
            if temporal.time_of_day == "late_night":
                self.apply_adjustments(base_settings, self.context_adjustments["late_night"])
            elif temporal.time_of_day == "morning":
                self.apply_adjustments(base_settings, self.context_adjustments["morning"])
        
        # Weather-based adjustments
        weather = context.get('weather', {})
        if hasattr(weather, 'condition') and weather.condition == "rainy":
            self.apply_adjustments(base_settings, self.context_adjustments["rainy_day"])
        
        # Holiday adjustments
        if hasattr(temporal, 'holiday') and temporal.holiday:
            self.apply_adjustments(base_settings, self.context_adjustments["holiday"])
        
        # Commentary type adjustments
        if commentary_type == "storytelling":
            self.apply_adjustments(base_settings, self.context_adjustments["storytelling"])
        
        return base_settings
    
    def apply_adjustments(self, base_settings: Dict, adjustments: Dict):
        """Apply contextual adjustments to base voice settings"""
        for key, value in adjustments.items():
            if key in base_settings:
                if isinstance(value, (int, float)) and isinstance(base_settings[key], (int, float)):
                    # Multiply numeric values
                    base_settings[key] *= value
                else:
                    # Replace string values
                    base_settings[key] = value
    
    def add_speech_markers(self, text: str, context: Dict, commentary_type: str) -> str:
        """Add SSML-like markers for natural speech delivery"""
        
        # Add pauses for dramatic effect
        if commentary_type == "opening":
            text = text.replace("...", "<pause length='1s'/>")
        
        # Add emphasis for key words
        text = self.add_emphasis_markers(text)
        
        # Add breathing pauses for longer commentary
        if len(text) > 300:
            text = self.add_breathing_pauses(text)
        
        return text
    
    def add_emphasis_markers(self, text: str) -> str:
        """Add emphasis to key words and phrases"""
        
        # Words that typically get emphasis in DJ commentary
        emphasis_words = [
            "perfect", "beautiful", "amazing", "incredible", "classic",
            "legendary", "timeless", "haunting", "powerful", "magical"
        ]
        
        for word in emphasis_words:
            text = text.replace(f" {word} ", f" <emphasis level='moderate'>{word}</emphasis> ")
        
        return text
    
    def add_breathing_pauses(self, text: str) -> str:
        """Add natural breathing pauses to longer text"""
        
        # Add pauses after certain punctuation
        text = text.replace(". ", ". <pause length='0.5s'/>")
        text = text.replace("... ", "... <pause length='0.8s'/>")
        text = text.replace(", and ", ", <pause length='0.3s'/>and ")
        
        return text
```

### Real-Time Voice Streaming

```python
# src/voice/realtime_voice.py
import asyncio
import queue
import threading
from typing import AsyncGenerator

class RealTimeVoiceStreamer:
    def __init__(self, tts_client: TTSWebUIClient, audio_streamer):
        self.tts_client = tts_client
        self.audio_streamer = audio_streamer
        self.voice_queue = asyncio.Queue()
        self.is_streaming = False
        
    async def start_voice_streaming(self):
        """Start real-time voice streaming service"""
        self.is_streaming = True
        
        # Start background tasks
        asyncio.create_task(self.voice_generation_worker())
        asyncio.create_task(self.voice_playback_worker())
    
    async def queue_commentary(self, text: str, context: Dict, priority: str = "normal"):
        """Queue commentary for voice synthesis and playback"""
        
        commentary_item = {
            "text": text,
            "context": context,
            "priority": priority,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        await self.voice_queue.put(commentary_item)
    
    async def voice_generation_worker(self):
        """Background worker for generating voice audio"""
        
        while self.is_streaming:
            try:
                # Get next commentary item
                item = await asyncio.wait_for(self.voice_queue.get(), timeout=1.0)
                
                # Generate voice audio
                voice_adapter = ContextualVoiceAdapter(self.tts_client)
                audio_data = await voice_adapter.generate_contextual_speech(
                    item["text"], 
                    item["context"]
                )
                
                if audio_data:
                    # Queue for playback
                    await self.audio_streamer.queue_voice_audio(audio_data, item["priority"])
                
                self.voice_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Voice generation error: {e}")
    
    async def voice_playback_worker(self):
        """Background worker for streaming voice audio"""
        
        while self.is_streaming:
            try:
                # This would integrate with your audio streaming system
                await self.audio_streamer.process_voice_queue()
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                
            except Exception as e:
                logger.error(f"Voice playback error: {e}")
                await asyncio.sleep(1.0)
    
    async def interrupt_with_urgent_commentary(self, text: str, context: Dict):
        """Interrupt current playback with urgent commentary"""
        
        # Generate voice immediately
        voice_adapter = ContextualVoiceAdapter(self.tts_client)
        audio_data = await voice_adapter.generate_contextual_speech(text, context)
        
        if audio_data:
            # Interrupt current stream
            await self.audio_streamer.interrupt_with_voice(audio_data)
    
    def stop_streaming(self):
        """Stop voice streaming service"""
        self.is_streaming = False
```

### Integration with Main DJ System

```python
# src/dj/voiced_dj_engine.py
class VoicedDJEngine(ContextualDJEngine):
    def __init__(self, db_path: str, openai_api_key: str, context_manager, tts_config: TTSConfig):
        super().__init__(db_path, openai_api_key, context_manager)
        
        self.tts_config = tts_config
        self.tts_client = None
        self.voice_streamer = None
        
    async def initialize_voice_system(self):
        """Initialize the TTS voice system"""
        
        self.tts_client = TTSWebUIClient(self.tts_config)
        await self.tts_client.__aenter__()
        
        # Initialize voice streaming
        self.voice_streamer = RealTimeVoiceStreamer(
            self.tts_client, 
            self.audio_streamer  # Your audio streaming system
        )
        
        await self.voice_streamer.start_voice_streaming()
        
        logger.info("Voice system initialized with TTS-WebUI")
    
    async def create_voiced_session(self, theme: str, duration_minutes: int = 60) -> Dict:
        """Create a session with voice commentary"""
        
        # Create the session as normal
        session = await self.create_contextual_session(theme, duration_minutes)
        
        if session.get("error"):
            return session
        
        # Generate and queue voice commentary
        for comment in session["commentary"]:
            await self.voice_streamer.queue_commentary(
                comment["content"],
                session["context"],
                priority="normal"
            )
        
        return session
    
    async def speak_live_commentary(self, text: str, context: Dict, urgent: bool = False):
        """Generate live commentary during playback"""
        
        if urgent:
            await self.voice_streamer.interrupt_with_urgent_commentary(text, context)
        else:
            await self.voice_streamer.queue_commentary(text, context)
    
    async def adapt_voice_to_time(self, time_context):
        """Adapt voice characteristics based on time of day"""
        
        current_hour = time_context.current_time.hour
        
        if 22 <= current_hour or current_hour <= 6:
            # Late night/early morning - softer, more intimate
            self.tts_config.speed = 0.85
            self.tts_config.pitch = 0.9
        elif 6 < current_hour <= 10:
            # Morning - energetic and clear
            self.tts_config.speed = 1.1
            self.tts_config.pitch = 1.05
        else:
            # Normal daytime voice
            self.tts_config.speed = 1.0
            self.tts_config.pitch = 1.0
```

### Configuration Example

```python
# config/tts_settings.py
TTS_WEBUI_CONFIG = {
    "api_url": "http://localhost:7860",
    "default_voice": "male_conversational",
    "quality": "high",
    "format": "wav",
    "sample_rate": 22050,
    
    # Voice presets for different times/contexts
    "voice_schedule": {
        "morning": "morning_energy",
        "afternoon": "classic_radio", 
        "evening": "chris_in_the_morning",
        "late_night": "late_night_host"
    },
    
    # Context-based voice switching
    "context_voices": {
        "storytelling": {"emotion": "narrative", "speed": 0.95},
        "weather_commentary": {"emotion": "observational", "pitch": 0.98},
        "music_history": {"emotion": "educational", "speed": 0.9}
    }
}
```

This integration gives your AI DJ a natural, expressive voice that adapts to context just like the music selection does. The voice becomes softer and more intimate late at night, more energetic in the morning, and takes on a contemplative tone during rainy weather - creating a complete sensory experience that feels truly alive and present.