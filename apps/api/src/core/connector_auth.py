import hashlib
import hmac
import time
import uuid
from typing import Annotated, Optional
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db_session
from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.models.device import Device

# In-memory sliding nonce cache for replay protection (TTL 60s)
_nonce_cache: dict[str, float] = {}


def check_and_record_nonce(nonce: str, ttl_seconds: int = 60) -> None:
    """Ensure nonce has not been seen within the TTL window and record it."""
    now = time.time()
    # Purge expired nonces
    expired = [n for n, exp in _nonce_cache.items() if exp < now]
    for n in expired:
        _nonce_cache.pop(n, None)

    if nonce in _nonce_cache:
        raise UnauthorizedException("Nonce has already been used (Replay attack detected).")

    _nonce_cache[nonce] = now + ttl_seconds


def reset_nonce_cache() -> None:
    _nonce_cache.clear()


async def verify_connector_hmac(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    x_tradedna_device_id: Annotated[Optional[str], Header(alias="X-TradeDNA-Device-ID")] = None,
    x_tradedna_timestamp: Annotated[Optional[str], Header(alias="X-TradeDNA-Timestamp")] = None,
    x_tradedna_nonce: Annotated[Optional[str], Header(alias="X-TradeDNA-Nonce")] = None,
    x_tradedna_signature: Annotated[Optional[str], Header(alias="X-TradeDNA-Signature")] = None,
) -> Device:
    """
    Validates exact raw-body HMAC-SHA256 signature according to Phase 3 V3.2 specification:
    1. Verify presence of all 4 authentication headers.
    2. Check timestamp freshness (|T_server - T_client| <= 30s).
    3. Check and record single-use nonce.
    4. Fetch device and verify active/revocation status.
    5. Compute SHA256(raw_http_body_bytes) and canonical signature.
    6. Constant-time signature comparison using hmac.compare_digest.
    """
    if not all([x_tradedna_device_id, x_tradedna_timestamp, x_tradedna_nonce, x_tradedna_signature]):
        raise UnauthorizedException("Missing required TradeDNA connector authentication headers.")

    # 1. Parse and validate device ID
    try:
        device_uuid = uuid.UUID(x_tradedna_device_id)
    except ValueError:
        raise UnauthorizedException("Invalid device identifier format.")

    # 2. Validate timestamp freshness (30 seconds skew allowance)
    try:
        client_timestamp_ms = int(x_tradedna_timestamp)
        server_timestamp_ms = int(time.time() * 1000)
        skew_seconds = abs(server_timestamp_ms - client_timestamp_ms) / 1000.0
        if skew_seconds > 30.0:
            raise UnauthorizedException(
                f"Request timestamp expired or desynchronized: skew of {skew_seconds:.2f}s exceeds 30s allowance."
            )
    except ValueError:
        raise UnauthorizedException("Malformed timestamp header.")

    # 3. Check and record Nonce
    check_and_record_nonce(x_tradedna_nonce, ttl_seconds=60)

    # 4. Fetch Device from database
    device_stmt = select(Device).where(Device.id == device_uuid)
    device_res = await db.execute(device_stmt)
    device = device_res.scalar_one_or_none()

    if not device:
        raise UnauthorizedException("Device is not registered.")

    if device.is_revoked or not device.is_active:
        raise UnauthorizedException("Connector device has been revoked or is inactive.")

    # 5. Read RAW HTTP BODY BYTES directly
    raw_body_bytes = await request.body()
    body_sha256 = hashlib.sha256(raw_body_bytes).hexdigest().lower()

    # 6. Construct canonical string: Device-ID | Timestamp | Nonce | Body-SHA256
    canonical_str = f"{str(device.id)}|{x_tradedna_timestamp}|{x_tradedna_nonce}|{body_sha256}"
    canonical_bytes = canonical_str.encode("utf-8")

    # 7. Compute expected HMAC-SHA256 signature
    device_secret_bytes = bytes.fromhex(device.device_secret)
    expected_signature = hmac.new(
        device_secret_bytes,
        canonical_bytes,
        hashlib.sha256,
    ).hexdigest().lower()

    # 8. Constant-time comparison
    if not hmac.compare_digest(x_tradedna_signature.lower(), expected_signature):
        raise UnauthorizedException("Invalid HMAC signature. Payload tampering or key mismatch detected.")

    return device
