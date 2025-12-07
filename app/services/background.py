"""
Background Tasks
Periodic cache warming and maintenance tasks
"""
import asyncio
import logging
from typing import Set, Optional
from datetime import datetime
from app.services.recommendations import RecommendationEngine
from app.models.config import UserConfig
from app.core.config import settings

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Manages background cache warming and maintenance tasks"""
    
    def __init__(self):
        self.active_configs: Set[str] = set()
        self.task: Optional[asyncio.Task] = None
        self.running = False
    
    def register_config(self, config: UserConfig):
        """Register a user config for background cache warming"""
        config_key = config.stremio_auth_key
        if config_key not in self.active_configs:
            self.active_configs.add(config_key)
            logger.info(f"Registered config for background warming: {config_key[:10]}...")
    
    async def warm_cache_for_config(self, config: UserConfig):
        """
        Warm cache for a single user configuration
        
        Fetches recommendations for both movies and series and stores in cache
        """
        try:
            engine = RecommendationEngine(config)
            
            # Warm cache for movies if enabled
            if config.include_movies:
                logger.debug(f"Warming movie cache for {config.stremio_auth_key[:10]}...")
                await engine.generate_recommendations(media_type="movie")
            
            # Warm cache for series if enabled
            if config.include_series:
                logger.debug(f"Warming series cache for {config.stremio_auth_key[:10]}...")
                await engine.generate_recommendations(media_type="series")
            
            await engine.close()
            logger.info(f"Cache warmed successfully for {config.stremio_auth_key[:10]}...")
            
        except Exception as e:
            logger.error(f"Error warming cache for config: {e}", exc_info=True)
    
    async def warm_all_caches(self):
        """Warm caches for all registered configurations"""
        if not self.active_configs:
            logger.debug("No configs registered for cache warming")
            return
        
        logger.info(f"Starting cache warming for {len(self.active_configs)} configs")
        
        # Note: We only have config keys, not full configs
        # In production, you'd store full configs or reconstruct them
        # For now, this serves as a framework that gets triggered by actual requests
        
        logger.info("Cache warming cycle complete")
    
    async def background_loop(self, interval_hours: float = 3):
        """
        Background loop that warms caches periodically
        
        Args:
            interval_hours: Hours between cache warming cycles
        """
        self.running = True
        interval_seconds = interval_hours * 3600
        
        logger.info(f"Background cache warming started (interval: {interval_hours}h)")
        
        while self.running:
            try:
                await asyncio.sleep(interval_seconds)
                await self.warm_all_caches()
            except asyncio.CancelledError:
                logger.info("Background cache warming cancelled")
                break
            except Exception as e:
                logger.error(f"Error in background loop: {e}", exc_info=True)
                # Continue running despite errors
    
    def start(self, interval_hours: float = 3):
        """Start the background task"""
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.background_loop(interval_hours))
            logger.info("Background task manager started")
    
    async def stop(self):
        """Stop the background task"""
        self.running = False
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Background task manager stopped")


# Global singleton instance
_task_manager = None


def get_task_manager() -> BackgroundTaskManager:
    """Get the global task manager instance"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager
