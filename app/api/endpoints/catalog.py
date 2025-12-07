"""
Catalog Endpoint
Returns recommendation catalogs
"""
from fastapi import APIRouter, HTTPException, Path
from app.models.stremio import CatalogResponse, MetaPoster
from app.services.recommendations import RecommendationEngine
from app.services.background import get_task_manager
from app.utils.token import decode_config
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def convert_to_meta_poster(item: dict, media_type: str) -> MetaPoster:
    """
    Convert TMDB item to Stremio MetaPoster
    
    Args:
        item: TMDB item data
        media_type: "movie" or "series"
        
    Returns:
        MetaPoster object
    """
    # Get IMDB ID
    external_ids = item.get("external_ids", {})
    imdb_id = external_ids.get("imdb_id") or item.get("imdb_id", "")
    
    # Build poster URL
    poster_path = item.get("poster_path")
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
    
    # Build background URL
    backdrop_path = item.get("backdrop_path")
    background = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else None
    
    # Get title
    title = item.get("title") or item.get("name", "Unknown")
    
    # Get release year
    release_date = item.get("release_date") or item.get("first_air_date", "")
    release_year = release_date[:4] if release_date else None
    
    # Get rating
    rating = item.get("merged_rating") or item.get("vote_average", 0.0)
    rating_str = f"{rating:.1f}" if rating > 0 else None
    
    return MetaPoster(
        id=imdb_id,
        type="movie" if media_type == "movie" else "series",
        name=title,
        poster=poster,
        background=background,
        description=item.get("overview"),
        releaseInfo=release_year,
        imdbRating=rating_str
    )


@router.get("/{token}/catalog/{type}/{id}.json")
async def get_catalog(
    token: str = Path(..., description="User configuration token"),
    type: str = Path(..., description="Content type: movie or series"),
    id: str = Path(..., description="Catalog ID")
):
    """
    Return catalog with recommendations
    
    Args:
        token: User configuration token
        type: "movie" or "series"
        id: Catalog identifier (e.g., "dynamic_movies_0")
    """
    # Decode and validate token
    config = decode_config(token)
    if not config:
        raise HTTPException(status_code=401, detail="Invalid configuration token")
    
    # Validate catalog type
    if type not in ["movie", "series"]:
        raise HTTPException(status_code=400, detail="Invalid catalog type")
    
    # Validate catalog ID format
    if not id.startswith("dynamic_"):
        raise HTTPException(status_code=404, detail="Catalog not found")
    
    try:
        # Register config for background cache warming
        task_manager = get_task_manager()
        task_manager.register_config(config)
        
        # Initialize recommendation engine
        engine = RecommendationEngine(config)
        
        # Generate recommendations
        recommendations = await engine.generate_recommendations(media_type=type)
        
        # Schedule background cache warming for this config (non-blocking)
        asyncio.create_task(task_manager.warm_cache_for_config(config))
        
        # Close engine connections
        await engine.close()
        
        # Convert to MetaPoster objects
        metas = []
        items_per_row = 20  # Standard Stremio row size
        
        # Extract row index from catalog ID
        try:
            row_index = int(id.split("_")[-1])
            start_idx = row_index * items_per_row
            end_idx = start_idx + items_per_row
            
            row_items = recommendations[start_idx:end_idx]
        except (ValueError, IndexError):
            row_items = recommendations[:items_per_row]
        
        for item in row_items:
            # Skip items without valid IMDB ID before conversion
            external_ids = item.get("external_ids", {})
            imdb_id = external_ids.get("imdb_id") or item.get("imdb_id")
            if not imdb_id:
                logger.debug(
                    "Skipping item without IMDB ID: %s (tmdb_id=%s)",
                    item.get("title") or item.get("name"),
                    item.get("id")
                )
                continue
            
            try:
                meta = convert_to_meta_poster(item, type)
                metas.append(meta)
            except Exception as e:
                logger.warning(
                    "Failed to convert item to MetaPoster: %s (tmdb_id=%s)",
                    item.get("title") or item.get("name"),
                    item.get("id"),
                    exc_info=True
                )
        
        logger.info(f"Catalog {id} returned {len(metas)} items")
        
        response = CatalogResponse(metas=metas)
        return response.model_dump()
        
    except Exception as e:
        logger.error(f"Error generating catalog: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate recommendations")
