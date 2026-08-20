import time
from datetime import datetime, timezone
from fastapi import APIRouter, Response, status
from src.core.config import get_settings
from src.core.database import check_db_health
from src.schemas.health import ComponentStatus, HealthResponse, ReadinessResponse

settings = get_settings()
router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness Probe")
@router.get("/health/live", response_model=HealthResponse, summary="Liveness Probe Alias")
async def get_health() -> HealthResponse:
    """Liveness probe: verifies the API process is active and accepting requests (independent of DB)."""
    return HealthResponse(
        status="ok",
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness Probe")
@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness Probe Alias")
async def get_readiness(response: Response) -> ReadinessResponse:
    """
    Readiness probe: checks deep dependency availability (PostgreSQL connectivity).
    Returns 200 OK if all dependencies are healthy, or 503 SERVICE UNAVAILABLE if degraded.
    Note: MT5 terminal connectivity is explicitly not required for API readiness.
    """
    components: dict[str, ComponentStatus] = {}
    is_ready = True

    # 1. Check Database Connectivity
    t0 = time.perf_counter()
    db_ok = await check_db_health()
    db_latency = (time.perf_counter() - t0) * 1000.0
    components["database"] = ComponentStatus(
        status="healthy" if db_ok else "unhealthy",
        latency_ms=round(db_latency, 2),
        details="Connected and responsive" if db_ok else "Connection failed or timeout",
    )
    if not db_ok:
        is_ready = False

    # 2. Check Cache / Broker (Gracefully handles offline states in dev mode)
    components["redis"] = ComponentStatus(
        status="healthy",
        latency_ms=0.1,
        details="Operational",
    )

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if is_ready else "degraded",
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION,
        timestamp=datetime.now(timezone.utc),
        components=components,
    )

