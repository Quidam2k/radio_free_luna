# Radio Free Luna - AI DJ System

*Where every song tells a story, and context creates the perfect moment*

Radio Free Luna is a self-hosted AI radio station. It scans your music library, builds notes on your tracks, and serves a continuous MP3 stream (`GET /stream.mp3`) with crossfades and generated DJ commentary between songs. It is under active development, so expect rough edges.

Radio Free Luna builds comprehensive knowledge about your music collection, creating contextual playlists and DJ commentary that connects songs through themes, history, and cultural significance. Inspired by Chris in the Morning from Northern Exposure, this AI DJ understands not just music, but the world around it.

## ✨ Features

### 🧠 Intelligent Music Understanding
- **Deep AI Analysis**: Uses OpenAI to analyze lyrics, themes, and cultural significance
- **Automatic Metadata**: Extracts and enriches music metadata from your files
- **Smart Connections**: Discovers thematic and musical relationships between tracks
- **Dynamic Discovery**: Finds hidden gems and makes surprising connections

### 🌍 Contextual Awareness
- **Weather Integration**: Adapts music selection to current weather conditions
- **Time Awareness**: Different personalities for morning, afternoon, evening, and late night
- **Seasonal Programming**: Understands how seasons affect musical moods
- **Cultural Calendar**: Aware of holidays, cultural moments, and music history dates
- **Location Intelligence**: Incorporates local music scenes and cultural characteristics

### 🎤 Natural Voice Commentary
- **TTS-WebUI Integration**: High-quality voice synthesis with multiple voice models
- **Adaptive Personality**: Voice changes throughout the day and with context
- **Thoughtful Commentary**: Chris in the Morning-style philosophical observations
- **Real-time Generation**: Creates spontaneous commentary based on current moment
- **Musical Storytelling**: Shares fascinating stories about artists and songs

### 🎵 Professional Audio Streaming
- **HTTP Streaming**: Real-time MP3 streaming via GET /stream.mp3 with chunked transfer
- **Smart Crossfading**: Adaptive transition types (linear, sine, logarithmic, smart auto-selection) with audio analysis
- **Advanced Audio Processing**: Real-time normalization, compression, and auto-gain control
- **Intelligent Programming**: Creates cohesive musical journeys around themes
- **Seamless Transitions**: Crossfades that adapt to track characteristics
- **Professional Quality**: ffmpeg-based MP3 encoding with per-listener buffering

## 🚀 Quick Start

### Prerequisites
- Python 3.11 (the version the Dockerfile uses)
- Music library in supported formats (MP3, FLAC, WAV, M4A, OGG)
- OpenAI API key (optional, for full AI features)
- TTS-WebUI (optional, for voice synthesis)

### Installation & Startup

1. **Get the code and install dependencies** (a virtual environment is recommended)
```bash
git clone https://github.com/Quidam2k/radio_free_luna.git
cd radio_free_luna
python -m venv .venv
.venv/Scripts/activate        # Windows; on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

2. **Configure the environment**
```bash
cp .env.example .env
# Edit .env: set MUSIC_DIRECTORIES, plus API keys for the features you want
```

3. **Start the server**
```bash
python main.py
```

4. **Open the web interface** at `http://localhost:8080` (override the port with `PORT` in `.env`).

### Project Layout

- `main.py` - FastAPI application entry point
- `src/` - the station: `core/` (config, database, file monitor, listener auth), `analysis/` (AI analysis, lyrics), `context/` (time, weather, location), `dj/` (planner, commentary, personas, sessions), `voice/` (TTS), `streaming/` (broadcaster, crossfader, audio processing), `mixdown/`, `enrich/`, `notes/`, `corpus/`, and `web/` (static web UI)
- `rfl_mcp/` - MCP server that exposes the station's API as agent tools (see its README)
- `scripts/` - maintenance, enrichment and batch-rendering scripts
- `docs/dj/` - DJ style guide and persona definitions
- `tests/` - pytest suite
- `Dockerfile`, `docker-compose.yml` - container setup

### Docker Setup

```bash
# Copy environment configuration
cp .env.example .env
# Edit .env with your settings

# Start with Docker Compose
docker-compose up -d
```

## 📖 Usage

### Web Interface
- Visit `http://localhost:8080` for the main interface
- Check system status at `http://localhost:8080/status`
- View API documentation at `http://localhost:8080/docs`

### API Examples

