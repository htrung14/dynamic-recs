"""
Tests for Stremio client
"""
import pytest
from app.services.stremio import StremioClient


def test_extract_loved_items(sample_stremio_library):
    """Test extraction of loved items from library"""
    client = StremioClient()
    
    # Note: datastoreGet API doesn't include loved/favorite info
    # This would require a different API endpoint
    loved = client.extract_loved_items(sample_stremio_library)
    
    assert len(loved) == 0  # Currently not supported


def test_extract_loved_items_empty():
    """Test extraction with no loved items"""
    client = StremioClient()
    
    library = {
        "result": [
            ["tt1234567", 1704484800000]
        ]
    }
    
    loved = client.extract_loved_items(library)
    assert len(loved) == 0


def test_extract_watched_items(sample_stremio_library):
    """Test extraction of watched items"""
    client = StremioClient()
    
    watched = client.extract_watched_items(sample_stremio_library)
    
    # Should extract only IMDB IDs (tt* format), not trakt IDs
    assert len(watched) == 3
    assert "tt0137523" in watched
    assert "tt0903747" in watched
    assert "tt0468569" in watched
    assert "trakt:123456" not in watched


def test_extract_recently_watched(sample_stremio_library):
    """Test extraction of recently watched items in order"""
    client = StremioClient()
    
    recent = client.extract_recently_watched(sample_stremio_library, limit=10)
    
    # Should be ordered by timestamp (most recent first)
    assert len(recent) == 3
    assert recent[0] == "tt0137523"  # Highest timestamp
    assert recent[1] == "tt0903747"  # Middle timestamp  
    assert recent[2] == "tt0468569"  # Lowest timestamp


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
    """Test that non-IMDB IDs are filtered out"""
    client = StremioClient()
    
    library = {
        "result": [
            ["tt1234567", 1704484800000],
            ["trakt:12345", 1704484800000],
            ["yt:abcdefg", 1704484800000]
        ]
    }
    
    watched = client.extract_watched_items(library)
    
    assert len(watched) == 1
    assert watched[0] == "tt1234567"
