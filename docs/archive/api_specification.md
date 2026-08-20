# API Specification & Web Interface

## REST API Endpoints

### Library Management

#### GET /api/library/stats
Returns overview statistics about the music library.

```json
{
  "total_tracks": 15420,
  "total_artists": 2341,
  "total_albums": 1876,
  "analyzed_tracks": 12450,
  "pending_analysis": 2970,
  "storage_size_gb": 248.7,
  "last_scan": "2025-06-14T10:30:00Z"
}
```

#### POST /api/library/scan
Triggers a library scan for new or modified files.

**Request Body:**
```json
{
  "paths": ["/music/new_albums", "/music/singles"],
  "force_rescan": false,
  "analyze_immediately": true
}
```

**Response:**
```json
{
  "scan_id": "scan_2025_06_15_001",
  "status": "started",
  "estimated_duration": 1800
}
```

#### GET /api/library/scan/{scan_id}
Check the status of a library scan.

```json
{
  "scan_id": "scan_2025_06_15_001",
  "status": "in_progress",
  "progress": 0.67,
  "files_processed": 1205,
  "files_total": 1800,
  "current_file": "/music/new_albums/artist/album/track.mp3",
  "errors": []
}
```

### Track Management

#### GET /api/tracks
List tracks with filtering and pagination.

**Query Parameters:**
- `page`: Page number (default: 1)
- `per_page`: Items per page (default: 50, max: 200)
- `artist`: Filter by artist name
- `genre`: Filter by genre
- `year`: Filter by year
- `theme`: Filter by theme tags
- `analyzed`: Filter by analysis status (true/false)
- `sort`: Sort by (title, artist, year, duration, added_date)
- `order`: Sort order (asc, desc)

**Response:**
```json
{
  "tracks": [
    {
      "id": 12345,
      "title": "Bohemian Rhapsody",
      "artist": "Queen",
      "album": "A Night at the Opera",
      "year": 1975,
      "duration": 354,
      "file_path": "/music/queen/a_night_at_the_opera/bohemian_rhapsody.mp3",
      "themes": ["love", "loss", "opera", "rock"],
      "mood": {
        "valence": 0.3,
        "energy": 0.8,
        "danceability": 0.4
      },
      "analysis_status": "complete",
      "last_played": "2025-06-10T15:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 15420,
    "pages": 309
  }
}
```

#### GET /api/tracks/{track_id}
Get detailed information about a specific track.

```json
{
  "id": 12345,
  "title": "Bohemian Rhapsody",
  "artist": "Queen",
  "album": "A Night at the Opera",
  "year": 1975,
  "duration": 354,
  "file_path": "/music/queen/a_night_at_the_opera/bohemian_rhapsody.mp3",
  "file_size": 8472653,
  "bitrate": 320,
  "sample_rate": 44100,
  "themes": ["love", "loss", "opera", "rock", "classical"],
  "mood": {
    "valence": 0.3,
    "energy": 0.8,
    "danceability": 0.4
  },
  "audio_features": {
    "key": "Bb major",
    "tempo": 72,
    "time_signature": "4/4",
    "loudness": -11.2
  },
  "lyrics": "Is this the real life? Is this just fantasy?...",
  "analysis": {
    "summary": "Epic rock opera exploring themes of identity, reality, and mortality through multiple musical movements.",
    "cultural_context": "Revolutionary song that broke conventional radio format rules...",
    "notable_elements": ["Multi-part structure", "Opera section", "Hard rock finale"]
  },
  "connections": [
    {
      "track_id": 23456,
      "track_title": "We Will Rock You",
      "connection_type": "same_artist",
      "strength": 0.8,
      "description": "Both showcase Queen's theatrical rock style"
    }
  ],
  "play_count": 47,
  "last_played": "2025-06-10T15:30:00Z",
  "created_at": "2025-03-15T09:22:00Z",
  "updated_at": "2025-06-01T14:15:00Z"
}
```

#### POST /api/tracks/{track_id}/analyze
Trigger analysis for a specific track.

```json
{
  "force_reanalysis": false,
  "include_lyrics": true,
  "include_themes": true,
  "include_connections": true
}
```

### Artist Information

#### GET /api/artists
List artists with their information.

```json
{
  "artists": [
    {
      "id": 456,
      "name": "Queen",
      "biography": "British rock band formed in London in 1970...",
      "formed_year": 1970,
      "origin_country": "United Kingdom",
      "genres": ["rock", "arena rock", "glam rock", "progressive rock"],
      "track_count": 87,
      "album_count": 15,
      "image_url": "https://example.com/queen.jpg",
      "wikipedia_url": "https://en.wikipedia.org/wiki/Queen_(band)"
    }
  ]
}
```

#### GET /api/artists/{artist_id}
Get detailed artist information including discography.

