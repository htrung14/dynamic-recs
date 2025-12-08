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
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

class TMDBClient:
    """Async client for TMDB API"""
    
    BASE_URL = "https://api.themoviedb.org/3"
    _rate_limiter: Optional[RateLimiter] = None
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TMDB_API_KEY
        self.cache = CacheManager()
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
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
        Make API request to TMDB with fast-fail timeout and light retry.
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

        backoff = 0.1
        attempts = 2

        for attempt in range(attempts):
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
                        logger.debug(
                            "TMDB 404 for %s (id may not exist or have no data)",
                            endpoint,
                        )
                        return None
                    elif 500 <= response.status < 600 and attempt + 1 < attempts:
                        await asyncio.sleep(backoff * (attempt + 1))
                        continue
                    else:
                        logger.error(
                            "TMDB API error: %s for %s params=%s",
                            response.status,
                            endpoint,
                            request_params,
                        )
                        return None

            except asyncio.TimeoutError:
                if attempt + 1 < attempts:
                    await asyncio.sleep(backoff * (attempt + 1))
                    continue
                logger.error(f"TMDB request timeout: {endpoint}")
                return None
            except Exception as e:
                if attempt + 1 < attempts:
                    await asyncio.sleep(backoff * (attempt + 1))
                    continue
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

        async def build() -> List[Dict[str, Any]]:
            endpoint = f"/{media_type}/{tmdb_id}/recommendations"
            response = await self._request(endpoint, {"page": page})

            if response and "results" in response:
                results = response["results"]
                for item in results:
                    item.setdefault("media_type", media_type)
                return results
            return []

        return await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build,
            ttl=settings.CACHE_TTL_RECOMMENDATIONS,
            stale_ttl=settings.CACHE_TTL_RECOMMENDATIONS * 3,
        )

    async def get_similar(
        self,
        tmdb_id: int,
        media_type: str,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """Get similar items when recommendations are missing or sparse."""
        cache_key = f"similar:{media_type}:{tmdb_id}:tmdb:page{page}"

        async def build() -> List[Dict[str, Any]]:
            endpoint = f"/{media_type}/{tmdb_id}/similar"
            response = await self._request(endpoint, {"page": page})

            if response and "results" in response:
                results = response["results"]
                for item in results:
                    item.setdefault("media_type", media_type)
                return results
            return []

        return await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build,
            ttl=settings.CACHE_TTL_RECOMMENDATIONS,
            stale_ttl=settings.CACHE_TTL_RECOMMENDATIONS * 3,
        )
    
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

        async def build() -> Optional[Dict[str, Any]]:
            endpoint = f"/{media_type}/{tmdb_id}"
            response = await self._request(endpoint, {"append_to_response": "external_ids"})
            return response

        return await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build,
            ttl=settings.CACHE_TTL_RECOMMENDATIONS,
            stale_ttl=settings.CACHE_TTL_RECOMMENDATIONS * 3,
        )

    async def get_popular(
        self,
        media_type: str,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """Fetch popular items as a fallback when recommendations are empty."""
        cache_key = f"popular:{media_type}:tmdb:page{page}"

        async def build() -> List[Dict[str, Any]]:
            endpoint = f"/{media_type}/popular"
            response = await self._request(endpoint, {"page": page})

            if response and "results" in response:
                results = response["results"]
                for item in results:
                    item.setdefault("media_type", media_type)
                return results
            return []

        return await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build,
            ttl=settings.CACHE_TTL_RECOMMENDATIONS,
            stale_ttl=settings.CACHE_TTL_RECOMMENDATIONS * 3,
        )
    
    async def find_by_imdb_id(self, imdb_id: str) -> Optional[Dict[str, Any]]:
        """
        Find TMDB entry by IMDB ID
        
        Args:
            imdb_id: IMDB ID (e.g., "tt1234567")
            
        Returns:
            TMDB data or None
        """
        cache_key = f"find:{imdb_id}:tmdb"

        async def build() -> Optional[Dict[str, Any]]:
            endpoint = f"/find/{imdb_id}"
            response = await self._request(endpoint, {"external_source": "imdb_id"})

            if response:
                result = None
                if response.get("movie_results"):
                    result = response["movie_results"][0]
                    result["media_type"] = "movie"
                    result["tmdb_id"] = result["id"]
                elif response.get("tv_results"):
                    result = response["tv_results"][0]
                    result["media_type"] = "tv"
                    result["tmdb_id"] = result["id"]
                return result
            return None

        return await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build,
            ttl=settings.CACHE_TTL_RECOMMENDATIONS,
            stale_ttl=settings.CACHE_TTL_RECOMMENDATIONS * 3,
        )
    
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

    async def batch_similar(
        self,
        items: List[Dict[str, Any]],
        max_per_item: int = 20
    ) -> List[Dict[str, Any]]:
        """Get similar items for multiple titles as a secondary signal."""
        tasks = []

        for item in items[:settings.MAX_SEEDS]:
            tmdb_id = item.get("tmdb_id")
            media_type = item.get("media_type", "movie")

            if tmdb_id:
                tasks.append(self.get_similar(tmdb_id, media_type, page=1))

        results = []
        for i in range(0, len(tasks), settings.MAX_CONCURRENT_API_CALLS):
            batch = tasks[i:i + settings.MAX_CONCURRENT_API_CALLS]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, list):
                    results.extend(result[:max_per_item])

        return results
    
    async def batch_details(
        self,
        items: List[Dict[str, Any]]
    ) -> Dict[int, Optional[Dict[str, Any]]]:
        """
        Get details for multiple items in parallel, checking cache first
        
        Args:
            items: List of items with 'id' and 'media_type'
            
        Returns:
            Dictionary mapping TMDB IDs to detail data
        """
        results = {}
        uncached_items = []
        
        # Check cache for all items first
        for item in items:
            tmdb_id = item.get("id")
            media_type = item.get("media_type", "movie")
            
            if not tmdb_id:
                continue
            
            cache_key = f"meta:{tmdb_id}:{media_type}:tmdb"
            cached = await self.cache.get(cache_key)
            
            if cached:
                results[tmdb_id] = cached
            else:
                uncached_items.append((tmdb_id, media_type))
        
        # Only fetch uncached items from API
        if uncached_items:
            tasks = []
            for tmdb_id, media_type in uncached_items:
                task = self.get_details(media_type, tmdb_id)
                tasks.append((tmdb_id, task))
            
            # Execute in parallel with concurrency limit
            for i in range(0, len(tasks), settings.MAX_CONCURRENT_API_CALLS):
                batch = tasks[i:i + settings.MAX_CONCURRENT_API_CALLS]
                batch_tasks = [task for _, task in batch]
                batch_ids = [tmdb_id for tmdb_id, _ in batch]
                
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                for tmdb_id, result in zip(batch_ids, batch_results):
                    if isinstance(result, dict):
                        results[tmdb_id] = result
                    else:
                        results[tmdb_id] = None
        
        return results

