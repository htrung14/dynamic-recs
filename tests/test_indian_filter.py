"""
Phase 1 tests: exclude_indian filter + cache-key config fingerprint.
"""
import pytest
from unittest.mock import AsyncMock

from app.models.config import UserConfig
from app.services.recommendations import RecommendationEngine


def _config(**overrides) -> UserConfig:
    base = dict(
        stremio_auth_key="SXFxRURKV2lNVXVjemtuaU1RYlZFaENXREhUTUVKeGY=",
        tmdb_api_key="9a3b6df7b9285e1b338a8ca4b2970365",
        num_rows=5,
        min_rating=6.0,
        use_loved_items=True,
        include_movies=True,
        include_series=True,
        exclude_anime=True,
        exclude_indian=True,
    )
    base.update(overrides)
    return UserConfig(**base)


# --- detector -------------------------------------------------------------

@pytest.mark.parametrize("lang", ["hi", "ta", "te", "ml", "kn", "bn", "pa", "mr"])
def test_is_indian_true_for_indian_languages(lang):
    engine = RecommendationEngine(_config())
    assert engine._is_indian({"original_language": lang}) is True


def test_is_indian_true_for_in_origin_country():
    engine = RecommendationEngine(_config())
    # English-language item produced in India still flagged
    assert engine._is_indian({"original_language": "en", "origin_country": ["IN"]}) is True


def test_is_indian_false_for_western():
    engine = RecommendationEngine(_config())
    assert engine._is_indian({"original_language": "en", "origin_country": ["US"]}) is False


def test_is_indian_fails_open_when_language_missing():
    engine = RecommendationEngine(_config())
    # No language and no origin -> not flagged (do not over-filter)
    assert engine._is_indian({}) is False


# --- gate behavior --------------------------------------------------------

@pytest.mark.asyncio
async def test_score_and_rank_drops_indian_when_enabled():
    engine = RecommendationEngine(_config(exclude_indian=True))
    engine._build_taste_profile = AsyncMock(
        return_value={"genre_weights": {}, "top_genres": [], "top_keywords": []}
    )
    items = [
        {"id": 1, "original_language": "en", "vote_average": 8.0,
         "merged_rating": 8.0, "external_ids": {"imdb_id": "tt1"}},
        {"id": 2, "original_language": "hi", "vote_average": 8.0,
         "merged_rating": 8.0, "external_ids": {"imdb_id": "tt2"}},
    ]
    ranked = await engine.score_and_rank(items, watched=[])
    ids = {item["id"] for item in ranked}
    assert ids == {1}


@pytest.mark.asyncio
async def test_score_and_rank_keeps_indian_when_disabled():
    engine = RecommendationEngine(_config(exclude_indian=False))
    engine._build_taste_profile = AsyncMock(
        return_value={"genre_weights": {}, "top_genres": [], "top_keywords": []}
    )
    items = [
        {"id": 1, "original_language": "en", "vote_average": 8.0,
         "merged_rating": 8.0, "external_ids": {"imdb_id": "tt1"}},
        {"id": 2, "original_language": "hi", "vote_average": 8.0,
         "merged_rating": 8.0, "external_ids": {"imdb_id": "tt2"}},
    ]
    ranked = await engine.score_and_rank(items, watched=[])
    ids = {item["id"] for item in ranked}
    assert ids == {1, 2}


# --- cache fingerprint ----------------------------------------------------

def test_cache_fingerprint_stable_for_identical_config():
    assert _config().cache_fingerprint() == _config().cache_fingerprint()


@pytest.mark.parametrize("field,value", [
    ("exclude_indian", False),
    ("exclude_anime", False),
    ("min_rating", 7.5),
    ("include_movies", False),
    ("include_series", False),
])
def test_cache_fingerprint_changes_with_output_fields(field, value):
    assert _config().cache_fingerprint() != _config(**{field: value}).cache_fingerprint()


def test_cache_fingerprint_ignores_non_output_fields():
    # loved token and num_rows do not change the ranked recs list
    a = _config().cache_fingerprint()
    b = _config(stremio_loved_token="different_token", num_rows=12).cache_fingerprint()
    assert a == b


# --- taste fingerprint ----------------------------------------------------

def test_taste_fingerprint_changes_with_exclude_indian():
    assert _config().taste_fingerprint() != _config(exclude_indian=False).taste_fingerprint()


def test_taste_fingerprint_stable_across_unrelated_fields():
    # taste sample only depends on exclude_indian; min_rating/anime do not filter it
    a = _config().taste_fingerprint()
    b = _config(min_rating=9.0, exclude_anime=False).taste_fingerprint()
    assert a == b
