"""
Weather context analysis for music selection

Uses the Open-Meteo API (no API key required). The legacy api_key
parameter is accepted for constructor compatibility but no longer used.
"""

import aiohttp
import asyncio
import logging
from typing import Dict, Optional
from dataclasses import dataclass

from .geocoding import geocode_location

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes (Open-Meteo `weather_code`) → our conditions
_WMO_CONDITIONS = {
    0: "sunny",
    1: "partly_cloudy", 2: "partly_cloudy",
    3: "cloudy",
    45: "foggy", 48: "foggy",
    51: "rainy", 53: "rainy", 55: "rainy", 56: "rainy", 57: "rainy",
    61: "rainy", 63: "rainy", 65: "rainy", 66: "rainy", 67: "rainy",
    71: "snowy", 73: "snowy", 75: "snowy", 77: "snowy",
    80: "rainy", 81: "rainy", 82: "rainy",
    85: "snowy", 86: "snowy",
    95: "stormy", 96: "stormy", 99: "stormy",
}

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
    def __init__(self, api_key: Optional[str] = None, location: str = "", offline: bool = False):
        self.api_key = api_key  # legacy, unused — Open-Meteo needs no key
        self.location = location
        self.offline = offline  # tests set this to force mock data (no network)
        self.session = None
        
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
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close the HTTP session (call at application shutdown)."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def get_current_weather(self) -> Optional[WeatherContext]:
        """Get current weather conditions from Open-Meteo (keyless)."""
        if self.offline:
            return self._get_mock_weather()

        try:
            # Lazily create the session — the analyzer is normally used as a
            # long-lived object, not via the async context manager.
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                )

            geo = await geocode_location(self.location, self.session)
            if geo is None:
                logger.warning(f"Could not geocode '{self.location}', using mock weather")
                return self._get_mock_weather()

            params = {
                "latitude": geo.latitude,
                "longitude": geo.longitude,
                "current": ",".join([
                    "temperature_2m", "relative_humidity_2m", "weather_code",
                    "wind_speed_10m", "surface_pressure", "cloud_cover",
                ]),
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
            }

            async with self.session.get(FORECAST_URL, params=params) as response:
                if response.status != 200:
                    logger.error(f"Weather API error: {response.status}")
                    return self._get_mock_weather()

                data = await response.json()
                current = data.get("current") or {}

                condition = _WMO_CONDITIONS.get(current.get("weather_code"), "cloudy")
                wind_speed = current.get("wind_speed_10m", 0) or 0
                # Strong wind dominates the mood when the sky itself is calm
                if wind_speed >= 25 and condition in ("sunny", "partly_cloudy", "cloudy"):
                    condition = "windy"

                return WeatherContext(
                    condition=condition,
                    temperature=current.get("temperature_2m", 60.0),
                    humidity=current.get("relative_humidity_2m", 50.0),
                    wind_speed=wind_speed,
                    pressure=current.get("surface_pressure", 1013.25),
                    visibility=10000,  # not in Open-Meteo current block
                    mood_impact=self.weather_to_mood.get(condition, "neutral")
                )

        except Exception as e:
            logger.error(f"Failed to fetch weather: {e}")
            return self._get_mock_weather()
    
    def _get_mock_weather(self) -> WeatherContext:
        """Return mock weather data when API is unavailable"""
        import random
        
        conditions = ["sunny", "cloudy", "rainy"]
        condition = random.choice(conditions)
        
        return WeatherContext(
            condition=condition,
            temperature=72.0,
            humidity=50.0,
            wind_speed=5.0,
            pressure=1013.25,
            visibility=10000,
            mood_impact=self.weather_to_mood.get(condition, "neutral")
        )
    
    def get_weather_themes(self, weather: WeatherContext) -> list:
        """Get themes associated with current weather"""
        
        weather_theme_map = {
            "rainy": ["melancholy", "introspection", "cozy", "jazz", "indie", "contemplative", "acoustic"],
            "sunny": ["upbeat", "happy", "energetic", "pop", "dance", "optimistic", "bright"],
            "stormy": ["dramatic", "powerful", "rock", "classical", "emotional", "intense", "electric"],
            "snowy": ["peaceful", "quiet", "ambient", "folk", "acoustic", "serene", "winter"],
            "cloudy": ["mellow", "alternative", "singer-songwriter", "thoughtful", "subdued"],
            "foggy": ["mysterious", "atmospheric", "ambient", "ethereal", "dream-like"],
            "windy": ["restless", "movement", "folk", "country", "journey"]
        }
        
        base_themes = weather_theme_map.get(weather.condition, ["neutral"])
        
        # Temperature-based modifications
        if weather.temperature > 80:
            base_themes.extend(["hot", "summer", "cool_down", "beach"])
        elif weather.temperature < 40:
            base_themes.extend(["cold", "winter", "warmth", "cozy"])
        
        # Humidity-based modifications
        if weather.humidity > 70:
            base_themes.extend(["humid", "tropical", "heavy"])
        
        return list(set(base_themes))
    
    def get_weather_energy_guidance(self, weather: WeatherContext) -> Dict[str, float]:
        """Get energy level guidance based on weather"""
        
        energy_map = {
            "sunny": {"min_energy": 0.4, "max_energy": 1.0, "optimal": 0.7},
            "rainy": {"min_energy": 0.1, "max_energy": 0.6, "optimal": 0.3},
            "stormy": {"min_energy": 0.5, "max_energy": 1.0, "optimal": 0.8},
            "snowy": {"min_energy": 0.0, "max_energy": 0.5, "optimal": 0.2},
            "cloudy": {"min_energy": 0.2, "max_energy": 0.7, "optimal": 0.4},
            "foggy": {"min_energy": 0.1, "max_energy": 0.4, "optimal": 0.2}
        }
        
        return energy_map.get(weather.condition, {"min_energy": 0.3, "max_energy": 0.7, "optimal": 0.5})
    
    def get_weather_mood_guidance(self, weather: WeatherContext) -> Dict[str, float]:
        """Get mood/valence guidance based on weather"""
        
        mood_map = {
            "sunny": {"min_valence": 0.2, "max_valence": 1.0, "optimal": 0.7},
            "rainy": {"min_valence": -0.5, "max_valence": 0.4, "optimal": 0.0},
            "stormy": {"min_valence": -0.3, "max_valence": 0.8, "optimal": 0.2},
            "snowy": {"min_valence": 0.0, "max_valence": 0.7, "optimal": 0.4},
            "cloudy": {"min_valence": -0.2, "max_valence": 0.6, "optimal": 0.2},
            "foggy": {"min_valence": -0.1, "max_valence": 0.5, "optimal": 0.1}
        }
        
        return mood_map.get(weather.condition, {"min_valence": 0.0, "max_valence": 0.5, "optimal": 0.3})
    
    def suggest_weather_transition_commentary(self, old_weather: WeatherContext, new_weather: WeatherContext) -> Optional[str]:
        """Suggest commentary for weather transitions"""
        
        if old_weather.condition == new_weather.condition:
            return None
        
        transition_templates = {
            ("sunny", "rainy"): "The sun's giving way to rain outside, and honestly, there's something beautiful about that shift. Let's adjust our musical landscape to match.",
            ("rainy", "sunny"): "Look at that - the rain's clearing and the sun's breaking through. Time to brighten up our sound to match the moment.",
            ("cloudy", "stormy"): "The sky's getting dramatic out there, building up some serious energy. Perfect time for music that matches that intensity.",
            ("stormy", "cloudy"): "The storm's settling into something more contemplative. Let's ease into some music that fits this calmer energy.",
            ("sunny", "cloudy"): "The bright sunshine's mellowing into something more subdued - sometimes that's exactly what the afternoon calls for.",
            ("cloudy", "sunny"): "The clouds are parting and letting that sunshine through. You know what that calls for in the music department."
        }
        
        return transition_templates.get((old_weather.condition, new_weather.condition))
    
    def get_seasonal_weather_adjustments(self, weather: WeatherContext, season: str) -> Dict:
        """Adjust weather interpretation based on season"""
        
        adjustments = {}
        
        # Same weather condition can mean different things in different seasons
        if weather.condition == "rainy":
            if season == "spring":
                adjustments["themes"] = ["renewal", "growth", "april_showers"]
                adjustments["mood_boost"] = 0.2  # Spring rain is more optimistic
            elif season == "autumn":
                adjustments["themes"] = ["nostalgia", "melancholy", "change"]
                adjustments["mood_reduction"] = 0.1
            elif season == "summer":
                adjustments["themes"] = ["relief", "cooling", "tropical"]
                adjustments["energy_boost"] = 0.1
        
        elif weather.condition == "sunny":
            if season == "winter":
                adjustments["themes"] = ["rare_sunshine", "precious_warmth", "vitamin_d"]
                adjustments["mood_boost"] = 0.3  # Winter sun is extra special
            elif season == "summer":
                adjustments["themes"] = ["heat", "vacation", "beach", "endless_summer"]
        
        elif weather.condition == "snowy":
            if season == "autumn":
                adjustments["themes"] = ["early_snow", "surprise", "transition"]
            elif season == "winter":
                adjustments["themes"] = ["winter_wonderland", "holidays", "cozy"]
        
        return adjustments