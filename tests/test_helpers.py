"""
Tests for helper utilities
"""
import pytest
from app.utils.helpers import (
    deduplicate_recommendations,
    score_by_frequency,
    merge_ratings,
    sanitize_title
)


def test_deduplicate_recommendations():
    """Test deduplication of recommendation items"""
    items = [
        {"id": "tt1234", "name": "Movie 1"},
        {"id": "tt5678", "name": "Movie 2"},
        {"id": "tt1234", "name": "Movie 1 Duplicate"},
        {"id": "tt9999", "name": "Movie 3"},
        {"id": "tt5678", "name": "Movie 2 Duplicate"},
    ]
    
    result = deduplicate_recommendations(items, key="id")
    
    assert len(result) == 3
    assert result[0]["id"] == "tt1234"
    assert result[1]["id"] == "tt5678"
    assert result[2]["id"] == "tt9999"


def test_deduplicate_empty_list():
    """Test deduplication with empty list"""
    result = deduplicate_recommendations([])
    assert result == []


def test_score_by_frequency():
    """Test frequency scoring"""
    items = ["tt1", "tt2", "tt1", "tt3", "tt1", "tt2"]
    
    scores = score_by_frequency(items)
    
    assert scores["tt1"] == 1.0  # Most frequent (3 times)
    assert scores["tt2"] == pytest.approx(0.666, rel=0.01)  # 2 times
    assert scores["tt3"] == pytest.approx(0.333, rel=0.01)  # 1 time


def test_score_by_frequency_empty():
    """Test frequency scoring with empty list"""
    scores = score_by_frequency([])
    assert scores == {}


def test_score_by_frequency_custom_max():
    """Test frequency scoring with custom max score"""
    items = ["a", "b", "a"]
    
    scores = score_by_frequency(items, max_score=10.0)
    
    assert scores["a"] == 10.0
    assert scores["b"] == 5.0


def test_merge_ratings_all_sources():
    """Test merging ratings from all sources"""
    rating = merge_ratings(
        imdb_rating=8.5,
        tmdb_rating=8.0,
        mdblist_rating=8.8
    )
    
    # Weighted average: 0.4*8.5 + 0.3*8.0 + 0.3*8.8
    expected = (0.4 * 8.5 + 0.3 * 8.0 + 0.3 * 8.8)
    assert rating == pytest.approx(expected, rel=0.01)


def test_merge_ratings_partial_sources():
    """Test merging ratings with missing sources"""
    rating = merge_ratings(
        imdb_rating=8.5,
        tmdb_rating=8.0,
        mdblist_rating=0.0
    )
    
    # Should only use imdb and tmdb
    expected = (0.4 * 8.5 + 0.3 * 8.0) / 0.7
    assert rating == pytest.approx(expected, rel=0.01)


def test_merge_ratings_no_sources():
    """Test merging ratings with no sources"""
    rating = merge_ratings()
    assert rating == 0.0


def test_sanitize_title():
    """Test title sanitization"""
    assert sanitize_title("  Fight Club  ") == "Fight Club"
    assert sanitize_title("") == ""
    assert sanitize_title("   ") == ""
    
    # Test length limit
    long_title = "A" * 300
    result = sanitize_title(long_title)
    assert len(result) == 200


def test_sanitize_title_special_characters():
    """Test sanitization preserves special characters"""
    title = "Movie: The Beginning (2024)"
    result = sanitize_title(title)
    assert result == title
