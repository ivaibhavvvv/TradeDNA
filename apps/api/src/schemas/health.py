from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", json_schema_extra={"example": "ok"})
    service: str = Field(default="tradedna-api")
    version: str = Field(default="1.0.0")
    timestamp: datetime


class ComponentStatus(BaseModel):
    status: str = Field(json_schema_extra={"example": "healthy"})
    latency_ms: Optional[float] = None
    details: Optional[str] = None


class ReadinessResponse(BaseModel):
    status: str = Field(json_schema_extra={"example": "ready"})
    service: str = Field(default="tradedna-api")
    version: str = Field(default="1.0.0")
    timestamp: datetime
    components: dict[str, ComponentStatus]
