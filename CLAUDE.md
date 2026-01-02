# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Radio Free Luna** is an intelligent AI-powered DJ system that streams music with contextual awareness and natural voice commentary. The system understands weather, time of day, season, location, and cultural moments to create "perfect musical moments" through smart track sequencing and AI-generated DJ commentary.

## Quick Start Commands

### Running the Application
```bash
# Main launcher (graceful initialization with mock component fallback)
python launch_radio_free_luna.py

# Access web interface
http://localhost:8080
```

### Database and Scanning
```bash
# Initialize database
python setup.py init-db

# Scan music directories for audio files
python setup.py scan-music --path /path/to/music
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

### Docker
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
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
- `weather.py` - OpenWeatherMap integration for weather-based mood shifts
- `location.py` - Location-based music scene analysis

**`src/dj/`** - DJ Intelligence
- `session_manager.py` - Track sequencing and themed session creation
- `commentary_generator.py` - AI-powered DJ commentary with philosophical observations

**`src/voice/`** - Text-to-Speech
- `tts_config.py` - TTS configuration and model management
- `tts_client.py` - TTS-WebUI client integration
- `contextual_voice.py` - Adaptive voice based on time and mood

**`src/streaming/`** - Audio Streaming
- `stream_manager.py` - Main streaming orchestration
- `audio_server.py` - HTTP audio streaming server
- `audio_processor.py` - Audio normalization, compression, auto-gain
- `icecast_client.py` - Professional Icecast2 HTTP streaming client
- `crossfader.py` - 5 types of smart audio transitions (linear, exponential, sine, logarithmic, intelligent)

**`src/web/`** - Web Interface
- Static HTML, CSS, JavaScript files in `src/web/static/`

### Data Flow

1. **Initialization**: `launch_radio_free_luna.py` → `main.py` (RadioFreeLuna class) → FastAPI app
2. **Music Scanning**: File monitor detects changes → metadata extraction → database storage
3. **AI Analysis**: New tracks → Genius API (lyrics) → OpenAI (deep analysis) → database cache
4. **Session Creation**: User request → context_manager gathers context → session_manager sequences tracks
5. **DJ Commentary**: Track plays → commentary_generator creates context-aware comments → TTS-WebUI synthesizes voice
6. **Audio Streaming**: Track audio → audio_processor (normalization) → crossfader (transitions) → icecast_client (Icecast2)

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
- **Audio Processing**: pydub, librosa, scipy, mutagen, soundfile
- **AI/Analytics**: OpenAI (GPT), numpy, pandas
- **Voice Synthesis**: TTS-WebUI client for high-quality synthesis
- **Streaming**: Icecast2 integration with custom audio processing
- **File Monitoring**: watchdog
- **Background Tasks**: Celery, Redis
- **Testing**: pytest, pytest-asyncio
- **Code Quality**: black, flake8, isort

## Configuration

### Environment Variables (.env)
```
OPENAI_API_KEY=your_key_here          # For AI analysis and commentary
MUSIC_DIRECTORIES=/path/to/music      # Comma-separated music folders
DATABASE_URL=sqlite:///data/radio_free_luna.db  # Database connection
TTS_WEBUI_URL=http://localhost:7860   # TTS service URL
LOCATION=Denver, CO                   # For weather/location context
DJ_PERSONALITY=conversational         # DJ commentary style
KNOWLEDGE_DEPTH=moderate              # Analysis depth
ICECAST_HOST=localhost                # For audio streaming
ICECAST_PORT=8000
ICECAST_PASSWORD=your_password
STREAM_MOUNT=/ai_dj_stream
```

### Optional External Services
- **OpenAI API**: For AI commentary (mock fallback available)
- **TTS-WebUI**: For voice synthesis (can run without voice)
- **Icecast2**: For real audio streaming (mock mode available)
- **OpenWeatherMap**: For weather integration
- **Genius API**: For lyrics fetching

## Important Implementation Details

### AI Integration
- AI responses are **cached** in the database to avoid repeated API calls
- **Mock fallback** available if OpenAI API unavailable
- Commentary includes philosophical observations tied to context
- Track analysis includes mood, themes, energy, and cultural significance

### Audio Streaming Architecture
- **Smart Crossfading**: Automatically selects transition type based on track characteristics
- **Audio Processing**: Normalization and compression for consistent levels
- **Graceful Fallback**: Works in mock mode without Icecast2
- Supports both **real streaming** (Icecast2) and **mock/file output** modes

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

- `GET /` - Web interface
- `GET /health` - Basic health check
- `GET /status` - Detailed system status
- `GET /api/context` - Current contextual information
- `POST /api/sessions` - Create themed DJ session
- `POST /api/commentary` - Generate AI commentary for a track
- `POST /api/test-voice` - Test voice synthesis
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
