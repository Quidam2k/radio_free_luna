# Contextual Awareness & Environmental Intelligence

## Overview

The AI DJ system incorporates deep contextual awareness to create a truly responsive and present musical experience. It understands not just the music, but the world around it - the time, season, weather, local events, and cultural moments that shape how we experience music.

## Contextual Data Sources

### Temporal Context

#### Calendar Awareness
```python
# src/context/temporal.py
import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class TemporalContext:
    current_time: datetime.datetime
    season: str
    holiday: Optional[str]
    time_of_day: str
    day_of_week: str
    month: str
    is_weekend: bool
    special_dates: List[str]

class TemporalAnalyzer:
    def __init__(self):
        self.holidays = {
            # Fixed holidays
            "01-01": "New Year's Day",
            "02-14": "Valentine's Day", 
            "03-17": "St. Patrick's Day",
            "07-04": "Independence Day",
            "10-31": "Halloween",
            "11-11": "Veterans Day",
            "12-25": "Christmas",
            "12-31": "New Year's Eve",
            
            # Cultural observances
            "04-22": "Earth Day",
            "05-05": "Cinco de Mayo",
            "06-19": "Juneteenth",
            "09-11": "9/11 Remembrance",
            
            # Music-specific dates
            "01-08": "Elvis Birthday",
            "02-06": "Bob Marley Birthday",
            "06-18": "Paul McCartney Birthday",
            "08-16": "Elvis Death Anniversary",
            "12-08": "John Lennon Memorial",
        }
        
        # Floating holidays (calculated dynamically)
        self.floating_holidays = [
            "Mother's Day", "Father's Day", "Easter", "Thanksgiving",
            "Labor Day", "Memorial Day", "Martin Luther King Day"
        ]
    
    def get_current_context(self) -> TemporalContext:
        now = datetime.datetime.now()
        
        return TemporalContext(
            current_time=now,
            season=self.get_season(now),
            holiday=self.get_current_holiday(now),
            time_of_day=self.get_time_of_day(now),
            day_of_week=now.strftime("%A"),
            month=now.strftime("%B"),
            is_weekend=now.weekday() >= 5,
            special_dates=self.get_special_dates(now)
        )
    
    def get_season(self, date: datetime.datetime) -> str:
        month = date.month
        day = date.day
        
        if month == 12 and day >= 21 or month <= 2:
            return "winter"
        elif month == 3 and day >= 20 or month <= 5:
            return "spring" 
        elif month == 6 and day >= 21 or month <= 8:
            return "summer"
        else:
            return "autumn"
    
    def get_time_of_day(self, date: datetime.datetime) -> str:
        hour = date.hour
        
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "late_night"
    
    def get_current_holiday(self, date: datetime.datetime) -> Optional[str]:
        # Check fixed holidays
        date_key = date.strftime("%m-%d")
        if date_key in self.holidays:
            return self.holidays[date_key]
        
        # Check floating holidays (would need more complex calculation)
        return self.calculate_floating_holiday(date)
    
    def get_special_dates(self, date: datetime.datetime) -> List[str]:
        """Get contextually relevant date markers"""
        special = []
        
        # Seasonal transitions
        if date.month == 3 and 19 <= date.day <= 21:
            special.append("Spring Equinox")
        elif date.month == 6 and 20 <= date.day <= 22:
            special.append("Summer Solstice")
        
        # Cultural periods
        if date.month == 2:
            special.append("Black History Month")
        elif date.month == 3:
            special.append("Women's History Month")
        elif date.month == 10:
            special.append("Halloween Season")
        elif date.month == 12:
            special.append("Holiday Season")
        
        # Music history dates
        if date.month == 8 and date.day == 15:
            special.append("Woodstock Anniversary")
        elif date.month == 7 and date.day == 13:
            special.append("Live Aid Anniversary")
        
        return special
```

### Weather Integration

