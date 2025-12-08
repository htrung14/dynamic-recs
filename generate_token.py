#!/usr/bin/env python3
"""
Generate Installation Token Script
Creates a properly signed token for manual Stremio addon installation
"""
import sys
from app.models.config import UserConfig
from app.utils.token import encode_config
from app.core.config import settings


def main():
    print("🎬 Dynamic Recommendations - Token Generator")
    print("=" * 60)
    
    # Get Stremio auth key
    stremio_auth = input("\n1. Enter your Stremio Auth Key: ").strip()
    if not stremio_auth:
        print("❌ Stremio Auth Key is required!")
        sys.exit(1)
    
    # Get API keys with defaults from environment
    default_tmdb = settings.TMDB_API_KEY or "your-tmdb-key"
    default_mdblist = settings.MDBLIST_API_KEY or "your-mdblist-key"
    
    tmdb_key = input(f"2. TMDB API Key (default: {default_tmdb[:10]}...): ").strip()
    if not tmdb_key:
        if not settings.TMDB_API_KEY:
            print("❌ TMDB API Key is required!")
            sys.exit(1)
        tmdb_key = settings.TMDB_API_KEY
    
    mdblist_key = input(f"3. MDBList API Key (default: {default_mdblist[:10]}...): ").strip()
    if not mdblist_key:
        if not settings.MDBLIST_API_KEY:
            print("❌ MDBList API Key is required!")
            sys.exit(1)
        mdblist_key = settings.MDBLIST_API_KEY
    
    # Get optional configuration
    num_rows = input("4. Number of recommendation rows (default: 5): ").strip()
    num_rows = int(num_rows) if num_rows else 5
    
    min_rating = input("5. Minimum rating filter (default: 6.0): ").strip()
    min_rating = float(min_rating) if min_rating else 6.0
    
    use_loved = input("6. Prioritize loved items? (Y/n): ").strip().lower()
    use_loved = use_loved != 'n'
    
    include_movies = input("7. Include movies? (Y/n): ").strip().lower()
    include_movies = include_movies != 'n'
    
    include_series = input("8. Include series? (Y/n): ").strip().lower()
    include_series = include_series != 'n'

    default_loved = settings.STREMIO_LOVED_TOKEN or ""
    loved_token = input("9. Stremio loved token (optional): ").strip()
    if not loved_token and default_loved:
        loved_token = default_loved
    
    # Create configuration
    try:
        config = UserConfig(
            stremio_auth_key=stremio_auth,
            stremio_loved_token=loved_token or None,
            stremio_username_enc=None,
            stremio_password_enc=None,
            tmdb_api_key=tmdb_key,
            mdblist_api_key=mdblist_key,
            num_rows=num_rows,
            min_rating=min_rating,
            use_loved_items=use_loved,
            include_movies=include_movies,
            include_series=include_series
        )
        
        # Generate signed token
        token = encode_config(config)
        
        # Build install URL
        base_url = str(settings.BASE_URL).rstrip('/')
        install_url = f"{base_url}/{token}/manifest.json"
        
        print("\n" + "=" * 60)
        print("✅ Token generated successfully!")
        print("=" * 60)
        print(f"\n📋 Install URL:\n{install_url}\n")
        print("🔗 Installation Steps:")
        print("  1. Copy the URL above")
        print("  2. Open Stremio")
        print("  3. Go to Add-ons → Install from URL")
        print("  4. Paste the URL and click Install")
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error generating token: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
