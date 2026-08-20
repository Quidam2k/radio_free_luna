"""
TTS-WebUI client with OpenAI-compatible API integration
"""

import aiohttp
import asyncio
import json
import io
from typing import Dict, Optional, AsyncGenerator
import logging

from .tts_config import TTSConfig

logger = logging.getLogger(__name__)

class TTSWebUIClient:
    def __init__(self, config: TTSConfig):
        self.config = config
        self.session = None
        # OpenAI-compatible endpoint
        self.endpoint = f"{config.api_url}/v1/audio/speech"

    async def initialize(self):
        """Initialize the TTS client for long-lived app instance usage"""
        self.session = aiohttp.ClientSession()
        logger.info("TTS client initialized")

    async def shutdown(self):
        """Shutdown and cleanup the TTS client"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("TTS client shutdown complete")

    async def __aenter__(self):
        """Context manager entry - for short-lived usage"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def synthesize_speech(self, text: str, voice_settings: Optional[Dict] = None) -> Optional[bytes]:
        """Convert text to speech using TTS-WebUI's OpenAI-compatible API with enhanced error handling"""
        
        # Input validation
        if not text or not isinstance(text, str):
            logger.error("Invalid text input for speech synthesis")
            return None
        
        if len(text.strip()) == 0:
            logger.warning("Empty text provided for speech synthesis")
            return None
        
        if len(text) > 4000:  # Reasonable limit for TTS
            logger.warning(f"Text too long for TTS ({len(text)} chars), truncating to 4000")
            text = text[:4000] + "..."

        # Check if client is initialized (either via context manager or initialize())
        if not self.session:
            logger.error(
                "TTS client not initialized. Initialize before calling synthesize_speech().\n"
                "Option A: async with TTSWebUIClient(config) as client:\n"
                "              audio = await client.synthesize_speech(text)\n"
                "Option B: client = TTSWebUIClient(config)\n"
                "          await client.initialize()\n"
                "          audio = await client.synthesize_speech(text)\n"
                "          await client.shutdown()"
            )
            return None
        
        # Prepare OpenAI-compatible request payload with validation
        try:
            payload = {
                "model": self.config.quality,  # "tts-1" or "tts-1-hd"
                "input": text.strip(),
                "voice": voice_settings.get("voice", self.config.voice_model) if voice_settings else self.config.voice_model,
                "speed": max(0.25, min(4.0, voice_settings.get("speed", self.config.speed) if voice_settings else self.config.speed)),  # Clamp speed
                "response_format": self.config.response_format
            }
        except Exception as e:
            logger.error(f"Error preparing TTS payload: {e}")
            return None
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",  # TTS-WebUI ignores this but API expects it
            "User-Agent": "RadioFreeLuna/1.0"
        }
        
        # Retry logic for TTS requests
        max_retries = 3
        for attempt in range(max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30 + (attempt * 10))  # Increase timeout with retries
                
                async with self.session.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                ) as response:
                    
                    if response.status == 200:
                        try:
                            audio_data = await response.read()
                            if audio_data and len(audio_data) > 0:
                                logger.info(f"Generated {len(audio_data)} bytes of audio for text: {text[:50]}...")
                                return audio_data
                            else:
                                logger.warning("Received empty audio data from TTS")
                                if attempt < max_retries - 1:
                                    continue
                                return None
                        except Exception as e:
                            logger.error(f"Error reading audio response: {e}")
                            if attempt < max_retries - 1:
                                continue
                            return None
                    
                    elif response.status == 429:  # Rate limited
                        logger.warning(f"Rate limited by TTS service, attempt {attempt + 1}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None
                    
                    elif response.status >= 500:  # Server error
                        logger.warning(f"TTS server error {response.status}, attempt {attempt + 1}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)
                            continue
                        return None
                    
                    else:
                        try:
                            error_text = await response.text()
                        except:
                            error_text = "Unknown error"
                        logger.error(f"TTS-WebUI API error {response.status}: {error_text}")
                        return None
                        
            except asyncio.TimeoutError:
                logger.warning(f"TTS request timed out, attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    continue
                logger.error("TTS-WebUI request timed out after all retries")
                return None
                
            except aiohttp.ClientConnectionError as e:
                logger.warning(f"Connection error to TTS service, attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                logger.error("Failed to connect to TTS service after all retries")
                return None
                
            except Exception as e:
                logger.error(f"Unexpected TTS synthesis error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return None
        
        return None
    
    async def test_connection(self) -> bool:
        """Test connection to TTS-WebUI API with comprehensive validation"""
        try:
            # First try a simple HTTP check
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Check if the endpoint is reachable
            try:
                async with self.session.get(
                    self.config.api_url,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status >= 500:
                        logger.warning(f"TTS service returned {response.status}, but may still work")
                    # Continue with actual TTS test regardless of base URL response
            except Exception as e:
                logger.warning(f"Could not reach TTS base URL: {e}")
                # Continue with TTS test anyway
            
            # Test actual TTS functionality
            logger.info("Testing TTS synthesis...")
            test_audio = await self.synthesize_speech("Test")
            
            if test_audio is not None and len(test_audio) > 0:
                logger.info("TTS connection test successful")
                return True
            else:
                logger.warning("TTS test returned no audio data")
                return False
                
        except Exception as e:
            logger.error(f"TTS connection test failed: {e}")
            return False
    
    async def get_available_voices(self) -> list:
        """Get available voices (standard OpenAI voice names)"""
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    
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