"""
Health Check Endpoint
"""
from fastapi import APIRouter, Query
from app.core.config import settings
from app.services.cache import CacheManager

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
