"""
Performance smoke tests (skipped by default).
Run with RUN_PERF_TESTS=1 to enable.
"""
import asyncio
import os
import time

import pytest
from httpx import AsyncClient

from app.core.app import create_app
from app.core.config import settings
from app.services.cache import CacheManager
from app.services.recommendations import RecommendationEngine
from app.utils.token import encode_config


@pytest.mark.asyncio
@pytest.mark.perf
async def test_catalog_swr_smoke(monkeypatch, sample_user_config, fake_redis):
    if not os.getenv("RUN_PERF_TESTS"):
        pytest.skip("RUN_PERF_TESTS not set")

    # Disable background loop during test
    class DummyTaskManager:
        def start(self, interval_hours: float = 3):
            return None

        async def stop(self):
            return None

    dummy_tm = DummyTaskManager()
    monkeypatch.setattr("app.core.app.get_task_manager", lambda: dummy_tm)

    # Use fake redis for cache interactions
    async def fake_get_client(self):
        return fake_redis

    monkeypatch.setattr(CacheManager, "get_client", fake_get_client, raising=False)
    cache = CacheManager()
    cache._metrics = {
        "swr_fresh_hit": 0,
        "swr_stale_served": 0,
        "swr_miss_build": 0,
        "swr_refresh_triggered": 0,
        "swr_refresh_failed": 0,
    }

    # Shorten TTL for the smoke
    monkeypatch.setattr(settings, "CACHE_TTL_CATALOG", 1)

    # Fake recommendation builder to simulate work
    call_counter = {"n": 0}

    async def fake_build(self, media_type, auth_key):
        call_counter["n"] += 1
        await asyncio.sleep(0.05)
        return [
            {
                "id": "tt0137523",
                "title": "Fight Club",
                "media_type": "movie",
                "external_ids": {"imdb_id": "tt0137523"},
                "poster_path": "/p",
                "backdrop_path": "/b",
                "overview": "desc",
                "release_date": "1999-10-15",
                "vote_average": 8.4,
            }
        ]

    monkeypatch.setattr(
        RecommendationEngine, "_build_recommendations", fake_build, raising=False
    )

    token = encode_config(sample_user_config)
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        t0 = time.perf_counter()
        resp1 = await client.get(f"/{token}/catalog/movie/dynamic_movies_0.json")
        t1 = time.perf_counter() - t0

        t0 = time.perf_counter()
        resp2 = await client.get(f"/{token}/catalog/movie/dynamic_movies_0.json")
        t2 = time.perf_counter() - t0

        # Allow fresh TTL to expire and trigger stale-while-revalidate
        await asyncio.sleep(1.1)

        t0 = time.perf_counter()
        resp3 = await client.get(f"/{token}/catalog/movie/dynamic_movies_0.json")
        t3 = time.perf_counter() - t0

        await asyncio.sleep(0.1)  # let background refresh complete

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp3.status_code == 200

    body = resp2.json()
    assert body.get("metas") and len(body["metas"]) >= 1

    # Second call should be faster due to cache hit
    assert t2 < t1

    # Third call should be fast (stale served) and trigger refresh
    metrics = cache.get_metrics_snapshot()
    assert metrics["swr_stale_served"] >= 1
    assert metrics["swr_refresh_triggered"] >= 1
    assert call_counter["n"] >= 1
    assert t3 < t1
