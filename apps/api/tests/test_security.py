import jwt
from src.core.config import get_settings
from src.core.security import (
    compute_hmac_sha256,
    create_access_token,
    create_refresh_token,
    generate_device_secret,
    generate_pairing_token,
    hash_password,
    hash_token,
    verify_hmac_sha256,
    verify_password,
)

settings = get_settings()


def test_password_hashing_and_verification():
    raw_password = "SuperSecurePassword123!"
    hashed = hash_password(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_access_token_creation():
    user_id = "user-12345"
    tenant_id = "tenant-67890"
    token = create_access_token(subject=user_id, tenant_id=tenant_id)

    decoded = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert decoded["sub"] == user_id
    assert decoded["tenant_id"] == tenant_id
    assert decoded["type"] == "access"
    assert "exp" in decoded


def test_refresh_token_creation_and_hash():
    raw_token, token_hash = create_refresh_token(subject="user-123", tenant_id="tenant-456")
    assert len(raw_token) > 32
    assert token_hash == hash_token(raw_token)


def test_pairing_token_generation():
    raw_token, token_hash = generate_pairing_token()
    assert len(raw_token) == 64
    assert token_hash == hash_token(raw_token)


def test_hmac_signature_generation_and_verification():
    secret = generate_device_secret()
    payload = "DEVICE_ID_123|1724000000|NONCE_ABC|{'balance':1000}"

    signature = compute_hmac_sha256(secret, payload)
    assert verify_hmac_sha256(secret, payload, signature) is True
    assert verify_hmac_sha256(secret, payload + "_tampered", signature) is False