```python
# src/context/weather.py
import requests
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class WeatherContext:
    condition: str  # sunny, rainy, cloudy, stormy, snowy
    temperature: float
    humidity: float
    wind_speed: float
    pressure: float
    visibility: float
    mood_impact: str  # cheerful, melancholy, cozy, energetic, contemplative

class WeatherAnalyzer:
    def __init__(self, api_key: str, location: str):
        self.api_key = api_key
        self.location = location
        self.weather_to_mood = {
            "sunny": "cheerful",
            "partly_cloudy": "optimistic", 
            "cloudy": "contemplative",
            "rainy": "melancholy",
            "stormy": "dramatic",
            "snowy": "cozy",
            "foggy": "mysterious",
            "windy": "restless"
        }
    
    async def get_current_weather(self) -> Optional[WeatherContext]:
        try:
            # Using OpenWeatherMap API as example
            url = f"http://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": self.location,
                "appid": self.api_key,
                "units": "imperial"
            }
            
            response = requests.get(url, params=params)
            data = response.json()
            
            condition = self.normalize_condition(data["weather"][0]["main"])
            temp = data["main"]["temp"]
            
            return WeatherContext(
                condition=condition,
                temperature=temp,
                humidity=data["main"]["humidity"],
                wind_speed=data["wind"]["speed"],
                pressure=data["main"]["pressure"],
                visibility=data.get("visibility", 10000),
                mood_impact=self.weather_to_mood.get(condition, "neutral")
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch weather: {e}")
            return None
    
    def normalize_condition(self, api_condition: str) -> str:
        """Normalize API weather conditions to our standard set"""
        condition_map = {
            "Clear": "sunny",
            "Clouds": "cloudy", 
            "Rain": "rainy",
            "Drizzle": "rainy",
            "Thunderstorm": "stormy",
            "Snow": "snowy",
            "Mist": "foggy",
            "Fog": "foggy"
        }
        return condition_map.get(api_condition, "cloudy")
```

### Location & Cultural Context

```python
# src/context/location.py
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class LocationContext:
    city: str
    state: str
    country: str
    timezone: str
    local_events: List[str]
    cultural_characteristics: Dict[str, str]
    music_scene: Dict[str, any]
    nearby_venues: List[str]

class LocationAnalyzer:
    def __init__(self, location: str):
        self.location = location
        self.cultural_data = {
            "Nashville": {
                "music_scene": "country_capital",
                "characteristics": ["music_city", "honky_tonk", "grand_ole_opry"],
                "local_flavor": "southern_hospitality"
            },
            "New Orleans": {
                "music_scene": "jazz_birthplace", 
                "characteristics": ["jazz", "blues", "creole", "mardi_gras"],
                "local_flavor": "big_easy"
            },
            "Seattle": {
                "music_scene": "grunge_origin",
                "characteristics": ["indie", "coffee_culture", "rain"],
                "local_flavor": "pacific_northwest"
            },
            "Austin": {
                "music_scene": "live_music_capital",
                "characteristics": ["keep_it_weird", "sxsw", "bbq"],
                "local_flavor": "texas_quirky"
            }
        }
    
    async def get_location_context(self) -> LocationContext:
        # Get basic location info
        location_data = await self.geocode_location()
        
        # Get local events
        events = await self.get_local_events()
        
        # Get cultural context
        cultural = self.cultural_data.get(location_data["city"], {})
        
        return LocationContext(
            city=location_data["city"],
            state=location_data["state"], 
            country=location_data["country"],
            timezone=location_data["timezone"],
            local_events=events,
            cultural_characteristics=cultural.get("characteristics", []),
            music_scene=cultural.get("music_scene", {}),
            nearby_venues=await self.get_nearby_venues()
        )
    
    async def get_local_events(self) -> List[str]:
        """Fetch local events that might influence music selection"""
        # Integration with Eventbrite, local APIs, etc.
        events = []
        
        # Example: Sports events
        if "championship" in await self.check_sports_events():
            events.append("local_team_championship")
        
        # Example: Festivals
        festival_data = await self.check_music_festivals()
        events.extend(festival_data)
        
        return events
```

## Contextual Music Selection Engine

