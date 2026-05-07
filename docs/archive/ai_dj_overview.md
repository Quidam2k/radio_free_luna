# AI DJ System - Project Overview

## Core Concept

An intelligent music streaming system that builds comprehensive knowledge about your music collection, creating contextual playlists and DJ commentary that connects songs through themes, history, and cultural significance.

## System Architecture

### 1. Music Scanner & Monitor
- **File System Watcher**: Monitors specified directories for new/changed audio files
- **Metadata Extraction**: Uses libraries like `mutagen` (Python) or `music-metadata` (Node.js)
- **Audio Fingerprinting**: Optional integration with AcoustID/MusicBrainz for identification
- **Database Storage**: SQLite for local storage, with options for PostgreSQL scaling

### 2. Knowledge Engine
- **Lyrics Fetching**: Integration with Genius API, AZLyrics scraping (with rate limiting)
- **Artist Research**: Wikipedia API, AllMusic, Last.fm for biographical data
- **Theme Analysis**: LLM-powered analysis of lyrics for themes, emotions, topics
- **Historical Context**: Research on song origins, cultural significance, chart performance
- **Cross-References**: Building connections between songs, artists, genres, themes

### 3. AI DJ Brain
- **Playlist Generation**: Smart sequencing based on tempo, key, theme, mood
- **Commentary Generation**: Contextual introductions, transitions, trivia
- **Poetry Integration**: Thematic poetry selection from public domain sources
- **Voice Synthesis**: TTS for DJ commentary (with personality customization)

### 4. Streaming Infrastructure
- **Audio Processing**: Real-time mixing, crossfading, normalization
- **Stream Server**: Icecast2/SHOUTcast compatible streaming
- **Web Interface**: Control panel, now playing, upcoming tracks
- **API**: REST endpoints for external control

### 5. Data Models

#### Track
- File path, metadata (title, artist, album, year, genre)
- Audio properties (duration, BPM, key, loudness)
- Lyrics, themes, emotional tags
- Historical context, chart positions
- Acoustic fingerprint, MusicBrainz ID

#### Artist
- Biography, career highlights, influences
- Discography timeline, collaborations
- Musical style evolution, genre associations
- Cultural impact, notable quotes

#### Playlist Context
- Theme/mood designation
- Transition rules and preferences
- Commentary templates
- Audience considerations

## Technology Stack

### Backend Options
- **Python**: FastAPI + SQLAlchemy + Celery (for async tasks)
- **Node.js**: Express + Prisma + Bull (queue processing)
- **Rust**: Axum + SeaORM (for high performance)

### AI/ML Components
- **OpenAI API**: For theme analysis and commentary generation
- **Local LLM**: Ollama integration for privacy-focused deployment
- **Audio Analysis**: librosa (Python) or Web Audio API features

### Streaming
- **Icecast2**: Open source streaming server
- **FFmpeg**: Audio processing and format conversion
- **WebRTC**: For low-latency web streaming

### Frontend
- **Web UI**: React/Vue with real-time updates (WebSockets)
- **Mobile Apps**: React Native or Flutter for remote control
- **Voice Control**: Integration with local voice assistants

## Key Features

### Intelligent Sequencing
- Harmonic mixing (key compatibility)
- Energy progression (BPM curves)
- Thematic continuity
- Mood transitions
- Genre blending rules

### DJ Personality
- Customizable speaking style and knowledge depth
- Historical anecdotes and musical trivia
- Poetry and literature connections
- Local/personal references integration
- Interaction with listener feedback

### Content Discovery
- Hidden gem identification in large collections
- Theme-based deep dives (e.g., "Songs about trains")
- Artist journey narratives
- Genre evolution storytelling
- Seasonal and temporal programming

### Quality Control
- Lyrics content filtering options
- Audio quality assessment
- Duplicate detection and handling
- Missing metadata completion
- Format standardization

## Deployment Scenarios

### Personal Home Server
- Raspberry Pi or NUC deployment
- Local network streaming
- Family/household customization
- Integration with smart home systems

### Cloud Deployment
- Docker containerization
- Scalable processing queues
- Content delivery network integration
- Multi-user support with personalization

### Hybrid Architecture
- Local music scanning and storage
- Cloud-based AI processing
- Edge caching for performance
- Privacy-preserving design

## Privacy & Legal Considerations

- No copyrighted material redistribution
- Personal use streaming compliance
- Lyrics fair use for analysis only
- Data sovereignty options
- Open source licensing strategy

## Success Metrics

- Library processing coverage and accuracy
- DJ commentary quality and relevance
- Theme connection discovery rate
- User engagement and listening duration
- System performance and reliability