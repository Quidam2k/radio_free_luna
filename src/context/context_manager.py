"""
Central context management system that coordinates all contextual awareness
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from .temporal import TemporalAnalyzer, TemporalContext
from .weather import WeatherAnalyzer, WeatherContext  
from .location import LocationAnalyzer, LocationContext

logger = logging.getLogger(__name__)

class ContextManager:
    def __init__(self, weather_analyzer: WeatherAnalyzer, location_analyzer: LocationAnalyzer, temporal_analyzer: TemporalAnalyzer):
        self.weather_analyzer = weather_analyzer
        self.location_analyzer = location_analyzer  
        self.temporal_analyzer = temporal_analyzer
        
        self.current_context = None
        self.last_update = None
        self.update_interval = timedelta(minutes=15)  # Update every 15 minutes
        self.monitoring_task = None
        
    async def start_monitoring(self):
        """Start continuous context monitoring"""
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Context monitoring started")
    
    async def stop_monitoring(self):
        """Stop context monitoring"""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Context monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while True:
            try:
                await self.update_context()
                await asyncio.sleep(self.update_interval.total_seconds())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Context update failed: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    async def update_context(self):
        """Update all contextual information"""
        logger.debug("Updating context...")
        
        try:
            # Get temporal context (always available)
            temporal = self.temporal_analyzer.get_current_context()
            
            # Get weather context (may fail)
            try:
                weather = await self.weather_analyzer.get_current_weather()
            except Exception as e:
                logger.warning(f"Weather update failed: {e}")
                weather = None
            
            # Get location context (may fail)
            try:
                location = await self.location_analyzer.get_location_context()
            except Exception as e:
                logger.warning(f"Location update failed: {e}")
                location = None
            
            # Store updated context
            old_context = self.current_context
            self.current_context = {
                "temporal": temporal,
                "weather": weather,
                "location": location,
                "updated_at": datetime.now()
            }
            
            self.last_update = datetime.now()
            
            # Check for significant changes and notify
            if old_context:
                await self._check_context_changes(old_context, self.current_context)
            
            logger.debug("Context updated successfully")
            
        except Exception as e:
            logger.error(f"Failed to update context: {e}")
    
    async def _check_context_changes(self, old_context: Dict, new_context: Dict):
        """Check for significant context changes that might affect music selection"""
        
        # Check weather changes
        old_weather = old_context.get("weather")
        new_weather = new_context.get("weather")
        
        if old_weather and new_weather and old_weather.condition != new_weather.condition:
            logger.info(f"Weather changed from {old_weather.condition} to {new_weather.condition}")
            await self._broadcast_context_change("weather_change", {
                "old": old_weather,
                "new": new_weather
            })
        
        # Check time period changes
        old_temporal = old_context.get("temporal")
        new_temporal = new_context.get("temporal")
        
        if old_temporal and new_temporal and old_temporal.time_of_day != new_temporal.time_of_day:
            logger.info(f"Time period changed from {old_temporal.time_of_day} to {new_temporal.time_of_day}")
            await self._broadcast_context_change("time_change", {
                "old": old_temporal,
                "new": new_temporal
            })
        
        # Check holiday transitions
        if old_temporal and new_temporal and old_temporal.holiday != new_temporal.holiday:
            if new_temporal.holiday:
                logger.info(f"Holiday started: {new_temporal.holiday}")
                await self._broadcast_context_change("holiday_start", {
                    "holiday": new_temporal.holiday
                })
    
    async def _broadcast_context_change(self, change_type: str, change_data: Dict):
        """Broadcast context changes to interested systems"""
        # This would integrate with the DJ engine and other systems
        # For now, just log the change
        logger.info(f"Context change: {change_type} - {change_data}")
    
    def get_current_context(self) -> Optional[Dict]:
        """Get the most recent contextual information"""
        return self.current_context
    
    def is_context_stale(self) -> bool:
        """Check if context needs updating"""
        if not self.last_update:
            return True
        return datetime.now() - self.last_update > self.update_interval
    
    def get_contextual_themes(self) -> list:
        """Get all themes from current context"""
        if not self.current_context:
            return []
        
        themes = []
        
        # Temporal themes
        temporal = self.current_context.get("temporal")
        if temporal:
            themes.extend(self.temporal_analyzer.get_time_themes(temporal))
        
        # Weather themes
        weather = self.current_context.get("weather")
        if weather:
            themes.extend(self.weather_analyzer.get_weather_themes(weather))
        
        # Location themes
        location = self.current_context.get("location")
        if location:
            themes.extend(self.location_analyzer.get_location_themes(location))
        
        return list(set(themes))  # Remove duplicates
    
    def get_contextual_music_guidance(self) -> Dict[str, Any]:
        """Get comprehensive music selection guidance based on current context"""
        if not self.current_context:
            return {}
        
        guidance = {
            "themes": self.get_contextual_themes(),
            "energy_guidance": {},
            "mood_guidance": {},
            "genre_preferences": [],
            "avoid_genres": [],
            "special_considerations": []
        }
        
        # Weather-based guidance
        weather = self.current_context.get("weather")
        if weather:
            weather_energy = self.weather_analyzer.get_weather_energy_guidance(weather)
            weather_mood = self.weather_analyzer.get_weather_mood_guidance(weather)
            
            guidance["energy_guidance"].update(weather_energy)
            guidance["mood_guidance"].update(weather_mood)
            
            # Weather-specific considerations
            if weather.condition == "rainy":
                guidance["special_considerations"].append("contemplative_atmosphere")
                guidance["avoid_genres"].extend(["hardcore", "death_metal"])
            elif weather.condition == "sunny":
                guidance["genre_preferences"].extend(["pop", "reggae", "surf_rock"])
        
        # Temporal guidance
        temporal = self.current_context.get("temporal")
        if temporal:
            if temporal.time_of_day == "late_night":
                guidance["special_considerations"].extend(["intimate_atmosphere", "lower_energy"])
                guidance["avoid_genres"].extend(["death_metal", "hardcore_punk"])
            elif temporal.time_of_day == "morning":
                guidance["special_considerations"].append("energizing_wake_up")
                guidance["genre_preferences"].extend(["pop", "rock", "folk"])
            
            if temporal.holiday:
                guidance["special_considerations"].append(f"holiday_{temporal.holiday.lower().replace(' ', '_')}")
        
        # Location-based guidance
        location = self.current_context.get("location")
        if location:
            location_programming = self.location_analyzer.get_venue_specific_programming(location)
            if location_programming:
                guidance["genre_preferences"].extend(location_programming.get("featured_genres", []))
                guidance["special_considerations"].extend([
                    key for key, value in location_programming.items() 
                    if isinstance(value, bool) and value
                ])
        
        return guidance
    
    def generate_context_description(self) -> str:
        """Generate a human-readable description of the current context"""
        if not self.current_context:
            return "Context information not available"
        
        parts = []
        
        # Temporal description
        temporal = self.current_context.get("temporal")
        if temporal:
            time_desc = f"{temporal.time_of_day} on {temporal.day_of_week}"
            if temporal.holiday:
                time_desc += f" ({temporal.holiday})"
            parts.append(time_desc)
        
        # Weather description
        weather = self.current_context.get("weather")
        if weather:
            temp_f = int(weather.temperature)
            weather_desc = f"{weather.condition}, {temp_f}°F"
            parts.append(weather_desc)
        
        # Location description
        location = self.current_context.get("location")
        if location:
            location_desc = f"in {location.city}"
            if location.music_scene != "general":
                location_desc += f" ({location.music_scene.replace('_', ' ')})"
            parts.append(location_desc)
        
        return ", ".join(parts) if parts else "Current moment"
    
    def get_context_summary_for_ai(self) -> str:
        """Get a concise context summary for AI prompts"""
        if not self.current_context:
            return "No context available"
        
        summary_parts = []
        
        temporal = self.current_context.get("temporal")
        if temporal:
            summary_parts.append(f"Time: {temporal.time_of_day} on {temporal.day_of_week}")
            if temporal.holiday:
                summary_parts.append(f"Holiday: {temporal.holiday}")
            summary_parts.append(f"Season: {temporal.season}")
        
        weather = self.current_context.get("weather")
        if weather:
            summary_parts.append(f"Weather: {weather.condition} ({weather.mood_impact} mood)")
        
        location = self.current_context.get("location")
        if location:
            summary_parts.append(f"Location: {location.city} ({location.music_scene.replace('_', ' ')})")
        
        return " | ".join(summary_parts)