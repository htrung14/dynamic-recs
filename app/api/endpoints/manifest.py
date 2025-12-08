"""
Manifest Endpoint
Returns the Stremio addon manifest with dynamic catalogs
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Path, Response
from app.models.stremio import Manifest, ManifestCatalog
from app.utils.token import decode_config
from app.services.stremio import StremioClient
from app.services.tmdb import TMDBClient

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{token}/manifest.json")
async def get_manifest(
    response: Response,
    token: str = Path(..., description="User configuration token")
):
    """
    Return addon manifest with user-specific configuration
    
    The manifest defines what catalogs this addon provides
    """
    # Add cache headers (avoid stale titles in Stremio)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Content-Type"] = "application/json"
    # Decode and validate token
    config = decode_config(token)
    if not config:
        raise HTTPException(status_code=401, detail="Invalid configuration token")
    
    # Fetch seed items for personalized catalog names
    stremio = StremioClient()
    tmdb = TMDBClient(config.tmdb_api_key)
    
    try:
        library = await stremio.fetch_library(config.stremio_auth_key)
        recent_watches = stremio.extract_recently_watched(library, limit=max(config.num_rows, 10))
    except Exception as e:
        logger.warning(f"Failed to fetch library for manifest: {e}")
        recent_watches = []

    # Loved items (for titles) if enabled
    loved_movies = []
    loved_series = []
    if config.use_loved_items:
        try:
            loved_movies = await stremio.fetch_loved_catalog("movie", token=config.stremio_loved_token)
            loved_series = await stremio.fetch_loved_catalog("series", token=config.stremio_loved_token)
        except Exception as e:
            logger.debug(f"Failed to fetch loved catalogs: {e}")
    
    # Build catalogs based on user configuration
    catalogs = []
    
    # Add movie catalogs if enabled
    if config.include_movies:
        # Prefer loved seeds first, then fall back to recent watches
        seeds_for_movies = (loved_movies or []) + ([w for w in recent_watches if w not in loved_movies] if recent_watches else [])
        if loved_movies:
            loved_preview = json.dumps(loved_movies[: config.num_rows], separators=(",", ":"))
            logger.info(f"Because you loved (movies) seeds preview: {loved_preview}")
        watched_only = [w for w in recent_watches if w not in loved_movies] if recent_watches else []
        if watched_only:
            watched_preview = json.dumps(watched_only[: config.num_rows], separators=(",", ":"))
            logger.info(f"Because you watched (movies) seeds preview: {watched_preview}")
        if seeds_for_movies:
            combined_preview = json.dumps(seeds_for_movies[: config.num_rows], separators=(",", ":"))
            logger.info(f"Movies catalog seeds (combined) preview: {combined_preview}")
        for i in range(config.num_rows):
            # Get title for this seed if available
            if i < len(seeds_for_movies):
                imdb_id = seeds_for_movies[i]
                is_loved_seed = i < len(loved_movies)
                try:
                    tmdb_data = await tmdb.find_by_imdb_id(imdb_id)
                    if tmdb_data:
                        title = tmdb_data.get("title") or tmdb_data.get("name", "")
                        prefix = "🎬 Because you loved" if is_loved_seed else "🎬 Because you watched"
                        catalog_name = f"{prefix} {title}" if title else f"{prefix}"
                    else:
                        prefix = "🎬 Because you loved" if is_loved_seed else "🎬 Recommended Movies"
                        catalog_name = f"{prefix} #{i+1}"
                except Exception as e:
                    logger.debug(f"Failed to get title for {imdb_id}: {e}")
                    prefix = "🎬 Because you loved" if is_loved_seed else "🎬 Recommended Movies"
                    catalog_name = f"{prefix} #{i+1}"
            else:
                # No seed available; default to generic row name
                prefix = "🎬 Recommended Movies"
                catalog_name = f"{prefix} #{i+1}"
            
            catalogs.append(
                ManifestCatalog(
                    type="movie",
                    id=f"dynamic_movies_{i}",
                    name=catalog_name
                )
            )
    
    # Add series catalogs if enabled
    if config.include_series:
        # Prefer loved seeds first, then fall back to recent watches
        seeds_for_series = (loved_series or []) + ([w for w in recent_watches if w not in loved_series] if recent_watches else [])
        if loved_series:
            loved_preview = json.dumps(loved_series[: config.num_rows], separators=(",", ":"))
            logger.info(f"Because you loved (series) seeds preview: {loved_preview}")
        watched_only_series = [w for w in recent_watches if w not in loved_series] if recent_watches else []
        if watched_only_series:
            watched_preview = json.dumps(watched_only_series[: config.num_rows], separators=(",", ":"))
            logger.info(f"Because you watched (series) seeds preview: {watched_preview}")
        if seeds_for_series:
            combined_preview = json.dumps(seeds_for_series[: config.num_rows], separators=(",", ":"))
            logger.info(f"Series catalog seeds (combined) preview: {combined_preview}")
        for i in range(config.num_rows):
            # Get title for this seed if available
            if i < len(seeds_for_series):
                imdb_id = seeds_for_series[i]
                is_loved_seed = i < len(loved_series)
                try:
                    tmdb_data = await tmdb.find_by_imdb_id(imdb_id)
                    if tmdb_data:
                        title = tmdb_data.get("title") or tmdb_data.get("name", "")
                        prefix = "📺 Because you loved" if is_loved_seed else "📺 Because you watched"
                        catalog_name = f"{prefix} {title}" if title else f"{prefix}"
                    else:
                        prefix = "📺 Because you loved" if is_loved_seed else "📺 Recommended Series"
                        catalog_name = f"{prefix} #{i+1}"
                except Exception as e:
                    logger.debug(f"Failed to get title for {imdb_id}: {e}")
                    prefix = "📺 Because you loved" if is_loved_seed else "📺 Recommended Series"
                    catalog_name = f"{prefix} #{i+1}"
            else:
                # No seed available; default to generic row name
                prefix = "📺 Recommended Series"
                catalog_name = f"{prefix} #{i+1}"
            
            catalogs.append(
                ManifestCatalog(
                    type="series",
                    id=f"dynamic_series_{i}",
                    name=catalog_name
                )
            )
    
    # Close connections
    await stremio.close()
    await tmdb.close()
    
    manifest = Manifest(catalogs=catalogs)
    
    logger.info(f"Manifest generated with {len(catalogs)} catalogs")
    
    return manifest.model_dump()
