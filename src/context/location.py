"""
Location and cultural context analysis

City/state/country/timezone are resolved via the keyless Open-Meteo
geocoding API; the curated music-scene data below adds cultural flavor
for cities we know well.
"""

import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

from .geocoding import geocode_location

logger = logging.getLogger(__name__)

@dataclass
class LocationContext:
    city: str
    state: str
    country: str
    timezone: str
    local_events: List[str]
    cultural_characteristics: List[str]
    music_scene: str
    nearby_venues: List[str]

class LocationAnalyzer:
    def __init__(self, location: str, default_timezone: str = "UTC", offline: bool = False):
        self.location = location
        self.default_timezone = default_timezone  # used when geocoding is unavailable
        self.offline = offline  # tests set this to skip network entirely
        self.session = None
        
        # Curated data about music scenes and cultural characteristics
        self.cultural_data = {
            "Nashville": {
                "music_scene": "country_capital",
                "characteristics": ["music_city", "honky_tonk", "grand_ole_opry", "songwriting"],
                "local_flavor": "southern_hospitality",
                "genres": ["country", "americana", "bluegrass", "southern_rock"],
                "venues": ["Grand Ole Opry", "Ryman Auditorium", "The Bluebird Cafe", "Tootsies"],
                "cultural_notes": "Heart of country music, where every song tells a story"
            },
            "New Orleans": {
                "music_scene": "jazz_birthplace", 
                "characteristics": ["jazz", "blues", "creole", "mardi_gras", "second_line"],
                "local_flavor": "big_easy",
                "genres": ["jazz", "blues", "zydeco", "brass_band", "funk"],
                "venues": ["Preservation Hall", "Tipitina's", "The Spotted Cat", "d.b.a."],
                "cultural_notes": "Where jazz was born and the good times roll"
            },
            "Seattle": {
                "music_scene": "grunge_origin",
                "characteristics": ["grunge", "indie", "coffee_culture", "rain", "alternative"],
                "local_flavor": "pacific_northwest",
                "genres": ["grunge", "indie_rock", "alternative", "folk"],
                "venues": ["The Crocodile", "Showbox", "Neptune Theatre", "The Triple Door"],
                "cultural_notes": "Birthplace of grunge, where flannel meets musical innovation"
            },
            "Austin": {
                "music_scene": "live_music_capital",
                "characteristics": ["keep_it_weird", "sxsw", "bbq", "live_music"],
                "local_flavor": "texas_quirky",
                "genres": ["indie", "country", "blues", "punk", "psychedelic"],
                "venues": ["ACL Live", "Stubbs", "The Continental Club", "Antone's"],
                "cultural_notes": "Live Music Capital of the World with an anything-goes attitude"
            },
            "Memphis": {
                "music_scene": "birthplace_of_blues",
                "characteristics": ["blues", "soul", "elvis", "sun_records", "beale_street"],
                "local_flavor": "delta_blues",
                "genres": ["blues", "soul", "rock_n_roll", "gospel"],
                "venues": ["Beale Street", "Sun Studio", "Graceland", "The Peabody"],
                "cultural_notes": "Where the blues began and rock 'n' roll was born"
            },
            "Detroit": {
                "music_scene": "motown_motor_city",
                "characteristics": ["motown", "techno", "industrial", "automotive", "resilience"],
                "local_flavor": "motor_city_grit",
                "genres": ["motown", "techno", "garage_rock", "punk"],
                "venues": ["Fox Theatre", "St. Andrew's Hall", "The Majestic", "Motown Museum"],
                "cultural_notes": "Motown sound and techno innovation from the Motor City"
            },
            "Los Angeles": {
                "music_scene": "entertainment_capital",
                "characteristics": ["hollywood", "sunset_strip", "diversity", "dreams", "surf"],
                "local_flavor": "california_dreaming",
                "genres": ["rock", "pop", "hip_hop", "punk", "latin"],
                "venues": ["The Troubadour", "Whisky a Go Go", "Hollywood Bowl", "The Greek"],
                "cultural_notes": "Where dreams are made and music careers are launched"
            },
            "New York": {
                "music_scene": "melting_pot_metropolis",
                "characteristics": ["jazz_age", "punk", "hip_hop", "broadway", "diversity"],
                "local_flavor": "never_sleeps",
                "genres": ["jazz", "punk", "hip_hop", "indie", "classical"],
                "venues": ["Apollo Theater", "Madison Square Garden", "CBGB", "Lincoln Center"],
                "cultural_notes": "The city that never sleeps, where every genre finds a home"
            },
            "Chicago": {
                "music_scene": "blues_and_house",
                "characteristics": ["electric_blues", "house_music", "jazz", "wind", "deep_dish"],
                "local_flavor": "second_city_soul",
                "genres": ["blues", "house", "jazz", "gospel"],
                "venues": ["Buddy Guy's Legends", "Green Mill", "Metro", "Chicago Theatre"],
                "cultural_notes": "Electric blues and house music with Midwest authenticity"
            },
            "Miami": {
                "music_scene": "latin_fusion",
                "characteristics": ["latin", "electronic", "beach", "art_deco", "multicultural"],
                "local_flavor": "tropical_heat",
                "genres": ["latin", "electronic", "reggaeton", "dance"],
                "venues": ["American Airlines Arena", "Fontainebleau", "LIV", "The Fillmore"],
                "cultural_notes": "Where Latin rhythms meet electronic beats under the Miami sun"
            }
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

    async def get_location_context(self) -> LocationContext:
        """Get comprehensive location context"""

        # Fallback: parse the location string directly
        location_parts = [part.strip() for part in self.location.split(',')]
        city = location_parts[0] if location_parts else "Unknown"
        state = location_parts[1] if len(location_parts) > 1 else "Unknown"
        country = "Unknown"
        timezone = self.default_timezone

        # Real geocoding (keyless Open-Meteo) — fixes city/state/country and
        # gives the actual IANA timezone instead of a hardcoded guess.
        if not self.offline:
            if self.session is None or self.session.closed:
                self.session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                )
            geo = await geocode_location(self.location, self.session)
            if geo:
                city = geo.city
                state = geo.admin1 or state
                country = geo.country or country
                timezone = geo.timezone

        # Get cultural context
        cultural = self.cultural_data.get(city, {})

        # Get local events (mock for now - would integrate with real APIs)
        events = await self.get_local_events()

        return LocationContext(
            city=city,
            state=state,
            country=country,
            timezone=timezone,
            local_events=events,
            cultural_characteristics=cultural.get("characteristics", []),
            music_scene=cultural.get("music_scene", "general"),
            nearby_venues=cultural.get("venues", [])
        )
    
    async def get_local_events(self) -> List[str]:
        """Fetch local events that might influence music selection"""
        # Mock implementation - in real system would integrate with:
        # - Eventbrite API
        # - Songkick API  
        # - Local venue websites
        # - Sports APIs for local team games
        # - Weather alerts
        
        events = []
        
        # Mock some events based on season/time
        import datetime
        now = datetime.datetime.now()
        
        if now.month in [6, 7, 8]:  # Summer
            events.append("summer_festival_season")
        
        if now.month == 3:  # March
            events.append("march_madness")
        
        if now.weekday() == 4:  # Friday
            events.append("friday_night_lights")
        
        return events
    
    def get_location_themes(self, location_context: LocationContext) -> List[str]:
        """Get themes associated with the location"""
        
        city_data = self.cultural_data.get(location_context.city, {})
        themes = []
        
        # Add music scene themes
        if city_data:
            themes.extend(city_data.get("characteristics", []))
            themes.extend(city_data.get("genres", []))
            
            # Add local flavor
            local_flavor = city_data.get("local_flavor", "")
            if local_flavor:
                themes.append(local_flavor)
        
        # Regional themes
        if location_context.state:
            regional_themes = self.get_regional_themes(location_context.state)
            themes.extend(regional_themes)
        
        return list(set(themes))  # Remove duplicates
    
    def get_regional_themes(self, state: str) -> List[str]:
        """Get themes based on geographic region.

        Accepts either a USPS code ("CO") or the full state name
        ("Colorado") that geocoding returns.
        """
        from .geocoding import US_STATES
        if state not in US_STATES:
            for code, name in US_STATES.items():
                if name.lower() == (state or "").lower():
                    state = code
                    break

        regional_map = {
            # South
            "TN": ["southern", "country", "storytelling"],
            "LA": ["southern", "jazz", "creole", "bayou"],
            "TX": ["western", "country", "barbecue", "independence"],
            "GA": ["southern", "soul", "peach"],
            "FL": ["tropical", "beach", "sunshine"],
            
            # West Coast
            "CA": ["surf", "sunshine", "innovation", "dreams"],
            "WA": ["grunge", "coffee", "rain", "nature"],
            "OR": ["indie", "craft", "nature", "quirky"],
            
            # Northeast
            "NY": ["urban", "fast_paced", "diversity", "culture"],
            "MA": ["historic", "intellectual", "traditional"],
            "ME": ["maritime", "folk", "rugged"],
            
            # Midwest
            "IL": ["heartland", "blues", "industrial"],
            "MI": ["automotive", "motown", "industrial"],
            "WI": ["cheese", "folk", "german_heritage"],
            
            # Mountain West
            "CO": ["mountain", "outdoor", "folk", "altitude"],
            "UT": ["mountain", "clean", "outdoor"],
            "WY": ["western", "country", "wide_open"]
        }
        
        return regional_map.get(state, ["american", "heartland"])
    
    def get_venue_specific_programming(self, location_context: LocationContext) -> Dict:
        """Get programming suggestions based on local venues and scene"""
        
        city_data = self.cultural_data.get(location_context.city, {})
        programming = {}
        
        if city_data:
            music_scene = city_data.get("music_scene", "")
            
            if music_scene == "country_capital":
                programming = {
                    "featured_genres": ["country", "americana", "bluegrass"],
                    "storytelling_emphasis": True,
                    "local_legends": ["Johnny Cash", "Dolly Parton", "Hank Williams"],
                    "venue_stories": True
                }
            
            elif music_scene == "jazz_birthplace":
                programming = {
                    "featured_genres": ["jazz", "blues", "brass_band"],
                    "improvisation_emphasis": True,
                    "local_legends": ["Louis Armstrong", "Jelly Roll Morton"],
                    "cultural_celebration": True
                }
            
            elif music_scene == "grunge_origin":
                programming = {
                    "featured_genres": ["grunge", "alternative", "indie"],
                    "alternative_emphasis": True,
                    "local_legends": ["Nirvana", "Pearl Jam", "Soundgarden"],
                    "coffee_culture": True
                }
        
        return programming
    
    def suggest_local_connection_commentary(self, location_context: LocationContext, track_info: Dict) -> Optional[str]:
        """Suggest commentary that connects track to local culture"""
        
        city_data = self.cultural_data.get(location_context.city, {})
        if not city_data:
            return None
        
        cultural_notes = city_data.get("cultural_notes", "")
        characteristics = city_data.get("characteristics", [])
        
        # Check if track has local connection
        artist = track_info.get("artist", "")
        genre = track_info.get("genre", "")
        
        # Local artist connection
        if any(char in artist.lower() for char in characteristics):
            return f"Speaking of {location_context.city}, this brings back the {city_data.get('local_flavor', 'local')} sound that makes this city special."
        
        # Genre connection
        if genre.lower() in city_data.get("genres", []):
            return f"Perfect {genre} for {location_context.city} - {cultural_notes}"
        
        # Venue connection
        venues = city_data.get("venues", [])
        if venues:
            return f"This is the kind of music you'd hear echoing through {venues[0]} on a perfect {location_context.city} evening."
        
        return None
    
    def get_local_time_adjustments(self, location_context: LocationContext) -> Dict:
        """Get time-based adjustments specific to location"""
        
        adjustments = {}
        
        # City-specific time patterns
        if location_context.city == "New York":
            adjustments["late_night_extension"] = 2  # City that never sleeps
            adjustments["rush_hour_energy"] = 0.8
        
        elif location_context.city == "Los Angeles":
            adjustments["traffic_time"] = True  # Consider traffic patterns
            adjustments["sunset_emphasis"] = True  # Famous sunsets
        
        elif location_context.city == "Nashville":
            adjustments["honky_tonk_hours"] = True  # Late night music scene
            adjustments["songwriter_circles"] = True
        
        return adjustments