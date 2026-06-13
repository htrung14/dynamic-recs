"""
Tests for XSS protection in the configure page placeholder substitutions.

Phase 3 of the exclude-indian design spec: string placeholders must be
HTML-escaped so a malicious tmdb_api_key (or similar) cannot inject scripts.
"""
import pytest
from httpx import AsyncClient
from app.core.app import create_app
from app.utils.token import encode_config
from app.models.config import UserConfig


XSS_PAYLOAD = '"><script>alert(1)</script>'


def _make_token(**overrides) -> str:
    """Build a signed token with XSS payloads in string fields."""
    defaults = dict(
        stremio_auth_key="testauthkey123456789012345678901234567890",
        tmdb_api_key="legit_key",
        stremio_loved_token="legit_token",
    )
    defaults.update(overrides)
    config = UserConfig(**defaults)
    return encode_config(config)


@pytest.mark.asyncio
async def test_tmdb_key_xss_escaped():
    """tmdb_api_key containing HTML must be escaped in the configure page."""
    token = _make_token(tmdb_api_key=XSS_PAYLOAD)
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/{token}/configure")

    assert response.status_code == 200
    html = response.text
    # The raw breakout payload must NOT appear unescaped
    assert XSS_PAYLOAD not in html
    # The escaped form must be present
    assert "&lt;script&gt;" in html
    assert "&quot;" in html


@pytest.mark.asyncio
async def test_stremio_auth_key_xss_escaped():
    """stremio_auth_key containing HTML must be escaped in the configure page."""
    token = _make_token(stremio_auth_key=XSS_PAYLOAD)
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/{token}/configure")

    assert response.status_code == 200
    html = response.text
    assert XSS_PAYLOAD not in html
    assert "&lt;script&gt;" in html


@pytest.mark.asyncio
async def test_stremio_loved_token_xss_escaped():
    """stremio_loved_token containing HTML must be escaped in the configure page."""
    token = _make_token(stremio_loved_token=XSS_PAYLOAD)
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/{token}/configure")

    assert response.status_code == 200
    html = response.text
    assert XSS_PAYLOAD not in html
    assert "&lt;script&gt;" in html


@pytest.mark.asyncio
async def test_no_token_page_not_broken():
    """The unauthenticated configure page must still render without errors."""
    app = create_app()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/configure")

    assert response.status_code == 200
    assert "Dynamic Recommendations" in response.text
