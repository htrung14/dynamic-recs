"""
Stremio API Client
Fetches user library and watch history from Stremio
"""
import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional, Any
from app.core.config import settings
from app.services.cache import CacheManager
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class StremioClient:
    """Async client for Stremio API"""
    
    API_URL = "https://api.strem.io/api/datastoreGet"
    LOVED_BASE_URL = "https://likes.stremio.com"
    _rate_limiter: Optional[RateLimiter] = None
    
    def __init__(self):
        self.cache = CacheManager()
        self.session: Optional[aiohttp.ClientSession] = None
        self.loved_base_url = self.LOVED_BASE_URL
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self.session
    
    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def fetch_library(self, auth_key: str) -> Optional[Dict[str, Any]]:
        """
        Fetch user's Stremio library
        
        Args:
            auth_key: Stremio authentication key
            
        Returns:
            Library data or None on error
        """
        cache_key = f"user:{auth_key}:library"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        self.loved_base_url = "https://likes.stremio.com"
        if cached:
            return cached
        
        # Get or create shared rate limiter for this service (skip if rate limit is 0)
        if settings.STREMIO_RATE_LIMIT > 0:
            if StremioClient._rate_limiter is None:
                StremioClient._rate_limiter = await RateLimiter.get_limiter(
                    "stremio", settings.STREMIO_RATE_LIMIT
                )
            await StremioClient._rate_limiter.acquire()
        
        try:
            session = await self.get_session()
            
            payload = {
                "authKey": auth_key,
                "collection": "libraryItem"
            }
            
            async with session.post(self.API_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Cache the result
                    await self.cache.set(
                        cache_key,
                        data,
                        ttl=settings.CACHE_TTL_LIBRARY
                    )
                    
                    return data
                else:
                    logger.error(f"Stremio API error: {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("Stremio library fetch timeout")
            return None
        except Exception as e:
            logger.error(f"Stremio library fetch error: {e}")
            return None
    
    def extract_loved_items(self, library: Optional[Dict[str, Any]]) -> List[str]:
        """
        Extract loved/favorited items from library
        
        Args:
            library: Stremio library data (format: {"result": [["id", timestamp], ...]})
            
        Returns:
            List of IMDB IDs
        """
        if not library or "result" not in library:
            return []
        
        # Note: Stremio datastoreGet doesn't include "loved" info in simple format
        return []
    async def fetch_loved_catalog(self, media_type: str, token: Optional[str] = None) -> List[str]:
        """Fetch loved items using the official Stremio loved addon.

        Args:
            media_type: "movie" or "series"
        Returns:
            List of IMDB IDs (tt- prefixed)
        """
        token = token or settings.STREMIO_LOVED_TOKEN
        if not token:
            return []

        # catalog ids from manifest
        catalog_id = "stremio-loved-movie" if media_type == "movie" else "stremio-loved-series"
        url = (
            f"{self.loved_base_url}/addons/loved/movies-shows/{token}/"
            f"catalog/{media_type}/{catalog_id}.json"
        )

        cache_key = f"loved:{media_type}:{token}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        logger.debug(f"Loved catalog fetch returned {resp.status} for {media_type}")
                        return []
                    data = await resp.json()
                    metas = data.get("metas", [])
                    imdb_ids = []
                    for m in metas:
                        imdb_id = m.get("imdb_id") or m.get("id")
                        if imdb_id and str(imdb_id).startswith("tt"):
                            imdb_ids.append(imdb_id)

                    if imdb_ids:
                        await self.cache.set(cache_key, imdb_ids, ttl=settings.CACHE_TTL_LIBRARY)
                    return imdb_ids
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Loved catalog fetch failed: {exc}")
            return []
    
    def extract_watched_items(self, library: Optional[Dict[str, Any]]) -> List[str]:
        """
        Extract watched items from library
        
        Args:
            library: Stremio library data (format: {"result": [["id", timestamp], ...]})
            
        Returns:
            List of IMDB IDs
        """
        if not library or "result" not in library:
            return []
        
        watched_items = []
        
        for item in library["result"]:
            if isinstance(item, list) and len(item) >= 1:
                imdb_id = item[0]
                if imdb_id and isinstance(imdb_id, str) and imdb_id.startswith("tt"):
                    watched_items.append(imdb_id)
        
        return watched_items
    
    def extract_recently_watched(
        self,
        library: Optional[Dict[str, Any]],
        limit: int = 50
    ) -> List[str]:
        """
        Extract recently watched items sorted by timestamp
        
        Args:
            library: Stremio library data (format: {"result": [["id", timestamp], ...]})
            limit: Maximum number of items to return
            
        Returns:
            List of IMDB IDs sorted by recency
        """
        if not library or "result" not in library:
            return []
        
        watched_with_time = []
        
        for item in library["result"]:
            if isinstance(item, list) and len(item) >= 2:
                imdb_id = item[0]
                timestamp = item[1]
                
                if imdb_id and isinstance(imdb_id, str) and imdb_id.startswith("tt"):
                    watched_with_time.append((imdb_id, timestamp))
        
        # Sort by timestamp (most recent first)
        watched_with_time.sort(key=lambda x: x[1], reverse=True)
        
        return [imdb_id for imdb_id, _ in watched_with_time[:limit]]
