#!/usr/bin/env python3
"""
Inspect Stremio library data structure
"""
import asyncio
import json
import os
from typing import Optional
from app.core.config import settings
from app.services.stremio import StremioClient


def require(value: Optional[str], name: str) -> str:
    if not value:
        raise RuntimeError(f"Set {name} in env before running this script")
    return value

async def inspect_library():
    """Inspect the raw library data"""
    
    stremio_auth_key = require(os.environ.get("STREMIO_AUTH_KEY"), "STREMIO_AUTH_KEY")
    
    client = StremioClient()
    
    try:
        library = await client.fetch_library(stremio_auth_key)
        
        if library and "result" in library:
            items = library["result"]
            print(f"Total library items: {len(items)}")

            # Count prefixes and detect any extra metadata beyond [id, timestamp]
            prefix_counts = {"tmdb": 0, "tt": 0, "other": 0}
            extra_items = []
            for item in items:
                if isinstance(item, list) and len(item) >= 1:
                    item_id = str(item[0])
                    if item_id.startswith("tmdb:"):
                        prefix_counts["tmdb"] += 1
                    elif item_id.startswith("tt"):
                        prefix_counts["tt"] += 1
                    else:
                        prefix_counts["other"] += 1
                    if len(item) > 2:
                        extra_items.append(item)

            print("\nID prefix counts:")
            for k, v in prefix_counts.items():
                print(f"  {k}: {v}")

            if extra_items:
                print("\nItems with extra metadata beyond [id, timestamp]:")
                for i, item in enumerate(extra_items[:10], 1):
                    print(f"  {i}. {item}")
            else:
                print("\nNo items contain extra metadata beyond [id, timestamp].")

            print(f"\nFirst 10 items (raw):")
            print("=" * 80)
            for i, item in enumerate(items[:10], 1):
                print(f"{i}. {item}")

            print("\n" + "=" * 80)
            print("Observation: datastoreGet returns [id, timestamp] only; no loved/favorite flag present.")
            print("To surface loved items we need a different Stremio endpoint that exposes favorites.")
    
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(inspect_library())
