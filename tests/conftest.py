"""
Test configuration and fixtures
"""
import pytest
from typing import Generator
from fakeredis import aioredis as fakeredis


@pytest.fixture
async def fake_redis():
    """Provide fake Redis client for testing"""
    redis_client = await fakeredis.FakeRedis(decode_responses=True)
    yield redis_client
    await redis_client.flushall()
    await redis_client.close()


@pytest.fixture
def sample_user_config():
    """Sample user configuration with realistic fake credentials"""
    from app.models.config import UserConfig
    
    return UserConfig(
        stremio_auth_key="SXFxRURKV2lNVXVjemtuaU1RYlZFaENXREhUTUVKeGY=",  # Base64-like (44 chars)
        tmdb_api_key="9a3b6df7b9285e1b338a8ca4b2970365",  # Fake 32-char hex
        mdblist_api_key="fake1234567890abcdefghijklmnop",  # Fake 30-char alphanumeric
        num_rows=5,
        min_rating=6.0,
        use_loved_items=True,
        include_movies=True,
        include_series=True
    )


@pytest.fixture
def sample_tmdb_movie():
    """Sample TMDB movie data"""
    return {
        "id": 550,
        "title": "Fight Club",
        "media_type": "movie",
        "poster_path": "/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg",
        "backdrop_path": "/fCayJrkfRaCRCTh8GqN30f8oyQF.jpg",
        "overview": "A ticking-time-bomb insomniac...",
        "release_date": "1999-10-15",
        "vote_average": 8.4,
        "popularity": 45.3,
        "external_ids": {
            "imdb_id": "tt0137523"
        }
    }


@pytest.fixture
def sample_tmdb_series():
    """Sample TMDB series data"""
    return {
        "id": 1396,
        "name": "Breaking Bad",
        "media_type": "tv",
        "poster_path": "/ggFHVNu6YYI5L9pCfOacjizRGt.jpg",
        "backdrop_path": "/tsRy63Mu5cu8etL1X7ZLyf7UP1M.jpg",
        "overview": "A high school chemistry teacher...",
        "first_air_date": "2008-01-20",
        "vote_average": 8.9,
        "popularity": 120.5,
        "external_ids": {
            "imdb_id": "tt0903747"
        }
    }


@pytest.fixture
def sample_stremio_library():
    """Sample Stremio library data (actual API format)"""
    return {
        "result": [
            ["tt0137523", 1705318200000],  # 2024-01-15 (most recent)
            ["tt0903747", 1704895200000],  # 2024-01-10
            ["tt0468569", 1704484800000],  # 2024-01-05 (oldest)
            ["trakt:123456", 1704484800000]  # Non-IMDB ID (should be filtered)
        ]
    }
