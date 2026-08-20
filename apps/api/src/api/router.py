from fastapi import APIRouter
from src.api.v1 import alerts, analytics, auth, backups, canonical, connections, dashboard, exness, health, onboarding, reconciliation

api_v1_router = APIRouter(prefix="/api/v1")

# Mount Route Handlers
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(onboarding.router)
api_v1_router.include_router(connections.router)
api_v1_router.include_router(exness.router)
api_v1_router.include_router(canonical.router, prefix="/canonical", tags=["Canonical Reconstruction & Ledger"])
api_v1_router.include_router(reconciliation.router)
api_v1_router.include_router(analytics.router)
api_v1_router.include_router(dashboard.router)
api_v1_router.include_router(alerts.router)
api_v1_router.include_router(backups.router)



