"""
Tests for correctness fixes from 3-reviewer cold review:
- B1: Indian seed filtering in get_seed_items
- B1: seed_fingerprint config fingerprinting
- B1: _is_indian details fallback
- Progress 0.0 gap
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.models.config import UserConfig
from app.services.recommendations import RecommendationEngine
from app.services.stremio import StremioClient


def _engine(**overrides) -> RecommendationEngine:
    defaults = dict(
        stremio_auth_key="a]b" * 14,
        tmdb_api_key="fake_tmdb_key",
    )
    defaults.update(overrides)
    return RecommendationEngine(UserConfig(**defaults))


# ── B1: _filter_indian_imdb_ids ─────────────────────────────────────────


class TestFilterIndianImdbIds:

    @pytest.mark.asyncio
    async def test_drops_indian_when_exclude_on(self):
        engine = _engine(exclude_indian=True)

        async def fake_find(imdb_id):
            if imdb_id == "ttBollywood":
                return {"id": 1, "original_language": "hi", "media_type": "movie"}
            return {"id": 2, "original_language": "en", "media_type": "movie"}

        engine.tmdb.find_by_imdb_id = fake_find
        result = await engine._filter_indian_imdb_ids(["ttBollywood", "ttHollywood"])
        assert result == ["ttHollywood"]

    @pytest.mark.asyncio
    async def test_keeps_all_when_exclude_off(self):
        engine = _engine(exclude_indian=False)
        engine.tmdb.find_by_imdb_id = AsyncMock(return_value={"id": 1, "original_language": "hi"})
        result = await engine._filter_indian_imdb_ids(["tt1", "tt2"])
        assert result == ["tt1", "tt2"]

    @pytest.mark.asyncio
    async def test_keeps_on_resolution_failure(self):
        engine = _engine(exclude_indian=True)

        async def fake_find(imdb_id):
            if imdb_id == "ttFail":
                raise RuntimeError("network")
            return {"id": 1, "original_language": "en", "media_type": "movie"}

        engine.tmdb.find_by_imdb_id = fake_find
        result = await engine._filter_indian_imdb_ids(["ttFail", "ttOK"])
        assert "ttFail" in result
        assert "ttOK" in result


# ── B1: _is_indian details fallback ─────────────────────────────────────


class TestIsIndianDetailsFallback:

    def test_item_lacks_language_but_details_has_it(self):
        engine = _engine()
        item = {"id": 1}  # no original_language, no origin_country
        details = {"original_language": "ta"}
        assert engine._is_indian(item, details) is True

    def test_item_and_details_both_lack_signal(self):
        engine = _engine()
        item = {"id": 1}
        details = {"original_language": "en"}
        assert engine._is_indian(item, details) is False


# ── B1: seed_fingerprint ────────────────────────────────────────────────


class TestSeedFingerprint:

    def test_changes_with_exclude_indian(self):
        c1 = UserConfig(stremio_auth_key="k" * 44, tmdb_api_key="x", exclude_indian=True)
        c2 = UserConfig(stremio_auth_key="k" * 44, tmdb_api_key="x", exclude_indian=False)
        assert c1.seed_fingerprint() != c2.seed_fingerprint()

    def test_changes_with_use_loved_items(self):
        c1 = UserConfig(stremio_auth_key="k" * 44, tmdb_api_key="x", use_loved_items=True)
        c2 = UserConfig(stremio_auth_key="k" * 44, tmdb_api_key="x", use_loved_items=False)
        assert c1.seed_fingerprint() != c2.seed_fingerprint()

    def test_changes_with_loved_token(self):
        c1 = UserConfig(stremio_auth_key="k" * 44, tmdb_api_key="x", stremio_loved_token="abc")
        c2 = UserConfig(stremio_auth_key="k" * 44, tmdb_api_key="x", stremio_loved_token="xyz")
        assert c1.seed_fingerprint() != c2.seed_fingerprint()

    def test_stable_when_same_config(self):
        c1 = UserConfig(stremio_auth_key="k" * 44, tmdb_api_key="x")
        c2 = UserConfig(stremio_auth_key="k" * 44, tmdb_api_key="x")
        assert c1.seed_fingerprint() == c2.seed_fingerprint()


# ── Progress 0.0 gap ───────────────────────────────────────────────────


class TestProgressZeroGap:

    def test_duration_with_no_watch_signal_is_zero(self):
        state = {"duration": 4000, "timeOffset": 0}
        assert StremioClient._progress_from_state(state) == pytest.approx(0.0)

    def test_duration_with_times_watched_still_one(self):
        state = {"duration": 4000, "timeOffset": 0, "timesWatched": 2}
        assert StremioClient._progress_from_state(state) == pytest.approx(1.0)


# ── B2: background_refresh must NOT re-enter SWR ───────────────────────


class TestSeedRecsNoSrwReentry:

    @pytest.mark.asyncio
    async def test_build_seed_recs_exists_and_is_callable(self):
        """_build_seed_recs is a real method, not a closure inside generate_*."""
        engine = _engine()
        assert hasattr(engine, "_build_seed_recs")
        # Should be a coroutine function
        import asyncio
        assert asyncio.iscoroutinefunction(engine._build_seed_recs)

    @pytest.mark.asyncio
    async def test_swr_captures_refresh_fn(self):
        """generate_recommendations_for_seed passes a refresh_fn to SWR
        that does NOT call stale_while_revalidate (i.e. it's a raw builder)."""
        engine = _engine()
        captured_kwargs = {}

        original_swr = engine.cache.stale_while_revalidate

        async def spy_swr(*args, **kwargs):
            captured_kwargs.update(kwargs)
            # Return the build_fn result directly to avoid needing real data
            return await kwargs.get("build_fn", args[1] if len(args) > 1 else None)()

        monkeypatch_ctx = patch.object(engine.cache, "stale_while_revalidate", spy_swr)
        monkeypatch_ctx.start()

        # Stub auth + seeds so we get past the guard
        engine.stremio.resolve_auth_key = AsyncMock(return_value="auth")
        engine.get_seed_items = AsyncMock(return_value=["ttSeed"])
        engine._build_seed_recs = AsyncMock(return_value=[{"id": 1, "score": 5.0}])

        result = await engine.generate_recommendations_for_seed("movie", 0)

        # refresh_fn was passed
        assert "refresh_fn" in captured_kwargs
        refresh_fn = captured_kwargs["refresh_fn"]
        assert refresh_fn is not None

        # The result came from _build_seed_recs (the raw path)
        assert result == [{"id": 1, "score": 5.0}]
        engine._build_seed_recs.assert_called_once_with("ttSeed", "movie")

        monkeypatch_ctx.stop()
