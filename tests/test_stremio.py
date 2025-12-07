"""
Tests for Stremio client
"""
import pytest
from app.services.stremio import StremioClient


def test_extract_loved_items(sample_stremio_library):
    """Test extraction of loved items from library"""
    client = StremioClient()
    
    loved = client.extract_loved_items(sample_stremio_library)
    
    assert len(loved) == 2
    assert "tt0137523" in loved  # Fight Club
    assert "tt0903747" in loved  # Breaking Bad


def test_extract_loved_items_empty():
    """Test extraction with no loved items"""
    client = StremioClient()
    
    library = {
        "items": [
            {"_id": "tt1234567", "state": {"watched": True}}
        ]
    }
    
    loved = client.extract_loved_items(library)
    assert len(loved) == 0


def test_extract_watched_items(sample_stremio_library):
    """Test extraction of watched items"""
    client = StremioClient()
    
    watched = client.extract_watched_items(sample_stremio_library)
    
    assert len(watched) == 3
    assert "tt0137523" in watched
    assert "tt0903747" in watched
    assert "tt0468569" in watched


def test_extract_recently_watched(sample_stremio_library):
    """Test extraction of recently watched items in order"""
    client = StremioClient()
    
    recent = client.extract_recently_watched(sample_stremio_library, limit=10)
    
    # Should be ordered by lastWatched (most recent first)
    assert len(recent) == 3
    assert recent[0] == "tt0137523"  # 2024-01-15
    assert recent[1] == "tt0903747"  # 2024-01-10
    assert recent[2] == "tt0468569"  # 2024-01-05


def test_extract_recently_watched_with_limit(sample_stremio_library):
    """Test limit parameter for recently watched"""
    client = StremioClient()
    
    recent = client.extract_recently_watched(sample_stremio_library, limit=2)
    
    assert len(recent) == 2


def test_extract_with_invalid_library():
    """Test extraction with invalid library data"""
    client = StremioClient()
    
    # None library
    assert client.extract_loved_items(None) == []
    assert client.extract_watched_items(None) == []
    assert client.extract_recently_watched(None) == []
    
    # Empty library
    assert client.extract_loved_items({}) == []
    assert client.extract_watched_items({}) == []


def test_extract_filters_non_imdb_ids():
    """Test that only IMDB IDs (starting with tt) are extracted"""
    client = StremioClient()
    
    library = {
        "items": [
            {"_id": "tt1234567", "loved": True},
            {"_id": "tmdb:550", "loved": True},  # Should be filtered
            {"_id": "tt9999999", "loved": True},
        ]
    }
    
    loved = client.extract_loved_items(library)
    
    assert len(loved) == 2
    assert "tt1234567" in loved
    assert "tt9999999" in loved
    assert "tmdb:550" not in loved
