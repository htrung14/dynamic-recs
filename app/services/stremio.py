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
from app.utils.crypto import decrypt_secret

logger = logging.getLogger(__name__)


class StremioClient:
    """Async client for Stremio API"""
    
    API_URL = "https://api.strem.io/api/datastoreGet"
    LOGIN_URL = "https://api.strem.io/api/login"
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

    async def login_with_credentials(self, username: str, password: str) -> Optional[str]:
        """Login to Stremio using username/password and return authKey."""
        try:
            session = await self.get_session()
            payload = {
                "type": "Login",
                "email": username,
                "password": password,
            }
            async with session.post(self.LOGIN_URL, json=payload, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"Stremio login failed with status {response.status}")
                    return None
                data = await response.json()
                auth_key = (
                    data.get("authKey")
                    or data.get("result", {}).get("authKey")
                )
                if not auth_key:
                    logger.warning("Stremio login succeeded but no authKey returned")
                return auth_key
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Stremio login error: {exc}")
            return None

    async def resolve_auth_key(self, config) -> Optional[str]:
        """Resolve auth key from config, using stored key or decrypting credentials."""
        if getattr(config, "stremio_auth_key", None):
            return config.stremio_auth_key

        username_enc = getattr(config, "stremio_username_enc", None)
        password_enc = getattr(config, "stremio_password_enc", None)
        if username_enc and password_enc:
            username = decrypt_secret(username_enc)
            password = decrypt_secret(password_enc)
            if not username or not password:
                logger.warning("Failed to decrypt Stremio credentials")
                return None
            auth_key = await self.login_with_credentials(username, password)
            if auth_key:
                config.stremio_auth_key = auth_key
                return auth_key
        return None
    
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
isn        Extract loved/favorited items from library
        
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
    
    async def fetch_watched_progress(self, auth_key: str, imdb_id: str) -> Optional[float]:
        """
        Fetch watch progress for a single item (0-1 scale, 0.5 = 50%)
        
        Args:
            auth_key: Stremio authentication key
            imdb_id: IMDB ID (e.g., tt1234567)
            
        Returns:
            Progress as float 0.0-1.0, or None on error
        """
        cache_key = f"progress:{auth_key}:{imdb_id}"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            session = await self.get_session()
            payload = {
                "authKey": auth_key,
                "collection": "libraryItem",
                "id": imdb_id
            }
            
            async with session.post(self.API_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    result = data.get("result", {})

                    # Some responses return a list of entries instead of a dict
                    if isinstance(result, list):
                        # Pick the first dict entry that has "watched"
                        for entry in result:
                            if isinstance(entry, dict) and "watched" in entry:
                                result = entry
                                break
                        else:
                            result = {}
                    elif not isinstance(result, dict):
                        result = {}

                    # Extract progress (0.0-1.0)
                    progress = result.get("watched", 0.0)
                    if isinstance(progress, (int, float)):
                        progress = float(progress)
                    else:
                        progress = 0.0
                    
                    # Cache for 1 hour
                    await self.cache.set(cache_key, progress, ttl=3600)
                    return progress
                else:
                    logger.debug(f"Stremio progress fetch returned {response.status}")
                    return None
                    
        except Exception as e:
            logger.debug(f"Error fetching progress for {imdb_id}: {e}")
            return None
    
    async def filter_by_progress(
        self, auth_key: str, imdb_ids: List[str], min_progress: float = 0.5
    ) -> List[str]:
        """
        Filter items by watch progress threshold
        
        Args:
            auth_key: Stremio authentication key
            imdb_ids: List of IMDB IDs to filter
            min_progress: Minimum progress required (0-1)
            
        Returns:
            Filtered list of IMDB IDs
        """
        filtered = []
        
        for imdb_id in imdb_ids:
            try:
                progress = await self.fetch_watched_progress(auth_key, imdb_id)
                if progress is not None and progress >= min_progress:
                    filtered.append(imdb_id)
            except Exception as e:
                logger.debug(f"Error filtering {imdb_id}: {e}")
                # Fall back to including the item if we can't fetch progress
                filtered.append(imdb_id)
        
        return filtered

