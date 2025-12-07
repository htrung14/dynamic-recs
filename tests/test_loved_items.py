#!/usr/bin/env python3
"""
Test loved items vs watch history priority
"""
import asyncio
import os
from typing import Optional
from app.core.config import settings
from app.models.config import UserConfig
from app.services.recommendations import RecommendationEngine


def require(value: Optional[str], name: str) -> str:
    if not value:
        raise RuntimeError(f"Set {name} in env before running this test script")
    return value

async def test_loved_items_priority():
    """Test that loved items take priority over watch history"""
    
    stremio_auth_key = require(os.environ.get("STREMIO_AUTH_KEY"), "STREMIO_AUTH_KEY")
    tmdb_api_key = require(os.environ.get("TMDB_API_KEY") or settings.TMDB_API_KEY, "TMDB_API_KEY")
    mdblist_api_key = require(os.environ.get("MDBLIST_API_KEY") or settings.MDBLIST_API_KEY, "MDBLIST_API_KEY")
    
    print("=" * 70)
    print("Testing Loved Items Priority")
    print("=" * 70)
    
    # Test 1: With loved items enabled (should prioritize loved items)
    print("\n1️⃣  Test with USE_LOVED_ITEMS = True")
    print("-" * 70)
    
    config_with_loved = UserConfig(
        stremio_auth_key=stremio_auth_key,
        stremio_loved_token=os.environ.get("STREMIO_LOVED_TOKEN"),
        tmdb_api_key=tmdb_api_key,
        mdblist_api_key=mdblist_api_key,
        num_rows=5,
        use_loved_items=True,  # ENABLED
        min_rating=6.0,
        include_movies=True,
        include_series=True
    )
    
    engine1 = RecommendationEngine(config_with_loved)
    
    try:
        # Get seed items
        seeds_loved = await engine1.get_seed_items()
        print(f"\n   Seeds used: {len(seeds_loved)} items")
        
        # Fetch library to check what's loved
        library = await engine1.stremio.fetch_library(stremio_auth_key)
        if library:
            print(f"\n   Library structure:")
            print(f"   Keys: {library.keys()}")
            if "result" in library:
                print(f"   Total items: {len(library['result'])}")
                print(f"\n   First 3 items format:")
                for i, item in enumerate(library['result'][:3], 1):
                    print(f"      {i}. {item}")
            
            loved_items = engine1.stremio.extract_loved_items(library)
            recent_items = engine1.stremio.extract_recently_watched(library, limit=10)
            
            print(f"   Loved items found: {len(loved_items)}")
            print(f"   Recent watch history: {len(recent_items)}")
            
            if loved_items:
                print(f"\n   ✅ Using LOVED items as seeds:")
                for i, imdb_id in enumerate(seeds_loved[:5], 1):
                    print(f"      {i}. {imdb_id}")
            else:
                print(f"\n   ℹ️  No loved items found, falling back to watch history:")
                for i, imdb_id in enumerate(seeds_loved[:5], 1):
                    print(f"      {i}. {imdb_id}")
    
    finally:
        await engine1.close()
    
    # Test 2: With loved items disabled (should use watch history)
    print("\n\n2️⃣  Test with USE_LOVED_ITEMS = False")
    print("-" * 70)
    
    config_without_loved = UserConfig(
        stremio_auth_key=stremio_auth_key,
        stremio_loved_token=None,
        tmdb_api_key=tmdb_api_key,
        mdblist_api_key=mdblist_api_key,
        num_rows=5,
        use_loved_items=False,  # DISABLED
        min_rating=6.0,
        include_movies=True,
        include_series=True
    )
    
    engine2 = RecommendationEngine(config_without_loved)
    
    try:
        seeds_history = await engine2.get_seed_items()
        print(f"\n   Seeds used: {len(seeds_history)} items")
        print(f"   ✅ Using WATCH HISTORY as seeds:")
        for i, imdb_id in enumerate(seeds_history[:5], 1):
            print(f"      {i}. {imdb_id}")
    
    finally:
        await engine2.close()
    
    print("\n" + "=" * 70)
    print("✅ Priority test complete!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_loved_items_priority())
