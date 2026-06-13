"""
Tests for Phase 2b ranking behavior changes:
  1. _is_anime AND logic (animated + Japanese, not OR)
  2. _taste_affinity denominator (matching genres only)
"""
import pytest
from app.models.config import UserConfig
from app.services.recommendations import RecommendationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(**overrides) -> RecommendationEngine:
    """Build a minimal engine for unit-testing static/instance helpers."""
    defaults = dict(
        stremio_auth_key="a]b" * 14,  # 42-char pad
        tmdb_api_key="fake_tmdb_key",
    )
    defaults.update(overrides)
    return RecommendationEngine(UserConfig(**defaults))


# ===================================================================
# CHANGE 1 — _is_anime must be AND: animation-genre AND Japanese
# ===================================================================

class TestIsAnime:
    """_is_anime should only flag content that is BOTH animated AND Japanese."""

    def test_pixar_not_anime(self):
        """Western animation (Pixar-like) must NOT be flagged."""
        item = {
            "genre_ids": [16],
            "original_language": "en",
            "origin_country": ["US"],
        }
        assert _engine()._is_anime(item) is False

    def test_live_action_japanese_not_anime(self):
        """Live-action Japanese film must NOT be flagged."""
        item = {
            "genre_ids": [18],
            "original_language": "ja",
            "origin_country": ["JP"],
        }
        assert _engine()._is_anime(item) is False

    def test_anime_via_origin_country(self):
        """Animated + JP origin → anime."""
        item = {"genre_ids": [16], "origin_country": ["JP"]}
        assert _engine()._is_anime(item) is True

    def test_anime_via_language(self):
        """Animated + ja language → anime."""
        item = {"genre_ids": [16], "original_language": "ja"}
        assert _engine()._is_anime(item) is True

    def test_plain_action_not_anime(self):
        """Non-animated, non-Japanese → not anime."""
        item = {"genre_ids": [28], "original_language": "en"}
        assert _engine()._is_anime(item) is False

    def test_genres_list_form(self):
        """genres list (instead of genre_ids) + ja language → anime."""
        item = {"genres": [{"id": 16}], "original_language": "ja"}
        assert _engine()._is_anime(item) is True


# ===================================================================
# CHANGE 2 — _taste_affinity averages over MATCHING genres only
# ===================================================================

class TestTasteAffinity:
    """_taste_affinity divides by matched-genre count, not total."""

    def test_partial_match(self):
        """Two of four genres match → average of matched weights."""
        result = RecommendationEngine._taste_affinity(
            [28, 12, 35, 80], {28: 1.0, 12: 0.1}
        )
        assert result == pytest.approx(0.55)

    def test_single_exact_match(self):
        """One genre, one weight → that weight."""
        result = RecommendationEngine._taste_affinity([28], {28: 1.0, 12: 0.1})
        assert result == pytest.approx(1.0)

    def test_empty_genre_ids(self):
        """No genres → 0."""
        result = RecommendationEngine._taste_affinity([], {28: 1.0})
        assert result == pytest.approx(0.0)

    def test_no_matching_genres(self):
        """Genre not in weights → 0."""
        result = RecommendationEngine._taste_affinity([99], {28: 1.0})
        assert result == pytest.approx(0.0)
