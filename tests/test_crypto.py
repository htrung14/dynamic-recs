from app.utils.crypto import encrypt_secret, decrypt_secret


def test_encrypt_roundtrip():
    plaintext = "s3cret-value"
    token = encrypt_secret(plaintext)
    assert token and isinstance(token, str)
    assert decrypt_secret(token) == plaintext


def test_decrypt_invalid_returns_none():
    assert decrypt_secret("invalid-token") is None
