"""
FastAPI Application Factory
Creates and configures the FastAPI app instance
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import manifest, catalog, configure, health
from app.core.config import settings
from app.services.background import get_task_manager
import logging

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    logger.info("Starting Dynamic Recommendations Addon")
    logger.info(f"Base URL: {settings.BASE_URL}")
    
    # Start background cache warming
    task_manager = get_task_manager()
    task_manager.start(interval_hours=settings.CACHE_WARM_INTERVAL_HOURS)
    logger.info(f"Background cache warming enabled (interval: {settings.CACHE_WARM_INTERVAL_HOURS}h)")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Dynamic Recommendations Addon")
    
    # Stop background tasks
    task_manager = get_task_manager()
    await task_manager.stop()


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    
    app = FastAPI(
        title="Dynamic Recommendations Stremio Addon",
        description="Personalized movie and series recommendations based on your watch history",
        version="1.0.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Mount static files
    try:
        app.mount("/static", StaticFiles(directory="static"), name="static")
    except Exception as e:
        logger.warning(f"Could not mount static files: {e}")
    
    # Include routers
    app.include_router(health.router)
    app.include_router(configure.router)
    app.include_router(manifest.router)
    app.include_router(catalog.router)
    
    return app
