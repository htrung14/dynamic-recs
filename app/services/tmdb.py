"""
TMDB API Client
Async client for The Movie Database API
"""
import aiohttp
import asyncio
import logging
import time
from typing import List, Dict, Optional, Any
from app.core.config import settings
from app.services.cache import CacheManager

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter"""
    
    def __init__(self, rate: int):
        self.rate = rate  # requests per second
        self.tokens = float(rate)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire a token, waiting if necessary"""
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            # Add tokens based on time elapsed
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
            else:
                # Wait until we have a token
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
                self.last_update = time.monotonic()


class TMDBClient:
    """Async client for TMDB API"""
    
    BASE_URL = "https://api.themoviedb.org/3"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TMDB_API_KEY
        self.cache = CacheManager()
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limiter = RateLimiter(settings.TMDB_RATE_LIMIT)
    
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
        
        # Get or create shared rate limiter for this service
        if TMDBClient._rate_limiter is None:
            TMDBClient._rate_limiter = await RateLimiter.get_limiter(
                "tmdb", settings.TMDB_RATE_LIMIT
            )
        await TMDBClient._rate_limiter.acquire()
        
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
                elif response.status == 404:
                    # 404 is expected for items without recommendations or invalid IDs
                    # Only log at debug level to avoid noise
                    logger.debug(
                        "TMDB 404 for %s (id may not exist or have no data)",
                        endpoint,
                    )
                    return None
                else:
                    logger.error(
                        "TMDB API error: %s for %s params=%s",
                        response.status,
                        endpoint,
                        request_params,
                    )
                    return None
                    
        except asyncio.TimeoutError:
            logger.error(f"TMDB request timeout: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"TMDB request error: {e}")
            return None
    
    async def get_recommendations(
        self,
        tmdb_id: int,
        media_type: str,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get recommendations for a movie or series
        
        Args:
            tmdb_id: TMDB ID
            media_type: "movie" or "tv"
            page: Page number
            
        Returns:
            List of recommendation items
        """
        cache_key = f"rec:{media_type}:{tmdb_id}:tmdb:page{page}"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        endpoint = f"/{media_type}/{tmdb_id}/recommendations"
        response = await self._request(endpoint, {"page": page})
        
        if response and "results" in response:
            results = response["results"]
            # Ensure media_type is set for downstream filtering
            for item in results:
                item.setdefault("media_type", media_type)
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

    async def get_popular(
        self,
        media_type: str,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """Fetch popular items as a fallback when recommendations are empty."""
        cache_key = f"popular:{media_type}:tmdb:page{page}"

        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        endpoint = f"/{media_type}/popular"
        response = await self._request(endpoint, {"page": page})

        if response and "results" in response:
            results = response["results"]
            # Ensure media_type is set for downstream filtering
            for item in results:
                item.setdefault("media_type", media_type)
            await self.cache.set(cache_key, results, ttl=settings.CACHE_TTL_RECOMMENDATIONS)
            return results
        return []
    
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
                result["tmdb_id"] = result["id"]  # Add tmdb_id field for compatibility
            elif response.get("tv_results"):
                result = response["tv_results"][0]
                result["media_type"] = "tv"
                result["tmdb_id"] = result["id"]  # Add tmdb_id field for compatibility
            
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
                task = self.get_recommendations(tmdb_id, media_type, page=1)
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
