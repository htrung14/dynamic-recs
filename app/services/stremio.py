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

logger = logging.getLogger(__name__)


class StremioClient:
    """Async client for Stremio API"""
    
    API_URL = "https://api.strem.io/api/datastoreGet"
    
    def __init__(self):
        self.cache = CacheManager()
        self.session: Optional[aiohttp.ClientSession] = None
    
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
        if cached:
            return cached
        
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
        # For now, return empty list. To get loved items, we'd need a different API call
        # or use the full library metadata
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
