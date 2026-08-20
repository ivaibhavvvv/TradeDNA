"""
TradeDNA Backup & Disaster Recovery Management API Endpoints
Provides authenticated, privileged backup listing, creation, verification, and safety-gated restore.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db_session
from src.core.dependencies import get_current_user
from src.core.exceptions import NotFoundException, ForbiddenException
from src.core.backup import BackupManager, backup_manager
from src.core.metrics import metrics
from src.models.user import User
from src.models.audit import AuditLog

router = APIRouter(prefix="/backups", tags=["Disaster Recovery & Backups"])


class RestoreRequest(BaseModel):
    emergency_override: bool = False
    override_reason: Optional[str] = None


@router.get("", status_code=status.HTTP_200_OK)
async def list_backups(
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Lists available backup archives and their manifest metadata."""
    backups_root = Path(getattr(settings, "BACKUP_DIR", "backups"))
    if not backups_root.exists():
        return []

    manifests = []
    for m_file in sorted(backups_root.rglob("manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(m_file, "r", encoding="utf-8") as f:
                manifests.append(json.load(f))
        except Exception:
            pass

    return manifests


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_backup(
    backup_type: str = Query("FULL", enum=["FULL", "INCREMENTAL"]),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Generates an automated database backup with deterministic checksums."""
    now_str = datetime_str = Path("backups") / time_dir()
    manifest = BackupManager.create_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        output_dir=str(now_str),
        backup_type=backup_type,
    )
    metrics.record_backup(
        success=True,
        verified=False,
        duration_ms=manifest.get("duration_ms", 0.0),
        size_bytes=manifest.get("file_size_bytes", 0),
    )

    # Log Audit Event
    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        event_type="BACKUP_COMPLETED",
        payload={
            "backup_id": manifest["backup_id"],
            "backup_type": backup_type,
            "file_size_bytes": manifest["file_size_bytes"],
            "sha256": manifest["sha256"],
        },
    )
    session.add(audit)
    await session.commit()

    return manifest


def time_dir() -> str:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%Y')}/{now.strftime('%m')}/{now.strftime('%d')}/backup_{now.strftime('%Y%m%d_%H%M%S')}"


@router.post("/{backup_id}/verify", status_code=status.HTTP_200_OK)
async def verify_backup(
    backup_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Verifies a backup archive's SHA-256 and financial integrity signatures."""
    backups_root = Path("backups")
    target_dir = None
    for m_file in backups_root.rglob("manifest.json"):
        try:
            with open(m_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("backup_id") == backup_id:
                    target_dir = m_file.parent
                    break
        except Exception:
            pass

    if not target_dir:
        raise NotFoundException(f"Backup {backup_id} not found.")

    is_valid, report = BackupManager.verify_backup(str(target_dir))
    metrics.record_backup(
        success=is_valid,
        verified=is_valid,
        duration_ms=report.get("duration_ms", 0.0),
        size_bytes=report.get("file_size_bytes", 0),
    )

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        event_type="BACKUP_VERIFIED" if is_valid else "BACKUP_CORRUPTED",
        payload={"backup_id": backup_id, "is_valid": is_valid, "report": report},
    )
    session.add(audit)
    await session.commit()

    return {"is_valid": is_valid, "report": report}


@router.post("/{backup_id}/restore", status_code=status.HTTP_200_OK)
async def restore_backup(
    backup_id: str,
    body: RestoreRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Executes database restoration protected by safety gates."""
    backups_root = Path("backups")
    target_dir = None
    for m_file in backups_root.rglob("manifest.json"):
        try:
            with open(m_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("backup_id") == backup_id:
                    target_dir = m_file.parent
                    break
        except Exception:
            pass

    if not target_dir:
        raise NotFoundException(f"Backup {backup_id} not found.")

    t0 = time.perf_counter()
    summary = BackupManager.restore_backup(
        sync_db_url=settings.DATABASE_URL_SYNC,
        backup_dir=str(target_dir),
        emergency_override=body.emergency_override,
        override_reason=body.override_reason,
    )
    dur_ms = (time.perf_counter() - t0) * 1000.0
    metrics.record_restore(success=True, duration_ms=dur_ms)

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        event_type="RESTORE_COMPLETED",
        payload={
            "backup_id": backup_id,
            "emergency_override": body.emergency_override,
            "override_reason": body.override_reason,
            "restored_tables": summary,
            "duration_ms": round(dur_ms, 2),
        },
    )
    session.add(audit)
    await session.commit()

    return {
        "success": True,
        "backup_id": backup_id,
        "restored_tables": summary,
        "duration_ms": round(dur_ms, 2),
    }
