# Getting Started - AI DJ Development Setup

## Prerequisites

- Python 3.9+ or Node.js 18+
- SQLite3 (for development) or PostgreSQL (for production)
- FFmpeg (for audio processing)
- OpenAI API key
- Optional: Genius API key for lyrics

## Quick Start

### 1. Environment Setup

```bash
# Create project directory
mkdir ai-dj-system
cd ai-dj-system

# Python setup (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create `.env` file:
```env
# API Keys
OPENAI_API_KEY=your_openai_api_key_here
GENIUS_API_TOKEN=your_genius_token_here

# Database
DATABASE_URL=sqlite:///ai_dj.db

# Music Directories (comma-separated)
MUSIC_DIRECTORIES=/path/to/music1,/path/to/music2

# Streaming
ICECAST_HOST=localhost
ICECAST_PORT=8000
ICECAST_PASSWORD=your_password

# AI Personality
DJ_PERSONALITY=conversational
KNOWLEDGE_DEPTH=deep
TRIVIA_FREQUENCY=moderate
```

### 3. Initial Setup

```bash
# Initialize database
python setup.py init-db

# Scan music directories (initial scan)
python setup.py scan-music --path /path/to/your/music

# Start the development server
python main.py
```

## Project Structure

```
ai-dj-system/
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── file_monitor.py
│   │   └── config.py
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── lyrics_fetcher.py
│   │   ├── ai_analyzer.py
│   │   └── audio_analyzer.py
│   ├── dj/
│   │   ├── __init__.py
│   │   ├── session_manager.py
│   │   ├── commentary_generator.py
│   │   └── track_sequencer.py
│   ├── streaming/
│   │   ├── __init__.py
│   │   ├── audio_server.py
│   │   └── stream_manager.py
│   └── web/
│       ├── __init__.py
│       ├── api.py
│       ├── static/
│       └── templates/
├── tests/
├── docs/
├── requirements.txt
├── setup.py
├── main.py
└── .env
```

## Development Workflow

### Phase 4: Streaming & Polish (Week 7-8)

#### Day 43-49: Audio Streaming
```bash
# Focus on these files:
src/streaming/audio_server.py    # Icecast2 integration
src/streaming/crossfader.py      # Real-time audio mixing
src/streaming/stream_manager.py  # Stream session management
```

#### Day 50-56: Final Integration
```bash
# Focus on these files:
src/web/dashboard.py             # Complete web interface
src/streaming/tts_engine.py      # Text-to-speech for commentary
main.py                          # Application orchestration
docker-compose.yml               # Deployment configuration
```

## Testing Strategy

### Unit Tests
```bash
# Run individual component tests
python -m pytest tests/test_metadata.py
python -m pytest tests/test_ai_analysis.py
python -m pytest tests/test_dj_engine.py
```

### Integration Tests
```bash
# Test full pipeline
python -m pytest tests/test_full_pipeline.py

# Test with sample music files
python scripts/test_with_samples.py
```

### Performance Tests
```bash
# Large library scanning performance
python scripts/benchmark_scanning.py

# AI analysis throughput
python scripts/benchmark_ai_analysis.py
```

## Debugging and Monitoring

### Logging Configuration
```python
# In src/core/config.py
import logging
import sys

