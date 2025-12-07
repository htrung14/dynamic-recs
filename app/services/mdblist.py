"""MDBList API Client
Async client for MDBList ratings and metadata
"""
import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional, Any
from app.core.config import settings
from app.services.cache import CacheManager
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class MDBListClient:
    """Async client for MDBList API"""
    
    BASE_URL = "https://mdblist.com/api/"
    _rate_limiter: Optional[RateLimiter] = None
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.MDBLIST_API_KEY
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
    
    async def get_rating(self, imdb_id: str) -> Optional[Dict[str, Any]]:
        """
        Get ratings for an IMDB ID
        
        Args:
            imdb_id: IMDB ID (e.g., "tt1234567")
            
        Returns:
            Rating data or None
        """
        if not self.api_key:
            logger.warning("MDBList API key not configured")
            return None
        
        cache_key = f"meta:{imdb_id}:mdblist"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        # Get or create shared rate limiter for this service
        if MDBListClient._rate_limiter is None:
            MDBListClient._rate_limiter = await RateLimiter.get_limiter(
                "mdblist", settings.MDBLIST_RATE_LIMIT
            )
        await MDBListClient._rate_limiter.acquire()
        
        try:
            session = await self.get_session()
            
            params = {
                "apikey": self.api_key,
                "i": imdb_id
            }
            
            async with session.get(self.BASE_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Cache the result
                    await self.cache.set(
                        cache_key,
                        data,
                        ttl=settings.CACHE_TTL_RATINGS
                    )
                    
                    return data
                elif response.status == 429:
                    logger.warning("MDBList rate limit exceeded")
                    await asyncio.sleep(2)
                    return None
                elif response.status == 503:
                    logger.debug(f"MDBList temporarily unavailable (503)")
                    return None
                else:
                    logger.error(f"MDBList API error: {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error(f"MDBList request timeout for {imdb_id}")
            return None
        except Exception as e:
            logger.error(f"MDBList request error: {e}")
            return None
    
    async def batch_ratings(
        self,
        imdb_ids: List[str]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Get ratings for multiple IMDB IDs in parallel
        
        Args:
            imdb_ids: List of IMDB IDs
            
        Returns:
            Dictionary mapping IMDB IDs to rating data
        """
        tasks = []
        
        for imdb_id in imdb_ids:
            task = self.get_rating(imdb_id)
            tasks.append((imdb_id, task))
        
        # Execute in parallel with concurrency limit
        results = {}
        
        for i in range(0, len(tasks), settings.MAX_CONCURRENT_API_CALLS):
            batch = tasks[i:i + settings.MAX_CONCURRENT_API_CALLS]
            batch_tasks = [task for _, task in batch]
            batch_ids = [imdb_id for imdb_id, _ in batch]
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for imdb_id, result in zip(batch_ids, batch_results):
                if isinstance(result, dict):
                    results[imdb_id] = result
                else:
                    results[imdb_id] = None
        
        return results
    
    def extract_rating(self, rating_data: Optional[Dict[str, Any]]) -> float:
        """
        Extract aggregate rating from MDBList response
        
        Args:
            rating_data: MDBList API response
            
        Returns:
            Aggregate rating (0-10) or 0.0 if unavailable
        """
        if not rating_data:
            return 0.0
        
        # Try different rating fields in order of preference
        rating_fields = [
            "score",
            "imdbrating",
            "tomatoesrating",
            "metacriticrating"
        ]
        
        for field in rating_fields:
            value = rating_data.get(field)
            if value:
                try:
                    rating = float(value)
                    # Normalize to 0-10 scale
                    if field == "tomatoesrating" or field == "metacriticrating":
                        rating = rating / 10.0
                    return max(0.0, min(10.0, rating))
                except (ValueError, TypeError):
                    continue
        
        return 0.0
