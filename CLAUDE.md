# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Radio Free Luna** is an intelligent AI-powered DJ system that streams music with contextual awareness and natural voice commentary. The system understands weather, time of day, season, location, and cultural moments to create "perfect musical moments" through smart track sequencing and AI-generated DJ commentary.

## Quick Start Commands

### Running the Application
```bash
# Start the AI DJ system
python main.py

# Access web interface
http://localhost:8080
```

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_api.py

# Run with verbose output
pytest tests/ -v

# Run single test
pytest tests/test_api.py::test_health_check -v
```

### Code Quality
```bash
# Format code with Black
black src/

# Check code style with Flake8
flake8 src/

# Sort imports
isort src/
```


## Architecture Overview

### Core Design Pattern
- **Event-driven, context-aware** music streaming system
- **Asynchronous architecture** using FastAPI and async/await throughout
- **Modular components** with clear separation of concerns
- **Graceful degradation** - system works with mock components when services unavailable

### Main Components

**`src/core/`** - Infrastructure Layer
- `config.py` - Settings management and environment variables
- `database.py` - SQLAlchemy ORM models and SQLite/PostgreSQL management
- `file_monitor.py` - Watches music directories for new/modified files

**`src/analysis/`** - Music Intelligence
- `ai_analyzer.py` - Deep AI analysis of lyrics, themes, cultural connections
- `lyrics_fetcher.py` - Fetches lyrics from Genius API

**`src/context/`** - Contextual Awareness
- `context_manager.py` - Orchestrates all context sources
- `temporal.py` - Time-of-day, seasonal, and holiday awareness
- `geocoding.py` - Keyless Open-Meteo geocoding (coordinates, IANA timezone)
- `weather.py` - Open-Meteo weather integration (no API key) for weather-based mood shifts
- `location.py` - Geocoded location + curated music scene analysis

**`src/dj/`** - DJ Intelligence
- `session_manager.py` - Track sequencing and themed session creation
- `commentary_generator.py` - AI-powered DJ commentary with philosophical observations

**`src/voice/`** - Text-to-Speech
- `tts_config.py` - TTS configuration and model management
- `tts_client.py` - TTS-WebUI client integration
- `contextual_voice.py` - Adaptive voice based on time and mood

**`src/streaming/`** - Audio Streaming
- `broadcaster.py` - Main streaming orchestration; owns ffmpeg subprocess lifecycle, PCM pump loop, MP3 fanout to per-listener queues
- `audio_processor.py` - Audio normalization, compression, auto-gain
- `crossfader.py` - Smart audio transitions (linear, sine, logarithmic, smart auto-selection based on track characteristics)

**`src/web/`** - Web Interface
- Static HTML, CSS, JavaScript files in `src/web/static/`

### Data Flow

1. **Initialization**: `python main.py` (RadioFreeLuna class) â†’ FastAPI app on port 8080
2. **Music Scanning**: File monitor detects changes â†’ metadata extraction â†’ database storage
3. **AI Analysis**: New tracks â†’ Genius API (lyrics) â†’ OpenAI (deep analysis) â†’ database cache
4. **Session Creation**: User request â†’ context_manager gathers context â†’ session_manager sequences tracks
5. **DJ Commentary**: Track plays â†’ commentary_generator creates context-aware comments â†’ TTS-WebUI synthesizes voice
6. **Audio Streaming**: Track audio â†’ AudioProcessor (normalization) â†’ crossfader (transitions) â†’ ffmpeg subprocess (MP3 encoding) â†’ per-listener asyncio queues via GET /stream.mp3

### Database Schema

**Key tables**:
- `tracks` - Audio file metadata (title, artist, duration, path)
- `artists` - Artist information and relationships
- `track_analysis` - AI analysis results (themes, mood, energy, cultural significance)
- `track_connections` - Relationships and thematic connections between tracks
- `dj_sessions` - Complete DJ session records with track sequences
- `contextual_sessions` - Sessions with snapshots of context data

## Technology Stack

- **Framework**: FastAPI 0.104.1 + Uvicorn 0.24.0
- **Database**: SQLAlchemy 2.0.23 (SQLite default, PostgreSQL/MySQL supported)
- **Audio Processing**: pydub, mutagen (file decoding and metadata extraction)
- **AI/Analytics**: OpenAI (GPT-4o-mini and beyond)
- **Voice Synthesis**: TTS-WebUI client for high-quality synthesis
- **Streaming**: HTTP chunked transfer via FastAPI; ffmpeg subprocess (libmp3lame) for real-time MP3 encoding
- **File Monitoring**: watchdog
- **Testing**: pytest, pytest-asyncio
- **Code Quality**: black, flake8, isort

### System Dependencies

- **ffmpeg**: Required for MP3 encoding (pydub also uses ffmpeg for decode). Install via package manager or include in venv.
- **Python 3.9+**: For async/await and pathlib.Path support

## Configuration

### Environment Variables (.env)
```
OPENAI_API_KEY=your_key_here          # For AI analysis and commentary (REQUIRED)
OPENAI_MODEL=gpt-4o-mini              # OpenAI model for analysis and commentary
AUTO_ANALYZE_TRACKS=true              # Background worker analyzes unanalyzed tracks into track_analysis
ARCHIVE_BROADCASTS=false              # Record each broadcast to archives/<session>.mp3
MUSIC_DIRECTORIES=/path/to/music      # Comma-separated music folders
DATABASE_URL=sqlite:///data/radio_free_luna.db  # Database connection (auto-anchored to project root)
TTS_WEBUI_URL=http://localhost:7860   # TTS service URL
LOCATION=Denver, CO                   # For weather/location context
DJ_PERSONALITY=conversational         # DJ commentary style
KNOWLEDGE_DEPTH=moderate              # Analysis depth
ICECAST_HOST=localhost                # Icecast2 host (for legacy config)
ICECAST_PORT=8000                     # Icecast2 port (for legacy config)
ICECAST_PASSWORD=ChangeMe-Example-1234 # Must be 12+ chars, uppercase, digit (for legacy config)
STREAM_MOUNT=/ai_dj_stream            # Icecast2 stream mount (for legacy config)
```

**Note**: Icecast2 settings are preserved for legacy compatibility. Current streaming uses HTTP chunked transfer with ffmpeg MP3 encoding on port 8080 via `/stream.mp3`.

### Optional External Services
- **OpenAI API**: For AI commentary (mock fallback available)
- **TTS-WebUI**: For voice synthesis (can run without voice)
- **Icecast2**: For real audio streaming (mock mode available)
- **Genius API**: For lyrics fetching

Weather and geocoding use the keyless Open-Meteo APIs — no key or account needed.

## Important Implementation Details

### AI Integration
- AI responses are **cached** in the database to avoid repeated API calls
- **Mock fallback** available if OpenAI API unavailable
- Commentary includes philosophical observations tied to context
- Track analysis includes mood, themes, energy, and cultural significance

### Audio Streaming Architecture
- **Smart Crossfading**: Automatically selects transition type (linear, sine, logarithmic, or smart) based on track characteristics
- **Audio Processing**: Normalization and compression for consistent levels
- **Pump/Reader Model**: Pump loop feeds raw PCM to ffmpeg subprocess; reader loop fans MP3 chunks to per-listener bounded queues
- **Real-time Pacing**: Cumulative audio-time deltas against wall clock prevent drift

### Voice Synthesis
- Integrated with **TTS-WebUI** for high-quality voice
- Voice personality adapts to **time of day** (morning, afternoon, evening, night)
- Can use multiple voice models (alloy, echo, fable, nova, onyx, shimmer)
- Falls back gracefully if TTS service unavailable

### Context Awareness System
The system intelligently reacts to:
- **Temporal Context**: Time of day, season, holidays, music anniversaries
- **Weather Context**: Current conditions, forecasts, emotional/mood associations
- **Location Context**: Local music scenes, cultural characteristics
- **Cultural Context**: Current events, historical music moments

### Graceful Degradation Pattern
When external services fail:
1. Try real service
2. Fall back to mock implementation
3. Log warning but continue operation
4. Cache responses to minimize repeated failures

This allows development and testing without all external services running.

## API Endpoints

- `GET /` - Web interface (or JSON fallback)
- `GET /health` - Basic health check
- `GET /status` - Detailed system status
- `GET /api` - API endpoint overview
- `GET /api/context` - Current contextual information
- `POST /api/sessions` - Create themed DJ session (dry-run, no streaming)
- `POST /api/commentary` - Generate AI commentary for a track
- `POST /api/test-voice` - Test voice synthesis
- `POST /api/requests` - Listener request line: search the library, queue the match next, DJ acknowledges the requester by name on air
- `GET /stream.mp3` - Live MP3 stream (HTTP chunked transfer); requires active session
- `POST /api/streaming/start` - Create session and start broadcasting
- `POST /api/streaming/stop` - Stop active broadcast
- `POST /api/streaming/skip` - Skip to next track
- `GET /api/streaming/status` - Detailed broadcaster state
- `GET /docs` - Swagger API documentation

## Important Notes for Future Development

1. **Always use async/await**: FastAPI is async-first. Use `async def` for endpoint handlers and async libraries (aiohttp, asyncpg).

2. **Database Queries**: Use SQLAlchemy with async session management. New connections go through `SessionLocal()`.

3. **AI Caching**: Before making OpenAI API calls, check if analysis already exists in database to save costs.

4. **Error Handling**: Implement graceful fallbacks for all external services. Never crash because an API is unavailable.

5. **Context Manager**: All contextual data flows through `context_manager.py`. Don't bypass it in new features.

6. **Testing**: Use fixtures in `tests/conftest.py`. Mock external services in tests (OpenAI, Icecast2, TTS-WebUI).

7. **Logging**: Use the configured logger. Check `logs/ai_dj.log` for application events.

8. **File Paths**: Use absolute paths or Path objects. Windows and Unix path handling is handled by pathlib.

9. **Performance**: Database queries can be expensive with large music libraries. Use pagination and caching where appropriate.

10. **Dependencies Location**: Pre-installed dependencies are in `lib/` directory. System should work without additional virtual environment for basic development.

## Migration Note
This project was moved from H: to Q: on 2026-03-25 as part of a filesystem reorganization.
Previous location: H:\Development\radio_free_luna
If you encounter hardcoded paths referencing the old location, update them to the current path.
