"""
Manifest Endpoint
Returns the Stremio addon manifest with dynamic catalogs
"""
import logging
import asyncio
from fastapi import APIRouter, HTTPException, Path, Response
from app.models.stremio import Manifest, ManifestCatalog
from app.utils.token import decode_config
from app.services.recommendations import RecommendationEngine

logger = logging.getLogger(__name__)
router = APIRouter()

# TMDB genre IDs are stable — map for display names
TMDB_GENRE_NAMES: dict = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
    10759: "Action & Adventure", 10762: "Kids", 10763: "News", 10764: "Reality",
    10765: "Sci-Fi & Fantasy", 10766: "Soap", 10767: "Talk", 10768: "War & Politics",
}


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
    
    # Build catalogs based on user configuration
    catalogs = []

    # Single engine for genre profile + seed items + title resolution
    engine = RecommendationEngine(config, token=token)
    try:
        user_genres = await engine.get_user_genre_profile()
    except Exception as e:
        logger.warning(f"Failed to get user genre profile: {e}")
        user_genres = []

    top_genres = user_genres[:2]  # Keep it to 2 genre rows to avoid clutter

    if config.include_movies:
        catalogs.append(ManifestCatalog(type="movie", id="gems_movie", name="💎 Hidden Gems"))
        catalogs.append(ManifestCatalog(type="movie", id="new_movie", name="🆕 New Releases For You"))
        for gid in top_genres:
            gname = TMDB_GENRE_NAMES.get(gid, f"Genre {gid}")
            catalogs.append(ManifestCatalog(type="movie", id=f"genre_{gid}_movie", name=f"🎯 {gname} For You"))

    if config.include_series:
        catalogs.append(ManifestCatalog(type="series", id="gems_series", name="💎 Hidden Gems"))
        catalogs.append(ManifestCatalog(type="series", id="new_series", name="🆕 New Releases For You"))
        for gid in top_genres:
            gname = TMDB_GENRE_NAMES.get(gid, f"Genre {gid}")
            catalogs.append(ManifestCatalog(type="series", id=f"genre_{gid}_series", name=f"🎯 {gname} For You"))

    # --- Personalized "Because you watched" catalogs ---
    # Use the same canonical seed list as catalog.py so titles match content.

    # Loved items (for label only: "loved" vs "watched")
    loved_movies: list = []
    loved_series: list = []
    if config.use_loved_items:
        try:
            loved_movies = await engine.stremio.fetch_loved_catalog("movie", token=config.stremio_loved_token) or []
            loved_series = await engine.stremio.fetch_loved_catalog("series", token=config.stremio_loved_token) or []
        except Exception as e:
            logger.debug(f"Failed to fetch loved catalogs: {e}")

    loved_set_movies = set(loved_movies)
    loved_set_series = set(loved_series)

    # Fetch canonical seed lists (same SWR-cached data catalog.py will use)
    movie_seeds: list = []
    series_seeds: list = []
    if config.include_movies:
        movie_seeds = await engine.get_seed_items("movie")
    if config.include_series:
        series_seeds = await engine.get_seed_items("series")

    # Resolve TMDB titles for the first num_rows seeds in parallel
    async def _resolve_title(imdb_id: str):
        """Return (imdb_id, tmdb_data_or_None)."""
        try:
            return imdb_id, await engine.tmdb.find_by_imdb_id(imdb_id)
        except Exception as e:
            logger.debug(f"Failed to get title for {imdb_id}: {e}")
            return imdb_id, None

    # Movie seed titles
    movie_title_tasks = [
        _resolve_title(imdb_id) for imdb_id in movie_seeds[:config.num_rows]
    ]
    movie_title_results = await asyncio.gather(*movie_title_tasks) if movie_title_tasks else []

    for i in range(config.num_rows):
        if i < len(movie_seeds):
            imdb_id, tmdb_data = movie_title_results[i] if i < len(movie_title_results) else (movie_seeds[i], None)
            is_loved = imdb_id in loved_set_movies

            if isinstance(tmdb_data, Exception):
                tmdb_data = None

            if tmdb_data:
                title = tmdb_data.get("title") or tmdb_data.get("name", "")
                prefix = "🎬 Because you loved" if is_loved else "🎬 Because you watched"
                catalog_name = f"{prefix} {title}" if title else f"🎬 Recommended Movies #{i+1}"
            else:
                prefix = "🎬 Because you loved" if is_loved else "🎬 Recommended Movies"
                catalog_name = f"{prefix} #{i+1}"
        else:
            catalog_name = f"🎬 Recommended Movies #{i+1}"

        catalogs.append(
            ManifestCatalog(type="movie", id=f"dynamic_movies_{i}", name=catalog_name)
        )

    # Series seed titles
    series_title_tasks = [
        _resolve_title(imdb_id) for imdb_id in series_seeds[:config.num_rows]
    ]
    series_title_results = await asyncio.gather(*series_title_tasks) if series_title_tasks else []

    for i in range(config.num_rows):
        if i < len(series_seeds):
            imdb_id, tmdb_data = series_title_results[i] if i < len(series_title_results) else (series_seeds[i], None)
            is_loved = imdb_id in loved_set_series

            if isinstance(tmdb_data, Exception):
                tmdb_data = None

            if tmdb_data:
                title = tmdb_data.get("title") or tmdb_data.get("name", "")
                prefix = "📺 Because you loved" if is_loved else "📺 Because you watched"
                catalog_name = f"{prefix} {title}" if title else f"📺 Recommended Series #{i+1}"
            else:
                prefix = "📺 Because you loved" if is_loved else "📺 Recommended Series"
                catalog_name = f"{prefix} #{i+1}"
        else:
            catalog_name = f"📺 Recommended Series #{i+1}"

        catalogs.append(
            ManifestCatalog(type="series", id=f"dynamic_series_{i}", name=catalog_name)
        )

    # Close engine connections
    await engine.close()
    
    # Build manifest with behavior hints including configure URL
    from app.core.config import settings
    manifest = Manifest(
        catalogs=catalogs,
        behaviorHints={
            "configurable": True,
            "configurationRequired": False,
            "adult": False,
            "p2p": False
        }
    )
    
    # Add the configuration URL to the manifest dict
    manifest_dict = manifest.model_dump()
    base_url = settings.BASE_URL.rstrip("/")
    manifest_dict["behaviorHints"]["configurationUrl"] = f"{base_url}/{token}/configure"
    
    logger.info(f"Manifest generated with {len(catalogs)} catalogs")
    
    return manifest_dict
