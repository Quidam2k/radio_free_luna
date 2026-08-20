"""
Lyrics fetching from various sources
"""

import aiohttp
import asyncio
import logging
from typing import Optional, Dict
import re
from urllib.parse import quote

logger = logging.getLogger(__name__)

class LyricsFetcher:
    def __init__(self, genius_token: Optional[str] = None):
        self.genius_token = genius_token
        self.session = None
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Seconds between requests
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_lyrics(self, artist: str, title: str) -> Optional[str]:
        """Fetch lyrics from available sources"""
        
        if not artist or not title:
            return None
        
        # Try Genius API first if token is available
        if self.genius_token:
            lyrics = await self._fetch_from_genius(artist, title)
            if lyrics:
                return lyrics
        
        # Keyless fallback. AZLyrics is currently reCAPTCHA-walled (returns a
        # "request for access" page at HTTP 200), so lyrics.ovh — a free, keyless
        # lyrics API — is tried first, with AZLyrics kept as a secondary path.
        lyrics = await self._fetch_from_lyrics_ovh(artist, title)
        if lyrics:
            return lyrics

        lyrics = await self._fetch_from_azlyrics(artist, title)
        if lyrics:
            return lyrics

        logger.info(f"No lyrics found for {artist} - {title}")
        return None

    async def _fetch_from_lyrics_ovh(self, artist: str, title: str) -> Optional[str]:
        """Fetch lyrics from the keyless lyrics.ovh API."""
        try:
            await self._rate_limit()
            url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
            async with self.session.get(url) as response:
                if response.status != 200:
                    return None
                data = await response.json(content_type=None)
                lyrics = (data.get("lyrics") or "").strip()
                return lyrics if len(lyrics) > 50 else None
        except Exception as e:
            logger.debug(f"Error fetching from lyrics.ovh: {e}")
            return None
    
    async def _fetch_from_genius(self, artist: str, title: str) -> Optional[str]:
        """Fetch lyrics from Genius API"""
        try:
            await self._rate_limit()
            
            # Search for song on Genius
            search_url = "https://api.genius.com/search"
            headers = {"Authorization": f"Bearer {self.genius_token}"}
            params = {"q": f"{artist} {title}"}
            
            async with self.session.get(search_url, headers=headers, params=params) as response:
                if response.status != 200:
                    logger.warning(f"Genius API search failed: {response.status}")
                    return None
                
                data = await response.json()
                hits = data.get('response', {}).get('hits', [])
                
                if not hits:
                    return None
                
                # Get the first result's URL
                song_url = hits[0]['result']['url']
                
                # Scrape lyrics from the song page
                return await self._scrape_genius_lyrics(song_url)
                
        except Exception as e:
            logger.error(f"Error fetching from Genius: {e}")
            return None
    
    async def _scrape_genius_lyrics(self, song_url: str) -> Optional[str]:
        """Scrape lyrics from Genius song page"""
        try:
            await self._rate_limit()
            
            async with self.session.get(song_url) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                
                # Extract lyrics from HTML
                # Genius uses various div classes for lyrics
                lyrics_patterns = [
                    r'<div[^>]*data-lyrics-container[^>]*>(.*?)</div>',
                    r'<div[^>]*class="[^"]*lyrics[^"]*"[^>]*>(.*?)</div>',
                    r'<div[^>]*id="lyrics-root[^>]*>(.*?)</div>'
                ]
                
                for pattern in lyrics_patterns:
                    matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
                    if matches:
                        # Clean up HTML and extract text
                        lyrics_html = ''.join(matches)
                        lyrics = self._clean_html_lyrics(lyrics_html)
                        if lyrics and len(lyrics) > 50:  # Basic validation
                            return lyrics
                
                return None
                
        except Exception as e:
            logger.error(f"Error scraping Genius lyrics: {e}")
            return None
    
    async def _fetch_from_azlyrics(self, artist: str, title: str) -> Optional[str]:
        """Fetch lyrics from AZLyrics (with rate limiting and respect for robots.txt)"""
        try:
            await self._rate_limit()
            
            # Clean artist and title for URL
            clean_artist = re.sub(r'[^a-zA-Z0-9]', '', artist.lower())
            clean_title = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
            
            # Construct AZLyrics URL
            url = f"https://www.azlyrics.com/lyrics/{clean_artist}/{clean_title}.html"
            
            # Set user agent to be respectful
            headers = {
                'User-Agent': 'Mozilla/5.0 (AI DJ System - Educational Use)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                
                # Extract lyrics from AZLyrics format
                # AZLyrics typically has lyrics in a div without class after "Sorry about that."
                pattern = r'<!-- Usage of azlyrics\.com content.*?-->(.*?)(?:<div|<script)'
                match = re.search(pattern, html, re.DOTALL)
                
                if match:
                    lyrics_html = match.group(1)
                    lyrics = self._clean_html_lyrics(lyrics_html)
                    if lyrics and len(lyrics) > 50:
                        return lyrics
                
                return None
                
        except Exception as e:
            logger.error(f"Error fetching from AZLyrics: {e}")
            return None
    
    def _clean_html_lyrics(self, html_content: str) -> str:
        """Clean HTML content to extract clean lyrics"""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html_content)
        
        # Decode HTML entities
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#x27;', "'")
        text = text.replace('&#39;', "'")
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Remove common non-lyric content
        patterns_to_remove = [
            r'\[.*?\]',  # Remove [Verse 1], [Chorus], etc.
            r'Lyrics powered by.*',
            r'Submit Corrections',
            r'Thanks to.*for adding these lyrics',
            r'Thanks to.*for correcting these lyrics'
        ]
        
        for pattern in patterns_to_remove:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    async def _rate_limit(self):
        """Implement rate limiting to be respectful to APIs"""
        import time
        
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last_request
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    async def batch_fetch_lyrics(self, tracks: list) -> Dict[int, str]:
        """Fetch lyrics for multiple tracks with proper rate limiting"""
        results = {}
        
        for track in tracks:
            try:
                lyrics = await self.fetch_lyrics(track.artist, track.title)
                if lyrics:
                    results[track.id] = lyrics
                    logger.info(f"Found lyrics for {track.artist} - {track.title}")
                
                # Extra delay between batch requests
                await asyncio.sleep(2.0)
                
            except Exception as e:
                logger.error(f"Error fetching lyrics for track {track.id}: {e}")
                continue
        
        return results