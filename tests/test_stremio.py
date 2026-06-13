"""
Tests for Stremio client

Note: extract_loved_items was removed — loved items now come from the async
fetch_loved_catalog (official loved addon), not a sync library-extraction
method.  Tests for that path live in integration, not here.
"""
import pytest
from app.services.stremio import StremioClient


def test_extract_watched_items(sample_stremio_library):
    """Test extraction of watched items"""
    client = StremioClient()
    
    # Should extract only IMDB IDs (tt* format), not trakt IDs
    watched = client.extract_watched_items(sample_stremio_library)
    
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
    assert client.extract_watched_items(None) == []
    assert client.extract_recently_watched(None) == []
    
    # Empty library
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
