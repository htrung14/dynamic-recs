"""
Rate Limiter Utility
Token bucket rate limiter for API clients with per-user limiting support
"""
import asyncio
import hashlib
import time
from typing import Dict, Optional


class RateLimiter:
    """
    Token bucket rate limiter with two tiers:
    1. Global per-service limiter: prevents addon from exceeding API limits
    2. Per-user limiter: prevents any single user from hogging shared quota
    
    Each user (identified by token_hash) gets their own bucket that refills
    at a fraction of the global rate.
    """
    
    _global_instances: Dict[str, "RateLimiter"] = {}
    _user_instances: Dict[str, "RateLimiter"] = {}
    _lock = asyncio.Lock()
    
    def __init__(self, service_name: str, rate: int, user_key: Optional[str] = None):
        self.service_name = service_name
        self.user_key = user_key  # None = global limiter
        self.rate = rate  # requests per second
        self.tokens = float(rate)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()
    
    @classmethod
    async def get_limiter(cls, service_name: str, rate: int) -> "RateLimiter":
        """Get or create a shared global rate limiter for a service"""
        async with cls._lock:
            if service_name not in cls._global_instances:
                cls._global_instances[service_name] = cls(service_name, rate)
            return cls._global_instances[service_name]
    
    @classmethod
    async def get_user_limiter(
        cls, service_name: str, rate: int, token: str
    ) -> "RateLimiter":
        """
        Get or create a per-user rate limiter.
        Each user gets 20% of the global rate to prevent any single user
        from consuming the entire shared quota.
        """
        # Hash token for shorter, non-identifiable key
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        user_key = f"{service_name}:{token_hash}"
        
        per_user_rate = max(1, int(rate * 0.2))  # 20% of global rate, min 1 req/s
        
        async with cls._lock:
            if user_key not in cls._user_instances:
                cls._user_instances[user_key] = cls(service_name, per_user_rate, user_key)
            return cls._user_instances[user_key]
    
    async def acquire(self):
        """Acquire a token, waiting if necessary"""
        from app.core.config import settings
        
        # Skip rate limiting if disabled for development
        if settings.DISABLE_RATE_LIMITING:
            return
        
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


class PerUserRateLimiter:
    """
    Per-user rate limiter wrapper that combines global + per-user limiting.
    Use this when you want BOTH protections.
    """
    
    def __init__(self, service_name: str, global_rate: int, per_user_rate: int):
        self.service_name = service_name
        self.global_rate = global_rate
        self.per_user_rate = per_user_rate
        self._global_limiter: Optional[RateLimiter] = None
        self._user_limiters: Dict[str, RateLimiter] = {}
        self._lock = asyncio.Lock()
    
    async def acquire(self, token: str):
        """
        Acquire rate limit tokens for both global and per-user limits.
        Waits if either limit is exceeded.
        """
        from app.core.config import settings
        
        if settings.DISABLE_RATE_LIMITING:
            return
        
        # Global limiter first
        if self._global_limiter is None:
            self._global_limiter = await RateLimiter.get_limiter(
                self.service_name, self.global_rate
            )
        await self._global_limiter.acquire()
        
        # Then per-user limiter
        user_limiter = await RateLimiter.get_user_limiter(
            self.service_name, self.per_user_rate, token
        )
        await user_limiter.acquire()
