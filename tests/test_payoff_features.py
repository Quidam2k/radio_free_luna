"""
Tests for the 2026-06-10 payoff features:
- Open-Meteo geocoding + keyless weather (real timezone, no API key)
- Dayparting personas (the writing changes with the hour)
- Request line (listener requests jump the queue, DJ acknowledges by name)
"""

import asyncio
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from src.context import geocoding
from src.context.geocoding import GeoLocation, _pick_result, geocode_location
from src.context.location import LocationAnalyzer
from src.context.weather import WeatherAnalyzer, _WMO_CONDITIONS
from src.dj.commentary_generator import DJCommentaryGenerator, DAYPART_PERSONAS
from src.models import SongRequest, ValidationError


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status = status

    async def json(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeHTTPSession:
    """Stands in for aiohttp.ClientSession; returns canned JSON per URL substring."""

    closed = False

    def __init__(self, responses: Dict[str, Any]):
        self.responses = responses
        self.calls: List[str] = []

    def get(self, url, params=None):
        self.calls.append(url)
        for fragment, data in self.responses.items():
            if fragment in url:
                return FakeResponse(data)
        return FakeResponse({}, status=404)


@dataclass
class FakeTemporal:
    time_of_day: str
    day_of_week: str = "Wednesday"
    holiday: Optional[str] = None


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

class TestGeocoding:
    def test_pick_result_honors_state_hint(self):
        results = [
            {"name": "Springfield", "admin1": "Massachusetts", "country_code": "US"},
            {"name": "Springfield", "admin1": "Illinois", "country_code": "US"},
        ]
        assert _pick_result(results, "IL")["admin1"] == "Illinois"
        assert _pick_result(results, "Illinois")["admin1"] == "Illinois"

    def test_pick_result_defaults_to_first(self):
        results = [
            {"name": "Springfield", "admin1": "Massachusetts", "country_code": "US"},
            {"name": "Springfield", "admin1": "Illinois", "country_code": "US"},
        ]
        assert _pick_result(results, "")["admin1"] == "Massachusetts"
        # unknown hint falls back to first rather than failing
        assert _pick_result(results, "Narnia")["admin1"] == "Massachusetts"

    def test_geocode_parses_and_caches(self):
        geocoding._cache.pop("denver test city, co", None)
        session = FakeHTTPSession({
            "geocoding-api": {
                "results": [{
                    "name": "Denver", "admin1": "Colorado",
                    "country": "United States", "country_code": "US",
                    "latitude": 39.74, "longitude": -104.98,
                    "timezone": "America/Denver",
                }]
            }
        })

        async def run():
            first = await geocode_location("Denver Test City, CO", session)
            second = await geocode_location("Denver Test City, CO", session)
            return first, second

        first, second = asyncio.run(run())
        assert first.timezone == "America/Denver"
        assert first.latitude == pytest.approx(39.74)
        assert second is first  # cached
        assert len(session.calls) == 1

    def test_geocode_failure_returns_none(self):
        session = FakeHTTPSession({})  # everything 404s

        result = asyncio.run(geocode_location("Nowhere Test Town, ZZ", session))
        assert result is None


# ---------------------------------------------------------------------------
# Weather (Open-Meteo, keyless)
# ---------------------------------------------------------------------------

class TestWeather:
    def test_offline_serves_mock(self):
        analyzer = WeatherAnalyzer(location="Denver, CO", offline=True)
        weather = asyncio.run(analyzer.get_current_weather())
        assert weather is not None
        assert weather.condition in analyzer.weather_to_mood
        assert analyzer.session is None  # never touched the network

    def test_wmo_code_mapping(self):
        assert _WMO_CONDITIONS[0] == "sunny"
        assert _WMO_CONDITIONS[3] == "cloudy"
        assert _WMO_CONDITIONS[61] == "rainy"
        assert _WMO_CONDITIONS[75] == "snowy"
        assert _WMO_CONDITIONS[95] == "stormy"
        assert _WMO_CONDITIONS[45] == "foggy"

    def test_fetch_parses_open_meteo_payload(self):
        # Pre-seed the geocode cache so no geocoding call is needed
        geocoding._cache["weathertown, co"] = GeoLocation(
            city="Weathertown", admin1="Colorado", country="United States",
            country_code="US", latitude=39.7, longitude=-104.9,
            timezone="America/Denver",
        )
        analyzer = WeatherAnalyzer(location="Weathertown, CO")
        analyzer.session = FakeHTTPSession({
            "api.open-meteo.com": {
                "current": {
                    "temperature_2m": 41.5,
                    "relative_humidity_2m": 80,
                    "weather_code": 63,  # moderate rain
                    "wind_speed_10m": 8.0,
                    "surface_pressure": 1010.0,
                    "cloud_cover": 90,
                }
            }
        })

        weather = asyncio.run(analyzer.get_current_weather())
        assert weather.condition == "rainy"
        assert weather.temperature == pytest.approx(41.5)
        assert weather.mood_impact == "melancholy"

    def test_high_wind_overrides_calm_sky(self):
        geocoding._cache["windytown, wy"] = GeoLocation(
            city="Windytown", admin1="Wyoming", country="United States",
            country_code="US", latitude=41.1, longitude=-104.8,
            timezone="America/Denver",
        )
        analyzer = WeatherAnalyzer(location="Windytown, WY")
        analyzer.session = FakeHTTPSession({
            "api.open-meteo.com": {
                "current": {
                    "temperature_2m": 55.0,
                    "relative_humidity_2m": 30,
                    "weather_code": 1,  # mostly clear
                    "wind_speed_10m": 32.0,
                    "surface_pressure": 1005.0,
                }
            }
        })

        weather = asyncio.run(analyzer.get_current_weather())
        assert weather.condition == "windy"
        assert weather.mood_impact == "restless"


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

class TestLocation:
    def test_offline_falls_back_to_string_parsing(self):
        analyzer = LocationAnalyzer(
            location="Denver, CO", default_timezone="America/Denver", offline=True
        )
        ctx = asyncio.run(analyzer.get_location_context())
        assert ctx.city == "Denver"
        assert ctx.state == "CO"
        assert ctx.timezone == "America/Denver"  # fallback, not New York

    def test_geocoded_context_uses_real_timezone(self):
        geocoding._cache["geotown, tn"] = GeoLocation(
            city="Nashville", admin1="Tennessee", country="United States",
            country_code="US", latitude=36.16, longitude=-86.78,
            timezone="America/Chicago",
        )
        analyzer = LocationAnalyzer(location="Geotown, TN")
        analyzer.session = FakeHTTPSession({})  # geocode comes from cache

        ctx = asyncio.run(analyzer.get_location_context())
        assert ctx.city == "Nashville"
        assert ctx.state == "Tennessee"
        assert ctx.timezone == "America/Chicago"
        # cultural lookup still applies to the geocoded city name
        assert ctx.music_scene == "country_capital"

    def test_regional_themes_accept_full_state_name(self):
        analyzer = LocationAnalyzer(location="Denver, CO", offline=True)
        assert analyzer.get_regional_themes("Colorado") == analyzer.get_regional_themes("CO")
        assert "mountain" in analyzer.get_regional_themes("Colorado")


# ---------------------------------------------------------------------------
# Dayparting personas
# ---------------------------------------------------------------------------

class TestDayparting:
    @pytest.fixture
    def gen(self):
        return DJCommentaryGenerator("sk-test-not-real")

    def test_persona_follows_time_of_day(self, gen):
        for tod, name in [
            ("morning", "Morning Drive"),
            ("afternoon", "Afternoon Companion"),
            ("evening", "Evening Host"),
            ("late_night", "Late-Night Voice"),
        ]:
            ctx = {"temporal": FakeTemporal(time_of_day=tod)}
            assert gen._persona(ctx)["name"] == name

    def test_persona_defaults_to_afternoon(self, gen):
        assert gen._persona(None)["name"] == "Afternoon Companion"
        assert gen._persona({})["name"] == "Afternoon Companion"
        assert gen._persona({"temporal": FakeTemporal(time_of_day="weird")})["name"] == \
            "Afternoon Companion"

    def test_fallback_opening_is_daypart_flavored(self, gen):
        ctx = {"temporal": FakeTemporal(time_of_day="late_night")}
        # the fallback pool = persona templates + one generic; sample until
        # we see a persona one (pool of 3, so 30 draws can't plausibly miss)
        persona_templates = {
            t.format(theme="jazz") for t in DAYPART_PERSONAS["late_night"]["fallback_openings"]
        }
        seen = {gen._create_fallback_opening("jazz", ctx).content for _ in range(30)}
        assert seen & persona_templates

    def test_fallback_transition_uses_context(self, gen):
        ctx = {"temporal": FakeTemporal(time_of_day="morning")}
        persona_templates = set(DAYPART_PERSONAS["morning"]["fallback_transitions"])
        seen = {
            gen._create_fallback_transition({"artist": "A"}, {"artist": "B"}, ctx).content
            for _ in range(30)
        }
        assert seen & persona_templates

    def test_all_personas_have_required_keys(self):
        for persona in DAYPART_PERSONAS.values():
            assert persona["directive"]
            assert persona["fallback_openings"]
            assert persona["fallback_transitions"]


# ---------------------------------------------------------------------------
# Request line
# ---------------------------------------------------------------------------

class TestSongRequestValidation:
    def test_valid_request(self):
        r = SongRequest(query="  Moonlight Sonata ", requested_by=" Todd ")
        assert r.query == "Moonlight Sonata"
        assert r.requested_by == "Todd"

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            SongRequest(query="   ")

    def test_long_query_rejected(self):
        with pytest.raises(ValidationError):
            SongRequest(query="x" * 201)

    def test_name_is_optional(self):
        assert SongRequest(query="song").requested_by is None
        assert SongRequest(query="song", requested_by="  ").requested_by is None

    def test_hostile_name_rejected(self):
        with pytest.raises(ValidationError):
            SongRequest(query="song", requested_by="<script>alert(1)</script>")


class TestRequestAcknowledgment:
    def test_fallback_ack_names_the_requester(self):
        gen = DJCommentaryGenerator("sk-test-not-real")
        track = {"title": "So What", "artist": "Miles Davis"}
        seg = gen._create_fallback_request_ack(track, "Todd")
        assert "Todd" in seg.content
        assert "So What" in seg.content
        assert seg.type == "request"

    def test_fallback_ack_anonymous(self):
        gen = DJCommentaryGenerator("sk-test-not-real")
        seg = gen._create_fallback_request_ack({"title": "Blue in Green"}, None)
        assert "Blue in Green" in seg.content

    def test_generate_falls_back_when_ai_fails(self):
        gen = DJCommentaryGenerator("sk-test-not-real")  # bogus key -> AI fails
        ctx = {"temporal": FakeTemporal(time_of_day="evening")}
        seg = asyncio.run(gen.generate_request_acknowledgment(
            {"title": "So What", "artist": "Miles Davis"}, "Todd", ctx
        ))
        assert seg.type == "request"
        assert "Todd" in seg.content


class TestBroadcasterRequestQueue:
    """Queue mechanics without audio: no ffmpeg needed."""

    def _make_broadcaster(self):
        pytest.importorskip("pydub")
        from src.streaming.broadcaster import Broadcaster

        class NoopSessionManager:
            pass

        return Broadcaster(session_manager=NoopSessionManager())

    def test_queue_request_requires_active_session(self):
        b = self._make_broadcaster()
        with pytest.raises(RuntimeError):
            asyncio.run(b.queue_request({"title": "x", "artist": "y"}))

    def test_queue_request_fifo_and_status(self):
        b = self._make_broadcaster()
        b._session_active = True

        async def run():
            r1 = await b.queue_request(
                {"title": "First", "artist": "A"}, requested_by="Todd"
            )
            r2 = await b.queue_request({"title": "Second", "artist": "B"})
            return r1, r2

        r1, r2 = asyncio.run(run())
        assert r1 == {"queued": True, "position_in_queue": 1}
        assert r2["position_in_queue"] == 2
        items = list(b._request_queue)
        assert items[0].track["title"] == "First"
        assert items[0].requested_by == "Todd"
        assert items[1].track["title"] == "Second"

    def test_stop_session_clears_queue(self):
        b = self._make_broadcaster()
        b._session_active = True
        asyncio.run(b.queue_request({"title": "x", "artist": "y"}))
        asyncio.run(b.stop_session())
        assert len(b._request_queue) == 0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
class TestRequestOnAir:
    """Full pipeline: a queued request actually airs next, with its name."""

    def test_requested_track_airs_next(self, tmp_path):
        pydub = pytest.importorskip("pydub")
        from pydub.generators import Sine
        from src.streaming.broadcaster import Broadcaster

        def write_tone(path, freq, duration_ms=4000):
            tone = (
                Sine(freq).to_audio_segment(duration=duration_ms)
                .apply_gain(-12.0).set_frame_rate(44100)
                .set_channels(2).set_sample_width(2)
            )
            tone.export(str(path), format="wav")
            return str(path)

        @dataclass
        class FakeTrackItem:
            track: Dict[str, Any]
            position: int
            start_time: str = "00:00:00"
            commentary_before: Any = None
            crossfade_duration: float = 0.5
            context_relevance_score: float = 0.0

        @dataclass
        class FakeSession:
            session_id: str = "req_session"
            theme: str = "test"
            tracks: List[Any] = field(default_factory=list)
            commentary_segments: List[Any] = field(default_factory=list)

        class FakeSessionManager:
            def __init__(self, session):
                self._session = session

            async def create_session(self, theme, duration_minutes, context):
                return self._session

        p1 = write_tone(tmp_path / "t1.wav", 440)
        p2 = write_tone(tmp_path / "t2.wav", 660)
        p3 = write_tone(tmp_path / "req.wav", 880, duration_ms=2000)

        session = FakeSession(tracks=[
            FakeTrackItem({"title": "Planned A", "artist": "T", "file_path": p1, "duration": 4}, 1),
            FakeTrackItem({"title": "Planned B", "artist": "T", "file_path": p2, "duration": 4}, 2),
        ])

        async def run():
            b = Broadcaster(session_manager=FakeSessionManager(session))
            await b.start_session("test", 1, {})
            # keep a listener attached so the pipeline flows
            queue = await b.register_listener()

            await asyncio.sleep(0.5)
            await b.queue_request(
                {"title": "Requested", "artist": "R", "file_path": p3, "duration": 2},
                requested_by="Todd",
            )
            await b.skip_track()  # end Planned A; request must jump Planned B

            saw_requested = None
            async with asyncio.timeout(20):
                while True:
                    status = b.current_status()
                    track = status.get("current_track") or {}
                    if track.get("title") == "Requested":
                        saw_requested = track
                        break
                    if not status.get("active"):
                        break
                    await asyncio.sleep(0.2)

            await b.unregister_listener(queue)
            await b.stop_session()
            return saw_requested

        track = asyncio.run(run())
        assert track is not None, "requested track never aired"
        assert track["requested_by"] == "Todd"