```python
# src/dj/contextual_engine.py
from typing import List, Dict, Optional
import json
from dataclasses import dataclass

@dataclass
class ContextualWeights:
    temporal: float = 0.3
    weather: float = 0.25
    location: float = 0.2
    mood: float = 0.15
    user_history: float = 0.1

class ContextualMusicEngine:
    def __init__(self, db_manager, ai_client):
        self.db_manager = db_manager
        self.ai_client = ai_client
        self.weights = ContextualWeights()
        
        # Contextual associations
        self.seasonal_themes = {
            "winter": ["christmas", "cozy", "fireplace", "snow", "hibernation", "reflection"],
            "spring": ["renewal", "love", "growth", "optimism", "fresh_start", "blooming"],
            "summer": ["vacation", "freedom", "beach", "road_trip", "party", "sunshine"],
            "autumn": ["nostalgia", "change", "harvest", "school", "melancholy", "falling_leaves"]
        }
        
        self.weather_themes = {
            "rainy": ["melancholy", "introspection", "cozy", "jazz", "indie", "contemplative"],
            "sunny": ["upbeat", "happy", "energetic", "pop", "dance", "optimistic"],
            "stormy": ["dramatic", "powerful", "rock", "classical", "emotional", "intense"],
            "snowy": ["peaceful", "quiet", "ambient", "folk", "acoustic", "serene"],
            "cloudy": ["mellow", "alternative", "singer-songwriter", "thoughtful"]
        }
        
        self.time_themes = {
            "morning": ["wake_up", "coffee", "motivation", "upbeat", "fresh_start"],
            "afternoon": ["work", "productivity", "steady", "background", "focused"],
            "evening": ["dinner", "relaxation", "family", "mellow", "unwinding"],
            "late_night": ["intimate", "quiet", "contemplative", "ambient", "deep"]
        }
        
        self.holiday_themes = {
            "Christmas": ["christmas", "holiday", "family", "tradition", "joy", "winter"],
            "Halloween": ["spooky", "dark", "fun", "party", "mysterious", "theatrical"],
            "Valentine's Day": ["love", "romance", "intimate", "heart", "relationship"],
            "Independence Day": ["patriotic", "america", "freedom", "celebration", "summer"],
            "New Year's Eve": ["celebration", "party", "reflection", "new_beginning", "countdown"]
        }
    
    async def get_contextual_recommendations(self, 
                                           temporal_context, 
                                           weather_context, 
                                           location_context,
                                           session_theme: Optional[str] = None) -> List[Dict]:
        """Generate music recommendations based on full context"""
        
        # Build contextual scoring
        context_themes = self.build_context_themes(
            temporal_context, weather_context, location_context
        )
        
        # Get candidate tracks
        candidates = await self.get_candidate_tracks(context_themes, session_theme)
        
        # Score tracks based on contextual relevance
        scored_tracks = []
        for track in candidates:
            score = await self.calculate_contextual_score(
                track, temporal_context, weather_context, location_context
            )
            scored_tracks.append((track, score))
        
        # Sort by relevance score
        scored_tracks.sort(key=lambda x: x[1], reverse=True)
        
        return [track for track, score in scored_tracks[:50]]
    
    def build_context_themes(self, temporal, weather, location) -> List[str]:
        """Build a list of contextually relevant themes"""
        themes = []
        
        # Seasonal themes
        if temporal.season in self.seasonal_themes:
            themes.extend(self.seasonal_themes[temporal.season])
        
        # Weather themes
        if weather and weather.condition in self.weather_themes:
            themes.extend(self.weather_themes[weather.condition])
        
        # Time of day themes
        if temporal.time_of_day in self.time_themes:
            themes.extend(self.time_themes[temporal.time_of_day])
        
        # Holiday themes
        if temporal.holiday and temporal.holiday in self.holiday_themes:
            themes.extend(self.holiday_themes[temporal.holiday])
            
        # Location-specific themes
        if location.cultural_characteristics:
            themes.extend(location.cultural_characteristics)
        
        # Weekend vs weekday
        if temporal.is_weekend:
            themes.extend(["relaxation", "party", "leisure", "fun"])
        else:
            themes.extend(["work", "motivation", "energy", "focus"])
        
        return list(set(themes))  # Remove duplicates
    
    async def calculate_contextual_score(self, track, temporal, weather, location) -> float:
        """Calculate how well a track fits the current context"""
        score = 0.0
        
        # Temporal scoring
        temporal_score = self.score_temporal_relevance(track, temporal)
        score += temporal_score * self.weights.temporal
        
        # Weather scoring  
        if weather:
            weather_score = self.score_weather_relevance(track, weather)
            score += weather_score * self.weights.weather
        
        # Location scoring
        location_score = self.score_location_relevance(track, location)
        score += location_score * self.weights.location
        
        # Mood alignment
        mood_score = self.score_mood_alignment(track, temporal, weather)
        score += mood_score * self.weights.mood
        
        return min(score, 1.0)  # Cap at 1.0
    
    def score_temporal_relevance(self, track, temporal) -> float:
        """Score track relevance to current time/date context"""
        score = 0.0
        
        # Check track themes against temporal context
        track_themes = json.loads(track.get('themes', '[]'))
        
        # Holiday relevance
        if temporal.holiday:
            holiday_themes = self.holiday_themes.get(temporal.holiday, [])
            theme_overlap = len(set(track_themes) & set(holiday_themes))
            score += theme_overlap * 0.4
        
        # Seasonal relevance
        seasonal_themes = self.seasonal_themes.get(temporal.season, [])
        theme_overlap = len(set(track_themes) & set(seasonal_themes))
        score += theme_overlap * 0.3
        
        # Time of day relevance
        time_themes = self.time_themes.get(temporal.time_of_day, [])
        theme_overlap = len(set(track_themes) & set(time_themes))
        score += theme_overlap * 0.3
        
        return min(score, 1.0)
    
    def score_weather_relevance(self, track, weather) -> float:
        """Score track relevance to current weather"""
        if not weather:
            return 0.0
        
        track_themes = json.loads(track.get('themes', '[]'))
        weather_themes = self.weather_themes.get(weather.condition, [])
        
        theme_overlap = len(set(track_themes) & set(weather_themes))
        base_score = theme_overlap * 0.3
        
        # Mood alignment with weather
        if hasattr(track, 'mood_valence'):
            if weather.mood_impact == "melancholy" and track.mood_valence < 0:
                base_score += 0.2
            elif weather.mood_impact == "cheerful" and track.mood_valence > 0.5:
                base_score += 0.2
        
        return min(base_score, 1.0)
```