def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('ai_dj.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
```

### Monitoring Endpoints
```bash
# Health check
curl http://localhost:8080/health

# System status
curl http://localhost:8080/status

# Current session info
curl http://localhost:8080/api/session/current
```

## Deployment Options

### Local Development
```bash
# Simple single-process development server
python main.py --dev

# With file watching for auto-reload
python main.py --dev --reload
```

### Docker Deployment
```bash
# Build and run with docker-compose
docker-compose up -d

# Scale analysis workers
docker-compose up -d --scale analysis-worker=3
```

### Production Deployment
```bash
# Using systemd service
sudo cp scripts/ai-dj.service /etc/systemd/system/
sudo systemctl enable ai-dj
sudo systemctl start ai-dj
```

## Common Issues and Solutions

### Music File Scanning Issues
- **Problem**: Files not being detected
- **Solution**: Check file permissions and supported formats
- **Debug**: `python scripts/debug_scanning.py /path/to/music`

### AI Analysis Errors
- **Problem**: OpenAI API rate limits
- **Solution**: Implement exponential backoff and queuing
- **Debug**: Check `logs/ai_analysis.log` for API responses

### Audio Streaming Problems
- **Problem**: Icecast connection issues
- **Solution**: Verify Icecast2 configuration and firewall settings
- **Debug**: `netstat -tulpn | grep :8000`

### Memory Usage
- **Problem**: High memory consumption during large library scans
- **Solution**: Implement batch processing and garbage collection
- **Monitor**: `python scripts/memory_monitor.py`

## Advanced Configuration

### AI Personality Customization
```python
# In src/dj/personality.py
PERSONALITY_PRESETS = {
    "chris_in_the_morning": {
        "speaking_style": "philosophical",
        "knowledge_depth": "deep",
        "cultural_references": "high",
        "poetry_frequency": "frequent",
        "trivia_style": "contemplative"
    },
    "classic_radio": {
        "speaking_style": "professional",
        "knowledge_depth": "moderate", 
        "cultural_references": "medium",
        "poetry_frequency": "rare",
        "trivia_style": "factual"
    }
}
```

### Custom Theme Categories
```python
# In src/analysis/themes.py
CUSTOM_THEMES = {
    "seasons": ["spring", "summer", "autumn", "winter"],
    "emotions": ["love", "heartbreak", "joy", "melancholy"],
    "activities": ["driving", "working", "relaxing", "partying"],
    "times": ["morning", "afternoon", "evening", "late_night"]
}
```

### Audio Processing Parameters
```python
# In src/streaming/audio_config.py
CROSSFADE_SETTINGS = {
    "default_duration": 8.0,  # seconds
    "fade_curve": "exponential",
    "tempo_sync": True,
    "key_matching": True
}
```

## Next Steps After MVP

### Enhanced Features to Consider
1. **Voice Control Integration**
   - "Hey DJ, play something upbeat"
   - "Tell me about this artist"

2. **Machine Learning Improvements**
   - User preference learning
   - Listening pattern analysis
   - Improved connection algorithms

3. **Social Features**
   - Guest DJ sessions
   - Listener requests and feedback
   - Collaborative playlists

4. **Advanced Audio Processing**
   - Automatic gain control
   - Dynamic EQ based on content
   - Smart crossfading with beat detection

5. **Mobile Apps**
   - React Native remote control
   - Offline playlist preparation
   - Push notifications for favorite themes

### Performance Optimization
1. **Caching Strategy**
   - Redis for frequently accessed data
   - CDN for audio delivery
   - Background pre-computation

2. **Scalability**
   - Microservices architecture
   - Kubernetes deployment
   - Load balancing for multiple streams

3. **Data Pipeline**
   - Apache Kafka for event streaming
   - Apache Airflow for workflow orchestration
   - Data lake for analytics

## Contributing Guidelines

### Code Style
- Follow PEP 8 for Python
- Use type hints where appropriate
- Document all public functions
- Write tests for new features

### Git Workflow
```bash
# Feature development
git checkout -b feature/track-sequencing
git commit -m "Add harmonic mixing algorithm"
git push origin feature/track-sequencing

# Create pull request with:
# - Clear description
# - Test coverage
# - Documentation updates
```

### Issue Reporting
Include:
- System information (OS, Python version)
- Steps to reproduce
- Expected vs actual behavior
- Relevant log excerpts
- Sample files (if applicable) 1: Core System (First 2 Weeks)

#### Day 1-3: Database and File Monitoring
```bash
# Focus on these files:
src/core/database.py      # Database models and connections
src/core/file_monitor.py  # File system watching
setup.py                  # Database initialization
```

#### Day 4-7: Metadata Extraction
```bash
# Focus on these files:
src/core/metadata_extractor.py  # Audio file metadata
src/analysis/audio_analyzer.py  # Basic audio analysis
tests/test_metadata.py          # Test coverage
```

#### Day 8-14: Basic Web Interface
```bash
# Focus on these files:
src/web/api.py           # REST API endpoints
src/web/templates/       # Basic HTML interface
src/web/static/          # CSS/JS for web UI
```

### Phase 2: AI Integration (Week 3-4)

#### Day 15-21: Lyrics and Analysis
```bash
# Focus on these files:
src/analysis/lyrics_fetcher.py  # Genius API integration
src/analysis/ai_analyzer.py     # OpenAI integration
src/core/themes.py              # Theme categorization
```

#### Day 22-28: Connection Discovery
```bash
# Focus on these files:
src/analysis/connection_finder.py  # Track relationship analysis
src/dj/recommendation_engine.py    # Smart playlist generation
tests/test_connections.py          # Test relationship algorithms
```

### Phase 3: DJ Engine (Week 5-6)

#### Day 29-35: Commentary Generation
```bash
# Focus on these files:
src/dj/commentary_generator.py  # AI-powered DJ commentary
src/dj/personality.py           # DJ personality system
src/dj/session_manager.py       # Session orchestration
```

#### Day 36-42: Track Sequencing
```bash
# Focus on these files:
src/dj/track_sequencer.py       # Intelligent track ordering
src/dj/transition_analyzer.py   # Seamless transitions
src/analysis/harmonic_mixing.py # Key-aware mixing
```

### Phase