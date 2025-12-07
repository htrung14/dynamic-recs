"""
Configuration Management
Loads and validates environment variables
"""
from pydantic_settings import BaseSettings
from typing import Optional
import secrets


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
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
    
    # Performance Limits
    MAX_SEEDS: int = 10
    MAX_RECOMMENDATIONS_PER_SEED: int = 20
    MAX_CONCURRENT_API_CALLS: int = 10
    
    # Development
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
