"""
Configuration Management
Loads and validates environment variables
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import secrets


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )
    # Required
    TOKEN_SALT: str = secrets.token_hex(32)
    BASE_URL: str = "http://localhost:8000"
    
    # API Keys (server defaults - users must provide if not set)
    TMDB_API_KEY: Optional[str] = None
    MDBLIST_API_KEY: Optional[str] = None
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Cache TTLs (seconds)
    CACHE_TTL_LIBRARY: int = 21600  # 6 hours
    CACHE_TTL_RECOMMENDATIONS: int = 86400  # 24 hours
    CACHE_TTL_RATINGS: int = 604800  # 7 days
    CACHE_TTL_CATALOG: int = 3600  # 1 hour
    
    # Background Tasks
    CACHE_WARM_INTERVAL_HOURS: int = 3  # Hours between cache warming cycles
    
    # Performance Limits
    MAX_SEEDS: int = 5  # Reduced from 10 to minimize API calls (5 seed items)
    MAX_RECOMMENDATIONS_PER_SEED: int = 15  # Reduced from 20 to minimize API calls (15 recs/seed)
    MAX_CONCURRENT_API_CALLS: int = 10
    
    # API Rate Limits (requests per second)
    # Optimized for performance while staying within API limits
    TMDB_RATE_LIMIT: int = 50  # TMDB allows 50/sec
    MDBLIST_RATE_LIMIT: int = 30  # MDBList allows 100k/day, 30 req/s = ~2.6M/day capacity
    STREMIO_RATE_LIMIT: int = 0  # No rate limiting for Stremio (personal library access)
    
    # Development
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    DISABLE_RATE_LIMITING: bool = False  # Set to True to disable rate limiting for local dev


settings = Settings()