## Contextual Commentary Generation

```python
# src/dj/contextual_commentary.py
class ContextualCommentaryGenerator:
    def __init__(self, ai_client):
        self.ai_client = ai_client
    
    async def generate_contextual_intro(self, 
                                      track, 
                                      temporal_context, 
                                      weather_context,
                                      location_context) -> str:
        """Generate context-aware track introduction"""
        
        context_elements = self.build_context_narrative(
            temporal_context, weather_context, location_context
        )
        
        prompt = f"""
        You are an AI DJ with deep awareness of your environment and the moment. Create an engaging introduction for this track that weaves together the current context.

        Track: "{track['title']}" by {track['artist']}
        
        Current Context:
        - Time: {temporal_context.time_of_day} on {temporal_context.day_of_week}
        - Season: {temporal_context.season}
        - Weather: {weather_context.condition if weather_context else 'Unknown'} 
        - Location: {location_context.city if location_context else 'Unknown'}
        - Special: {temporal_context.holiday or 'Regular day'}
        
        Track Themes: {track.get('themes', [])}
        
        Create a 60-90 second spoken introduction that:
        1. Acknowledges the current moment and context naturally
        2. Connects the track to what's happening right now
        3. Uses the context to enhance the track's meaning
        4. Feels spontaneous and present, not scripted
        5. Includes relevant cultural or seasonal references
        
        Speak as if you're truly present in this moment and place.
        """
        
        response = await self.ai_client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=300
        )
        
        return response.choices[0].message.content.strip()
    
    def build_context_narrative(self, temporal, weather, location) -> str:
        """Build a narrative description of the current context"""
        elements = []
        
        # Time context
        if temporal.time_of_day == "morning":
            if temporal.is_weekend:
                elements.append("lazy weekend morning")
            else:
                elements.append("start of another weekday")
        elif temporal.time_of_day == "evening":
            elements.append("end of the day unwinding")
        
        # Weather context
        if weather:
            if weather.condition == "rainy":
                elements.append("rain pattering against the windows")
            elif weather.condition == "sunny":
                elements.append("beautiful sunshine streaming in")
            elif weather.condition == "snowy":
                elements.append("snow creating a winter wonderland")
        
        # Seasonal context
        if temporal.season == "autumn":
            elements.append("leaves changing colors outside")
        elif temporal.season == "spring":
            elements.append("world coming back to life")
        
        # Holiday context
        if temporal.holiday:
            elements.append(f"spirit of {temporal.holiday} in the air")
        
        return "; ".join(elements)
```

## Real-Time Context Updates

