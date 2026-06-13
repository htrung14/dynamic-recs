"""
Tests for API endpoints
"""
import pytest
from httpx import AsyncClient
from app.core.app import create_app
from app.utils.token import encode_config


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint"""
    app = create_app()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


@pytest.mark.asyncio
async def test_configure_page():
    """Test configuration page is accessible"""
    app = create_app()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/configure")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Dynamic Recommendations" in response.text


@pytest.mark.asyncio
async def test_generate_token_endpoint():
    """Test token generation endpoint with valid configuration"""
    app = create_app()
    
    config_request = {
        "stremio_auth_key": "test_auth_key",
        "tmdb_api_key": "test_tmdb_key",
        "num_rows": 5,
        "min_rating": 6.0,
        "use_loved_items": True,
        "include_movies": True,
        "include_series": True
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/generate-token", json=config_request)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "token" in data
        assert "install_url" in data
        assert data["install_url"].endswith("/manifest.json")
        
        # Verify token is valid by decoding it
        from app.utils.token import decode_config
        decoded_config = decode_config(data["token"])
        assert decoded_config is not None
        assert decoded_config.stremio_auth_key == "test_auth_key"


@pytest.mark.asyncio
async def test_generate_token_missing_fields():
    """Test token generation endpoint with missing required fields"""
    app = create_app()
    
    config_request = {
        "stremio_auth_key": "test_auth_key"
        # Missing required fields
    }
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/generate-token", json=config_request)
        
        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_manifest_endpoint(sample_user_config):
    """Test manifest endpoint with valid token"""
    app = create_app()
    token = encode_config(sample_user_config)
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/{token}/manifest.json")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == "com.dynamic.recommendations"
        assert data["name"] == "Dynamic Recommendations"
        assert "catalogs" in data

        # Verify curated catalogs are present
        cat_ids = [c["id"] for c in data["catalogs"]]
        assert "gems_movie" in cat_ids
        assert "new_movie" in cat_ids
        assert "gems_series" in cat_ids
        assert "new_series" in cat_ids

        # Verify per-seed dynamic rows (config.num_rows=5, both types enabled)
        movie_dynamic = [c for c in data["catalogs"] if c["id"].startswith("dynamic_movies_")]
        series_dynamic = [c for c in data["catalogs"] if c["id"].startswith("dynamic_series_")]
        assert len(movie_dynamic) == 5
        assert len(series_dynamic) == 5

        # Total = 4 curated + 0 genre rows (no taste profile) + 5+5 dynamic
        assert len(data["catalogs"]) == 14


@pytest.mark.asyncio
async def test_manifest_invalid_token():
    """Test manifest endpoint with invalid token"""
    app = create_app()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/invalid_token/manifest.json")
        
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_manifest_movies_only():
    """Test manifest with only movies enabled"""
    from app.models.config import UserConfig
    
    test_config = UserConfig(
        stremio_auth_key="VGVzdEtleUZha2VTdHJlbWlvQXV0aEtleUJhc2U2NA==",
        stremio_username_enc="dGVzdF91c2VybmFtZQ==",
        stremio_password_enc="dGVzdF9wYXNzd29yZA==",
        stremio_loved_token="test_loved_token",
        tmdb_api_key="7c1d4ee5a7063e9f116b6ca2a0850143",
        num_rows=3,
        min_rating=6.0,
        use_loved_items=True,
        include_movies=True,
        include_series=False
    )
    
    app = create_app()
    token = encode_config(test_config)
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/{token}/manifest.json")
        
        assert response.status_code == 200
        data = response.json()
        
        # With include_series=False, only movie catalogs should appear
        # Expected: 2 curated (gems_movie, new_movie) + 0 genre rows + 3 dynamic = 5
        assert all(cat["type"] == "movie" for cat in data["catalogs"])
        cat_ids = [c["id"] for c in data["catalogs"]]
        assert "gems_movie" in cat_ids
        assert "new_movie" in cat_ids
        assert not any(c["id"].startswith("dynamic_series_") for c in data["catalogs"])
        movie_dynamic = [c for c in data["catalogs"] if c["id"].startswith("dynamic_movies_")]
        assert len(movie_dynamic) == 3
        assert len(data["catalogs"]) == 5  # 2 curated + 0 genre + 3 dynamic


@pytest.mark.asyncio
async def test_catalog_invalid_token():
    """Test catalog endpoint with invalid token"""
    app = create_app()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/invalid_token/catalog/movie/dynamic_movies_0.json")
        
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_catalog_invalid_type(sample_user_config):
    """Test catalog endpoint with invalid type"""
    app = create_app()
    token = encode_config(sample_user_config)
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/{token}/catalog/invalid/dynamic_movies_0.json")
        
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_catalog_invalid_id(sample_user_config):
    """Test catalog endpoint with invalid catalog ID"""
    app = create_app()
    token = encode_config(sample_user_config)
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/{token}/catalog/movie/invalid_id.json")
        
        assert response.status_code == 404
