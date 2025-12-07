"""
Rate Limiter Utility
Token bucket rate limiter for API clients
"""
import asyncio
import time
from typing import Dict


class RateLimiter:
    """Token bucket rate limiter with shared state per service"""
    
    _instances: Dict[str, "RateLimiter"] = {}
    _lock = asyncio.Lock()
    
    def __init__(self, service_name: str, rate: int):
        self.service_name = service_name
        self.rate = rate  # requests per second
        self.tokens = float(rate)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()
    
    @classmethod
    async def get_limiter(cls, service_name: str, rate: int) -> "RateLimiter":
        """Get or create a shared rate limiter for a service"""
        async with cls._lock:
            if service_name not in cls._instances:
                cls._instances[service_name] = cls(service_name, rate)
            return cls._instances[service_name]
    
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
