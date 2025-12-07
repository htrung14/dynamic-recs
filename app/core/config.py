"""
Configuration Management
Loads and validates environment variables
"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional
import secrets


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    model_config = ConfigDict(
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
    MAX_SEEDS: int = 10
    MAX_RECOMMENDATIONS_PER_SEED: int = 20
    MAX_CONCURRENT_API_CALLS: int = 10
    
    # API Rate Limits (requests per second)
    TMDB_RATE_LIMIT: int = 40  # TMDB allows 50/sec, use 40 to be safe
    MDBLIST_RATE_LIMIT: int = 10  # Conservative limit
    STREMIO_RATE_LIMIT: int = 5  # Conservative limit
    
    # Development
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"


settings = Settings()