```json
{
  "id": 456,
  "name": "Queen",
  "biography": "British rock band formed in London in 1970...",
  "formed_year": 1970,
  "origin_country": "United Kingdom",
  "genres": ["rock", "arena rock", "glam rock", "progressive rock"],
  "members": [
    {
      "name": "Freddie Mercury",
      "role": "Lead vocals, piano",
      "years": "1970-1991"
    }
  ],
  "discography": [
    {
      "album": "A Night at the Opera",
      "year": 1975,
      "track_count": 12,
      "tracks": [
        {
          "id": 12345,
          "title": "Bohemian Rhapsody",
          "duration": 354
        }
      ]
    }
  ],
  "influences": ["Led Zeppelin", "The Beatles", "David Bowie"],
  "influenced": ["Muse", "Foo Fighters", "My Chemical Romance"],
  "awards": ["Rock and Roll Hall of Fame (2001)", "Grammy Lifetime Achievement Award (2018)"],
  "notable_songs": [12345, 23456, 34567],
  "cultural_impact": "Pioneers of stadium rock and theatrical performance...",
  "play_statistics": {
    "total_plays": 2847,
    "most_played_track": {
      "id": 12345,
      "title": "Bohemian Rhapsody",
      "play_count": 47
    }
  }
}
```

### DJ Sessions

#### POST /api/sessions
Create a new DJ session.

**Request Body:**
```json
{
  "name": "Sunday Morning Vibes",
  "theme": "relaxing",
  "duration_minutes": 120,
  "parameters": {
    "energy_progression": "gradual_increase",
    "include_commentary": true,
    "commentary_frequency": "moderate",
    "crossfade_duration": 8,
    "allow_explicit": false,
    "preferred_decades": ["1970s", "1980s", "1990s"],
    "mood_target": {
      "valence": 0.7,
      "energy": 0.4
    }
  }
}
```

**Response:**
```json
{
  "session_id": "session_2025_06_15_001",
  "status": "created",
  "estimated_generation_time": 45
}
```

#### GET /api/sessions/{session_id}
Get session details and current status.

```json
{
  "session_id": "session_2025_06_15_001",
  "name": "Sunday Morning Vibes",
  "theme": "relaxing",
  "status": "ready", // created, generating, ready, playing, completed, error
  "created_at": "2025-06-15T08:30:00Z",
  "duration_minutes": 120,
  "tracks": [
    {
      "position": 1,
      "track": {
        "id": 78901,
        "title": "The Night We Met",
        "artist": "Lord Huron",
        "duration": 243
      },
      "start_time": "00:00:00",
      "commentary_before": {
        "text": "Good morning, and welcome to our Sunday morning journey...",
        "duration": 15,
        "voice_style": "conversational"
      }
    }
  ],
  "total_duration": 7230,
  "commentary_segments": 12,
  "play_statistics": {
    "started_at": "2025-06-15T09:00:00Z",
    "current_position": 3,
    "current_track_progress": 0.42,
    "listeners": 1
  }
}
```

#### POST /api/sessions/{session_id}/start
Start playing a session.

```json
{
  "stream_url": "http://localhost:8000/ai_dj_stream",
  "started_at": "2025-06-15T09:00:00Z",
  "estimated_end": "2025-06-15T11:00:00Z"
}
```

#### POST /api/sessions/{session_id}/stop
Stop a playing session.

#### GET /api/sessions/{session_id}/now-playing
Get current playing information.

```json
{
  "session_id": "session_2025_06_15_001",
  "current_track": {
    "id": 78901,
    "title": "The Night We Met",
    "artist": "Lord Huron",
    "album": "Strange Trails",
    "duration": 243,
    "position": 3
  },
  "progress": {
    "elapsed_seconds": 102,
    "remaining_seconds": 141,
    "percentage": 0.42
  },
  "next_track": {
    "id": 89012,
    "title": "Rivers and Roads",
    "artist": "The Head and the Heart"
  },
  "upcoming_commentary": {
    "text": "The Head and the Heart brings us this beautiful reflection on distance and longing...",
    "scheduled_at": "00:04:03"
  },
  "listeners": 1,
  "stream_url": "http://localhost:8000/ai_dj_stream"
}
```

### Theme Management

#### GET /api/themes
List all available themes with statistics.

```json
{
  "themes": [
    {
      "name": "love",
      "track_count": 2847,
      "description": "Songs about romantic love, relationships, and heartbreak",
      "mood_range": {
        "valence": [-0.8, 0.9],
        "energy": [0.1, 1.0]
      },
      "popular_artists": ["Taylor Swift", "Ed Sheeran", "Adele"],
      "sample_tracks": [12345, 23456, 34567]
    }
  ]
}
```

#### GET /api/themes/{theme_name}/tracks
Get tracks for a specific theme.

#### POST /api/themes/custom
Create a custom theme definition.

**Request Body:**
```json
{
  "name": "rainy_day",
  "description": "Perfect for contemplative rainy afternoons",
  "keywords": ["rain", "melancholy", "introspective", "acoustic"],
  "mood_criteria": {
    "valence": [-0.5, 0.3],
    "energy": [0.2, 0.6]
  },
  "genre_preferences": ["folk", "indie", "acoustic"],
  "exclude_genres": ["death metal", "hardcore"]
}
```

### Analytics and Insights

#### GET /api/analytics/listening-patterns
Get listening pattern analysis.

