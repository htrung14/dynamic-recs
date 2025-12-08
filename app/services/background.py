"""
Background Tasks
Periodic cache warming and maintenance tasks
"""
import asyncio
import logging
from typing import Set, Optional
from datetime import datetime
from app.services.recommendations import RecommendationEngine
from app.services.stremio import StremioClient
from app.models.config import UserConfig
from app.core.config import settings

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Manages background cache warming and maintenance tasks"""
    
    def __init__(self):
        self.active_configs: Set[str] = set()
        self.config_cache: dict = {}  # Store full configs for background tasks
        self.task: Optional[asyncio.Task] = None
        self.running = False
    
    def register_config(self, config: UserConfig):
        """Register a user config for background cache warming"""
        config_key = config.stremio_auth_key or config.stremio_username_enc or "unknown"
        if config_key not in self.active_configs:
            self.active_configs.add(config_key)
            self.config_cache[config_key] = config
            logger.info(f"Registered config for background warming: {config_key[:10]}...")
    
    async def warm_cache_for_config(self, config: UserConfig):
        """
        Warm cache for a single user configuration
        
        Fetches fresh library history, filters by 50% progress, loved items, then generates recommendations
        """
        auth_key_short = (config.stremio_auth_key or config.stremio_username_enc or "unknown")[:10]
        logger.info(f"[Background] Starting cache warming for {auth_key_short}...")
        try:
            engine = RecommendationEngine(config)

            # Prime SWR caches for seeds and watched to avoid re-pulling libraries during warm cycles
            await engine.get_seed_items()
            await engine.get_watched_items()
            
            # Warm cache for movies if enabled
            if config.include_movies:
                logger.debug(f"[Background] Warming movie recommendations for {auth_key_short}...")
                await engine.generate_recommendations(media_type="movie")
            
            # Warm cache for series if enabled
            if config.include_series:
                logger.debug(f"[Background] Warming series recommendations for {auth_key_short}...")
                await engine.generate_recommendations(media_type="series")
            
            await engine.close()
            logger.info(f"[Background] Cache warming complete for {auth_key_short}")
            
        except Exception as e:
            logger.error(f"[Background] Error warming cache for config: {e}", exc_info=True)
    
    async def warm_all_caches(self):
        """Warm caches for all registered configurations"""
        if not self.active_configs:
            logger.debug("[Background] No configs registered for cache warming")
            return
        
        logger.info(f"[Background] Starting cache warming cycle for {len(self.active_configs)} configs")
        
        # Warm all registered configs in parallel
        tasks = []
        for config_key in self.active_configs:
            config = self.config_cache.get(config_key)
            if config:
                tasks.append(self.warm_cache_for_config(config))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            errors = [r for r in results if isinstance(r, Exception)]
            if errors:
                logger.warning(f"[Background] Cache warming cycle completed with {len(errors)} errors")
            else:
                logger.info(f"[Background] Cache warming cycle complete ({len(self.active_configs)} configs refreshed)")
        else:
            logger.info("[Background] No configs found to warm")
    
    async def background_loop(self, interval_hours: float = 3):
        """
        Background loop that warms caches periodically
        
        Args:
            interval_hours: Hours between cache warming cycles
        """
        self.running = True
        interval_seconds = interval_hours * 3600
        
        logger.info(f"[Background] Cache warming loop started (interval: {interval_hours}h)")
        
        while self.running:
            try:
                await asyncio.sleep(interval_seconds)
                logger.info(f"[Background] Triggering scheduled cache warming cycle")
                await self.warm_all_caches()
            except asyncio.CancelledError:
                logger.info("[Background] Cache warming cancelled")
                break
            except Exception as e:
                logger.error(f"[Background] Error in background loop: {e}", exc_info=True)
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
