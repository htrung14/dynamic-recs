"""
Recommendation Engine
Core recommendation logic combining multiple data sources
"""
import asyncio
import logging
from collections import Counter
from datetime import datetime
from typing import List, Dict, Optional, Any, Set, Tuple
from app.services.tmdb import TMDBClient
from app.services.stremio import StremioClient
from app.services.cache import CacheManager
from app.models.config import UserConfig
from app.core.config import settings
from app.utils.helpers import deduplicate_recommendations, score_by_frequency

logger = logging.getLogger(__name__)

# TMDB original_language codes for major Indian film/TV industries:
# Hindi, Tamil, Telugu, Malayalam, Kannada, Bengali, Punjabi, Marathi.
INDIAN_LANGUAGES = frozenset({"hi", "ta", "te", "ml", "kn", "bn", "pa", "mr"})


class RecommendationEngine:
    """Generate personalized recommendations"""
    
    def __init__(self, config: UserConfig, token: Optional[str] = None):
        self.config = config
        self.token = token  # Reserved for future per-user features
        self.tmdb = TMDBClient(config.tmdb_api_key, token=token)
        self.stremio = StremioClient()
        self.cache = CacheManager()
    
    async def close(self):
        """Close all client connections"""
        await self.tmdb.close()
        await self.stremio.close()
    
    def _is_anime(self, item: Dict[str, Any]) -> bool:
        """
        Detect if an item is anime: animated AND Japanese.

        Both conditions must hold.  Western animation (Pixar, Disney) and
        live-action Japanese film are NOT anime.

        Args:
            item: TMDB item data

        Returns:
            True if item is anime, False otherwise
        """
        # Derive genre ids (genre_ids list or genres list-of-dicts)
        genre_ids = item.get("genre_ids", [])
        if not genre_ids and item.get("genres"):
            genre_ids = [g.get("id") for g in item.get("genres", []) if g.get("id")]

        is_animation = 16 in genre_ids

        is_japanese = (
            "JP" in (item.get("origin_country") or [])
            or item.get("original_language") == "ja"
        )

        return is_animation and is_japanese

    def _is_indian(self, item: Dict[str, Any], details: Optional[Dict[str, Any]] = None) -> bool:
        """
        Detect Indian/Bollywood content by language or origin country.

        Flags an item when its TMDB ``original_language`` is a major Indian
        film language OR its ``origin_country`` includes India. ``original_language``
        and ``origin_country`` are not always present on list-level items, so an
        optional ``details`` dict (the full TMDB detail object) is consulted as a
        fallback. Fails open: an item with no language/country signal is NOT flagged.
        """
        lang = item.get("original_language")
        origin = item.get("origin_country") or []
        if details:
            lang = lang or details.get("original_language")
            if not origin:
                origin = details.get("origin_country") or []

        if lang in INDIAN_LANGUAGES:
            return True
        if "IN" in origin:
            return True
        return False

    @staticmethod
    def _taste_affinity(genre_ids: list, genre_weights: dict) -> float:
        """Average user-genre weight over MATCHING genres only.

        Dividing by the matched count (not total genre count) prevents
        multi-genre titles from being penalised when they do match the
        user's taste profile.
        """
        matching = [genre_weights[g] for g in genre_ids if g in genre_weights]
        if not matching:
            return 0.0
        return sum(matching) / len(matching)

    async def _filter_imdb_ids_by_media_type(
        self,
        imdb_ids: List[str],
        media_type: Optional[str],
    ) -> List[str]:
        """Filter a list of IMDB IDs to those matching the requested media type."""
        if not media_type:
            return imdb_ids

        tmdb_type = {"movie": "movie", "series": "tv"}.get(media_type)
        if not tmdb_type:
            return imdb_ids

        tasks = [self.tmdb.find_by_imdb_id(imdb_id) for imdb_id in imdb_ids]
        resolved = await asyncio.gather(*tasks, return_exceptions=True)

        filtered: List[str] = []
        for imdb_id, tmdb_data in zip(imdb_ids, resolved):
            if isinstance(tmdb_data, dict) and tmdb_data.get("media_type") == tmdb_type:
                filtered.append(imdb_id)
        return filtered

    async def _filter_indian_imdb_ids(self, imdb_ids: List[str]) -> List[str]:
        """Drop Indian/Bollywood seeds when exclude_indian is enabled.

        Resolves each IMDB ID via find_by_imdb_id (SWR-cached) and checks
        _is_indian on the resolved dict, with a batch_details fallback for
        origin_country (which /find results don't carry).  Items that fail
        to resolve are kept (fail open).
        """
        if not self.config.exclude_indian:
            return imdb_ids

        tasks = [self.tmdb.find_by_imdb_id(imdb_id) for imdb_id in imdb_ids]
        resolved = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect resolved dicts for a batch_details call so we can check
        # origin_country (not present on /find results).
        resolved_dicts = [d for d in resolved if isinstance(d, dict)]
        details_map: dict = {}
        if resolved_dicts:
            details_map = await self.tmdb.batch_details(resolved_dicts)

        kept: List[str] = []
        for imdb_id, data in zip(imdb_ids, resolved):
            if isinstance(data, dict):
                det = details_map.get(data.get("id") or data.get("tmdb_id"))
                if not self._is_indian(data, det):
                    kept.append(imdb_id)
            else:
                # Resolution failed — keep (fail open)
                kept.append(imdb_id)
        return kept

    async def _get_library(self):
        """Fetch and cache the user's Stremio library (single shared call)."""
        auth_key = await self.stremio.resolve_auth_key(self.config)
        if not auth_key:
            return None, auth_key
        self.config.stremio_auth_key = auth_key
        cache_key = f"user:{auth_key}:library_raw"

        async def build():
            return await self.stremio.fetch_library(auth_key)

        library = await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build,
            ttl=settings.CACHE_TTL_LIBRARY,
            stale_ttl=settings.CACHE_TTL_LIBRARY * 3,
        )
        return library, auth_key

    async def get_seed_items(self, media_type: Optional[str] = None) -> List[str]:
        """Get seed items for recommendations (loved items or watch history)."""
        library, auth_key = await self._get_library()
        if not auth_key:
            logger.warning("No valid Stremio auth key available; skipping seed fetch")
            return []
        cache_key = f"user:{auth_key}:seeds:{media_type or 'all'}:{self.config.seed_fingerprint()}"

        async def build_seeds() -> List[str]:
            seeds: List[str] = []

            # 1) Try loved items via official liked addon if enabled
            if self.config.use_loved_items:
                logger.debug("Fetching loved catalogs in parallel...")
                loved_tasks = []
                if media_type in (None, "movie"):
                    loved_tasks.append(self.stremio.fetch_loved_catalog("movie", token=self.config.stremio_loved_token))
                if media_type in (None, "series"):
                    loved_tasks.append(self.stremio.fetch_loved_catalog("series", token=self.config.stremio_loved_token))

                loved_results = await asyncio.gather(*loved_tasks)
                loved = [item for sub in loved_results for item in (sub or [])]

                if media_type:
                    loved = await self._filter_imdb_ids_by_media_type(loved, media_type)

                loved = await self._filter_indian_imdb_ids(loved)
                loved = loved[: settings.MAX_SEEDS]
                if loved:
                    seeds.extend(loved)
                    logger.info(f"Using {len(seeds)} loved items as seeds")

            # 2) Library watch history — oversample, then rank by watch progress
            logger.debug("  Library fetched")
            recent = self.stremio.extract_recently_watched(library, limit=settings.MAX_SEEDS * 4)

            if not recent:
                recent = self.stremio.extract_watched_items(library)

            if media_type:
                recent = await self._filter_imdb_ids_by_media_type(recent, media_type)

            recent = await self._filter_indian_imdb_ids(recent)

            # Fetch watch progress in parallel to prioritize completed items
            candidates = [r for r in recent if r not in seeds][:settings.MAX_SEEDS * 3]
            if candidates and auth_key:
                progress_tasks = [
                    self.stremio.fetch_watched_progress(auth_key, imdb_id)
                    for imdb_id in candidates
                ]
                progress_results = await asyncio.gather(*progress_tasks, return_exceptions=True)

                # Sort by progress descending — fully watched items first.
                # None means genuinely unknown; sort those after known values
                # but keep them in the running (fall open).
                scored = []
                for imdb_id, prog in zip(candidates, progress_results):
                    p = prog if isinstance(prog, (int, float)) else None
                    scored.append((imdb_id, p))
                scored.sort(key=lambda x: (x[1] is not None, x[1] or 0.0), reverse=True)

                # Accept items with known progress >= 0.2, OR unknown progress
                # (fall open — prefer including a watched item over missing it).
                for imdb_id, p in scored:
                    if (p is None or p >= 0.2) and imdb_id not in seeds:
                        seeds.append(imdb_id)
                    if len(seeds) >= settings.MAX_SEEDS:
                        break
                logger.info(f"Using {len(seeds)} progress-ranked items as seeds")
            else:
                for imdb_id in recent:
                    if imdb_id not in seeds:
                        seeds.append(imdb_id)
                seeds = seeds[: settings.MAX_SEEDS]

            return seeds

        seeds = await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build_seeds,
            ttl=settings.CACHE_TTL_LIBRARY,
            stale_ttl=settings.CACHE_TTL_LIBRARY * 3,
        )

        if seeds:
            logger.debug(f"Seeds served via SWR: {len(seeds)} items")
        return seeds or []

    async def get_watched_items(self) -> List[str]:
        """Get all watched items to filter out from recommendations."""
        library, auth_key = await self._get_library()
        if not auth_key:
            logger.warning("No valid Stremio auth key available; skipping watched fetch")
            return []
        cache_key = f"user:{auth_key}:watched"

        async def build_watched() -> List[str]:
            watched = self.stremio.extract_watched_items(library)
            return watched

        watched = await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build_watched,
            ttl=settings.CACHE_TTL_LIBRARY,
            stale_ttl=settings.CACHE_TTL_LIBRARY * 3,
        )
        return watched or []
    
    async def fetch_recommendations_for_seeds(
        self,
        seeds: List[str]
    ) -> Tuple[List[Dict[str, Any]], Set[int]]:
        """Fetch recommendations pooled across all seeds (used for combined ranking)."""
        per_seed_rows, seed_genres = await self._fetch_per_seed(seeds)
        combined: List[Dict[str, Any]] = []
        for row in per_seed_rows:
            combined.extend(row)
        return combined, seed_genres

    async def _fetch_per_seed(
        self,
        seeds: List[str]
    ) -> Tuple[List[List[Dict[str, Any]]], Set[int]]:
        """Fetch recommendations grouped per seed for distinct rows.

        Returns:
            Tuple of (list of per-seed item lists, seed genre set)
        """
        tmdb_items = []
        seed_genres: Set[int] = set()

        tasks = [self.tmdb.find_by_imdb_id(imdb_id) for imdb_id in seeds]
        resolved = await asyncio.gather(*tasks, return_exceptions=True)
        for tmdb_data in resolved:
            if isinstance(tmdb_data, dict):
                tmdb_items.append(tmdb_data)

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

            # Drop Indian seeds so we don't generate recs from them.
            # Must run after seed_genres is collected (above) but before
            # per-seed rec generation (below).  Details fallback covers items
            # whose base object lacks original_language / origin_country.
            if self.config.exclude_indian:
                kept = []
                for it in tmdb_items:
                    tid = it.get("id")
                    det = details_map.get(tid) if tid is not None else None
                    if not self._is_indian(it, det):
                        kept.append(it)
                tmdb_items = kept

        if not tmdb_items:
            return [], seed_genres

        # Fetch recs + similar PER SEED in parallel
        all_tasks = []
        for item in tmdb_items:
            tmdb_id = item.get("tmdb_id") or item.get("id")
            media_type = item.get("media_type", "movie")
            if tmdb_id:
                all_tasks.append(self._recs_for_one_seed(tmdb_id, media_type))

        per_seed_results = await asyncio.gather(*all_tasks, return_exceptions=True)
        per_seed_rows: List[List[Dict[str, Any]]] = []
        for result in per_seed_results:
            if isinstance(result, list):
                per_seed_rows.append(result)
        return per_seed_rows, seed_genres

    async def _recs_for_one_seed(self, tmdb_id: int, media_type: str) -> List[Dict[str, Any]]:
        """Get keyword-based niche recommendations for a single seed."""
        recs = await self.tmdb.get_recommendations(tmdb_id, media_type)
        if isinstance(recs, list):
            return recs[:settings.MAX_RECOMMENDATIONS_PER_SEED]
        return []

    async def _attach_external_ids(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure each TMDB item has external_ids/imdb_id by fetching details when missing."""
        enriched_items = []
        items_needing_cache_check = []

        # First pass: separate items that already have IMDB IDs from those needing cache
        for item in items:
            media_type = item.get("media_type") or "movie"
            item["media_type"] = media_type

            imdb_id = item.get("imdb_id")
            if not imdb_id:
                external_ids = item.get("external_ids", {})
                imdb_id = external_ids.get("imdb_id") if external_ids else None

            if imdb_id:
                enriched_items.append(item)
            else:
                items_needing_cache_check.append(item)

        # Batch cache lookup for items without IMDB IDs
        items_needing_enrichment = []
        if items_needing_cache_check:
            cache_keys = [
                f"enriched:{item.get('id')}:{item.get('media_type', 'movie')}"
                for item in items_needing_cache_check
            ]
            cached_values = await self.cache.mget(cache_keys)

            for item, cached in zip(items_needing_cache_check, cached_values):
                if cached:
                    enriched_items.append(cached)
                else:
                    items_needing_enrichment.append(item)
        
        # Batch fetch details for items without IMDB IDs
        if items_needing_enrichment:
            details_map = await self.tmdb.batch_details(items_needing_enrichment)
            to_cache: dict = {}

            for item in items_needing_enrichment:
                tmdb_id = item.get("id")
                media_type = item.get("media_type", "movie")

                if tmdb_id in details_map:
                    details = details_map[tmdb_id]
                    if details:
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
                        details_external_ids = details.get("external_ids", {})
                        item_imdb_id = item.get("imdb_id") or details.get("imdb_id") or details_external_ids.get("imdb_id")
                        if item_imdb_id:
                            item["imdb_id"] = item_imdb_id

                to_cache[f"enriched:{tmdb_id}:{media_type}"] = item
                enriched_items.append(item)

            # Single pipeline round-trip instead of N sequential writes
            await self.cache.mset(to_cache, ttl=settings.CACHE_TTL_RECOMMENDATIONS)

        return enriched_items
    
    def _apply_ratings(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Set merged_rating from TMDB vote_average for each item."""
        for item in items:
            item["merged_rating"] = item.get("vote_average", 0.0)
        return items

    async def _build_taste_profile(self, media_type: Optional[str] = None) -> Dict[str, Any]:
        """Build a deep taste profile from a large sample of watch history.

        The profile is built from ALL watch history (media_type agnostic) and
        cached once. The media_type parameter is accepted for API compat but
        ignored — a unified profile avoids rebuilding 75 TMDB calls per type.

        Returns dict with:
            genre_weights: {genre_id: 0.0-1.0} normalised weight vector
            top_genres: [genre_id, ...] top 5 by weight
            top_keywords: [keyword_id, ...] top 15 by frequency
        """
        library, auth_key = await self._get_library()
        if not auth_key or not library:
            return {"genre_weights": {}, "top_genres": [], "top_keywords": []}
        cache_key = f"user:{auth_key}:taste:v4:{self.config.taste_fingerprint()}"

        async def build() -> Dict[str, Any]:
            # Sample up to MAX_TASTE_SAMPLE recent watches for the profile
            recent = self.stremio.extract_recently_watched(library, limit=settings.MAX_TASTE_SAMPLE)
            if not recent:
                recent = self.stremio.extract_watched_items(library)[:settings.MAX_TASTE_SAMPLE]
            if not recent:
                return {"genre_weights": {}, "top_genres": [], "top_keywords": []}

            # Resolve to TMDB in parallel
            tasks = [self.tmdb.find_by_imdb_id(imdb_id) for imdb_id in recent]
            resolved = await asyncio.gather(*tasks, return_exceptions=True)
            tmdb_items = [r for r in resolved if isinstance(r, dict)]
            if not tmdb_items:
                return {"genre_weights": {}, "top_genres": [], "top_keywords": []}

            # Batch details for genre enrichment
            details_map = await self.tmdb.batch_details(tmdb_items)

            # Drop Indian items from the taste-profile sample so the profile
            # doesn't chase Bollywood genres when the user has exclude_indian on.
            if self.config.exclude_indian:
                kept = []
                for it in tmdb_items:
                    tid = it.get("id")
                    det = details_map.get(tid) if tid is not None else None
                    if not self._is_indian(it, det):
                        kept.append(it)
                tmdb_items = kept
            if not tmdb_items:
                return {"genre_weights": {}, "top_genres": [], "top_keywords": []}

            # Build genre frequency counter with recency weighting
            # Most recent item gets weight 1.0, oldest gets 0.3
            genre_counter: dict[int, float] = {}
            n = len(tmdb_items)
            for idx, item in enumerate(tmdb_items):
                recency_weight = 0.3 + 0.7 * ((n - idx) / n)
                genre_ids = item.get("genre_ids", [])
                tmdb_id = item.get("id")
                details = details_map.get(tmdb_id) if tmdb_id else None
                if not genre_ids and details:
                    genre_ids = [g.get("id") for g in details.get("genres", []) if g.get("id")]
                for gid in genre_ids:
                    if isinstance(gid, int):
                        genre_counter[gid] = genre_counter.get(gid, 0.0) + recency_weight

            # Normalise to 0-1 weight vector
            max_weight = max(genre_counter.values()) if genre_counter else 1.0
            genre_weights = {gid: w / max_weight for gid, w in genre_counter.items()}
            top_genres = sorted(genre_counter, key=lambda g: genre_counter[g], reverse=True)[:5]

            # Fetch keywords for top 15 items (most recent) in parallel
            kw_sample = tmdb_items[:15]
            kw_tasks = [
                self.tmdb.get_keywords(item["id"], item.get("media_type", "movie"))
                for item in kw_sample if item.get("id")
            ]
            kw_results = await asyncio.gather(*kw_tasks, return_exceptions=True)
            kw_counter: Counter = Counter()
            for result in kw_results:
                if isinstance(result, list):
                    for kw in result:
                        kw_id = kw.get("id")
                        if kw_id:
                            kw_counter[kw_id] += 1
            top_keywords = [kid for kid, _ in kw_counter.most_common(15)]

            return {
                "genre_weights": genre_weights,
                "top_genres": top_genres,
                "top_keywords": top_keywords,
            }

        result = await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build,
            ttl=settings.CACHE_TTL_LIBRARY,
            stale_ttl=settings.CACHE_TTL_LIBRARY * 3,
        )
        return result or {"genre_weights": {}, "top_genres": [], "top_keywords": []}

    async def get_user_genre_profile(self, media_type: Optional[str] = None) -> List[int]:
        """Return top genre IDs from the deep taste profile."""
        profile = await self._build_taste_profile(media_type)
        return profile.get("top_genres", [])

    async def _get_user_keywords(self, media_type: Optional[str] = None) -> List[int]:
        """Return top keyword IDs from the deep taste profile."""
        profile = await self._build_taste_profile(media_type)
        return profile.get("top_keywords", [])

    async def _generate_curated(
        self,
        media_type: str,
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Shared pipeline for curated catalogs: attach IDs, rate, score, rank."""
        # Parallelize watched list and external IDs
        watched_task = self.get_watched_items()

        try:
            items = await self._attach_external_ids(items)
        except Exception as ex:
            logger.warning(f"External ID attachment failed for curated catalog: {ex}")

        items = self._apply_ratings(items)
        watched = await watched_task
        # score_and_rank loads taste profile internally
        ranked = await self.score_and_rank(items, watched)
        return ranked

    async def generate_hidden_gems(self, media_type: str) -> List[Dict[str, Any]]:
        """Generate hidden gem recommendations using user's keywords + genres."""
        tmdb_type = {"movie": "movie", "series": "tv"}.get(media_type, media_type)
        genre_ids = await self.get_user_genre_profile(media_type)
        keyword_ids = await self._get_user_keywords(media_type)
        if not genre_ids:
            return []
        items = await self.tmdb.discover_hidden_gems(tmdb_type, genre_ids, keyword_ids)
        return await self._generate_curated(media_type, items)

    async def generate_new_releases(self, media_type: str) -> List[Dict[str, Any]]:
        """Generate new release recommendations using user's keywords + genres."""
        tmdb_type = {"movie": "movie", "series": "tv"}.get(media_type, media_type)
        genre_ids = await self.get_user_genre_profile(media_type)
        keyword_ids = await self._get_user_keywords(media_type)
        if not genre_ids:
            return []
        items = await self.tmdb.discover_new_releases(tmdb_type, genre_ids, keyword_ids)
        return await self._generate_curated(media_type, items)

    async def generate_genre_picks(self, media_type: str, genre_id: int) -> List[Dict[str, Any]]:
        """Generate picks for a specific genre, narrowed by user's keywords."""
        tmdb_type = {"movie": "movie", "series": "tv"}.get(media_type, media_type)
        keyword_ids = await self._get_user_keywords(media_type)
        items = await self.tmdb.discover_genre_picks(tmdb_type, genre_id, keyword_ids)
        return await self._generate_curated(media_type, items)
    
    async def score_and_rank(
        self,
        items: List[Dict[str, Any]],
        watched: List[str],
        seed_genres: Optional[Set[int]] = None
    ) -> List[Dict[str, Any]]:
        """Score and rank using deep taste profile (genre weight vector)."""
        # Frequency scores must be computed before dedup
        item_ids = [str(item["id"]) for item in items]
        freq_scores = score_by_frequency(item_ids)

        items = deduplicate_recommendations(items, key="id")

        # Load deep taste profile for weighted genre scoring
        profile = await self._build_taste_profile()
        genre_weights = profile.get("genre_weights", {})

        watched_set = set(watched)

        # Content-exclusion filters: (enabled_flag, predicate, label).
        # Add new content filters here instead of copy-pasting if-blocks.
        exclusion_filters = [
            (self.config.exclude_anime, self._is_anime, "anime"),
            (self.config.exclude_indian, self._is_indian, "indian"),
        ]
        active_filters = [(pred, label) for enabled, pred, label in exclusion_filters if enabled]

        filtered = []
        for item in items:
            external_ids = item.get("external_ids", {})
            imdb_id = external_ids.get("imdb_id") or item.get("imdb_id")

            # Watched gating stays first; items without an IMDB id pass here and
            # are dropped later during MetaPoster conversion (unchanged behavior).
            if imdb_id in watched_set:
                continue

            if any(pred(item) for pred, _ in active_filters):
                continue
            filtered.append(item)

        scored = []
        now_year = datetime.now().year
        for item in filtered:
            item_id = str(item["id"])

            freq_score = freq_scores.get(item_id, 0.0)
            rating_score = item.get("merged_rating", 0.0) / 10.0

            # Taste affinity: weighted genre match against full watch history
            # Average over MATCHING genres only (not total), so multi-genre
            # titles that do match aren't penalised.
            genre_ids = item.get("genre_ids") or []
            if not genre_ids and item.get("genres"):
                genre_ids = [g.get("id") for g in item.get("genres", []) if g.get("id")]
            taste_affinity = self._taste_affinity(genre_ids, genre_weights) if genre_ids else 0.0

            # Recency bonus
            release_str = item.get("release_date") or item.get("first_air_date") or ""
            recency = 0.0
            if release_str:
                try:
                    release_year = int(release_str[:4])
                    if now_year - release_year <= 2:
                        recency = 1.0
                except (ValueError, IndexError):
                    pass

            # Mainstream penalty
            raw_pop = item.get("popularity", 0.0)
            mainstream_penalty = min(raw_pop / 500.0, 1.0) if raw_pop > 100 else 0.0

            final_score = (
                0.35 * freq_score +
                0.25 * rating_score +
                0.25 * taste_affinity +
                0.05 * recency
                - 0.10 * mainstream_penalty
            )

            item["score"] = final_score

            if item.get("merged_rating", 0.0) >= self.config.min_rating:
                scored.append(item)

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

        # Resolve auth key (support username/password-backed configs)
        auth_key = await self.stremio.resolve_auth_key(self.config)
        if not auth_key:
            logger.warning("No valid Stremio auth key available; skipping recommendations")
            return []
        self.config.stremio_auth_key = auth_key
        # Fingerprint output-affecting config so toggling a filter takes effect
        # immediately instead of being masked by a stale cache entry.
        cache_key = f"user:{auth_key}:recs:{media_type or 'all'}:{self.config.cache_fingerprint()}"

        async def build_current() -> List[Dict[str, Any]]:
            return await self._build_recommendations(media_type, auth_key)

        async def background_refresh() -> List[Dict[str, Any]]:
            # Use a fresh engine to avoid interfering with the caller's lifecycle
            clone_config = UserConfig.model_validate(self.config.model_dump())
            clone_config.stremio_auth_key = auth_key
            engine = RecommendationEngine(clone_config)
            try:
                return await engine._build_recommendations(media_type, auth_key)
            finally:
                await engine.close()

        ranked = await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build_current,
            ttl=settings.CACHE_TTL_CATALOG,
            stale_ttl=settings.CACHE_TTL_CATALOG * 3,
            refresh_fn=background_refresh,
        )

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

        logger.info(
            "Recommendations served from cache with SWR (key=%s, items=%s)",
            cache_key,
            len(ranked) if ranked else 0,
        )
        return ranked or []

    async def _build_seed_recs(self, seed_imdb: str, media_type: Optional[str]) -> List[Dict[str, Any]]:
        """Raw per-seed build — no SWR wrapper.

        Used by both the SWR ``build_fn`` and the clone-engine
        ``background_refresh`` so the latter never re-enters
        ``stale_while_revalidate``.
        """
        data = await self.tmdb.find_by_imdb_id(seed_imdb)
        if not isinstance(data, dict):
            return []

        tmdb_id = data.get("tmdb_id") or data.get("id")
        mtype = data.get("media_type", "movie")
        if not tmdb_id:
            return []

        recs = await self._recs_for_one_seed(tmdb_id, mtype)
        if not recs:
            return []

        watched = await self.get_watched_items()

        try:
            recs = await self._attach_external_ids(recs)
        except Exception as ex:
            logger.warning(f"External ID attachment failed for seed {seed_imdb}: {ex}")

        recs = self._apply_ratings(recs)
        ranked = await self.score_and_rank(recs, watched)

        # Filter by media type (same tail as _build_recommendations)
        if media_type:
            type_map = {"movie": "movie", "series": "tv"}
            tmdb_type = type_map.get(media_type)
            if tmdb_type:
                ranked = [item for item in ranked if item.get("media_type") == tmdb_type]

        return ranked

    async def generate_recommendations_for_seed(
        self,
        media_type: Optional[str],
        seed_index: int,
    ) -> List[Dict[str, Any]]:
        """Generate recommendations from a single seed at the given index.

        Mirrors generate_recommendations auth/cache flow but resolves exactly
        one seed from the canonical get_seed_items list, so row titles and
        content align.
        """
        # Resolve auth key (same pattern as generate_recommendations)
        auth_key = await self.stremio.resolve_auth_key(self.config)
        if not auth_key:
            logger.warning("No valid Stremio auth key available; skipping per-seed recommendations")
            return []
        self.config.stremio_auth_key = auth_key

        seeds = await self.get_seed_items(media_type)
        if seed_index < 0 or seed_index >= len(seeds):
            return []

        seed_imdb = seeds[seed_index]
        cache_key = (
            f"user:{auth_key}:recs_seed:{media_type or 'all'}:"
            f"{seed_imdb}:{self.config.cache_fingerprint()}"
        )

        async def build() -> List[Dict[str, Any]]:
            return await self._build_seed_recs(seed_imdb, media_type)

        async def background_refresh() -> List[Dict[str, Any]]:
            # Fresh engine so the request engine's close() in catalog.py
            # doesn't yank the session out from under the refresh.
            # Calls the RAW builder — NOT generate_recommendations_for_seed
            # — so we never re-enter stale_while_revalidate.
            clone_config = UserConfig.model_validate(self.config.model_dump())
            clone_config.stremio_auth_key = auth_key
            engine = RecommendationEngine(clone_config)
            try:
                return await engine._build_seed_recs(seed_imdb, media_type)
            finally:
                await engine.close()

        ranked = await self.cache.stale_while_revalidate(
            key=cache_key,
            build_fn=build,
            ttl=settings.CACHE_TTL_CATALOG,
            stale_ttl=settings.CACHE_TTL_CATALOG * 3,
            refresh_fn=background_refresh,
        )
        return ranked or []

    async def _build_recommendations(
        self,
        media_type: Optional[str],
        auth_key: str,
    ) -> List[Dict[str, Any]]:
        """Compute recommendations without handling cache lifecycle."""
        self.config.stremio_auth_key = auth_key

        # Get seed items and watched list in parallel
        logger.debug("Fetching seed items and watched list...")
        seeds_task = self.get_seed_items(media_type)
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

        # Ensure external_ids/imdb_id are attached BEFORE ratings enrichment.
        # ratings lookup depends on IMDB IDs populated during external ID enrichment.
        logger.debug("Attaching external IDs...")
        try:
            recommendations = await self._attach_external_ids(recommendations)
        except Exception as ex:
            logger.warning(f"External ID attachment failed: {ex}, continuing with available data")

        enriched = self._apply_ratings(recommendations)

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

        return ranked
