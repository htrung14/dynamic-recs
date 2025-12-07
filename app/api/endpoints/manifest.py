"""
Manifest Endpoint
Returns the Stremio addon manifest with dynamic catalogs
"""
from fastapi import APIRouter, HTTPException, Path, Response
from app.models.stremio import Manifest, ManifestCatalog
from app.utils.token import decode_config
from app.services.stremio import StremioClient
from app.services.tmdb import TMDBClient
import logging

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
    # Add cache headers
    response.headers["Cache-Control"] = "max-age=3600, public"  # 1 hour for dynamic names
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
    
    # Build catalogs based on user configuration
    catalogs = []
    
    # Add movie catalogs if enabled
    if config.include_movies:
        for i in range(config.num_rows):
            # Get title for this seed if available
            if i < len(recent_watches):
                imdb_id = recent_watches[i]
                try:
                    tmdb_data = await tmdb.find_by_imdb_id(imdb_id)
                    if tmdb_data:
                        title = tmdb_data.get("title") or tmdb_data.get("name", "")
                        catalog_name = f"🎬 Because you watched {title}"
                    else:
                        catalog_name = f"🎬 Recommended Movies #{i+1}"
                except Exception as e:
                    logger.debug(f"Failed to get title for {imdb_id}: {e}")
                    catalog_name = f"🎬 Recommended Movies #{i+1}"
            else:
                catalog_name = f"🎬 Recommended Movies #{i+1}"
            
            catalogs.append(
                ManifestCatalog(
                    type="movie",
                    id=f"dynamic_movies_{i}",
                    name=catalog_name
                )
            )
    
    # Add series catalogs if enabled
    if config.include_series:
        for i in range(config.num_rows):
            # Get title for this seed if available
            if i < len(recent_watches):
                imdb_id = recent_watches[i]
                try:
                    tmdb_data = await tmdb.find_by_imdb_id(imdb_id)
                    if tmdb_data:
                        title = tmdb_data.get("title") or tmdb_data.get("name", "")
                        catalog_name = f"📺 Because you watched {title}"
                    else:
                        catalog_name = f"📺 Recommended Series #{i+1}"
                except Exception as e:
                    logger.debug(f"Failed to get title for {imdb_id}: {e}")
                    catalog_name = f"📺 Recommended Series #{i+1}"
            else:
                catalog_name = f"📺 Recommended Series #{i+1}"
            
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
