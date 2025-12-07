"""
Tests for background task manager
"""
import pytest
import asyncio
from app.services.background import BackgroundTaskManager, get_task_manager
from app.models.config import UserConfig


@pytest.fixture
def sample_config():
    """Sample user configuration for testing"""
    return UserConfig(
        stremio_auth_key="test_auth_key_123",
        tmdb_api_key="test_tmdb_key",
        mdblist_api_key="test_mdblist_key",
        num_rows=5,
        min_rating=6.0,
        use_loved_items=True,
        include_movies=True,
        include_series=True,
    )


def test_task_manager_singleton():
    """Test that get_task_manager returns singleton instance"""
    manager1 = get_task_manager()
    manager2 = get_task_manager()
    
    assert manager1 is manager2


def test_task_manager_init():
    """Test BackgroundTaskManager initialization"""
    manager = BackgroundTaskManager()
    
    assert manager.active_configs == set()
    assert manager.task is None
    assert manager.running is False


def test_register_config(sample_config):
    """Test registering a config for background warming"""
    manager = BackgroundTaskManager()
    
    # Register first time
    manager.register_config(sample_config)
    assert sample_config.stremio_auth_key in manager.active_configs
    assert len(manager.active_configs) == 1
    
    # Register same config again (should not duplicate)
    manager.register_config(sample_config)
    assert len(manager.active_configs) == 1


def test_register_multiple_configs():
    """Test registering multiple different configs"""
    manager = BackgroundTaskManager()
    
    config1 = UserConfig(
        stremio_auth_key="key1",
        tmdb_api_key="tmdb1",
        mdblist_api_key="mdb1",
        num_rows=5,
        min_rating=6.0,
        use_loved_items=True,
        include_movies=True,
        include_series=True,
    )
    
    config2 = UserConfig(
        stremio_auth_key="key2",
        tmdb_api_key="tmdb2",
        mdblist_api_key="mdb2",
        num_rows=5,
        min_rating=6.0,
        use_loved_items=True,
        include_movies=True,
        include_series=True,
    )
    
    manager.register_config(config1)
    manager.register_config(config2)
    
    assert len(manager.active_configs) == 2
    assert "key1" in manager.active_configs
    assert "key2" in manager.active_configs


@pytest.mark.asyncio
async def test_warm_cache_handles_errors(sample_config):
    """Test that warm_cache_for_config handles errors gracefully"""
    manager = BackgroundTaskManager()
    
    # Should not raise even with invalid config (test keys)
    try:
        await manager.warm_cache_for_config(sample_config)
        # If it completes without exception, that's fine
        assert True
    except Exception:
        # Should not raise exceptions to caller
        pytest.fail("warm_cache_for_config should handle errors gracefully")


@pytest.mark.asyncio
async def test_warm_all_caches_empty():
    """Test warm_all_caches with no registered configs"""
    manager = BackgroundTaskManager()
    
    # Should handle empty configs gracefully
    await manager.warm_all_caches()
    assert len(manager.active_configs) == 0


@pytest.mark.asyncio
async def test_task_lifecycle():
    """Test starting and stopping background task"""
    manager = BackgroundTaskManager()
    
    # Start task with very short interval for testing
    manager.start(interval_hours=0.001)  # ~3.6 seconds
    
    # Give it a moment to start
    await asyncio.sleep(0.1)
    
    assert manager.task is not None
    assert manager.running is True
    assert not manager.task.done()
    
    # Stop task
    await manager.stop()
    
    assert manager.running is False
    # Task should be cancelled or done
    assert manager.task.done()


@pytest.mark.asyncio
async def test_task_restart():
    """Test that task can be restarted after stopping"""
    manager = BackgroundTaskManager()
    
    # Start and stop
    manager.start(interval_hours=0.001)
    await asyncio.sleep(0.1)
    await manager.stop()
    
    assert manager.task is not None
    assert manager.task.done()
    
    # Restart
    manager.start(interval_hours=0.001)
    await asyncio.sleep(0.1)
    
    assert manager.task is not None
    assert manager.running is True
    assert not manager.task.done()
    
    # Cleanup
    await manager.stop()


@pytest.mark.asyncio
async def test_background_loop_cancellation():
    """Test that background loop handles cancellation"""
    manager = BackgroundTaskManager()
    
    manager.start(interval_hours=24)  # Long interval
    await asyncio.sleep(0.1)
    
    assert manager.task is not None
    
    # Cancel the task
    manager.task.cancel()
    
    try:
        await manager.task
    except asyncio.CancelledError:
        # Expected
        pass
    
    assert manager.task.done()