```python
# src/context/context_manager.py
import asyncio
from datetime import datetime, timedelta
from typing import Optional

class ContextManager:
    def __init__(self, weather_analyzer, location_analyzer, temporal_analyzer):
        self.weather_analyzer = weather_analyzer
        self.location_analyzer = location_analyzer  
        self.temporal_analyzer = temporal_analyzer
        
        self.current_context = None
        self.last_update = None
        self.update_interval = timedelta(minutes=15)  # Update every 15 minutes
        
    async def start_monitoring(self):
        """Start continuous context monitoring"""
        while True:
            try:
                await self.update_context()
                await asyncio.sleep(self.update_interval.total_seconds())
            except Exception as e:
                logger.error(f"Context update failed: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    async def update_context(self):
        """Update all contextual information"""
        temporal = self.temporal_analyzer.get_current_context()
        weather = await self.weather_analyzer.get_current_weather()
        location = await self.location_analyzer.get_location_context()
        
        self.current_context = {
            "temporal": temporal,
            "weather": weather,
            "location": location,
            "updated_at": datetime.now()
        }
        
        self.last_update = datetime.now()
        
        # Notify other systems of context change
        await self.broadcast_context_update()
    
    async def broadcast_context_update(self):
        """Notify other systems that context has changed"""
        # This could trigger re-evaluation of current playlist
        # or adjustment of upcoming track selections
        pass
    
    def get_current_context(self):
        """Get the most recent contextual information"""
        return self.current_context
    
    def is_context_stale(self) -> bool:
        """Check if context needs updating"""
        if not self.last_update:
            return True
        return datetime.now() - self.last_update > self.update_interval
```

## Advanced Contextual Features

### Event-Driven Context Changes

```python
# src/context/event_driven.py
class EventDrivenContext:
    def __init__(self):
        self.event_handlers = {
            "weather_change": self.handle_weather_change,
            "time_change": self.handle_time_change,
            "holiday_start": self.handle_holiday_start,
            "local_event": self.handle_local_event
        }
    
    async def handle_weather_change(self, old_weather, new_weather):
        """React to significant weather changes"""
        if old_weather.condition != new_weather.condition:
            # Weather changed significantly
            if new_weather.condition == "rainy" and old_weather.condition == "sunny":
                # Transition to more mellow, indoor music
                await self.suggest_weather_transition("sunny_to_rainy")
            elif new_weather.condition == "sunny" and old_weather.condition == "rainy":
                # Brighten up the mood
                await self.suggest_weather_transition("rainy_to_sunny")
    
    async def handle_time_change(self, time_context):
        """React to significant time transitions"""
        hour = time_context.current_time.hour
        
        # Golden hour transitions
        if hour == 17:  # 5 PM - start of evening
            await self.suggest_time_transition("afternoon_to_evening")
        elif hour == 22:  # 10 PM - late night 
            await self.suggest_time_transition("evening_to_night")
        elif hour == 6:   # 6 AM - morning
            await self.suggest_time_transition("night_to_morning")
```

### Cultural Calendar Integration

```python
# src/context/cultural_calendar.py
class CulturalCalendar:
    def __init__(self):
        self.cultural_events = {
            # Music history dates
            "02-03": {"event": "The Day the Music Died", "significance": "Buddy Holly, Ritchie Valens, Big Bopper plane crash"},
            "04-05": {"event": "Kurt Cobain Memorial", "significance": "Grunge icon remembrance"},
            "08-15": {"event": "Woodstock Anniversary", "significance": "Peace, love, and music celebration"},
            "12-08": {"event": "John Lennon Memorial", "significance": "Imagine all the people"},
            
            # Cultural celebrations
            "02-**": {"event": "Black History Month", "themes": ["jazz", "blues", "hip_hop", "soul", "civil_rights"]},
            "03-**": {"event": "Women's History Month", "themes": ["female_artists", "empowerment", "equality"]},
            "06-**": {"event": "Pride Month", "themes": ["love", "acceptance", "celebration", "lgbtq"]},
            
            # Seasonal markers
            "03-20": {"event": "Spring Equinox", "themes": ["renewal", "growth", "optimism"]},
            "06-21": {"event": "Summer Solstice", "themes": ["energy", "celebration", "freedom"]},
            "09-22": {"event": "Autumn Equinox", "themes": ["change", "reflection", "harvest"]},
            "12-21": {"event": "Winter Solstice", "themes": ["introspection", "peace", "renewal"]}
        }
    
    def get_cultural_significance(self, date: datetime) -> Optional[Dict]:
        """Get cultural significance for current date"""
        date_key = date.strftime("%m-%d")
        month_key = date.strftime("%m-**")
        
        # Check specific date
        if date_key in self.cultural_events:
            return self.cultural_events[date_key]
        
        # Check month-long observances
        if month_key in self.cultural_events:
            return self.cultural_events[month_key]
        
        return None
```

This contextual awareness system transforms the AI DJ from a simple music player into a truly intelligent companion that understands and responds to the world around it. It creates that magical feeling of having a DJ who's really "present" - someone who knows it's a rainy Tuesday in October and picks exactly the right song to match the moment.