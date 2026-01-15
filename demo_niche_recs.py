#!/usr/bin/env python3
"""
Demo script showing how niche recommendations work
Example usage: python demo_niche_recs.py
"""
import asyncio
import os
from app.services.tmdb import TMDBClient


async def demo_niche_recommendations():
    """Demo the new niche recommendation system"""
    
    # Example: The Matrix (TMDB ID: 603)
    tmdb_id = 603
    media_type = "movie"
    
    print(f"\n{'='*70}")
    print(f"🎬 Fetching NICHE recommendations for: The Matrix (TMDB ID: {tmdb_id})")
    print(f"{'='*70}\n")
    
    client = TMDBClient()
    
    try:
        # Step 1: Show keywords being fetched
        print("Step 1: Fetching keywords...")
        keywords = await client.get_keywords(tmdb_id, media_type)
        
        if keywords:
            print(f"  Found {len(keywords)} keywords:")
            for i, kw in enumerate(keywords[:5], 1):
                print(f"    {i}. {kw.get('name')} (ID: {kw.get('id')})")
        else:
            print("  No keywords found")
        
        print()
        
        # Step 2: Fetch niche recommendations
        print("Step 2: Fetching niche recommendations using Discover API...")
        print("  Filters applied:")
        print("    • vote_count.gte: 50 (avoid garbage)")
        print("    • vote_count.lte: 5000 (filter out blockbusters)")
        print("    • vote_average.gte: 7.0 (ensure quality)")
        print("    • sort_by: vote_average.desc (best-rated first)")
        print()
        
        recommendations = await client.get_niche_recommendations(tmdb_id, media_type)
        
        if recommendations:
            print(f"✅ Found {len(recommendations)} niche recommendations:\n")
            
            for i, item in enumerate(recommendations[:10], 1):
                title = item.get("title") or item.get("name", "Unknown")
                vote_avg = item.get("vote_average", 0.0)
                vote_count = item.get("vote_count", 0)
                release_date = item.get("release_date", "N/A")
                
                print(f"  {i}. {title}")
                print(f"     Rating: ⭐ {vote_avg}/10 ({vote_count} votes)")
                print(f"     Release: {release_date}")
                print()
        else:
            print("❌ No recommendations found")
        
        print(f"\n{'='*70}")
        print("💡 These are NICHE recommendations - hidden gems, not blockbusters!")
        print(f"{'='*70}\n")
        
    finally:
        await client.close()


if __name__ == "__main__":
    # Check if TMDB API key is set
    if not os.getenv("TMDB_API_KEY"):
        print("\n⚠️  Warning: TMDB_API_KEY not set in environment")
        print("Set it using: export TMDB_API_KEY='your_api_key_here'\n")
    
    asyncio.run(demo_niche_recommendations())
