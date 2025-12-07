"""
Recommendation Engine
Core recommendation logic combining multiple data sources
"""
import asyncio
import logging
from typing import List, Dict, Optional, Any
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
            return cached
        
        # Fetch library
        library = await self.stremio.fetch_library(self.config.stremio_auth_key)
        
        seeds = []
        
        if self.config.use_loved_items:
            # Prioritize loved items
            loved = self.stremio.extract_loved_items(library)
            if loved:
                seeds = loved[:settings.MAX_SEEDS]
                logger.info(f"Using {len(seeds)} loved items as seeds")
        
        # Fallback to recent watch history if no loved items
        if not seeds:
            recent = self.stremio.extract_recently_watched(library, limit=settings.MAX_SEEDS)
            seeds = recent
            logger.info(f"Using {len(seeds)} recently watched items as seeds")
        
        # Cache seeds
        if seeds:
            await self.cache.set(cache_key, seeds, ttl=settings.CACHE_TTL_LIBRARY)
        
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
    ) -> List[Dict[str, Any]]:
        """
        Fetch recommendations from TMDB for seed items
        
        Args:
            seeds: List of IMDB IDs to use as seeds
            
        Returns:
            List of recommendation items
        """
        # Convert IMDB IDs to TMDB IDs
        tmdb_items = []
        
        for imdb_id in seeds:
            tmdb_data = await self.tmdb.find_by_imdb_id(imdb_id)
            if tmdb_data:
                tmdb_items.append(tmdb_data)
        
        # Fetch recommendations in parallel
        recommendations = await self.tmdb.batch_recommendations(
            tmdb_items,
            max_per_item=settings.MAX_RECOMMENDATIONS_PER_SEED
        )
        
        return recommendations

    async def _attach_external_ids(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure each TMDB item has external_ids/imdb_id by fetching details when missing."""
        enriched_items = []
        items_needing_enrichment = []
        
        # Check cache for enriched items first
        for item in items:
            tmdb_id = item.get("id")
            media_type = item.get("media_type", "movie")
            
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
        watched: List[str]
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
        for item in filtered:
            item_id = str(item["id"])
            
            # Fallback to TMDB vote_average when mdblist rating is missing
            if item.get("merged_rating") is None:
                item["merged_rating"] = item.get("vote_average", 0.0)
            
            freq_score = freq_scores.get(item_id, 0.0)
            rating_score = item.get("merged_rating", 0.0) / 10.0
            popularity_score = min(item.get("popularity", 0.0) / 100.0, 1.0)
            
            # Combined score
            final_score = (
                0.5 * freq_score +
                0.3 * rating_score +
                0.2 * popularity_score
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
        cache_key = f"user:{self.config.stremio_auth_key}:recs:{media_type or 'all'}"
        
        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        
        # Get seed items and watched list in parallel
        seeds_task = self.get_seed_items()
        watched_task = self.get_watched_items()
        
        seeds, watched = await asyncio.gather(seeds_task, watched_task)
        
        if not seeds:
            logger.warning("No seed items found for recommendations")
            return []
        
        # Fetch recommendations
        recommendations = await self.fetch_recommendations_for_seeds(seeds)
        
        if not recommendations:
            logger.info(
                "No recommendations from seeds (may be normal if items lack TMDB recs), using popular feed for %s",
                media_type or "all"
            )
            # Use TMDB popular as fallback to avoid empty catalogs
            if media_type in {"movie", "series"}:
                tmdb_type = "movie" if media_type == "movie" else "tv"
                recommendations = await self.tmdb.get_popular(tmdb_type, page=1)
            else:
                # default to movies popular
                recommendations = await self.tmdb.get_popular("movie", page=1)
            if not recommendations:
                logger.warning("Popular feed also returned no results for %s", media_type)
                return []
        
        # Ensure external_ids/imdb_id present for poster conversion and scoring
        recommendations = await self._attach_external_ids(recommendations)

        # Enrich with ratings
        enriched = await self.enrich_with_ratings(recommendations)
        
        # Score and rank
        ranked = await self.score_and_rank(enriched, watched)
        
        # Filter by media type
        if media_type:
            type_map = {"movie": "movie", "series": "tv"}
            tmdb_type = type_map.get(media_type)
            
            if tmdb_type:
                ranked = [
                    item for item in ranked
                    if item.get("media_type") == tmdb_type
                ]
        
        # Cache results
        await self.cache.set(cache_key, ranked, ttl=settings.CACHE_TTL_CATALOG)
        
        return ranked
