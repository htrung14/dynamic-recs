"""
Tests for Phase 4 — true per-seed "Because you watched X" rows.

Verifies that generate_recommendations_for_seed resolves the correct seed
and returns ranked recs, with cache bypassed for deterministic testing.
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.models.config import UserConfig
from app.services.recommendations import RecommendationEngine


def _engine(**overrides) -> RecommendationEngine:
    defaults = dict(
        stremio_auth_key="a]b" * 14,
        tmdb_api_key="fake_tmdb_key",
    )
    defaults.update(overrides)
    return RecommendationEngine(UserConfig(**defaults))


@pytest.mark.asyncio
async def test_per_seed_resolves_correct_seed(monkeypatch):
    """generate_recommendations_for_seed resolves the seed at seed_index."""
    engine = _engine()

    # Bypass cache: just await and return build_fn()
    async def passthrough(key, build_fn, **kw):
        return await build_fn()
    monkeypatch.setattr(engine.cache, "stale_while_revalidate", passthrough)

    # Stub auth
    monkeypatch.setattr(engine.stremio, "resolve_auth_key", AsyncMock(return_value="auth"))

    # Stub seed list — two seeds
    monkeypatch.setattr(engine, "get_seed_items", AsyncMock(return_value=["ttAAA", "ttBBB"]))

    # Track which imdb_id is passed to find_by_imdb_id
    call_log = {}
    original_find = engine.tmdb.find_by_imdb_id

    async def tracking_find(imdb_id):
        call_log["imdb_id"] = imdb_id
        return {"id": 42, "tmdb_id": 42, "media_type": "movie"}
    monkeypatch.setattr(engine.tmdb, "find_by_imdb_id", tracking_find)

    # Stub recs generation
    monkeypatch.setattr(engine, "_recs_for_one_seed", AsyncMock(return_value=[
        {"id": 1, "media_type": "movie", "vote_average": 8.0, "external_ids": {"imdb_id": "tt1"}},
    ]))

    # Stub watched / enrichment / taste profile
    monkeypatch.setattr(engine, "get_watched_items", AsyncMock(return_value=[]))
    monkeypatch.setattr(engine, "_attach_external_ids", AsyncMock(side_effect=lambda x: x))
    monkeypatch.setattr(engine, "_build_taste_profile", AsyncMock(
        return_value={"genre_weights": {}, "top_genres": [], "top_keywords": []}
    ))

    result = await engine.generate_recommendations_for_seed(media_type="movie", seed_index=1)

    # Must have resolved the SECOND seed
    assert call_log["imdb_id"] == "ttBBB"
    # Must return ranked recs
    assert len(result) > 0
    assert result[0]["id"] == 1


@pytest.mark.asyncio
async def test_per_seed_out_of_range_returns_empty(monkeypatch):
    """seed_index >= len(seeds) returns [] without calling TMDB."""
    engine = _engine()

    async def passthrough(key, build_fn, **kw):
        return await build_fn()
    monkeypatch.setattr(engine.cache, "stale_while_revalidate", passthrough)
    monkeypatch.setattr(engine.stremio, "resolve_auth_key", AsyncMock(return_value="auth"))
    monkeypatch.setattr(engine, "get_seed_items", AsyncMock(return_value=["ttAAA"]))

    find_called = {"yes": False}

    async def tracking_find(imdb_id):
        find_called["yes"] = True
        return {"id": 1, "tmdb_id": 1, "media_type": "movie"}
    monkeypatch.setattr(engine.tmdb, "find_by_imdb_id", tracking_find)

    result = await engine.generate_recommendations_for_seed(media_type="movie", seed_index=5)

    assert result == []
    assert find_called["yes"] is False


@pytest.mark.asyncio
async def test_per_seed_valid_index_returns_recs(monkeypatch):
    """Valid seed_index returns non-empty ranked recs."""
    engine = _engine()

    async def passthrough(key, build_fn, **kw):
        return await build_fn()
    monkeypatch.setattr(engine.cache, "stale_while_revalidate", passthrough)
    monkeypatch.setattr(engine.stremio, "resolve_auth_key", AsyncMock(return_value="auth"))
    monkeypatch.setattr(engine, "get_seed_items", AsyncMock(return_value=["ttAAA", "ttBBB"]))
    monkeypatch.setattr(engine.tmdb, "find_by_imdb_id", AsyncMock(
        return_value={"id": 42, "tmdb_id": 42, "media_type": "movie"}
    ))
    monkeypatch.setattr(engine, "_recs_for_one_seed", AsyncMock(return_value=[
        {"id": 1, "media_type": "movie", "vote_average": 8.0, "external_ids": {"imdb_id": "tt1"}},
        {"id": 2, "media_type": "movie", "vote_average": 7.5, "external_ids": {"imdb_id": "tt2"}},
    ]))
    monkeypatch.setattr(engine, "get_watched_items", AsyncMock(return_value=[]))
    monkeypatch.setattr(engine, "_attach_external_ids", AsyncMock(side_effect=lambda x: x))
    monkeypatch.setattr(engine, "_build_taste_profile", AsyncMock(
        return_value={"genre_weights": {}, "top_genres": [], "top_keywords": []}
    ))

    result = await engine.generate_recommendations_for_seed(media_type="movie", seed_index=0)

    assert len(result) == 2
    assert result[0]["score"] >= result[1]["score"]
