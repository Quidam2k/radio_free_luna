"""
AI Analysis Engine for music themes, lyrics, and connections
"""

import openai
import json
import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session

from ..core.database import get_db, Track, TrackAnalysis, TrackConnection
from ..core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class AnalysisResult:
    themes: List[str]
    mood_valence: float  # -1 to 1
    energy_level: float  # 0 to 1
    danceability: float  # 0 to 1
    summary: str
    cultural_context: str
    notable_elements: List[str]

class MusicAnalysisEngine:
    def __init__(self, openai_api_key: str, base_url: Optional[str] = None):
        client_kwargs = {"api_key": openai_api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = openai.OpenAI(**client_kwargs)
        self.analysis_cache = {}
        
    async def analyze_track_comprehensive(self, track: Track, lyrics: Optional[str] = None) -> AnalysisResult:
        """Perform comprehensive AI analysis of a track"""

        # Check cache first
        cache_key = f"{track.id}_{track.file_hash}"
        if cache_key in self.analysis_cache:
            return self.analysis_cache[cache_key]

        # Check persistent cache (track_analysis table) before spending API calls
        stored = await asyncio.to_thread(self._load_analysis_from_db, track.id)
        if stored is not None:
            self.analysis_cache[cache_key] = stored
            return stored

        # Prepare analysis prompt
        prompt = self._build_analysis_prompt(track, lyrics)
        
        try:
            # Call OpenAI API
            response = await self._call_openai_analysis(prompt)
            
            # Parse response
            analysis_result = self._parse_analysis_response(response)
            
            # Cache result
            self.analysis_cache[cache_key] = analysis_result
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"AI analysis failed for track {track.id}: {e}")
            return self._create_fallback_analysis(track)
    
    def _build_analysis_prompt(self, track: Track, lyrics: Optional[str]) -> str:
        """Build comprehensive analysis prompt for OpenAI"""
        
        prompt = f"""
        Analyze this song and provide a structured JSON response with deep musical and cultural insights:

        Song Information:
        - Title: "{track.title}"
        - Artist: {track.artist}
        - Album: {track.album}
        - Year: {track.year}
        - Genre: {track.genre}
        - Duration: {track.duration} seconds
        
        Lyrics: {lyrics[:1500] if lyrics else 'No lyrics available'}
        
        Please provide analysis in this exact JSON format:
        {{
            "themes": ["theme1", "theme2", "theme3", ...],
            "mood_analysis": {{
                "valence": -0.5 to 1.0,
                "energy": 0.0 to 1.0,
                "danceability": 0.0 to 1.0
            }},
            "summary": "2-3 sentence summary of the song's essence and impact",
            "cultural_context": "Historical, cultural, or musical significance",
            "notable_elements": ["element1", "element2", ...],
            "musical_characteristics": {{
                "style": "primary musical style",
                "influences": ["influence1", "influence2"],
                "innovations": ["innovation1", "innovation2"]
            }},
            "emotional_journey": "How the song takes the listener on an emotional journey",
            "lyrical_themes": ["theme1", "theme2"] or null if no lyrics,
            "connections": {{
                "similar_artists": ["artist1", "artist2"],
                "similar_songs": ["song1", "song2"],
                "influenced_by": ["influence1", "influence2"]
            }}
        }}
        
        Focus on:
        1. Thematic content (love, loss, freedom, rebellion, nostalgia, etc.)
        2. Emotional characteristics and mood
        3. Cultural and historical significance
        4. Musical style and innovations
        5. Potential connections to other artists/songs
        6. What makes this song unique or noteworthy
        
        Be specific and insightful. Consider the era, cultural context, and lasting impact.
        """
        
        return prompt
    
    async def _call_openai_analysis(self, prompt: str) -> str:
        """Call OpenAI API with retry logic"""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=settings.openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a deep music analyst with encyclopedic knowledge of music history, culture, and emotional impact. Provide detailed, accurate analysis in the requested JSON format."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1000
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                logger.warning(f"OpenAI API attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise e
    
    def _parse_analysis_response(self, response: str) -> AnalysisResult:
        """Parse OpenAI response into AnalysisResult"""
        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")
            
            json_str = response[json_start:json_end]
            data = json.loads(json_str)
            
            # Extract mood analysis
            mood = data.get('mood_analysis', {})
            
            return AnalysisResult(
                themes=data.get('themes', []),
                mood_valence=float(mood.get('valence', 0.0)),
                energy_level=float(mood.get('energy', 0.5)),
                danceability=float(mood.get('danceability', 0.5)),
                summary=data.get('summary', ''),
                cultural_context=data.get('cultural_context', ''),
                notable_elements=data.get('notable_elements', [])
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse analysis response: {e}")
            logger.debug(f"Response was: {response}")
            raise e
    
    def _create_fallback_analysis(self, track: Track) -> AnalysisResult:
        """Create basic analysis when AI fails"""
        
        # Basic genre-based theme mapping
        genre_themes = {
            'rock': ['energy', 'rebellion', 'freedom'],
            'pop': ['love', 'relationships', 'mainstream'],
            'jazz': ['sophistication', 'improvisation', 'culture'],
            'blues': ['emotion', 'struggle', 'authenticity'],
            'country': ['storytelling', 'tradition', 'rural'],
            'hip-hop': ['urban', 'social_commentary', 'rhythm'],
            'classical': ['complexity', 'tradition', 'elegance'],
            'folk': ['storytelling', 'tradition', 'acoustic']
        }
        
        themes = genre_themes.get(track.genre.lower() if track.genre else '', ['general', 'music'])
        
        return AnalysisResult(
            themes=themes,
            mood_valence=0.0,
            energy_level=0.5,
            danceability=0.5,
            summary=f"A {track.genre or 'music'} track by {track.artist}",
            cultural_context="Analysis not available",
            notable_elements=[]
        )
    
    def _load_analysis_from_db(self, track_id: int) -> Optional[AnalysisResult]:
        """Load a previously stored analysis from the track_analysis table."""
        try:
            session = get_db()
        except Exception:
            return None  # DB not initialized — treat as cache miss
        try:
            row = session.query(TrackAnalysis).filter_by(track_id=track_id).first()
            if not row or row.themes is None:
                return None
            try:
                themes = json.loads(row.themes or '[]')
                notable = json.loads(row.notable_elements or '[]')
            except json.JSONDecodeError:
                logger.warning(f"Corrupt stored analysis JSON for track {track_id}; re-analyzing")
                return None
            return AnalysisResult(
                themes=themes,
                mood_valence=row.mood_valence if row.mood_valence is not None else 0.0,
                energy_level=row.energy_level if row.energy_level is not None else 0.5,
                danceability=row.danceability if row.danceability is not None else 0.5,
                summary=row.summary or '',
                cultural_context=row.cultural_context or '',
                notable_elements=notable
            )
        finally:
            session.close()

    async def store_analysis_result(self, track_id: int, analysis: AnalysisResult):
        """Store analysis result in database"""
        await asyncio.to_thread(self._store_analysis_result_sync, track_id, analysis)

    def _store_analysis_result_sync(self, track_id: int, analysis: AnalysisResult):
        session = get_db()
        try:
            # Check if analysis already exists
            existing = session.query(TrackAnalysis).filter_by(track_id=track_id).first()
            
            analysis_data = {
                'track_id': track_id,
                'themes': json.dumps(analysis.themes),
                'mood_valence': analysis.mood_valence,
                'energy_level': analysis.energy_level,
                'danceability': analysis.danceability,
                'summary': analysis.summary,
                'cultural_context': analysis.cultural_context,
                'notable_elements': json.dumps(analysis.notable_elements),
                'analysis_version': '1.0'
            }
            
            if existing:
                # Update existing analysis
                for key, value in analysis_data.items():
                    if key != 'track_id':
                        setattr(existing, key, value)
            else:
                # Create new analysis
                track_analysis = TrackAnalysis(**analysis_data)
                session.add(track_analysis)
            
            session.commit()
            logger.info(f"Stored analysis for track {track_id}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store analysis for track {track_id}: {e}")
        finally:
            session.close()
    
    async def find_track_connections(self, track_id: int) -> List[Tuple[int, float, str]]:
        """Find thematic and musical connections to other tracks"""
        return await asyncio.to_thread(self._find_track_connections_sync, track_id)

    def _find_track_connections_sync(self, track_id: int) -> List[Tuple[int, float, str]]:
        session = get_db()
        try:
            # Get current track analysis
            current_analysis = session.query(TrackAnalysis).filter_by(track_id=track_id).first()
            if not current_analysis:
                return []
            
            current_themes = json.loads(current_analysis.themes or '[]')
            
            # Find tracks with similar themes
            all_analyses = session.query(TrackAnalysis).filter(
                TrackAnalysis.track_id != track_id
            ).all()
            
            connections = []
            
            for other_analysis in all_analyses:
                other_themes = json.loads(other_analysis.themes or '[]')
                
                # Calculate theme similarity
                common_themes = set(current_themes) & set(other_themes)
                if not current_themes or not other_themes:
                    theme_similarity = 0.0
                else:
                    theme_similarity = len(common_themes) / max(len(current_themes), len(other_themes))
                
                # Calculate mood similarity
                mood_diff = abs((current_analysis.mood_valence or 0) - (other_analysis.mood_valence or 0))
                mood_similarity = 1.0 - (mood_diff / 2.0)  # Normalize to 0-1
                
                # Calculate energy similarity
                energy_diff = abs((current_analysis.energy_level or 0.5) - (other_analysis.energy_level or 0.5))
                energy_similarity = 1.0 - energy_diff
                
                # Combined similarity score
                overall_similarity = (
                    theme_similarity * 0.5 +
                    mood_similarity * 0.3 +
                    energy_similarity * 0.2
                )
                
                if overall_similarity > 0.3:  # Threshold for relevance
                    description = f"Shares themes: {', '.join(common_themes)}" if common_themes else "Similar mood and energy"
                    connections.append((other_analysis.track_id, overall_similarity, description))
            
            # Sort by similarity and return top connections
            connections.sort(key=lambda x: x[1], reverse=True)
            return connections[:10]
            
        except Exception as e:
            logger.error(f"Failed to find connections for track {track_id}: {e}")
            return []
        finally:
            session.close()
    
    async def store_track_connections(self, track_id: int, connections: List[Tuple[int, float, str]]):
        """Store track connections in database"""
        await asyncio.to_thread(self._store_track_connections_sync, track_id, connections)

    def _store_track_connections_sync(self, track_id: int, connections: List[Tuple[int, float, str]]):
        session = get_db()
        try:
            # Remove existing connections
            session.query(TrackConnection).filter_by(track_id_1=track_id).delete()
            
            # Add new connections
            for other_track_id, strength, description in connections:
                connection = TrackConnection(
                    track_id_1=track_id,
                    track_id_2=other_track_id,
                    connection_type='thematic',
                    strength=strength,
                    description=description
                )
                session.add(connection)
            
            session.commit()
            logger.info(f"Stored {len(connections)} connections for track {track_id}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to store connections for track {track_id}: {e}")
        finally:
            session.close()
    
    def _get_track_sync(self, track_id: int) -> Optional[Track]:
        session = get_db()
        try:
            track = session.query(Track).filter_by(id=track_id).first()
            if track is not None:
                session.expunge(track)  # detach so it's usable after close
            return track
        finally:
            session.close()

    def get_unanalyzed_track_ids(self, limit: int = 10) -> List[int]:
        """IDs of tracks with no stored analysis yet (sync; call via to_thread)."""
        session = get_db()
        try:
            rows = (
                session.query(Track.id)
                .outerjoin(TrackAnalysis, Track.id == TrackAnalysis.track_id)
                .filter(TrackAnalysis.track_id.is_(None))
                .limit(limit)
                .all()
            )
            return [row[0] for row in rows]
        finally:
            session.close()

    async def analyze_and_store_track(self, track_id: int, lyrics: Optional[str] = None):
        """Complete analysis pipeline for a track"""
        track = await asyncio.to_thread(self._get_track_sync, track_id)
        if not track:
            logger.error(f"Track {track_id} not found")
            return

        logger.info(f"Starting comprehensive analysis for track {track_id}: {track.title}")

        # Perform AI analysis
        analysis = await self.analyze_track_comprehensive(track, lyrics)

        # Store analysis
        await self.store_analysis_result(track_id, analysis)

        # Find and store connections
        connections = await self.find_track_connections(track_id)
        await self.store_track_connections(track_id, connections)

        logger.info(f"Completed analysis for track {track_id}")