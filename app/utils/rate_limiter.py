"""
Rate Limiter Utility
Token bucket rate limiter for global per-service rate limiting.
"""
import asyncio
import time
from typing import Dict


class RateLimiter:
    """Token bucket rate limiter — global per-service."""

    _global_instances: Dict[str, "RateLimiter"] = {}
    _lock = asyncio.Lock()

    def __init__(self, service_name: str, rate: int):
        self.service_name = service_name
        self.rate = rate  # requests per second
        self.tokens = float(rate)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()

    @classmethod
    async def get_limiter(cls, service_name: str, rate: int) -> "RateLimiter":
        """Get or create a shared global rate limiter for a service."""
        async with cls._lock:
            if service_name not in cls._global_instances:
                cls._global_instances[service_name] = cls(service_name, rate)
            return cls._global_instances[service_name]

    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        from app.core.config import settings

        if settings.DISABLE_RATE_LIMITING:
            return

        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update

            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
            else:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
                self.last_update = time.monotonic()
