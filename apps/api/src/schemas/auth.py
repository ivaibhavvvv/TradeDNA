import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters")
    full_name: str = Field(min_length=1, max_length=255)
    tenant_name: Optional[str] = Field(default=None, max_length=255)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenRefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_verified: bool
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_agent: str
    ip_address: str
    is_current: bool = False
    is_revoked: bool
    created_at: datetime
    last_activity_at: datetime


class MessageResponse(BaseModel):
    success: bool
    message: str
