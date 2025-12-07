"""
Tests for token utilities
"""
import pytest
from app.utils.token import encode_config, decode_config, validate_token
from app.models.config import UserConfig


def test_encode_decode_config(sample_user_config):
    """Test encoding and decoding of user configuration"""
    # Encode
    token = encode_config(sample_user_config)
    assert token
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Decode
    decoded = decode_config(token)
    assert decoded is not None
    assert decoded.stremio_auth_key == sample_user_config.stremio_auth_key
    assert decoded.tmdb_api_key == sample_user_config.tmdb_api_key
    assert decoded.num_rows == sample_user_config.num_rows
    assert decoded.min_rating == sample_user_config.min_rating


def test_decode_invalid_token():
    """Test decoding invalid token returns None"""
    invalid_tokens = [
        "invalid",
        "not_a_token",
        "",
        "eyJpbnZhbGlkIjoidG9rZW4ifQ==",  # Valid base64 but invalid payload
    ]
    
    for token in invalid_tokens:
        decoded = decode_config(token)
        assert decoded is None


def test_validate_token(sample_user_config):
    """Test token validation"""
    # Valid token
    valid_token = encode_config(sample_user_config)
    assert validate_token(valid_token) is True
    
    # Invalid token
    assert validate_token("invalid_token") is False
    assert validate_token("") is False


def test_token_tampering(sample_user_config):
    """Test that tampered tokens are rejected"""
    token = encode_config(sample_user_config)
    
    # Tamper with token
    tampered = token[:-5] + "XXXXX"
    
    decoded = decode_config(tampered)
    assert decoded is None


def test_config_serialization():
    """Test that all config fields are preserved"""
    config = UserConfig(
        stremio_auth_key="VGVzdEF1dGhGYWtlU3RyZW1pb0F1dGhLZXlCYXNlNjQ=",
        tmdb_api_key="6a0c3dd4a6952d8e005a5ba1a9740032",
        mdblist_api_key="testmdbfake123456789abc",
        num_rows=10,
        min_rating=7.5,
        use_loved_items=False,
        include_movies=False,
        include_series=True
    )
    
    token = encode_config(config)
    decoded = decode_config(token)
    
    assert decoded is not None
    assert decoded.stremio_auth_key == config.stremio_auth_key
    assert decoded.tmdb_api_key == config.tmdb_api_key
    assert decoded.mdblist_api_key == config.mdblist_api_key
    assert decoded.num_rows == config.num_rows
    assert decoded.min_rating == config.min_rating
    assert decoded.use_loved_items == config.use_loved_items
    assert decoded.include_movies == config.include_movies
    assert decoded.include_series == config.include_series
