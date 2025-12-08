"""
Recommendation Engine
Core recommendation logic combining multiple data sources
"""
import asyncio
import logging
from typing import List, Dict, Optional, Any, Set, Tuple
from collections import Counter
from app.services.tmdb import TMDBClient
from app.services.mdblist import MDBListClient
from app.services.stremio import StremioClient
from app.services.cache import CacheManager
from app.models.config import UserConfig
from app.core.config import settings
from app.utils.helpers import deduplicate_recommendations, score_by_frequency, merge_ratings

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Generate personalized recommendations"""
    
    def __init__(self, config: UserConfig):
        self.config = config
        self.tmdb = TMDBClient(config.tmdb_api_key)
        self.mdblist = MDBListClient(config.mdblist_api_key)
        self.stremio = StremioClient()
        self.cache = CacheManager()
    
    async def close(self):
        """Close all client connections"""
        await self.tmdb.close()
        await self.mdblist.close()
        await self.stremio.close()
    
    async def get_seed_items(self) -> List[str]:
        """
        Get seed items for recommendations (loved items or watch history)
        
        Returns:
            List of IMDB IDs to use as seeds
        """
        cache_key = f"user:{self.config.stremio_auth_key}:seeds"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Seeds found in cache: {len(cached)} items")
            return cached

        seeds: List[str] = []

        # 1) Try loved items via official liked addon if enabled
        if self.config.use_loved_items:
            logger.debug("Fetching loved catalog (movies)...")
            loved_movies = await self.stremio.fetch_loved_catalog("movie", token=self.config.stremio_loved_token)
            logger.debug(f"  Found {len(loved_movies) if loved_movies else 0} loved movies")
            logger.debug("Fetching loved catalog (series)...")
            loved_series = await self.stremio.fetch_loved_catalog("series", token=self.config.stremio_loved_token)
            logger.debug(f"  Found {len(loved_series) if loved_series else 0} loved series")
            loved = (loved_movies + loved_series)[: settings.MAX_SEEDS]
            if loved:
                seeds = loved
                logger.info(f"Using {len(seeds)} loved items as seeds")

        # 2) Fallback to library watch history
        if not seeds:
            logger.debug("No loved items found, fetching library watch history...")
            library = await self.stremio.fetch_library(self.config.stremio_auth_key)
            logger.debug(f"  Library fetched")
            recent = self.stremio.extract_recently_watched(library, limit=settings.MAX_SEEDS)
            seeds = recent
            logger.info(f"Using {len(seeds)} recently watched items as seeds")

        # Cache seeds
        if seeds:
            await self.cache.set(cache_key, seeds, ttl=settings.CACHE_TTL_LIBRARY)
            logger.debug(f"Seeds cached with TTL {settings.CACHE_TTL_LIBRARY}s")

        return seeds
    
    async def get_watched_items(self) -> List[str]:
        """
        Get all watched items to filter out from recommendations
        
        Returns:
            List of IMDB IDs that user has watched
        """
        cache_key = f"user:{self.config.stremio_auth_key}:watched"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        # Fetch library
        library = await self.stremio.fetch_library(self.config.stremio_auth_key)
        watched = self.stremio.extract_watched_items(library)
        
        # Cache watched list
        if watched:
            await self.cache.set(cache_key, watched, ttl=settings.CACHE_TTL_LIBRARY)
        
        return watched
    
    async def fetch_recommendations_for_seeds(
        self,
        seeds: List[str]
    ) -> Tuple[List[Dict[str, Any]], Set[int]]:
        """
        Fetch recommendations from TMDB for seed items
        
        Args:
            seeds: List of IMDB IDs to use as seeds
            
        Returns:
            Tuple of (recommendation items, seed genre set)
        """
        # Convert IMDB IDs to TMDB IDs
        tmdb_items = []
        seed_genres: Set[int] = set()
        
        for imdb_id in seeds:
            tmdb_data = await self.tmdb.find_by_imdb_id(imdb_id)
            if tmdb_data:
                tmdb_items.append(tmdb_data)

        # Enrich seeds with genres to guide similarity scoring
        if tmdb_items:
            details_map = await self.tmdb.batch_details(tmdb_items)
            for item in tmdb_items:
                tmdb_id = item.get("id")
                genre_ids = item.get("genre_ids", [])
                details = details_map.get(tmdb_id) if tmdb_id else None
                if not genre_ids and details:
                    genre_ids = [g.get("id") for g in details.get("genres", []) if g.get("id")]
                    if genre_ids:
                        item["genre_ids"] = genre_ids
                seed_genres.update(g for g in genre_ids if isinstance(g, int))
        
        if not tmdb_items:
            return [], seed_genres

        # Fetch recommendations and similars in parallel (avoid falling back to popular feed)
        recs_task = self.tmdb.batch_recommendations(
            tmdb_items,
            max_per_item=settings.MAX_RECOMMENDATIONS_PER_SEED
        )
        similars_task = self.tmdb.batch_similar(
            tmdb_items,
            max_per_item=settings.MAX_RECOMMENDATIONS_PER_SEED
        )

        recs, similars = await asyncio.gather(recs_task, similars_task)

        combined: List[Dict[str, Any]] = []
        if recs:
            combined.extend(recs)
        if similars:
            combined.extend(similars)

        return combined, seed_genres

    async def _attach_external_ids(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure each TMDB item has external_ids/imdb_id by fetching details when missing."""
        enriched_items = []
        items_needing_enrichment = []
        
        # Check cache for enriched items first
        for item in items:
            # Default media_type so downstream filtering doesn't drop items
            media_type = item.get("media_type") or "movie"
            item["media_type"] = media_type
            tmdb_id = item.get("id")
            
            # Check if already has IMDB ID
            external_ids = item.get("external_ids", {})
            imdb_id = external_ids.get("imdb_id") or item.get("imdb_id")
            if imdb_id:
                enriched_items.append(item)
                continue
            
            # Check enrichment cache
            if tmdb_id:
                cache_key = f"enriched:{tmdb_id}:{media_type}"
                cached = await self.cache.get(cache_key)
                if cached:
                    enriched_items.append(cached)
                    continue
            
            items_needing_enrichment.append(item)
        
        # Batch fetch details for items without IMDB IDs
        if items_needing_enrichment:
            details_map = await self.tmdb.batch_details(items_needing_enrichment)
            
            for item in items_needing_enrichment:
                tmdb_id = item.get("id")
                media_type = item.get("media_type", "movie")
                
                if tmdb_id in details_map:
                    details = details_map[tmdb_id]
                    if details:
                        # Merge missing fields
                        item.setdefault("external_ids", details.get("external_ids", {}))
                        if not item.get("poster_path"):
                            item["poster_path"] = details.get("poster_path")
                        if not item.get("backdrop_path"):
                            item["backdrop_path"] = details.get("backdrop_path")
                        if not item.get("overview"):
                            item["overview"] = details.get("overview")
                        if not item.get("release_date"):
                            item["release_date"] = details.get("release_date")
                        if not item.get("first_air_date"):
                            item["first_air_date"] = details.get("first_air_date")
                        item["imdb_id"] = item.get("external_ids", {}).get("imdb_id")
                
                # Cache enriched item
                cache_key = f"enriched:{tmdb_id}:{media_type}"
                await self.cache.set(cache_key, item, ttl=settings.CACHE_TTL_RECOMMENDATIONS)
                enriched_items.append(item)
        
        return enriched_items
    
    async def enrich_with_ratings(
        self,
        items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich items with ratings from MDBList
        
        Args:
            items: List of TMDB recommendation items
            
        Returns:
            Items with added rating information
        """
        # Extract IMDB IDs
        imdb_ids = []
        for item in items:
            external_ids = item.get("external_ids", {})
            imdb_id = external_ids.get("imdb_id") or item.get("imdb_id")
            if imdb_id:
                imdb_ids.append(imdb_id)
        
        # Fetch ratings in batch
        ratings = await self.mdblist.batch_ratings(imdb_ids)
        
        # Merge ratings into items
        enriched = []
        for item in items:
            external_ids = item.get("external_ids", {})
            imdb_id = external_ids.get("imdb_id") or item.get("imdb_id")
            
            if imdb_id and imdb_id in ratings:
                rating_data = ratings[imdb_id]
                mdblist_rating = self.mdblist.extract_rating(rating_data)
                
                item["mdblist_rating"] = mdblist_rating
                item["imdb_rating"] = item.get("vote_average", 0.0)
                
                # Calculate merged rating
                item["merged_rating"] = merge_ratings(
                    imdb_rating=mdblist_rating,
                    tmdb_rating=item.get("vote_average", 0.0)
                )
            
            enriched.append(item)
        
        return enriched
    
    async def score_and_rank(
        self,
        items: List[Dict[str, Any]],
        watched: List[str],
        seed_genres: Optional[Set[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Score and rank recommendations
        
        Args:
            items: List of recommendation items
            watched: List of watched IMDB IDs to filter out
            
        Returns:
            Scored and ranked items
        """
        # Deduplicate by TMDB ID
        items = deduplicate_recommendations(items, key="id")
        
        # Filter out watched items
        watched_set = set(watched)
        filtered = []
        
        for item in items:
            external_ids = item.get("external_ids", {})
            imdb_id = external_ids.get("imdb_id") or item.get("imdb_id")
            
            if imdb_id not in watched_set:
                filtered.append(item)
        
        # Calculate frequency scores
        item_ids = [str(item["id"]) for item in items]
        freq_scores = score_by_frequency(item_ids)
        
        # Score each item
        scored = []
        seed_genres = seed_genres or set()
        for item in filtered:
            item_id = str(item["id"])
            
            # Fallback to TMDB vote_average when mdblist rating is missing
            if item.get("merged_rating") is None:
                item["merged_rating"] = item.get("vote_average", 0.0)
            
            freq_score = freq_scores.get(item_id, 0.0)
            rating_score = item.get("merged_rating", 0.0) / 10.0
            popularity_score = min(item.get("popularity", 0.0) / 100.0, 1.0)

            # Genre similarity against seed set
            genre_ids = item.get("genre_ids") or []
            if not genre_ids and item.get("genres"):
                genre_ids = [g.get("id") for g in item.get("genres", []) if g.get("id")]
            overlap = 0.0
            if genre_ids and seed_genres:
                overlap = len(set([g for g in genre_ids if g]) & seed_genres) / float(len(genre_ids))
            
            # Combined score
            final_score = (
                0.45 * freq_score +
                0.35 * rating_score +
                0.1 * popularity_score +
                0.1 * overlap
            )
            
            item["score"] = final_score
            
            # Filter by minimum rating
            if item.get("merged_rating", 0.0) >= self.config.min_rating:
                scored.append(item)
        
        # Sort by score
        scored.sort(key=lambda x: x["score"], reverse=True)
        
        return scored
    
    async def generate_recommendations(
        self,
        media_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate personalized recommendations
        
        Args:
            media_type: Filter by "movie" or "series" (None for both)
            
        Returns:
            List of recommended items
        """
        logger.info(f"Generating recommendations (media_type={media_type})...")
        cache_key = f"user:{self.config.stremio_auth_key}:recs:{media_type or 'all'}"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            logger.debug(f"Recommendations found in cache: {len(cached)} items")
            return cached
        
        logger.debug("Cache miss, generating fresh recommendations...")
        
        # Get seed items and watched list in parallel
        logger.debug("Fetching seed items and watched list...")
        seeds_task = self.get_seed_items()
        watched_task = self.get_watched_items()
        
        seeds, watched = await asyncio.gather(seeds_task, watched_task)
        logger.debug(f"  Seeds: {len(seeds)} items, Watched: {len(watched)} items")
        if seeds:
            seed_preview = seeds[:10]
            logger.info(f"Seed IMDB IDs (up to 10): {seed_preview}")
        
        if not seeds:
            logger.warning("No seed items found for recommendations")
            return []
        
        # Fetch recommendations
        logger.debug(f"Fetching recommendations for {len(seeds)} seed items...")
        recommendations, seed_genres = await self.fetch_recommendations_for_seeds(seeds)
        logger.debug(f"  Found {len(recommendations)} candidate recommendations")
        
        if not recommendations:
            logger.info("No recommendations or similars found for seeds; returning empty list")
            return []
        
        # Ensure external_ids/imdb_id present for poster conversion and scoring
        logger.debug("Attaching external IDs...")
        recommendations = await self._attach_external_ids(recommendations)

        # Enrich with ratings
        logger.debug("Enriching with ratings...")
        enriched = await self.enrich_with_ratings(recommendations)
        
        # Score and rank
        logger.debug("Scoring and ranking recommendations...")
        ranked = await self.score_and_rank(enriched, watched, seed_genres)
        logger.debug(f"  Ranked to {len(ranked)} items")
        
        # Filter by media type
        if media_type:
            type_map = {"movie": "movie", "series": "tv"}
            tmdb_type = type_map.get(media_type)
            
            if tmdb_type:
                ranked = [
                    item for item in ranked
                    if item.get("media_type") == tmdb_type
                ]
            logger.debug(f"  Filtered to {len(ranked)} {media_type}s")
        
        # Cache results
        if ranked:
            top_preview = []
            for item in ranked[:10]:
                external_ids = item.get("external_ids", {})
                imdb_id = external_ids.get("imdb_id") or item.get("imdb_id") or item.get("id")
                title = item.get("title") or item.get("name") or "<unknown>"
                score = round(item.get("score", 0.0), 3)
                media_type_val = item.get("media_type")
                top_preview.append(f"{imdb_id}|{title}|{media_type_val}|score={score}")
            logger.info(f"Top recommendations preview (up to 10): {top_preview}")

        await self.cache.set(cache_key, ranked, ttl=settings.CACHE_TTL_CATALOG)
        logger.info(f"Generated {len(ranked)} recommendations (cached with TTL {settings.CACHE_TTL_CATALOG}s)")
        
        return ranked
