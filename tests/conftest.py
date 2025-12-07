"""
Test configuration and fixtures
"""
import pytest
import asyncio
from typing import Generator
from fakeredis import aioredis as fakeredis


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def fake_redis():
    """Provide fake Redis client for testing"""
    redis_client = await fakeredis.FakeRedis(decode_responses=True)
    yield redis_client
    await redis_client.flushall()
    await redis_client.close()


@pytest.fixture
def sample_user_config():
    """Sample user configuration"""
    from app.models.config import UserConfig
    
    return UserConfig(
        stremio_auth_key="test_auth_key_123",
        tmdb_api_key="test_tmdb_key",
        mdblist_api_key="test_mdblist_key",
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
    """Sample Stremio library data"""
    return {
        "items": [
            {
                "_id": "tt0137523",
                "name": "Fight Club",
                "type": "movie",
                "loved": True,
                "state": {
                    "watched": True,
                    "lastWatched": "2024-01-15T10:30:00Z"
                }
            },
            {
                "_id": "tt0903747",
                "name": "Breaking Bad",
                "type": "series",
                "loved": True,
                "state": {
                    "watched": True,
                    "lastWatched": "2024-01-10T15:20:00Z"
                }
            },
            {
                "_id": "tt0468569",
                "name": "The Dark Knight",
                "type": "movie",
                "state": {
                    "watched": True,
                    "lastWatched": "2024-01-05T20:00:00Z"
                }
            }
        ]
    }
