import uuid
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.logging import logger
from src.models.audit import AuditLog


async def log_security_event(
    db: AsyncSession,
    event_type: str,
    ip_address: str = "",
    user_agent: str = "",
    tenant_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    payload: Optional[dict[str, Any]] = None,
) -> AuditLog:
    """
    Persist an audit log entry to the database and log to structured logging.
    Guarantees that sensitive credentials (passwords, tokens) are never included.
    """
    clean_payload = dict(payload or {})
    # Filter any accidental sensitive keys
    sensitive_keys = {"password", "token", "refresh_token", "secret", "jwt", "access_token"}
    for key in list(clean_payload.keys()):
        if any(sens in key.lower() for sens in sensitive_keys):
            clean_payload[key] = "[REDACTED]"

    audit_entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=event_type,
        ip_address=ip_address,
        user_agent=user_agent,
        payload=clean_payload,
    )
    db.add(audit_entry)
    await db.flush()

    logger.info(
        f"Security Event: [{event_type}] user_id={user_id} tenant_id={tenant_id} ip={ip_address}"
    )
    return audit_entry
