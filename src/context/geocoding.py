"""
Keyless geocoding via the Open-Meteo geocoding API.

Resolves a free-form location string ("Denver, CO") to real coordinates,
an IANA timezone, and normalized place names. No API key required.
Results are cached for the process lifetime — places don't move.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# USPS state codes → full names, for matching "Denver, CO" against
# Open-Meteo's admin1 field ("Colorado").
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


@dataclass
class GeoLocation:
    city: str
    admin1: str  # state/province full name ("Colorado")
    country: str
    country_code: str  # ISO-3166 alpha-2 ("US")
    latitude: float
    longitude: float
    timezone: str  # IANA name ("America/Denver")


_cache: Dict[str, GeoLocation] = {}


def _pick_result(results: list, region_hint: str) -> Optional[dict]:
    """Pick the best geocoding match, honoring a state/country hint if given."""
    if not results:
        return None
    if region_hint:
        hint = region_hint.strip()
        state_name = US_STATES.get(hint.upper(), hint)
        for r in results:
            if (r.get("admin1", "").lower() == state_name.lower()
                    or r.get("country_code", "").lower() == hint.lower()
                    or r.get("country", "").lower() == hint.lower()):
                return r
    return results[0]


async def geocode_location(
    location: str, session: aiohttp.ClientSession
) -> Optional[GeoLocation]:
    """Resolve a location string like "Denver, CO" to a GeoLocation.

    Returns None on any failure (offline, unknown place) — callers are
    expected to fall back gracefully.
    """
    key = (location or "").strip().lower()
    if not key:
        return None
    if key in _cache:
        return _cache[key]

    parts = [p.strip() for p in location.split(",")]
    city = parts[0]
    region_hint = parts[1] if len(parts) > 1 else ""

    try:
        params = {"name": city, "count": 10, "language": "en", "format": "json"}
        async with session.get(GEOCODING_URL, params=params) as response:
            if response.status != 200:
                logger.warning(f"Geocoding API returned {response.status} for '{location}'")
                return None
            data = await response.json()
    except Exception as e:
        logger.warning(f"Geocoding failed for '{location}': {e}")
        return None

    result = _pick_result(data.get("results") or [], region_hint)
    if not result:
        logger.warning(f"No geocoding match for '{location}'")
        return None

    geo = GeoLocation(
        city=result.get("name", city),
        admin1=result.get("admin1", ""),
        country=result.get("country", ""),
        country_code=result.get("country_code", ""),
        latitude=result["latitude"],
        longitude=result["longitude"],
        timezone=result.get("timezone", "UTC"),
    )
    _cache[key] = geo
    logger.info(
        f"Geocoded '{location}' → {geo.city}, {geo.admin1} "
        f"({geo.latitude:.4f}, {geo.longitude:.4f}, tz={geo.timezone})"
    )
    return geo
