"""
Redis Cache Manager
High-performance caching layer with Redis
"""
import asyncio
import json
import logging
import random
import time
from typing import Optional, Any, Awaitable, Callable, Tuple, Dict
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Redis cache manager with async support"""
    
    _instance = None
    _redis_client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Lightweight in-process metrics for SWR behavior
        if not hasattr(self, "_metrics"):
            self._metrics: Dict[str, int] = {
                "swr_fresh_hit": 0,
                "swr_stale_served": 0,
                "swr_miss_build": 0,
                "swr_refresh_triggered": 0,
                "swr_refresh_failed": 0,
            }

    def _bump(self, key: str):
        try:
            if key in self._metrics:
                self._metrics[key] += 1
        except Exception:
            pass

    def get_metrics_snapshot(self) -> Dict[str, int]:
        """Return a shallow copy of SWR metrics counters."""
        return dict(self._metrics)
    
    async def get_client(self) -> redis.Redis:
        """Get or create Redis client"""
        if self._redis_client is None:
            self._redis_client = await redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis_client
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        try:
            client = await self.get_client()
            value = await client.get(key)
            
            if value:
                parsed = json.loads(value)
                # unwrap SWR payloads transparently
                if isinstance(parsed, dict) and "value" in parsed and "fresh_until" in parsed:
                    return parsed.get("value")
                return parsed
            return None
            
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def get_with_freshness(self, key: str) -> Tuple[Optional[Any], bool]:
        """
        Get value along with freshness metadata.
        Returns (value, is_stale). If key is missing, (None, False).
        """
        try:
            client = await self.get_client()
            value = await client.get(key)
            if not value:
                return None, False
            parsed = json.loads(value)
            if isinstance(parsed, dict) and "value" in parsed and "fresh_until" in parsed:
                is_stale = time.time() > parsed.get("fresh_until", 0)
                return parsed.get("value"), is_stale
            return parsed, False
        except Exception as e:
            logger.error(f"Cache get_with_freshness error for key {key}: {e}")
            return None, False
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            client = await self.get_client()
            serialized = json.dumps(value)
            
            if ttl:
                await client.setex(key, ttl, serialized)
            else:
                await client.set(key, serialized)
            
            return True
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    async def set_with_freshness(
        self,
        key: str,
        value: Any,
        ttl: int,
        stale_ttl: Optional[int] = None
    ) -> bool:
        """
        Set value with freshness metadata for stale-while-revalidate.
        ttl defines the fresh window; stale_ttl controls how long stale data remains usable.
        """
        try:
            client = await self.get_client()
            stale_expires = stale_ttl or ttl
            payload = {
                "value": value,
                "fresh_until": time.time() + ttl,
            }
            serialized = json.dumps(payload)
            await client.setex(key, stale_expires, serialized)
            return True
        except Exception as e:
            logger.error(f"Cache set_with_freshness error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Delete value from cache
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        try:
            client = await self.get_client()
            await client.delete(key)
            return True
            
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache
        
        Args:
            key: Cache key
            
        Returns:
            True if exists, False otherwise
        """
        try:
            client = await self.get_client()
            return await client.exists(key) > 0
            
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    async def close(self):
        """Close Redis connection"""
        if self._redis_client:
            await self._redis_client.aclose()
            self._redis_client = None

    async def stale_while_revalidate(
        self,
        key: str,
        build_fn: Callable[[], Awaitable[Any]],
        ttl: int,
        stale_ttl: Optional[int] = None,
        lock_ttl: Optional[int] = None,
        refresh_fn: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> Any:
        """
        Serve cached value immediately and refresh in the background when stale.
        The cache entry remains readable (stale) for stale_ttl while revalidation happens.
        """
        stale_expires = stale_ttl or ttl
        computed_lock_ttl = lock_ttl or max(stale_expires, ttl, 30)
        client = await self.get_client()
        value, is_stale = await self.get_with_freshness(key)

        if value is not None:
            if is_stale:
                # Acquire lock to avoid stampede
                lock_key = f"swr-lock:{key}"
                try:
                    acquired = await client.set(lock_key, "1", nx=True, ex=computed_lock_ttl)
                except Exception:
                    acquired = False

                if acquired:
                    self._bump("swr_refresh_triggered")
                    async def _revalidate():
                        try:
                            builder = refresh_fn or build_fn
                            logger.debug("SWR refresh start for key=%s", key)
                            fresh_value = await builder()
                            await self.set_with_freshness(key, fresh_value, ttl, stale_expires)
                            logger.debug("SWR refresh complete for key=%s", key)
                        except Exception as exc:  # pragma: no cover - defensive logging
                            self._bump("swr_refresh_failed")
                            logger.error(f"SWR refresh failed for {key}: {exc}", exc_info=True)
                        finally:
                            try:
                                await client.delete(lock_key)
                            except Exception:
                                pass

                    asyncio.create_task(_revalidate())
                else:
                    # Slight jitter to reduce simultaneous refresh attempts after lock expiry
                    await asyncio.sleep(random.uniform(0.01, 0.05))
                self._bump("swr_stale_served")
            return value

        # Cold miss -> build synchronously
        self._bump("swr_miss_build")
        fresh_value = await build_fn()
        await self.set_with_freshness(key, fresh_value, ttl, stale_expires)
        self._bump("swr_fresh_hit")
        return fresh_value
