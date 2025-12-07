"""
Manifest Endpoint
Returns the Stremio addon manifest with dynamic catalogs
"""
from fastapi import APIRouter, HTTPException, Path
from app.models.stremio import Manifest, ManifestCatalog
from app.utils.token import decode_config
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{token}/manifest.json")
async def get_manifest(token: str = Path(..., description="User configuration token")):
    """
    Return addon manifest with user-specific configuration
    
    The manifest defines what catalogs this addon provides
    """
    # Decode and validate token
    config = decode_config(token)
    if not config:
        raise HTTPException(status_code=401, detail="Invalid configuration token")
    
    # Build catalogs based on user configuration
    catalogs = []
    
    # Add movie catalogs if enabled
    if config.include_movies:
        for i in range(config.num_rows):
            catalogs.append(
                ManifestCatalog(
                    type="movie",
                    id=f"dynamic_movies_{i}",
                    name=f"🎬 Recommended Movies #{i+1}"
                )
            )
    
    # Add series catalogs if enabled
    if config.include_series:
        for i in range(config.num_rows):
            catalogs.append(
                ManifestCatalog(
                    type="series",
                    id=f"dynamic_series_{i}",
                    name=f"📺 Recommended Series #{i+1}"
                )
            )
    
    manifest = Manifest(catalogs=catalogs)
    
    logger.info(f"Manifest generated with {len(catalogs)} catalogs")
    
    return manifest.model_dump()
