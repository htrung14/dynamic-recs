"""
Health Check & Admin Endpoints
"""
import asyncio
from fastapi import APIRouter, Query
from app.core.config import settings
from app.services.cache import CacheManager
from app.services.background import get_task_manager

router = APIRouter()


@router.get("/health")
async def health_check(include_swr: bool = Query(False, description="Include SWR cache metrics")):
    """Health check endpoint for monitoring"""
    payload = {
        "status": "healthy",
        "version": "1.0.0",
        "base_url": settings.BASE_URL,
    }

    if include_swr:
        import json
        cache = CacheManager()
        payload["swr_metrics"] = json.dumps(cache.get_metrics_snapshot())

    return payload


@router.post("/refresh")
async def refresh_all():
    """Trigger a cache refresh for all registered users (runs in background)."""
    manager = get_task_manager()
    count = len(manager.active_configs)
    if count == 0:
        return {"status": "no_configs", "message": "No users registered yet. Configs are registered on first catalog request."}
    asyncio.create_task(manager.warm_all_caches())
    return {"status": "started", "configs": count}