```json
{
  "time_periods": {
    "morning": {"most_played_themes": ["upbeat", "coffee"], "average_energy": 0.7},
    "afternoon": {"most_played_themes": ["work", "focus"], "average_energy": 0.5},
    "evening": {"most_played_themes": ["relaxing", "dinner"], "average_energy": 0.4},
    "night": {"most_played_themes": ["ambient", "sleep"], "average_energy": 0.2}
  },
  "favorite_artists": [
    {"name": "Queen", "play_count": 2847, "avg_session_length": 45},
    {"name": "The Beatles", "play_count": 2103, "avg_session_length": 38}
  ],
  "theme_popularity": [
    {"theme": "love", "sessions": 156, "avg_duration": 67},
    {"theme": "rock", "sessions": 134, "avg_duration": 82}
  ]
}
```

#### GET /api/analytics/discovery
Get music discovery insights.

```json
{
  "recommendations": [
    {
      "track_id": 99999,
      "title": "New Song You Might Like",
      "artist": "Similar Artist",
      "reason": "Based on your love for Queen's theatrical style",
      "confidence": 0.87
    }
  ],
  "underplayed_gems": [
    {
      "track_id": 88888,
      "title": "Hidden Gem",
      "artist": "Favorite Artist",
      "reason": "Great track you've only played once",
      "themes": ["love", "acoustic"]
    }
  ],
  "genre_exploration": {
    "current_preferences": ["rock", "pop", "folk"],
    "suggested_expansions": ["indie rock", "alternative folk", "art rock"],
    "gateway_tracks": [77777, 66666, 55555]
  }
}
```

## WebSocket Events

### Real-time Updates

**Connection:** `ws://localhost:8080/ws`

#### Session Events
```javascript
// Session started
{
  "type": "session_started",
  "session_id": "session_2025_06_15_001",
  "stream_url": "http://localhost:8000/ai_dj_stream"
}

// Track changed
{
  "type": "track_changed",
  "session_id": "session_2025_06_15_001",
  "current_track": {
    "id": 78901,
    "title": "The Night We Met",
    "artist": "Lord Huron"
  },
  "progress": 0.0
}

// Progress update (sent every 5 seconds during playback)
{
  "type": "progress_update",
  "session_id": "session_2025_06_15_001",
  "elapsed_seconds": 127,
  "remaining_seconds": 116,
  "percentage": 0.52
}

// Commentary starting
{
  "type": "commentary_started",
  "session_id": "session_2025_06_15_001",
  "text": "The Head and the Heart brings us this beautiful reflection...",
  "duration": 18
}
```

#### Library Events
```javascript
// New tracks discovered
{
  "type": "tracks_added",
  "count": 15,
  "tracks": [78901, 78902, 78903]
}

// Analysis completed
{
  "type": "analysis_completed",
  "track_id": 78901,
  "themes": ["love", "acoustic", "melancholy"]
}
```

## Web Interface Specifications

### Dashboard Layout

#### Header Navigation
- AI DJ logo/branding
- Current session status indicator
- Quick theme selector
- Settings menu
- User profile (future)

#### Main Content Areas

**Left Sidebar (25%)**
- Library statistics
- Quick actions (scan library, create session)
- Theme browser
- Recent sessions history

**Center Panel (50%)**
- Now playing display (when session active)
  - Album artwork
  - Track information
  - Progress bar
  - Next track preview
- Session creation form (when no session)
- Theme exploration interface

**Right Sidebar (25%)**
- Live stream player controls
- Commentary transcript
- Upcoming tracks queue
- Session analytics

#### Footer
- System status indicators
- Background task progress
- Quick links to documentation

### Responsive Design Breakpoints

**Desktop (>1200px)**
- Full three-panel layout
- Rich media controls
- Advanced filtering options

**Tablet (768px - 1200px)**
- Collapsible sidebars
- Touch-optimized controls
- Streamlined interface

**Mobile (<768px)**
- Single-column layout
- Bottom navigation bar
- Swipe gestures for navigation
- Minimal but functional controls

### Key Interactive Components

#### Session Creator
- Theme selection with preview
- Duration slider with time estimates
- Energy progression curve editor
- Advanced options panel
- Real-time track count updates

#### Now Playing Widget
- Large album artwork
- Animated progress indicators
- Skip/pause/stop controls
- Volume control
- Share current session button

#### Library Browser
- Virtual scrolling for large collections
- Multi-column sorting
- Advanced search with autocomplete
- Filter chips for quick refinement
- Bulk actions for selected tracks

#### Theme Explorer
- Visual theme categorization
- Mood matrix visualization
- Related theme suggestions
- Custom theme creation wizard
- Theme popularity charts

### Accessibility Features

- ARIA labels for all interactive elements
- Keyboard navigation support
- High contrast mode option
- Screen reader optimized
- Reduced motion preferences
- Audio descriptions for visual elements

### Performance Optimizations

- Lazy loading for large track lists
- Progressive image loading
- WebSocket connection management
- Local caching for frequently accessed data
- Debounced search inputs
- Virtualized scrolling for performance

This comprehensive API specification provides the foundation for building both the backend services and frontend interfaces that will make the AI DJ system come to life!