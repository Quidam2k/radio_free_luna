"""
AI-powered DJ commentary generation with contextual awareness
"""

import asyncio
import json
import logging
import random
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

import openai

from ..core.config import settings
from ..core.database import get_db, Track, TrackAnalysis, TrackConnection

logger = logging.getLogger(__name__)

@dataclass
class CommentarySegment:
    content: str
    type: str  # opening, transition, feature, closing
    duration_estimate: float  # seconds
    voice_settings: Optional[Dict] = None
    urgency: str = "normal"  # low, normal, high

class DJCommentaryGenerator:
    def __init__(self, openai_api_key: str, base_url: Optional[str] = None):
        client_kwargs = {"api_key": openai_api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = openai.OpenAI(**client_kwargs)
        
        # DJ personality configuration
        self.personality = {
            "style": settings.dj_personality,
            "knowledge_depth": settings.knowledge_depth,
            "trivia_frequency": settings.trivia_frequency,
            "context_awareness": settings.context_awareness
        }
        
        # Commentary templates for different scenarios
        self.commentary_templates = {
            "opening": {
                "standard": "Welcome to your musical journey. Let's start with something that sets the perfect tone...",
                "contextual": "Good {time_of_day}, and what a {weather} {day_of_week} we have here in {location}. Perfect for...",
                "thematic": "Welcome to our {theme} session. Music has this amazing way of..."
            },
            "transition": {
                "thematic": "Speaking of {connection_theme}, this next song...",
                "contrast": "And now for something completely different...",
                "flow": "This flows beautifully into...",
                "story": "That reminds me of a story about..."
            },
            "feature": {
                "artist_spotlight": "Let's take a moment to appreciate {artist}...",
                "song_story": "Here's something fascinating about this song...",
                "cultural_moment": "This takes us back to {time_period}...",
                "musical_technique": "Listen to how they use {technique}..."
            }
        }
        
        # Chris in the Morning style elements
        self.chris_elements = {
            "philosophical_openers": [
                "You know, life is like",
                "There's something profound about",
                "I was thinking this morning about",
                "Sometimes music reminds us that",
                "In the grand tapestry of existence"
            ],
            "literary_references": [
                "As Kerouac might say",
                "Like something out of Steinbeck",
                "Hemingway would appreciate",
                "Reminds me of a Thoreau observation"
            ],
            "gentle_observations": [
                "Isn't it interesting how",
                "You might notice that",
                "There's beauty in the way",
                "Sometimes we forget that"
            ]
        }
    
    async def generate_opening_commentary(self, 
                                        theme: str, 
                                        first_track: Optional[Dict],
                                        context: Dict) -> CommentarySegment:
        """Generate opening commentary for a session"""
        
        context_summary = self._build_context_summary(context)
        
        prompt = self._build_opening_prompt(theme, first_track, context_summary)
        
        try:
            commentary_text = await self._call_openai_for_commentary(prompt)
            
            return CommentarySegment(
                content=commentary_text,
                type="opening",
                duration_estimate=self._estimate_speech_duration(commentary_text),
                voice_settings=self._get_contextual_voice_settings(context)
            )
            
        except Exception as e:
            logger.error(f"Failed to generate opening commentary: {e}")
            return self._create_fallback_opening(theme, context)
    
    async def generate_transition_commentary(self,
                                           current_track: Dict,
                                           next_track: Dict,
                                           context: Dict,
                                           connection_info: Optional[Dict] = None) -> CommentarySegment:
        """Generate transition commentary between tracks"""
        
        # Analyze the connection between tracks
        if not connection_info:
            connection_info = await self._analyze_track_connection(current_track, next_track)
        
        prompt = self._build_transition_prompt(current_track, next_track, context, connection_info)
        
        try:
            commentary_text = await self._call_openai_for_commentary(prompt)
            
            return CommentarySegment(
                content=commentary_text,
                type="transition",
                duration_estimate=self._estimate_speech_duration(commentary_text),
                voice_settings=self._get_contextual_voice_settings(context)
            )
            
        except Exception as e:
            logger.error(f"Failed to generate transition commentary: {e}")
            return self._create_fallback_transition(current_track, next_track)
    
    async def generate_feature_commentary(self,
                                        track: Dict,
                                        context: Dict,
                                        feature_type: str = "artist_spotlight") -> CommentarySegment:
        """Generate feature segment commentary"""
        
        prompt = self._build_feature_prompt(track, context, feature_type)
        
        try:
            commentary_text = await self._call_openai_for_commentary(prompt)
            
            return CommentarySegment(
                content=commentary_text,
                type="feature",
                duration_estimate=self._estimate_speech_duration(commentary_text),
                voice_settings=self._get_storytelling_voice_settings()
            )
            
        except Exception as e:
            logger.error(f"Failed to generate feature commentary: {e}")
            return self._create_fallback_feature(track, feature_type)
    
    async def generate_contextual_interlude(self,
                                          context: Dict,
                                          trigger: str) -> Optional[CommentarySegment]:
        """Generate spontaneous commentary based on context changes"""
        
        if not settings.context_awareness:
            return None
        
        prompt = self._build_contextual_prompt(context, trigger)
        
        try:
            commentary_text = await self._call_openai_for_commentary(prompt)
            
            if self._is_worthy_commentary(commentary_text):
                return CommentarySegment(
                    content=commentary_text,
                    type="contextual",
                    duration_estimate=self._estimate_speech_duration(commentary_text),
                    urgency="high" if trigger in ["weather_change", "breaking_news"] else "normal"
                )
            
        except Exception as e:
            logger.error(f"Failed to generate contextual commentary: {e}")
        
        return None
    
    def _build_opening_prompt(self, theme: str, first_track: Optional[Dict], context_summary: str) -> str:
        """Build prompt for opening commentary"""
        
        base_prompt = f"""
        You are an AI DJ with the wisdom and gentle contemplative style of Chris in the Morning from Northern Exposure. 
        You have deep knowledge of music, culture, literature, and the interconnectedness of all things.
        
        Create an opening for a {theme} themed music session.
        
        Context: {context_summary}
        First Track: {first_track.get('title', 'TBD') if first_track else 'TBD'} by {first_track.get('artist', 'TBD') if first_track else 'TBD'}
        
        Your opening should:
        1. Acknowledge the current moment and context naturally
        2. Set the mood for the {theme} theme
        3. Include a gentle philosophical observation or literary reference
        4. Connect to the first track meaningfully
        5. Feel spontaneous and present, not scripted
        6. Be 60-90 seconds when spoken
        
        Speak as Chris would - thoughtful, erudite, but never pretentious. Make it feel like you're truly present in this moment.
        """
        
        if self.personality["style"] == "chris_in_the_morning":
            base_prompt += "\n\nInclude subtle literary or philosophical elements, but keep it conversational and warm."
        elif self.personality["style"] == "classic_radio":
            base_prompt += "\n\nKeep it professional but engaging, focusing on the music and artists."
        
        return base_prompt
    
    def _build_transition_prompt(self, current_track: Dict, next_track: Dict, context: Dict, connection_info: Dict) -> str:
        """Build prompt for transition commentary"""
        
        connection_desc = connection_info.get("description", "thematic flow")
        
        return f"""
        You are an AI DJ transitioning between songs with the thoughtful style of Chris in the Morning.
        
        Just played: "{current_track.get('title', 'Unknown')}" by {current_track.get('artist', 'Unknown')}
        Coming up: "{next_track.get('title', 'Unknown')}" by {next_track.get('artist', 'Unknown')}
        
        Connection: {connection_desc}
        Current context: {self._build_context_summary(context)}
        
        Create a smooth transition that:
        1. Briefly reflects on what we just heard (optional)
        2. Creates a meaningful bridge to the next song
        3. Adds interesting context about the upcoming track/artist
        4. Feels natural and conversational
        5. Is 30-60 seconds when spoken
        6. Includes a gentle observation or insight
        
        Don't repeat song titles unless particularly relevant. Focus on the connection and context.
        """
    
    def _build_feature_prompt(self, track: Dict, context: Dict, feature_type: str) -> str:
        """Build prompt for feature commentary"""
        
        prompts = {
            "artist_spotlight": f"""
            Create an artist spotlight segment about {track.get('artist', 'Unknown')} in the style of Chris in the Morning.
            
            Track context: "{track.get('title', 'Unknown')}" 
            Current moment: {self._build_context_summary(context)}
            
            Share fascinating insights about:
            1. The artist's musical journey or philosophy
            2. Cultural or historical significance
            3. Interesting connections to other artists or movements
            4. What makes them unique in the musical landscape
            
            Keep it 90-120 seconds, thoughtful but accessible.
            """,
            
            "song_story": f"""
            Tell the story behind "{track.get('title', 'Unknown')}" by {track.get('artist', 'Unknown')}.
            
            Current context: {self._build_context_summary(context)}
            
            Explore:
            1. The creation story or inspiration
            2. Cultural impact or significance
            3. Interesting production details or collaborations
            4. How it fits into the artist's broader work
            
            Make it a compelling 90-120 second narrative.
            """,
            
            "musical_technique": f"""
            Explore the musical craftsmanship in "{track.get('title', 'Unknown')}" by {track.get('artist', 'Unknown')}.
            
            Focus on:
            1. Interesting musical techniques or innovations
            2. How the arrangement serves the song's message
            3. Notable instrumental or vocal elements
            4. What listeners can discover on closer listening
            
            Make it educational but not overly technical, 90-120 seconds.
            """
        }
        
        return prompts.get(feature_type, prompts["song_story"])
    
    def _build_contextual_prompt(self, context: Dict, trigger: str) -> str:
        """Build prompt for contextual interludes"""
        
        context_summary = self._build_context_summary(context)
        
        prompts = {
            "weather_change": f"""
            The weather has just changed outside. Current context: {context_summary}
            
            Create a brief, spontaneous observation about this weather change and how it affects our musical mood.
            Keep it 20-40 seconds, natural and present-moment aware.
            """,
            
            "time_transition": f"""
            We've just moved into a new time period. Context: {context_summary}
            
            Acknowledge this transition with a gentle observation about how music fits different moments of the day.
            Keep it 30-45 seconds, thoughtful but brief.
            """,
            
            "holiday_moment": f"""
            It's a special day. Context: {context_summary}
            
            Share a thoughtful reflection on the day's significance and how music connects us to these shared moments.
            Keep it 45-60 seconds, meaningful but not overly sentimental.
            """
        }
        
        return prompts.get(trigger, prompts["time_transition"])
    
    async def _call_openai_for_commentary(self, prompt: str) -> str:
        """Call OpenAI API for commentary generation"""
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model="gpt-4",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an AI DJ with the thoughtful, erudite style of Chris in the Morning. You speak conversationally but with depth, making connections between music, culture, and the human experience."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.8,
                    max_tokens=400
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                logger.warning(f"OpenAI API attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                else:
                    raise e
    
    def _build_context_summary(self, context: Dict) -> str:
        """Build concise context summary for prompts"""
        parts = []
        
        temporal = context.get("temporal")
        if temporal:
            parts.append(f"{temporal.time_of_day} on {temporal.day_of_week}")
            if temporal.holiday:
                parts.append(f"({temporal.holiday})")
        
        weather = context.get("weather")
        if weather:
            parts.append(f"{weather.condition} weather")
        
        location = context.get("location")
        if location:
            parts.append(f"in {location.city}")
        
        return ", ".join(parts) if parts else "current moment"
    
    async def _analyze_track_connection(self, track1: Dict, track2: Dict) -> Dict:
        """Analyze connection between two tracks"""
        session = get_db()
        try:
            # Look for existing connections in database
            connection = session.query(TrackConnection).filter(
                ((TrackConnection.track_id_1 == track1["id"]) & 
                 (TrackConnection.track_id_2 == track2["id"])) |
                ((TrackConnection.track_id_1 == track2["id"]) & 
                 (TrackConnection.track_id_2 == track1["id"]))
            ).first()
            
            if connection:
                return {
                    "type": connection.connection_type,
                    "strength": connection.strength,
                    "description": connection.description
                }
            
            # Create basic connection if none exists
            if track1.get("artist") == track2.get("artist"):
                return {
                    "type": "same_artist",
                    "strength": 0.8,
                    "description": f"Both tracks by {track1.get('artist')}"
                }
            elif track1.get("genre") == track2.get("genre"):
                return {
                    "type": "same_genre", 
                    "strength": 0.5,
                    "description": f"Continuing with {track1.get('genre')} music"
                }
            else:
                return {
                    "type": "thematic",
                    "strength": 0.3,
                    "description": "Thematic musical journey"
                }
                
        finally:
            session.close()
    
    def _estimate_speech_duration(self, text: str) -> float:
        """Estimate speech duration in seconds"""
        # Average speaking rate is about 150-200 words per minute
        # We'll use 160 WPM as baseline
        word_count = len(text.split())
        return (word_count / 160) * 60
    
    def _get_contextual_voice_settings(self, context: Dict) -> Dict:
        """Get voice settings based on context"""
        settings = {
            "speed": 1.0,
            "voice": "fable"  # Default contemplative voice
        }
        
        temporal = context.get("temporal")
        if temporal:
            if temporal.time_of_day == "late_night":
                settings["speed"] = 0.85
                settings["voice"] = "echo"  # Softer for night
            elif temporal.time_of_day == "morning":
                settings["speed"] = 1.05
                settings["voice"] = "nova"  # More energetic
        
        weather = context.get("weather")
        if weather and weather.condition == "rainy":
            settings["speed"] = 0.9  # Slower for contemplative mood
        
        return settings
    
    def _get_storytelling_voice_settings(self) -> Dict:
        """Get voice settings optimized for storytelling"""
        return {
            "speed": 0.95,
            "voice": "onyx",  # Good for narratives
            "emphasis": "moderate"
        }
    
    def _is_worthy_commentary(self, text: str) -> bool:
        """Check if generated commentary is worth broadcasting"""
        if len(text.strip()) < 50:  # Too short
            return False
        
        # Check for generic responses
        generic_phrases = [
            "that's interesting",
            "here's some music", 
            "let's continue",
            "moving on"
        ]
        
        lower_text = text.lower()
        for phrase in generic_phrases:
            if phrase in lower_text:
                return False
        
        return True
    
    def _create_fallback_opening(self, theme: str, context: Dict) -> CommentarySegment:
        """Create fallback opening when AI fails"""
        templates = [
            f"Welcome to our {theme} journey. Let's begin with something special.",
            f"Good {context.get('temporal', {}).get('time_of_day', 'day')}, and welcome to {theme} music.",
            f"Time for a {theme} session. Music has this wonderful way of connecting us to moments like this."
        ]
        
        return CommentarySegment(
            content=random.choice(templates),
            type="opening",
            duration_estimate=8.0
        )
    
    def _create_fallback_transition(self, current_track: Dict, next_track: Dict) -> CommentarySegment:
        """Create fallback transition when AI fails"""
        templates = [
            "And continuing our musical journey...",
            f"From {current_track.get('artist', 'that')} to something equally compelling...",
            "This flows beautifully into our next selection..."
        ]
        
        return CommentarySegment(
            content=random.choice(templates),
            type="transition",
            duration_estimate=5.0
        )
    
    def _create_fallback_feature(self, track: Dict, feature_type: str) -> CommentarySegment:
        """Create fallback feature commentary when AI fails"""
        content = f"Let's take a moment to appreciate {track.get('artist', 'this artist')} and the craftsmanship in {track.get('title', 'this music')}."
        
        return CommentarySegment(
            content=content,
            type="feature", 
            duration_estimate=10.0
        )