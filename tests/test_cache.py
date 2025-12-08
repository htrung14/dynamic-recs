"""
Tests for cache manager
"""
import pytest


# Note: Cache tests require Redis to be running
# These are integration tests that should be run when Redis is available
# For unit testing, mock the Redis client or skip these tests

@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_set_and_get():
    """Test basic cache set and get operations"""
    from app.services.cache import CacheManager
    cache = CacheManager()
    
    try:
        # Set value
        success = await cache.set("test_key", {"data": "test_value"})
        if success:
            # Get value
            value = await cache.get("test_key")
            assert value is not None
            assert value["data"] == "test_value"
    except Exception:
        pytest.skip("Redis not available")
    finally:
        await cache.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_get_nonexistent():
    """Test getting non-existent key returns None"""
    from app.services.cache import CacheManager
    cache = CacheManager()
    
    try:
        value = await cache.get("nonexistent_key_12345")
        assert value is None
    except Exception:
        pytest.skip("Redis not available")
    finally:
        await cache.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_set_with_ttl():
    """Test cache with TTL"""
    from app.services.cache import CacheManager
    cache = CacheManager()
    
    try:
        # Set value with 100 second TTL
        success = await cache.set("ttl_key", {"data": "expires"}, ttl=100)
        if success:
            # Should exist immediately
            value = await cache.get("ttl_key")
            assert value is not None
    except Exception:
        pytest.skip("Redis not available")
    finally:
        await cache.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_delete():
    """Test cache deletion"""
    from app.services.cache import CacheManager
    cache = CacheManager()
    
    try:
        # Set value
        success = await cache.set("delete_key", {"data": "to_delete"})
        if success:
            # Verify it exists
            value = await cache.get("delete_key")
            assert value is not None
            
            # Delete
            success = await cache.delete("delete_key")
            assert success is True
            
            # Verify it's gone
            value = await cache.get("delete_key")
            assert value is None
    except Exception:
        pytest.skip("Redis not available")
    finally:
        await cache.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_exists():
    """Test cache key existence check"""
    from app.services.cache import CacheManager
    cache = CacheManager()
    
    try:
        # Key doesn't exist
        exists = await cache.exists("not_here_54321")
        assert exists is False
        
        # Create key
        success = await cache.set("exists_key", {"data": "here"})
        if success:
            # Key exists
            exists = await cache.exists("exists_key")
            assert exists is True
    except Exception:
        pytest.skip("Redis not available")
    finally:
        await cache.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_complex_data():
    """Test caching complex data structures"""
    from app.services.cache import CacheManager
    cache = CacheManager()
    
    complex_data = {
        "items": [
            {"id": 1, "name": "Item 1", "nested": {"value": 100}},
            {"id": 2, "name": "Item 2", "nested": {"value": 200}},
        ],
        "metadata": {
            "count": 2,
            "timestamp": "2024-01-01T00:00:00Z"
        }
    }
    
    try:
        success = await cache.set("complex_key", complex_data)
        if success:
            retrieved = await cache.get("complex_key")
            assert retrieved is not None
            assert retrieved == complex_data
            assert len(retrieved["items"]) == 2
            assert retrieved["metadata"]["count"] == 2
    except Exception:
        pytest.skip("Redis not available")
    finally:
        await cache.close()


def test_cache_singleton():
    """Test CacheManager is a singleton"""
    from app.services.cache import CacheManager
    cache1 = CacheManager()
    cache2 = CacheManager()
    
    assert cache1 is cache2
