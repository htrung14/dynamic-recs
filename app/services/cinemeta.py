"""
Cinemeta API Client
Lightweight helper to fetch meta details as a fallback when TMDB data is incomplete.
"""
import aiohttp
import logging
from typing import Optional, Dict, Any
from app.services.cache import CacheManager

logger = logging.getLogger(__name__)


class CinemetaClient:
    BASE_URL = "https://v3-cinemeta.strem.io/meta"

    def __init__(self):
        self.cache = CacheManager()
        self.session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch_meta(self, media_type: str, imdb_id: str) -> Optional[Dict[str, Any]]:
        """Fetch Cinemeta meta by imdb id (media_type: movie or series)."""
        cache_key = f"cinemeta:{media_type}:{imdb_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        url = f"{self.BASE_URL}/{media_type}/{imdb_id}.json"
        try:
            session = await self.get_session()
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    logger.debug("Cinemeta fetch %s returned %s", imdb_id, resp.status)
                    return None
                data = await resp.json()
                meta = data.get("meta") or {}
                await self.cache.set(cache_key, meta, ttl=3600)
                return meta
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cinemeta fetch error for %s: %s", imdb_id, exc)
            return None
