class ContextualDJEngine:
    def __init__(self, db_path: str, openai_api_key: str, context_manager):
        self.db_path = db_path
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        self.context_manager = context_manager
        self.personality_traits = {
            "knowledge_depth": "deep",  # surface, moderate, deep
            "speaking_style": "conversational",  # formal, conversational, poetic
            "trivia_frequency": "moderate",  # rare, moderate, frequent
            "personal_touch": True,
            "context_awareness": True  # Makes DJ reference current conditions
        }
    
    def create_contextual_session(self, theme: str, duration_minutes: int = 60) -> Dict:
        """Create a DJ session that's aware of current context"""
        
        # Get current contextual information
        context = self.context_manager.get_current_context()
        
        # Enhance theme with contextual elements
        enhanced_theme = self.enhance_theme_with_context(theme, context)
        
        # Find tracks matching both theme and context
        matching_tracks = self.find_contextual_tracks(enhanced_theme, context)
        
        if not matching_tracks:
            return {"# Technical Architecture & Implementation Plan

## Phase 1: Core Infrastructure (MVP)

### Database Schema

```sql
-- Core music library tables

CREATE TABLE tracks (
    id INTEGER PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    title TEXT,
    artist TEXT,
    album TEXT,
    year INTEGER,
    genre TEXT,
    duration INTEGER, -- seconds
    file_size INTEGER,
    file_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE artists (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    biography TEXT,
    formed_year INTEGER,
    origin_country TEXT,
    genres TEXT, -- JSON array
    wikipedia_url TEXT,
    image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE track_analysis (
    track_id INTEGER REFERENCES tracks(id),
    lyrics TEXT,
    themes TEXT, -- JSON array
    mood_valence REAL, -- -1 to 1
    energy_level REAL, -- 0 to 1
    danceability REAL, -- 0 to 1
    key_signature TEXT,
    tempo INTEGER, -- BPM
    time_signature TEXT,
    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE track_connections (
    id INTEGER PRIMARY KEY,
    track_id_1 INTEGER REFERENCES tracks(id),
    track_id_2 INTEGER REFERENCES tracks(id),
    connection_type TEXT, -- 'thematic', 'harmonic', 'temporal', 'lyrical'
    strength REAL, -- 0 to 1
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dj_sessions (
    id INTEGER PRIMARY KEY,
    name TEXT,
    theme TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    track_sequence TEXT, -- JSON array of track IDs
    commentary TEXT, -- JSON array of commentary segments
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### File System Monitor

```python
# file_monitor.py - Watches music directories for changes
import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import sqlite3
import hashlib
from mutagen import File as MutagenFile

class MusicFileHandler(FileSystemEventHandler):
    def __init__(self, db_path):
        self.db_path = db_path
        self.audio_extensions = {'.mp3', '.flac', '.wav', '.m4a', '.ogg'}
    
    def on_created(self, event):
        if not event.is_directory and self.is_audio_file(event.src_path):
            self.process_audio_file(event.src_path)
    
    def on_modified(self, event):
        if not event.is_directory and self.is_audio_file(event.src_path):
            self.process_audio_file(event.src_path)
    
    def is_audio_file(self, file_path):
        return os.path.splitext(file_path)[1].lower() in self.audio_extensions
    
    def process_audio_file(self, file_path):
        try:
            # Extract metadata
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                return
            
            # Calculate file hash for duplicate detection
            file_hash = self.calculate_file_hash(file_path)
            
            # Store in database
            self.store_track_metadata(file_path, audio_file, file_hash)
            
            # Queue for further analysis
            self.queue_for_analysis(file_path)
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    def calculate_file_hash(self, file_path):
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def store_track_metadata(self, file_path, audio_file, file_hash):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Extract metadata with fallbacks
        title = audio_file.get('TIT2', [str(audio_file.get('TITLE', ['Unknown']))[0]])[0]
        artist = audio_file.get('TPE1', [str(audio_file.get('ARTIST', ['Unknown']))[0]])[0]
        album = audio_file.get('TALB', [str(audio_file.get('ALBUM', ['Unknown']))[0]])[0]
        year = self.extract_year(audio_file)
        genre = self.extract_genre(audio_file)
        duration = getattr(audio_file, 'info', None)
        duration = duration.length if duration else 0
        
        cursor.execute('''
            INSERT OR REPLACE INTO tracks 
            (file_path, title, artist, album, year, genre, duration, file_size, file_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (file_path, title, artist, album, year, genre, 
              duration, os.path.getsize(file_path), file_hash))
        
        conn.commit()
        conn.close()
```

### AI Analysis Engine

```python
# analysis_engine.py - Processes tracks for themes, connections
import openai
import sqlite3
import json
import requests
from typing import Dict, List, Optional
import re

class MusicAnalysisEngine:
    def __init__(self, db_path: str, openai_api_key: str):
        self.db_path = db_path
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        self.genius_token = None  # Configure Genius API token
    
    def analyze_track(self, track_id: int):
        """Complete analysis pipeline for a single track"""
        track_data = self.get_track_data(track_id)
        if not track_data:
            return
        
        # Fetch lyrics
        lyrics = self.fetch_lyrics(track_data['artist'], track_data['title'])
        
        # Analyze themes and mood
        analysis = self.analyze_lyrics_and_metadata(track_data, lyrics)
        
        # Store analysis results
        self.store_analysis(track_id, lyrics, analysis)
        
        # Find connections to other tracks
        self.find_track_connections(track_id)
    
    def fetch_lyrics(self, artist: str, title: str) -> Optional[str]:
        """Fetch lyrics from Genius API"""
        if not self.genius_token:
            return None
        
        # Search for song on Genius
        search_url = "https://api.genius.com/search"
        headers = {"Authorization": f"Bearer {self.genius_token}"}
        params = {"q": f"{artist} {title}"}
        
        try:
            response = requests.get(search_url, headers=headers, params=params)
            data = response.json()
            
            if data['response']['hits']:
                song_url = data['response']['hits'][0]['result']['url']
                # Note: Would need to scrape lyrics from the song page
                # This is a simplified example
                return self.scrape_genius_lyrics(song_url)
        except Exception as e:
            print(f"Error fetching lyrics: {e}")
        
        return None
    
    def analyze_lyrics_and_metadata(self, track_data: Dict, lyrics: Optional[str]) -> Dict:
        """Use OpenAI to analyze song themes and characteristics"""
        
        prompt = f"""
        Analyze this song and provide a structured response:
        
        Song: {track_data['title']} by {track_data['artist']}
        Album: {track_data['album']} ({track_data['year']})
        Genre: {track_data['genre']}
        Lyrics: {lyrics[:1000] if lyrics else 'No lyrics available'}
        
        Please provide:
        1. Main themes (maximum 5)
        2. Emotional mood (valence: -1 to 1, energy: 0 to 1)
        3. Cultural/historical context (if significant)
        4. Notable lyrical elements or metaphors
        5. Potential connections to other songs/artists
        
        Respond in JSON format.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            analysis_text = response.choices[0].message.content
            return json.loads(analysis_text)
            
        except Exception as e:
            print(f"Error in AI analysis: {e}")
            return {}
    
    def find_track_connections(self, track_id: int):
        """Find thematic and musical connections to other tracks"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get current track analysis
        cursor.execute('''
            SELECT tracks.*, track_analysis.themes, track_analysis.mood_valence, 
                   track_analysis.energy_level, track_analysis.key_signature, track_analysis.tempo
            FROM tracks 
            JOIN track_analysis ON tracks.id = track_analysis.track_id 
            WHERE tracks.id = ?
        ''', (track_id,))
        
        current_track = cursor.fetchone()
        if not current_track:
            return
        
        # Find tracks with similar themes
        cursor.execute('''
            SELECT tracks.id, tracks.title, tracks.artist, track_analysis.themes
            FROM tracks 
            JOIN track_analysis ON tracks.id = track_analysis.track_id 
            WHERE tracks.id != ?
        ''', (track_id,))
        
        all_tracks = cursor.fetchall()
        
        # Calculate connections (simplified algorithm)
        for other_track in all_tracks:
            connection_strength = self.calculate_connection_strength(
                current_track, other_track
            )
            
            if connection_strength > 0.3:  # Threshold for relevance
                self.store_connection(track_id, other_track[0], 
                                    'thematic', connection_strength)
        
        conn.close()
    
    def calculate_connection_strength(self, track1, track2) -> float:
        """Calculate similarity between two tracks"""
        # This is a simplified example - in reality, you'd want more sophisticated algorithms
        
        if not track1 or not track2:
            return 0.0
        
        strength = 0.0
        
        # Theme similarity (if themes are stored as JSON arrays)
        try:
            themes1 = json.loads(track1[7] or '[]')  # Assuming themes is at index 7
            themes2 = json.loads(track2[3] or '[]')
            
            common_themes = set(themes1) & set(themes2)
            if themes1 and themes2:
                theme_similarity = len(common_themes) / max(len(themes1), len(themes2))
                strength += theme_similarity * 0.4
        except:
            pass
        
        # Mood similarity
        try:
            mood_diff = abs(float(track1[8] or 0) - float(track2[8] or 0))  # mood_valence
            mood_similarity = 1.0 - mood_diff  # Assuming mood is -1 to 1
            strength += mood_similarity * 0.3
        except:
            pass
        
        # Same artist bonus
        if track1[3] == track2[2]:  # artist names
            strength += 0.2
        
        return min(strength, 1.0)
```

### Contextual Integration in Database

```sql
-- Add contextual tables to the schema

CREATE TABLE contextual_sessions (
    id INTEGER PRIMARY KEY,
    session_id TEXT REFERENCES dj_sessions(session_id),
    temporal_context TEXT, -- JSON
    weather_context TEXT,  -- JSON
    location_context TEXT, -- JSON
    context_snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE contextual_track_plays (
    id INTEGER PRIMARY KEY,
    track_id INTEGER REFERENCES tracks(id),
    session_id TEXT REFERENCES dj_sessions(session_id),
    context_relevance_score REAL,
    temporal_factors TEXT, -- JSON array
    weather_factors TEXT,  -- JSON array
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE location_preferences (
    id INTEGER PRIMARY KEY,
    location_key TEXT UNIQUE, -- city_state format
    preferred_themes TEXT,    -- JSON array
    cultural_characteristics TEXT, -- JSON
    music_scene_data TEXT,   -- JSON
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE seasonal_track_associations (
    id INTEGER PRIMARY KEY,
    track_id INTEGER REFERENCES tracks(id),
    season TEXT,
    relevance_score REAL,
    context_reasons TEXT, -- JSON array explaining why
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE weather_mood_mappings (
    id INTEGER PRIMARY KEY,
    weather_condition TEXT,
    mood_description TEXT,
    energy_range TEXT, -- JSON [min, max]
    valence_range TEXT, -- JSON [min, max]
    preferred_genres TEXT, -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Enhanced DJ Commentary Generator

```python
# dj_engine.py - Generates commentary and manages sessions with contextual awareness
import sqlite3
import json
import random
from typing import List, Dict, Optional
import openai
from datetime import datetime

class ContextualDJEngine:
    def __init__(self, db_path: str, openai_api_key: str):
        self.db_path = db_path
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        self.personality_traits = {
            "knowledge_depth": "deep",  # surface, moderate, deep
            "speaking_style": "conversational",  # formal, conversational, poetic
            "trivia_frequency": "moderate",  # rare, moderate, frequent
            "personal_touch": True
        }
    
    def create_themed_session(self, theme: str, duration_minutes: int = 60) -> Dict:
        """Create a thematic DJ session"""
        
        # Find tracks matching the theme
        matching_tracks = self.find_tracks_by_theme(theme)
        
        if not matching_tracks:
            return {"error": "No tracks found for theme"}
        
        # Select and sequence tracks
        session_tracks = self.sequence_tracks(matching_tracks, duration_minutes)
        
        # Generate commentary for each transition
        commentary = self.generate_session_commentary(theme, session_tracks)
        
        # Store session in database
        session_id = self.store_session(theme, session_tracks, commentary)
        
        return {
            "session_id": session_id,
            "theme": theme,
            "tracks": session_tracks,
            "commentary": commentary,
            "estimated_duration": sum(track['duration'] for track in session_tracks)
        }
    
    def find_tracks_by_theme(self, theme: str) -> List[Dict]:
        """Find tracks related to a specific theme"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Search in themes and lyrics
        cursor.execute('''
            SELECT tracks.*, track_analysis.themes, track_analysis.lyrics
            FROM tracks 
            JOIN track_analysis ON tracks.id = track_analysis.track_id 
            WHERE track_analysis.themes LIKE ? OR track_analysis.lyrics LIKE ?
        ''', (f'%{theme}%', f'%{theme}%'))
        
        results = cursor.fetchall()
        conn.close()
        
        return [self.format_track_data(track) for track in results]
    
    def sequence_tracks(self, tracks: List[Dict], duration_minutes: int) -> List[Dict]:
        """Intelligently sequence tracks for optimal flow"""
        
        target_duration = duration_minutes * 60  # Convert to seconds
        current_duration = 0
        sequenced_tracks = []
        remaining_tracks = tracks.copy()
        
        # Simple sequencing algorithm - can be made much more sophisticated
        while remaining_tracks and current_duration < target_duration:
            if not sequenced_tracks:
                # First track - pick something engaging
                next_track = self.pick_opening_track(remaining_tracks)
            else:
                # Find best next track based on current track
                current_track = sequenced_tracks[-1]
                next_track = self.pick_next_track(current_track, remaining_tracks)
            
            if next_track:
                sequenced_tracks.append(next_track)
                current_duration += next_track['duration']
                remaining_tracks.remove(next_track)
            else:
                break
        
        return sequenced_tracks
    
    def generate_session_commentary(self, theme: str, tracks: List[Dict]) -> List[Dict]:
        """Generate DJ commentary for the entire session"""
        
        commentary = []
        
        # Opening commentary
        opening = self.generate_opening_commentary(theme, tracks[0] if tracks else None)
        commentary.append({"type": "opening", "content": opening, "position": 0})
        
        # Transition commentary between tracks
        for i in range(len(tracks) - 1):
            current_track = tracks[i]
            next_track = tracks[i + 1] 
            
            transition = self.generate_transition_commentary(current_track, next_track, theme)
            commentary.append({
                "type": "transition", 
                "content": transition, 
                "position": i + 1,
                "after_track": current_track['id'],
                "before_track": next_track['id']
            })
        
        # Closing commentary
        if tracks:
            closing = self.generate_closing_commentary(theme, tracks[-1])
            commentary.append({"type": "closing", "content": closing, "position": len(tracks)})
        
        return commentary
    
    def generate_opening_commentary(self, theme: str, first_track: Optional[Dict]) -> str:
        """Generate opening commentary for the session"""
        
        prompt = f"""
        You are an AI DJ with deep knowledge of music, culture, and poetry. You're starting a themed music session.

        Theme: {theme}
        First Track: {first_track['title'] if first_track else 'Unknown'} by {first_track['artist'] if first_track else 'Unknown'}

        Create an engaging opening that:
        1. Sets the mood for the theme
        2. Introduces the first track with context
        3. Uses a conversational, knowledgeable tone
        4. Includes a relevant cultural reference or poetic element
        5. Keeps it under 90 seconds when spoken

        Write as if you're speaking directly to listeners.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"Error generating commentary: {e}")
            return f"Welcome to our {theme} session. Let's start with something special..."
    
    def generate_transition_commentary(self, current_track: Dict, next_track: Dict, theme: str) -> str:
        """Generate transition commentary between two tracks"""
        
        # Find connection between tracks
        connection = self.find_track_connection(current_track['id'], next_track['id'])
        
        prompt = f"""
        You are an AI DJ transitioning between songs in a {theme} themed session.

        Just played: "{current_track['title']}" by {current_track['artist']}
        Coming up: "{next_track['title']}" by {next_track['artist']}
        
        Connection: {connection.get('description', 'Thematic continuation') if connection else 'Thematic flow'}

        Create a smooth transition that:
        1. Briefly reflects on what we just heard (optional)
        2. Connects to the upcoming track
        3. Adds interesting context about the next song/artist
        4. Maintains the session's thematic flow
        5. Keeps it conversational and under 60 seconds

        No need to repeat song titles unless particularly relevant.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"Error generating transition: {e}")
            return "And continuing our journey..."

    def find_track_connection(self, track1_id: int, track2_id: int) -> Optional[Dict]:
        """Find stored connection between two tracks"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT connection_type, strength, description
            FROM track_connections
            WHERE (track_id_1 = ? AND track_id_2 = ?) 
               OR (track_id_1 = ? AND track_id_2 = ?)
            ORDER BY strength DESC
            LIMIT 1
        ''', (track1_id, track2_id, track2_id, track1_id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "type": result[0],
                "strength": result[1], 
                "description": result[2]
            }
        return None
```

## Phase 2: Streaming Infrastructure

### Audio Server
- Icecast2 configuration for streaming
- FFmpeg integration for audio processing
- Real-time crossfading and normalization
- Multiple bitrate/format support

### Web Interface
- Real-time session control
- Now playing display with track information
- Commentary scheduling and editing
- Theme management and playlist creation

### API Design
- RESTful endpoints for all functionality
- WebSocket support for real-time updates
- Authentication and session management
- Mobile app integration support

## Development Roadmap

### Week 1-2: Core Infrastructure
- Database setup and schema
- File monitoring system
- Basic metadata extraction
- Simple web interface

### Week 3-4: AI Integration
- OpenAI API integration
- Lyrics fetching system
- Theme analysis pipeline
- Connection discovery algorithms

### Week 5-6: DJ Engine
- Commentary generation
- Session management
- Track sequencing logic
- Basic streaming setup

### Week 7-8: Polish & Features
- Web interface improvements
- Audio processing pipeline
- Performance optimization
- Documentation and testing

## Configuration Management

All configuration will be managed through environment variables and config files:
- API keys (OpenAI, Genius, etc.)
- Database connections
- Music directory paths
- Streaming server settings
- AI personality parameters

## Performance Considerations

- Async processing for file scanning
- Caching for frequently accessed data
- Background jobs for AI analysis
- Efficient database indexing
- Audio streaming optimizations