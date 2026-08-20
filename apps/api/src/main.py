import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.api.router import api_v1_router
from src.core.config import get_settings
from src.core.exceptions import TradeDNAException
from src.core.logging import logger, setup_logging

settings = get_settings()


from src.core.database import check_db_health, engine, init_db_schema


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle initialization and teardown."""
    setup_logging(log_level=settings.LOG_LEVEL)
    logger.info(
        f"Starting {settings.SERVICE_NAME} v{settings.SERVICE_VERSION} in {settings.ENVIRONMENT} mode"
    )
    # 1. Startup validation
    try:
        settings.validate_production_configuration()
    except Exception as e:
        logger.error(f"Startup configuration error: {e}")
        raise

    # 2. Database readiness check and schema initialization on startup
    db_ok = await check_db_health()
    if db_ok:
        logger.info("Database connectivity established successfully.")
        await init_db_schema()
        # Ensure default personal workspace user exists
        try:
            from sqlalchemy import select
            from src.core.database import async_session_factory
            from src.core.security import hash_password
            from src.models.user import User
            from src.models.tenant import Tenant

            async with async_session_factory() as db:
                stmt = select(User).where(User.email == "vaibhav251001@gmail.com")
                res = await db.execute(stmt)
                user = res.scalar_one_or_none()
                if not user:
                    tenant = Tenant(name="Vaibhav Chauhan's Workspace")
                    db.add(tenant)
                    await db.flush()
                    user = User(
                        tenant_id=tenant.id,
                        email="vaibhav251001@gmail.com",
                        password_hash=hash_password("TradeDNA@2026"),
                        full_name="Vaibhav Chauhan",
                        is_active=True,
                        is_verified=True,
                    )
                    db.add(user)
                    await db.commit()
                    logger.info("Default personal user seeded successfully.")
        except Exception as e:
            logger.warning(f"Default user seeding check notice: {e}")
    else:
        logger.warning("Database connectivity check failed on startup. Service running in degraded state.")

    yield

    # 3. Graceful shutdown: Dispose database engine connection pool
    logger.info(f"Shutting down {settings.SERVICE_NAME}: Disposing database connection pools...")
    try:
        await engine.dispose()
        logger.info("Database connection pools closed successfully.")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")
    logger.info(f"{settings.SERVICE_NAME} shutdown complete.")



app = FastAPI(
    title="TradeDNA API",
    description="Exness Trading Intelligence Platform API — Strictly Read-Only",
    version=settings.SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware (Hardened allowlist, no wildcard origins with credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


import time
from src.core.metrics import metrics


@app.middleware("http")
async def security_headers_and_logging_middleware(request: Request, call_next):
    """Middleware attaching request_id, latency tracking, metrics recording, and production security headers."""
    t0 = time.perf_counter()
    raw_request_id = request.headers.get("X-Request-ID", "").strip()
    if raw_request_id and len(raw_request_id) <= 64 and all(c.isalnum() or c in "-_" for c in raw_request_id):
        request_id = raw_request_id
    else:
        request_id = str(uuid.uuid4())

    request.state.request_id = request_id
    metrics.active_requests += 1

    try:
        response = await call_next(request)
    finally:
        metrics.active_requests = max(0, metrics.active_requests - 1)

    latency_ms = (time.perf_counter() - t0) * 1000.0
    metrics.record_request(response.status_code, latency_ms)
    response.headers["X-Request-ID"] = request_id

    if settings.SECURE_HEADERS_ENABLED:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(), payment=()"
        if settings.ENVIRONMENT == "production":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https:; "
                "object-src 'none'; "
                "frame-ancestors 'none'; "
                "base-uri 'self';"
            )
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:; "
                "connect-src 'self' http://localhost:* ws://localhost:*; "
                "object-src 'none'; "
                "frame-ancestors 'none'; "
                "base-uri 'self';"
            )
            if settings.HSTS_ENABLED:
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    return response



# Global Exception Handlers (Suppresses stack traces, database parameters, and internal secrets)
@app.exception_handler(TradeDNAException)
async def handle_tradedna_exception(request: Request, exc: TradeDNAException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
                "details": exc.details,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    # Sanitize any sensitive input from validation error output
    sanitized_errors = []
    for err in exc.errors():
        err_copy = dict(err)
        if any(s in str(err_copy.get("loc", "")).lower() for s in ("password", "secret", "token")):
            err_copy["input"] = "[REDACTED]"
        sanitized_errors.append(err_copy)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters or payload",
                "request_id": request_id,
                "details": {"errors": sanitized_errors},
            },
        },
    )


@app.exception_handler(Exception)
async def handle_unhandled_exception(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.exception(f"Unhandled server error [request_id={request_id}]: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal server error occurred.",
                "request_id": request_id,
            },
        },
    )


# Mount API Routers
app.include_router(api_v1_router)

from src.api.v1.health import get_health, get_readiness

# Root-level health probes for orchestrators / load balancers
app.add_api_route("/health", get_health, methods=["GET"], tags=["Health"], include_in_schema=False)
app.add_api_route("/health/live", get_health, methods=["GET"], tags=["Health"], include_in_schema=False)
app.add_api_route("/health/ready", get_readiness, methods=["GET"], tags=["Health"], include_in_schema=False)


@app.get("/metrics", tags=["Observability"], summary="System Metrics Snapshot")
@app.get("/api/v1/metrics", tags=["Observability"], summary="System Metrics Snapshot Alias")
async def get_metrics(request: Request):
    """
    Protected operational metrics endpoint.
    In production mode, requires matching 'X-Metrics-Key' header.
    Exposes zero tenant financial records, secrets, or raw trading events.
    """
    if settings.ENVIRONMENT == "production":
        provided_key = request.headers.get("X-Metrics-Key", "")
        if not provided_key or provided_key != settings.METRICS_KEY:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN_METRICS_ACCESS",
                        "message": "Access to internal system metrics is forbidden.",
                        "request_id": getattr(request.state, "request_id", ""),
                    },
                },
            )
    return metrics.get_snapshot()


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "tagline": "Decode Your Trading.",
        "docs": "/docs",
    }


