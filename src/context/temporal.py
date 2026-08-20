"""
Temporal context analysis - time, date, season, holidays
"""

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
            "08-15": "Woodstock Anniversary",
            "07-13": "Live Aid Anniversary",
            "02-03": "The Day the Music Died",
            "04-05": "Kurt Cobain Memorial"
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

        # Winter: Dec 21 - Mar 19
        if (month == 12 and day >= 21) or (month == 1) or (month == 2) or (month == 3 and day < 20):
            return "winter"
        # Spring: Mar 20 - Jun 20
        elif (month == 3 and day >= 20) or (month == 4) or (month == 5) or (month == 6 and day < 21):
            return "spring"
        # Summer: Jun 21 - Sep 21
        elif (month == 6 and day >= 21) or (month == 7) or (month == 8) or (month == 9 and day < 22):
            return "summer"
        # Autumn: Sep 22 - Dec 20
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
    
    def calculate_floating_holiday(self, date: datetime.datetime) -> Optional[str]:
        """Calculate floating holidays like Thanksgiving, Mother's Day, etc."""
        year = date.year
        month = date.month
        day = date.day
        
        # Thanksgiving - 4th Thursday in November
        if month == 11:
            thanksgiving = self._get_nth_weekday(year, 11, 3, 4)  # 4th Thursday (3=Thursday)
            if date.date() == thanksgiving:
                return "Thanksgiving"
        
        # Mother's Day - 2nd Sunday in May
        if month == 5:
            mothers_day = self._get_nth_weekday(year, 5, 6, 2)  # 2nd Sunday (6=Sunday)
            if date.date() == mothers_day:
                return "Mother's Day"
        
        # Father's Day - 3rd Sunday in June
        if month == 6:
            fathers_day = self._get_nth_weekday(year, 6, 6, 3)  # 3rd Sunday
            if date.date() == fathers_day:
                return "Father's Day"
        
        # Labor Day - 1st Monday in September
        if month == 9:
            labor_day = self._get_nth_weekday(year, 9, 0, 1)  # 1st Monday (0=Monday)
            if date.date() == labor_day:
                return "Labor Day"
        
        # Memorial Day - Last Monday in May
        if month == 5:
            memorial_day = self._get_last_weekday(year, 5, 0)  # Last Monday
            if date.date() == memorial_day:
                return "Memorial Day"
        
        return None
    
    def _get_nth_weekday(self, year: int, month: int, weekday: int, n: int) -> datetime.date:
        """Get the nth occurrence of a weekday in a month"""
        first = datetime.date(year, month, 1)
        first_weekday = first.weekday()
        
        # Calculate days to the first occurrence of the desired weekday
        days_to_weekday = (weekday - first_weekday) % 7
        first_occurrence = first + datetime.timedelta(days=days_to_weekday)
        
        # Add weeks to get the nth occurrence
        nth_occurrence = first_occurrence + datetime.timedelta(weeks=n-1)
        
        return nth_occurrence
    
    def _get_last_weekday(self, year: int, month: int, weekday: int) -> datetime.date:
        """Get the last occurrence of a weekday in a month"""
        # Start from the last day of the month and work backwards
        if month == 12:
            last_day = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
        
        # Find the last occurrence of the weekday
        days_back = (last_day.weekday() - weekday) % 7
        return last_day - datetime.timedelta(days=days_back)
    
    def get_special_dates(self, date: datetime.datetime) -> List[str]:
        """Get contextually relevant date markers"""
        special = []
        
        # Seasonal transitions
        if date.month == 3 and 19 <= date.day <= 21:
            special.append("Spring Equinox")
        elif date.month == 6 and 20 <= date.day <= 22:
            special.append("Summer Solstice")
        elif date.month == 9 and 21 <= date.day <= 23:
            special.append("Autumn Equinox")
        elif date.month == 12 and 20 <= date.day <= 22:
            special.append("Winter Solstice")
        
        # Cultural periods
        if date.month == 2:
            special.append("Black History Month")
        elif date.month == 3:
            special.append("Women's History Month")
        elif date.month == 6:
            special.append("Pride Month")
        elif date.month == 10:
            special.append("Halloween Season")
        elif date.month == 12:
            special.append("Holiday Season")
        
        # Back to school season
        if (date.month == 8 and date.day >= 15) or (date.month == 9 and date.day <= 15):
            special.append("Back to School Season")
        
        # Summer vacation
        if date.month in [6, 7, 8]:
            special.append("Summer Vacation")
        
        return special
    
    def get_time_themes(self, context: TemporalContext) -> List[str]:
        """Get themes associated with current time"""
        themes = []
        
        # Time of day themes
        time_themes = {
            "morning": ["wake_up", "coffee", "motivation", "fresh_start", "energy"],
            "afternoon": ["work", "productivity", "steady", "focus", "midday"],
            "evening": ["dinner", "relaxation", "family", "unwinding", "sunset"],
            "late_night": ["intimate", "quiet", "contemplative", "deep", "mysterious"]
        }
        
        themes.extend(time_themes.get(context.time_of_day, []))
        
        # Day of week themes
        if context.is_weekend:
            themes.extend(["relaxation", "leisure", "fun", "freedom"])
        else:
            themes.extend(["work", "routine", "productivity"])
        
        # Seasonal themes
        seasonal_themes = {
            "winter": ["cozy", "fireplace", "snow", "hibernation", "reflection", "holidays"],
            "spring": ["renewal", "growth", "optimism", "fresh_start", "blooming", "love"],
            "summer": ["vacation", "freedom", "beach", "sunshine", "energy", "adventure"],
            "autumn": ["nostalgia", "change", "harvest", "school", "melancholy", "reflection"]
        }
        
        themes.extend(seasonal_themes.get(context.season, []))
        
        # Holiday themes
        if context.holiday:
            holiday_themes = {
                "Christmas": ["family", "tradition", "joy", "giving", "peace"],
                "Halloween": ["spooky", "fun", "mysterious", "theatrical", "autumn"],
                "Valentine's Day": ["love", "romance", "intimate", "heart", "relationship"],
                "Independence Day": ["patriotic", "freedom", "celebration", "summer", "fireworks"],
                "New Year's Eve": ["celebration", "reflection", "new_beginning", "party", "countdown"]
            }
            
            themes.extend(holiday_themes.get(context.holiday, []))
        
        return list(set(themes))  # Remove duplicates