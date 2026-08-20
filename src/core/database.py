"""
Database models and connection management
"""

import asyncio
from datetime import datetime
from typing import Optional, List
import json

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, 
    DateTime, Boolean, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.sqlite import JSON
import sqlite3

Base = declarative_base()

class Track(Base):
    __tablename__ = "tracks"
    
    id = Column(Integer, primary_key=True)
    file_path = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, index=True)
    artist = Column(String, index=True)
    album = Column(String, index=True)
    year = Column(Integer, index=True)
    genre = Column(String, index=True)
    duration = Column(Integer)  # seconds
    file_size = Column(Integer)
    file_hash = Column(String, index=True)
    bitrate = Column(Integer)
    sample_rate = Column(Integer)
    
    # Playback statistics
    play_count = Column(Integer, default=0)
    last_played = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    analysis = relationship("TrackAnalysis", back_populates="track", uselist=False)
    connections_from = relationship("TrackConnection", foreign_keys="TrackConnection.track_id_1")
    connections_to = relationship("TrackConnection", foreign_keys="TrackConnection.track_id_2")

class Artist(Base):
    __tablename__ = "artists"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    biography = Column(Text)
    formed_year = Column(Integer)
    origin_country = Column(String)
    genres = Column(Text)  # JSON array
    wikipedia_url = Column(String)
    image_url = Column(String)
    
    # Statistics
    track_count = Column(Integer, default=0)
    play_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TrackAnalysis(Base):
    __tablename__ = "track_analysis"
    
    track_id = Column(Integer, ForeignKey("tracks.id"), primary_key=True)
    lyrics = Column(Text)
    themes = Column(Text)  # JSON array
    
    # Mood analysis
    mood_valence = Column(Float)  # -1 to 1
    energy_level = Column(Float)  # 0 to 1
    danceability = Column(Float)  # 0 to 1
    
    # Musical analysis
    key_signature = Column(String)
    tempo = Column(Integer)  # BPM
    time_signature = Column(String)
    loudness = Column(Float)  # dB
    
    # AI Analysis
    summary = Column(Text)
    cultural_context = Column(Text)
    notable_elements = Column(Text)  # JSON array
    
    analysis_date = Column(DateTime, default=datetime.utcnow)
    analysis_version = Column(String, default="1.0")
    
    # Relationships
    track = relationship("Track", back_populates="analysis")

class TrackConnection(Base):
    __tablename__ = "track_connections"
    
    id = Column(Integer, primary_key=True)
    track_id_1 = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    track_id_2 = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    connection_type = Column(String, nullable=False, index=True)  # 'thematic', 'harmonic', 'temporal', 'lyrical'
    strength = Column(Float, nullable=False, index=True)  # 0 to 1
    description = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Ensure no duplicate connections
    __table_args__ = (
        UniqueConstraint('track_id_1', 'track_id_2', 'connection_type'),
        Index('idx_track_connections_strength', 'strength'),
    )

class DJSession(Base):
    __tablename__ = "dj_sessions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    theme = Column(String, index=True)
    status = Column(String, default="created", index=True)  # created, generating, ready, playing, completed, error
    
    # Configuration
    duration_minutes = Column(Integer)
    parameters = Column(Text)  # JSON configuration
    
    # Content
    track_sequence = Column(Text)  # JSON array of track IDs
    commentary = Column(Text)  # JSON array of commentary segments
    
    # Playback
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    current_position = Column(Integer, default=0)
    
    # Statistics
    listener_count = Column(Integer, default=0)
    total_plays = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Theme(Base):
    __tablename__ = "themes"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text)
    keywords = Column(Text)  # JSON array
    
    # Mood criteria
    mood_criteria = Column(Text)  # JSON object
    genre_preferences = Column(Text)  # JSON array
    exclude_genres = Column(Text)  # JSON array
    
    # Statistics
    track_count = Column(Integer, default=0)
    session_count = Column(Integer, default=0)
    
    is_custom = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Contextual tables for enhanced awareness
class ContextualSession(Base):
    __tablename__ = "contextual_sessions"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String, ForeignKey("dj_sessions.session_id"))
    temporal_context = Column(Text)  # JSON
    weather_context = Column(Text)   # JSON
    location_context = Column(Text)  # JSON
    context_snapshot_time = Column(DateTime, default=datetime.utcnow)

class ContextualTrackPlay(Base):
    __tablename__ = "contextual_track_plays"
    
    id = Column(Integer, primary_key=True)
    track_id = Column(Integer, ForeignKey("tracks.id"))
    session_id = Column(String, ForeignKey("dj_sessions.session_id"))
    context_relevance_score = Column(Float)
    temporal_factors = Column(Text)  # JSON array
    weather_factors = Column(Text)   # JSON array
    played_at = Column(DateTime, default=datetime.utcnow)

class LocationPreference(Base):
    __tablename__ = "location_preferences"
    
    id = Column(Integer, primary_key=True)
    location_key = Column(String, unique=True)  # city_state format
    preferred_themes = Column(Text)    # JSON array
    cultural_characteristics = Column(Text)  # JSON
    music_scene_data = Column(Text)   # JSON
    updated_at = Column(DateTime, default=datetime.utcnow)

class SeasonalTrackAssociation(Base):
    __tablename__ = "seasonal_track_associations"
    
    id = Column(Integer, primary_key=True)
    track_id = Column(Integer, ForeignKey("tracks.id"))
    season = Column(String)
    relevance_score = Column(Float)
    context_reasons = Column(Text)  # JSON array explaining why
    created_at = Column(DateTime, default=datetime.utcnow)