**Create a themed session:**
```bash
curl -X POST "http://localhost:8080/api/sessions" \
  -H "Content-Type: application/json" \
  -d '{"theme": "rainy_day", "duration_minutes": 60}'
```

**Get current context:**
```bash
curl "http://localhost:8080/api/context"
```

**Generate commentary:**
```bash
curl -X POST "http://localhost:8080/api/commentary" \
  -H "Content-Type: application/json" \
  -d '{"text_type": "contextual"}'
```

**Test voice system:**
```bash
curl -X POST "http://localhost:8080/api/test-voice" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Radio Free Luna"}'
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for AI analysis | Required |
| `MUSIC_DIRECTORIES` | Comma-separated music directory paths | Required |
| `TTS_WEBUI_URL` | TTS-WebUI endpoint for voice synthesis | http://localhost:7860 |
| `WEATHER_API_KEY` | OpenWeatherMap API key | Optional |
| `LOCATION` | Your location for context awareness | Denver, CO |
| `DJ_PERSONALITY` | AI personality style | conversational |
| `KNOWLEDGE_DEPTH` | Commentary depth level | deep |

### DJ Personalities

- **conversational**: Friendly, accessible, Chris in the Morning style
- **classic_radio**: Professional, authoritative radio DJ
- **contemplative**: Deep, philosophical, poetic observations

### Voice Models (TTS-WebUI)

- **alloy**: Balanced, versatile voice
- **echo**: Soft, intimate for late night
- **fable**: Thoughtful, contemplative 
- **nova**: Bright, energetic for mornings
- **onyx**: Professional, authoritative
- **shimmer**: Warm, expressive

## 🎯 Themes and Context

### Built-in Themes
- **rainy_day**: Perfect for contemplative rainy afternoons
- **upbeat**: High-energy, positive motivation music
- **relaxing**: Calm, soothing music for unwinding
- **nostalgic**: Songs that evoke memories
- **driving**: Perfect road trip music
- **love**: Romantic songs and heartbreak

### Contextual Factors
- **Time of Day**: Morning energy vs late night intimacy
- **Weather**: Sunny optimism vs rainy contemplation
- **Season**: Spring renewal vs autumn reflection
- **Holidays**: Special programming for cultural moments
- **Location**: Local music scenes and cultural characteristics

## 🏗️ Architecture

### Core Components
- **File Monitor**: Watches music directories for changes
- **AI Analyzer**: Deep analysis of lyrics, themes, and connections
- **Context Manager**: Real-time awareness of environment
- **Commentary Generator**: AI-powered DJ commentary
- **Voice Synthesizer**: Natural speech with contextual adaptation
- **Session Manager**: Intelligent track sequencing

### Database Schema
- **Tracks**: Metadata and audio properties
- **Analysis**: AI-generated themes and insights
- **Connections**: Relationships between tracks
- **Sessions**: Complete DJ sessions with commentary
- **Context**: Environmental and temporal data

## 🧪 Development

### Running Tests
```bash
pytest tests/
```

### Code Style
```bash
black src/
flake8 src/
```

### Adding New Features
1. Create feature branch
2. Implement with tests
3. Update documentation
4. Submit pull request

## 🎼 Musical Intelligence

Radio Free Luna understands music at multiple levels:

### Thematic Analysis
- Extracts emotional and topical themes from lyrics
- Identifies cultural and historical significance
- Maps connections between different songs and artists
- Understands musical movements and influences

### Contextual Programming
- Weather-aware music selection (rainy day jazz, sunny pop)
- Time-sensitive programming (morning energy, late night intimacy)
- Seasonal awareness (spring renewal, autumn reflection)
- Cultural moment recognition (holidays, anniversaries)

### Intelligent Sequencing
- Energy flow optimization across sessions
- Harmonic mixing for seamless transitions
- Thematic continuity throughout programs
- Discovery balance between familiar and new

## 🌟 Philosophy

Radio Free Luna embodies the spirit of Chris Stephens from Northern Exposure - a DJ who sees music as part of the larger tapestry of human experience. Every song has a story, every moment has its perfect soundtrack, and the AI DJ serves as a thoughtful guide through the musical landscape.

The system respects both the art of music and the science of recommendation, creating experiences that feel both intelligent and deeply human.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome. Open an issue or pull request on GitHub.

## 📞 Support

- Issues: [GitHub Issues](https://github.com/Quidam2k/radio_free_luna/issues)

---

*"In the vast library of human expression, every song is a book, every playlist a curriculum, and every listening session a journey of discovery."* - Radio Free Luna AI DJ