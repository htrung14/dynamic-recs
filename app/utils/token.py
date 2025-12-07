"""
Token Management Utilities
Handles encoding/decoding of user configuration in URLs
"""
import base64
import json
import hmac
import hashlib
from typing import Optional
from app.models.config import UserConfig
from app.core.config import settings


def encode_config(config: UserConfig) -> str:
    """
    Encode user configuration into a secure token
    
    Args:
        config: User configuration object
        
    Returns:
        Base64-encoded token string
    """
    config_json = config.model_dump_json()
    config_bytes = config_json.encode('utf-8')
    
    # Create HMAC signature
    signature = hmac.new(
        settings.TOKEN_SALT.encode('utf-8'),
        config_bytes,
        hashlib.sha256
    ).hexdigest()
    
    # Combine config and signature
    payload = {
        'config': config_json,
        'signature': signature
    }
    
    payload_json = json.dumps(payload)
    token = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8')
    
    return token


def decode_config(token: str) -> Optional[UserConfig]:
    """
    Decode and validate user configuration from token
    
    Args:
        token: Base64-encoded token string
        
    Returns:
        UserConfig object if valid, None otherwise
    """
    try:
        # Decode base64
        payload_json = base64.urlsafe_b64decode(token.encode('utf-8')).decode('utf-8')
        payload = json.loads(payload_json)
        
        config_json = payload.get('config')
        signature = payload.get('signature')
        
        if not config_json or not signature:
            return None
        
        # Verify signature
        expected_signature = hmac.new(
            settings.TOKEN_SALT.encode('utf-8'),
            config_json.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            return None
        
        # Parse and validate config
        config_dict = json.loads(config_json)
        return UserConfig(**config_dict)
        
    except Exception:
        return None


def validate_token(token: str) -> bool:
    """
    Validate if a token is properly formatted and signed
    
    Args:
        token: Token string to validate
        
    Returns:
        True if valid, False otherwise
    """
    return decode_config(token) is not None
