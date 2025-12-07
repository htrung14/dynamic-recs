"""
TMDB API Client
Async client for The Movie Database API
"""
import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional, Any
from app.core.config import settings
from app.services.cache import CacheManager

logger = logging.getLogger(__name__)


class TMDBClient:
    """Async client for TMDB API"""
    
    BASE_URL = "https://api.themoviedb.org/3"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TMDB_API_KEY
        self.cache = CacheManager()
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self.session
    
    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make API request to TMDB
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            
        Returns:
            JSON response or None on error
        """
        if not self.api_key:
            logger.error("TMDB API key not configured")
            return None
        
        try:
            session = await self.get_session()
            url = f"{self.BASE_URL}{endpoint}"
            
            request_params = {"api_key": self.api_key}
            if params:
                request_params.update(params)
            
            async with session.get(url, params=request_params) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    logger.warning("TMDB rate limit exceeded")
                    await asyncio.sleep(1)
                    return None
                else:
                    logger.error(f"TMDB API error: {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error(f"TMDB request timeout: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"TMDB request error: {e}")
            return None
    
    async def get_recommendations(
        self,
        media_type: str,
        tmdb_id: int,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get recommendations for a movie or series
        
        Args:
            media_type: "movie" or "tv"
            tmdb_id: TMDB ID
            page: Page number
            
        Returns:
            List of recommendation items
        """
        cache_key = f"rec:{tmdb_id}:{media_type}:tmdb:page{page}"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        endpoint = f"/{media_type}/{tmdb_id}/recommendations"
        response = await self._request(endpoint, {"page": page})
        
        if response and "results" in response:
            results = response["results"]
            await self.cache.set(
                cache_key,
                results,
                ttl=settings.CACHE_TTL_RECOMMENDATIONS
            )
            return results
        
        return []
    
    async def get_details(
        self,
        media_type: str,
        tmdb_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a movie or series
        
        Args:
            media_type: "movie" or "tv"
            tmdb_id: TMDB ID
            
        Returns:
            Metadata dictionary or None
        """
        cache_key = f"meta:{tmdb_id}:{media_type}:tmdb"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        endpoint = f"/{media_type}/{tmdb_id}"
        response = await self._request(endpoint, {"append_to_response": "external_ids"})
        
        if response:
            await self.cache.set(
                cache_key,
                response,
                ttl=settings.CACHE_TTL_RECOMMENDATIONS
            )
            return response
        
        return None
    
    async def find_by_imdb_id(self, imdb_id: str) -> Optional[Dict[str, Any]]:
        """
        Find TMDB entry by IMDB ID
        
        Args:
            imdb_id: IMDB ID (e.g., "tt1234567")
            
        Returns:
            TMDB data or None
        """
        cache_key = f"find:{imdb_id}:tmdb"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        endpoint = f"/find/{imdb_id}"
        response = await self._request(endpoint, {"external_source": "imdb_id"})
        
        if response:
            # Extract movie or TV result
            result = None
            if response.get("movie_results"):
                result = response["movie_results"][0]
                result["media_type"] = "movie"
            elif response.get("tv_results"):
                result = response["tv_results"][0]
                result["media_type"] = "tv"
            
            if result:
                await self.cache.set(
                    cache_key,
                    result,
                    ttl=settings.CACHE_TTL_RECOMMENDATIONS
                )
                return result
        
        return None
    
    async def batch_recommendations(
        self,
        items: List[Dict[str, Any]],
        max_per_item: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get recommendations for multiple items in parallel
        
        Args:
            items: List of items with 'tmdb_id' and 'media_type'
            max_per_item: Maximum recommendations per item
            
        Returns:
            Combined list of recommendations
        """
        tasks = []
        
        for item in items[:settings.MAX_SEEDS]:
            tmdb_id = item.get("tmdb_id")
            media_type = item.get("media_type", "movie")
            
            if tmdb_id:
                task = self.get_recommendations(media_type, tmdb_id, page=1)
                tasks.append(task)
        
        # Execute in parallel with concurrency limit
        results = []
        for i in range(0, len(tasks), settings.MAX_CONCURRENT_API_CALLS):
            batch = tasks[i:i + settings.MAX_CONCURRENT_API_CALLS]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, list):
                    results.extend(result[:max_per_item])
        
        return results
