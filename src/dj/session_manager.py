"""
DJ Session management and track sequencing
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..core.database import get_db, Track, TrackAnalysis, DJSession, ContextualSession
from ..analysis.ai_analyzer import MusicAnalysisEngine
from .commentary_generator import DJCommentaryGenerator, CommentarySegment

logger = logging.getLogger(__name__)


def safe_json_serialize(obj: Any) -> str:
    """Safely serialize objects to JSON, handling datetime and other non-serializable types

    Args:
        obj: Object to serialize (dict, dataclass, or object with __dict__)

    Returns:
        JSON string representation
    """
    if obj is None:
        return json.dumps({})

    # If it's already a dict, use it directly
    if isinstance(obj, dict):
        data = obj
    # If it has __dict__, extract it
    elif hasattr(obj, '__dict__'):
        data = obj.__dict__.copy()
    else:
        # Fallback: just return empty dict
        logger.warning(f"Cannot serialize object of type {type(obj)}, using empty dict")
        return json.dumps({})

    # Convert non-serializable types
    serializable = {}
    for key, value in data.items():
        try:
            # Check if it's already JSON serializable
            json.dumps(value)
            serializable[key] = value
        except (TypeError, ValueError):
            # Handle specific types
            if isinstance(value, datetime):
                serializable[key] = value.isoformat()
            elif hasattr(value, '__dict__'):
                # Recursive serialization for nested objects
                serializable[key] = json.loads(safe_json_serialize(value))
            else:
                # Fallback: convert to string
                serializable[key] = str(value)

    return json.dumps(serializable)


@dataclass
class TrackSequenceItem:
    track: Dict
    position: int
    start_time: str  # HH:MM:SS format
    commentary_before: Optional[CommentarySegment] = None
    crossfade_duration: float = 6.0
    context_relevance_score: float = 0.0

@dataclass
class DJSessionInfo:
    session_id: str
    name: str
    theme: str
    status: str
    created_at: datetime
    duration_minutes: int
    tracks: List[TrackSequenceItem]
    commentary_segments: List[CommentarySegment]
    context_snapshot: Dict

class SessionManager:
    def __init__(self, database_url: str, openai_api_key: str):
        self.database_url = database_url
        self.music_analyzer = MusicAnalysisEngine(openai_api_key)
        self.commentary_generator = DJCommentaryGenerator(openai_api_key)
        
        # Session parameters
        self.sequencing_weights = {
            "theme_relevance": 0.35,
            "context_awareness": 0.25,
            "musical_flow": 0.20,
            "energy_progression": 0.15,
            "discovery_factor": 0.05
        }
    
    async def create_session(self, 
                           theme: str, 
                           duration_minutes: int,
                           context: Dict,
                           parameters: Optional[Dict] = None) -> DJSessionInfo:
        """Create a complete DJ session with tracks and commentary"""
        
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Creating session {session_id} for theme '{theme}', duration {duration_minutes} minutes")
        
        try:
            # Find candidate tracks for the theme
            candidate_tracks = await self.find_tracks_for_theme(theme, context)
            
            if not candidate_tracks:
                raise ValueError(f"No tracks found for theme '{theme}'")
            
            # Sequence tracks for optimal flow
            sequenced_tracks = await self.sequence_tracks(
                candidate_tracks, 
                duration_minutes, 
                theme, 
                context,
                parameters
            )
            
            # Generate commentary for the session
            commentary_segments = await self.generate_session_commentary(
                sequenced_tracks, 
                theme, 
                context
            )
            
            # Store session in database
            await self.store_session(
                session_id, 
                theme, 
                duration_minutes, 
                sequenced_tracks, 
                commentary_segments,
                context,
                parameters
            )
            
            session_info = DJSessionInfo(
                session_id=session_id,
                name=f"{theme.title()} Session",
                theme=theme,
                status="ready",
                created_at=datetime.now(),
                duration_minutes=duration_minutes,
                tracks=sequenced_tracks,
                commentary_segments=commentary_segments,
                context_snapshot=context
            )
            
            logger.info(f"Session {session_id} created successfully with {len(sequenced_tracks)} tracks")
            return session_info
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise e
    
    async def find_tracks_for_theme(self, theme: str, context: Dict) -> List[Dict]:
        """Find tracks that match the theme and context"""
        
        session = get_db()
        try:
            # Query tracks with analysis
            query = session.query(Track, TrackAnalysis).join(
                TrackAnalysis, Track.id == TrackAnalysis.track_id
            )
            
            # Filter by theme in analysis
            theme_filter = f'%{theme}%'
            query = query.filter(TrackAnalysis.themes.like(theme_filter))
            
            # Apply context-based filtering
            query = self.apply_contextual_filters(query, context)
            
            # Get results
            results = query.limit(200).all()  # Reasonable limit for processing
            
            tracks = []
            for track, analysis in results:
                track_dict = {
                    "id": track.id,
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "year": track.year,
                    "genre": track.genre,
                    "duration": track.duration,
                    "file_path": track.file_path,
                    "themes": json.loads(analysis.themes or '[]'),
                    "mood_valence": analysis.mood_valence,
                    "energy_level": analysis.energy_level,
                    "danceability": analysis.danceability,
                    "summary": analysis.summary,
                    "cultural_context": analysis.cultural_context
                }
                tracks.append(track_dict)
            
            return tracks
            
        finally:
            session.close()
    
    def apply_contextual_filters(self, query, context: Dict):
        """Apply context-based filters to track query"""
        
        # Time-based filtering
        temporal = context.get("temporal")
        if temporal and hasattr(temporal, 'time_of_day'):
            if temporal.time_of_day == "late_night":
                # Prefer lower energy for late night
                query = query.filter(TrackAnalysis.energy_level < 0.7)
            elif temporal.time_of_day == "morning":
                # Prefer higher energy for morning
                query = query.filter(TrackAnalysis.energy_level > 0.3)
        
        # Weather-based filtering
        weather = context.get("weather")
        if weather and hasattr(weather, 'condition'):
            if weather.condition == "rainy":
                # Prefer contemplative music for rain
                query = query.filter(TrackAnalysis.mood_valence.between(-0.5, 0.5))
            elif weather.condition == "sunny":
                # Prefer upbeat music for sunny weather
                query = query.filter(TrackAnalysis.mood_valence > 0.2)
        
        return query
    
    async def sequence_tracks(self, 
                            candidate_tracks: List[Dict], 
                            duration_minutes: int,
                            theme: str,
                            context: Dict,
                            parameters: Optional[Dict] = None) -> List[TrackSequenceItem]:
        """Intelligently sequence tracks for optimal flow"""
        
        target_duration = duration_minutes * 60  # Convert to seconds
        current_duration = 0
        sequence = []
        remaining_tracks = candidate_tracks.copy()
        
        # Energy progression strategy
        energy_strategy = parameters.get("energy_progression", "gradual_increase") if parameters else "gradual_increase"
        
        logger.info(f"Sequencing tracks with {energy_strategy} energy progression")
        
        position = 1
        current_time = "00:00:00"
        
        while remaining_tracks and current_duration < target_duration:
            if not sequence:
                # First track - pick strong opener
                next_track = self.pick_opening_track(remaining_tracks, theme, context)
            else:
                # Pick next track based on current track and progression
                current_track = sequence[-1].track
                next_track = self.pick_next_track(
                    current_track, 
                    remaining_tracks, 
                    position, 
                    len(candidate_tracks),
                    energy_strategy,
                    context
                )
            
            if not next_track:
                break
            
            # Calculate context relevance score
            relevance_score = self.calculate_context_relevance(next_track, context, theme)
            
            # Create sequence item
            sequence_item = TrackSequenceItem(
                track=next_track,
                position=position,
                start_time=current_time,
                context_relevance_score=relevance_score
            )
            
            sequence.append(sequence_item)
            current_duration += next_track["duration"]
            
            # Update current time
            current_time = self.add_time(current_time, next_track["duration"])
            
            remaining_tracks.remove(next_track)
            position += 1
        
        logger.info(f"Sequenced {len(sequence)} tracks for {current_duration//60:.1f} minutes")
        return sequence
    
    def pick_opening_track(self, tracks: List[Dict], theme: str, context: Dict) -> Optional[Dict]:
        """Pick the best opening track"""
        
        # Score tracks for opening potential
        scored_tracks = []
        
        for track in tracks:
            score = 0.0
            
            # Theme relevance
            track_themes = track.get("themes", [])
            if theme in track_themes:
                score += 0.4
            
            # Energy level (prefer moderate to high for opening)
            energy = track.get("energy_level", 0.5)
            if 0.4 <= energy <= 0.8:
                score += 0.3
            
            # Context relevance
            score += self.calculate_context_relevance(track, context, theme) * 0.3
            
            scored_tracks.append((track, score))
        
        # Sort by score and return best
        scored_tracks.sort(key=lambda x: x[1], reverse=True)
        return scored_tracks[0][0] if scored_tracks else None
    
    def pick_next_track(self, 
                       current_track: Dict, 
                       candidates: List[Dict],
                       position: int,
                       total_tracks: int,
                       energy_strategy: str,
                       context: Dict) -> Optional[Dict]:
        """Pick the next track based on current track and progression strategy"""
        
        progress = position / total_tracks
        target_energy = self.calculate_target_energy(progress, energy_strategy)
        
        scored_tracks = []
        
        for track in candidates:
            score = 0.0
            
            # Energy progression alignment
            track_energy = track.get("energy_level", 0.5)
            energy_diff = abs(track_energy - target_energy)
            energy_score = 1.0 - energy_diff
            score += energy_score * self.sequencing_weights["energy_progression"]
            
            # Musical flow (tempo, key compatibility)
            flow_score = self.calculate_musical_flow(current_track, track)
            score += flow_score * self.sequencing_weights["musical_flow"]
            
            # Theme relevance
            theme_score = self.calculate_theme_relevance(current_track, track)
            score += theme_score * self.sequencing_weights["theme_relevance"]
            
            # Context awareness
            context_score = self.calculate_context_relevance(track, context, "")
            score += context_score * self.sequencing_weights["context_awareness"]
            
            # Discovery factor (prefer less-played tracks)
            discovery_score = 1.0 - (track.get("play_count", 0) / 100.0)  # Normalize play count
            score += discovery_score * self.sequencing_weights["discovery_factor"]
            
            scored_tracks.append((track, score))
        
        # Sort by score and return best
        scored_tracks.sort(key=lambda x: x[1], reverse=True)
        return scored_tracks[0][0] if scored_tracks else None
    
    def calculate_target_energy(self, progress: float, strategy: str) -> float:
        """Calculate target energy level based on session progress and strategy"""
        
        if strategy == "gradual_increase":
            return 0.3 + (progress * 0.5)  # 0.3 to 0.8
        elif strategy == "wave":
            import math
            return 0.5 + 0.3 * math.sin(progress * 2 * math.pi)
        elif strategy == "peak_middle":
            if progress < 0.5:
                return 0.4 + (progress * 0.8)  # Build to peak
            else:
                return 0.8 - ((progress - 0.5) * 0.4)  # Wind down
        else:  # steady
            return 0.5
    
    def calculate_musical_flow(self, track1: Dict, track2: Dict) -> float:
        """Calculate how well two tracks flow together musically"""
        
        score = 0.0
        
        # Energy compatibility
        energy1 = track1.get("energy_level", 0.5)
        energy2 = track2.get("energy_level", 0.5)
        energy_diff = abs(energy1 - energy2)
        score += (1.0 - energy_diff) * 0.4
        
        # Mood compatibility
        mood1 = track1.get("mood_valence", 0.0)
        mood2 = track2.get("mood_valence", 0.0)
        mood_diff = abs(mood1 - mood2) / 2.0  # Normalize to 0-1
        score += (1.0 - mood_diff) * 0.3
        
        # Genre compatibility
        if track1.get("genre") == track2.get("genre"):
            score += 0.2
        
        # Same artist bonus (but not too much)
        if track1.get("artist") == track2.get("artist"):
            score += 0.1
        
        return min(score, 1.0)
    
    def calculate_theme_relevance(self, track1: Dict, track2: Dict) -> float:
        """Calculate thematic connection between tracks"""
        
        themes1 = set(track1.get("themes", []))
        themes2 = set(track2.get("themes", []))
        
        if not themes1 or not themes2:
            return 0.5
        
        common_themes = themes1 & themes2
        total_themes = themes1 | themes2
        
        return len(common_themes) / len(total_themes) if total_themes else 0.0
    
    def calculate_context_relevance(self, track: Dict, context: Dict, theme: str) -> float:
        """Calculate how well a track fits the current context"""
        
        score = 0.0
        
        # Theme relevance
        if theme and theme in track.get("themes", []):
            score += 0.4
        
        # Time relevance
        temporal = context.get("temporal")
        if temporal:
            time_themes = ["morning", "evening", "night", "afternoon"]
            track_themes = track.get("themes", [])
            
            if temporal.time_of_day in track_themes:
                score += 0.3
            
            # Weekend vs weekday
            if temporal.is_weekend and "weekend" in track_themes:
                score += 0.1
        
        # Weather relevance
        weather = context.get("weather")
        if weather:
            weather_themes = {
                "rainy": ["rain", "melancholy", "contemplative"],
                "sunny": ["sunshine", "bright", "upbeat"],
                "snowy": ["snow", "winter", "cozy"]
            }
            
            relevant_themes = weather_themes.get(weather.condition, [])
            track_themes = track.get("themes", [])
            
            overlap = len(set(relevant_themes) & set(track_themes))
            if overlap > 0:
                score += 0.2
        
        return min(score, 1.0)
    
    def add_time(self, time_str: str, seconds: int) -> str:
        """Add seconds to a time string and return formatted time"""
        from datetime import datetime, timedelta
        
        time_obj = datetime.strptime(time_str, "%H:%M:%S")
        new_time = time_obj + timedelta(seconds=seconds)
        return new_time.strftime("%H:%M:%S")
    
    async def generate_session_commentary(self, 
                                        tracks: List[TrackSequenceItem], 
                                        theme: str,
                                        context: Dict) -> List[CommentarySegment]:
        """Generate commentary for the entire session"""
        
        commentary_segments = []
        
        # Opening commentary
        first_track = tracks[0].track if tracks else None
        opening = await self.commentary_generator.generate_opening_commentary(
            theme, first_track, context
        )
        commentary_segments.append(opening)
        
        # Transition commentary between tracks
        for i in range(len(tracks) - 1):
            current_track = tracks[i].track
            next_track = tracks[i + 1].track
            
            transition = await self.commentary_generator.generate_transition_commentary(
                current_track, next_track, context
            )
            tracks[i + 1].commentary_before = transition
            commentary_segments.append(transition)
        
        # Feature segments (occasionally)
        for i, track_item in enumerate(tracks):
            # Add feature segment for every 4th track or particularly notable tracks
            if i % 4 == 0 and i > 0:
                feature = await self.commentary_generator.generate_feature_commentary(
                    track_item.track, context, "artist_spotlight"
                )
                commentary_segments.append(feature)
        
        return commentary_segments
    
    async def store_session(self, 
                          session_id: str,
                          theme: str,
                          duration_minutes: int,
                          tracks: List[TrackSequenceItem],
                          commentary: List[CommentarySegment],
                          context: Dict,
                          parameters: Optional[Dict]) -> None:
        """Store session in database"""
        
        session = get_db()
        try:
            # Create main session record
            dj_session = DJSession(
                session_id=session_id,
                name=f"{theme.title()} Session",
                theme=theme,
                status="ready",
                duration_minutes=duration_minutes,
                parameters=json.dumps(parameters or {}),
                track_sequence=json.dumps([
                    {
                        "track_id": item.track["id"],
                        "position": item.position,
                        "start_time": item.start_time,
                        "context_relevance_score": item.context_relevance_score
                    } for item in tracks
                ]),
                commentary=json.dumps([
                    {
                        "type": segment.type,
                        "content": segment.content,
                        "duration_estimate": segment.duration_estimate
                    } for segment in commentary
                ])
            )
            session.add(dj_session)
            
            # Create contextual session record with safe serialization
            contextual_session = ContextualSession(
                session_id=session_id,
                temporal_context=safe_json_serialize(context.get("temporal", {})),
                weather_context=safe_json_serialize(context.get("weather", {})),
                location_context=safe_json_serialize(context.get("location", {}))
            )
            session.add(contextual_session)
            
            session.commit()
            logger.info(f"Session {session_id} stored in database")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store session {session_id}: {e}")
            raise e
        finally:
            session.close()