class WeatherMoodMapping(Base):
    __tablename__ = "weather_mood_mappings"
    
    id = Column(Integer, primary_key=True)
    weather_condition = Column(String)
    mood_description = Column(String)
    energy_range = Column(Text)  # JSON [min, max]
    valence_range = Column(Text)  # JSON [min, max]
    preferred_genres = Column(Text)  # JSON array
    created_at = Column(DateTime, default=datetime.utcnow)

# Database connection management
class DatabaseManager:
    def __init__(self, database_url: str):
        self.database_url = database_url
        # Sessions run on worker threads (asyncio.to_thread) and watchdog's
        # observer thread; pooled SQLite connections may be handed to a
        # different thread than the one that created them.
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def get_session(self):
        """Get a database session"""
        return self.SessionLocal()
    
    def init_database(self):
        """Initialize database tables"""
        Base.metadata.create_all(bind=self.engine)
        
        # Create default themes
        session = self.get_session()
        try:
            self._create_default_themes(session)
            self._create_default_weather_mappings(session)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def _create_default_themes(self, session):
        """Create default theme categories"""
        default_themes = [
            {
                "name": "love",
                "description": "Songs about romantic love, relationships, and heartbreak",
                "keywords": ["love", "romance", "heart", "relationship", "dating", "heartbreak"],
                "mood_criteria": {"valence": [-1.0, 1.0], "energy": [0.0, 1.0]}
            },
            {
                "name": "upbeat",
                "description": "High-energy, positive songs perfect for motivation",
                "keywords": ["happy", "energetic", "dance", "party", "celebration"],
                "mood_criteria": {"valence": [0.3, 1.0], "energy": [0.6, 1.0]}
            },
            {
                "name": "relaxing",
                "description": "Calm, soothing music for relaxation and unwinding",
                "keywords": ["calm", "peaceful", "chill", "relaxing", "ambient"],
                "mood_criteria": {"valence": [-0.2, 0.8], "energy": [0.0, 0.5]}
            },
            {
                "name": "nostalgic",
                "description": "Songs that evoke memories and contemplation of the past",
                "keywords": ["memory", "past", "childhood", "nostalgia", "remember"],
                "mood_criteria": {"valence": [-0.5, 0.5], "energy": [0.2, 0.7]}
            },
            {
                "name": "driving",
                "description": "Perfect road trip and driving music",
                "keywords": ["road", "highway", "journey", "travel", "freedom"],
                "mood_criteria": {"valence": [-0.2, 0.8], "energy": [0.4, 0.9]}
            },
            {
                "name": "rainy_day",
                "description": "Perfect for contemplative rainy afternoons",
                "keywords": ["rain", "melancholy", "introspective", "acoustic"],
                "mood_criteria": {"valence": [-0.5, 0.3], "energy": [0.2, 0.6]}
            }
        ]
        
        for theme_data in default_themes:
            existing = session.query(Theme).filter_by(name=theme_data["name"]).first()
            if not existing:
                theme = Theme(
                    name=theme_data["name"],
                    description=theme_data["description"],
                    keywords=json.dumps(theme_data["keywords"]),
                    mood_criteria=json.dumps(theme_data["mood_criteria"]),
                    is_custom=False
                )
                session.add(theme)
    
    def _create_default_weather_mappings(self, session):
        """Create default weather mood mappings"""
        weather_mappings = [
            {
                "weather_condition": "rainy",
                "mood_description": "contemplative",
                "energy_range": json.dumps([0.2, 0.6]),
                "valence_range": json.dumps([-0.3, 0.4]),
                "preferred_genres": json.dumps(["indie", "folk", "jazz", "acoustic"])
            },
            {
                "weather_condition": "sunny",
                "mood_description": "cheerful",
                "energy_range": json.dumps([0.5, 1.0]),
                "valence_range": json.dumps([0.3, 1.0]),
                "preferred_genres": json.dumps(["pop", "rock", "dance", "reggae"])
            },
            {
                "weather_condition": "cloudy",
                "mood_description": "mellow",
                "energy_range": json.dumps([0.3, 0.7]),
                "valence_range": json.dumps([-0.1, 0.6]),
                "preferred_genres": json.dumps(["alternative", "indie", "singer-songwriter"])
            },
            {
                "weather_condition": "stormy",
                "mood_description": "dramatic",
                "energy_range": json.dumps([0.6, 1.0]),
                "valence_range": json.dumps([-0.2, 0.8]),
                "preferred_genres": json.dumps(["rock", "classical", "progressive"])
            },
            {
                "weather_condition": "snowy",
                "mood_description": "peaceful",
                "energy_range": json.dumps([0.1, 0.5]),
                "valence_range": json.dumps([0.0, 0.7]),
                "preferred_genres": json.dumps(["ambient", "folk", "classical", "acoustic"])
            }
        ]
        
        for mapping_data in weather_mappings:
            existing = session.query(WeatherMoodMapping).filter_by(
                weather_condition=mapping_data["weather_condition"]
            ).first()
            if not existing:
                mapping = WeatherMoodMapping(**mapping_data)
                session.add(mapping)

# Global database manager instance
db_manager = None

async def init_database(database_url: str):
    """Initialize the database"""
    global db_manager
    db_manager = DatabaseManager(database_url)
    db_manager.init_database()
    return db_manager

def get_db():
    """Dependency to get database session"""
    return db_manager.get_session()