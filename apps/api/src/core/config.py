from functools import lru_cache
from typing import Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Environment
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")
    DEBUG: bool = Field(default=False)

    # Service metadata
    SERVICE_NAME: str = "tradedna-api"
    SERVICE_VERSION: str = "1.0.0"

    # Application URLs
    APP_BASE_URL: str = Field(default="http://localhost:3000")
    API_BASE_URL: str = Field(default="http://localhost:8000")
    API_V1_PREFIX: str = Field(default="/api/v1")

    # Security & Cryptography
    JWT_SECRET: str = Field(default="dev_insecure_jwt_secret_must_be_overridden_in_production_min32")
    JWT_REFRESH_SECRET: str = Field(default="dev_insecure_jwt_refresh_secret_must_be_overridden_min32")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Pairing Token Security
    PAIRING_TOKEN_EXPIRE_MINUTES: int = 5
    PAIRING_MAX_ATTEMPTS_PER_HOUR: int = 3

    # Observability & Metrics Security
    METRICS_KEY: str = Field(default="tradedna_internal_metrics_key_default")

    # Database
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_USER: str = Field(default="tradedna_user")
    POSTGRES_PASSWORD: str = Field(default="tradedna_secure_password")
    POSTGRES_DB: str = Field(default="tradedna_db")

    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./tradedna_dev.db"
    )
    DATABASE_URL_SYNC: Optional[str] = Field(
        default="sqlite:///./tradedna_dev.db"
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30


    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_SOCKET_TIMEOUT: int = 5

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    # Cookie & Browser Security
    COOKIE_SECURE: bool = Field(default=False)
    COOKIE_SAMESITE: str = Field(default="lax")
    COOKIE_DOMAIN: Optional[str] = Field(default=None)
    SECURE_HEADERS_ENABLED: bool = Field(default=True)
    HSTS_ENABLED: bool = Field(default=False)

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        """Strict validation of security-critical configuration for production environments."""
        if self.ENVIRONMENT == "production":
            # 1. Reject default/insecure JWT secrets
            if (
                "insecure" in self.JWT_SECRET.lower()
                or "dev" in self.JWT_SECRET.lower()
                or len(self.JWT_SECRET) < 32
            ):
                raise ValueError(
                    "CRITICAL: Production JWT_SECRET must be a secure cryptographic string of at least 32 characters."
                )

            if (
                "insecure" in self.JWT_REFRESH_SECRET.lower()
                or "dev" in self.JWT_REFRESH_SECRET.lower()
                or len(self.JWT_REFRESH_SECRET) < 32
            ):
                raise ValueError(
                    "CRITICAL: Production JWT_REFRESH_SECRET must be a secure cryptographic string of at least 32 characters."
                )

            # 2. Reject SQLite in production
            if "sqlite" in self.DATABASE_URL.lower():
                raise ValueError(
                    "CRITICAL: SQLite is not permitted in production. Must use production PostgreSQL database."
                )

            # 3. Reject DEBUG mode in production
            if self.DEBUG:
                raise ValueError("CRITICAL: DEBUG mode must be disabled in production.")

            # 4. Require secure cookies and HSTS in production
            if not self.COOKIE_SECURE:
                raise ValueError("CRITICAL: COOKIE_SECURE must be enabled (True) in production.")

            if not self.HSTS_ENABLED:
                raise ValueError("CRITICAL: HSTS_ENABLED must be enabled (True) in production.")

            # 5. Reject wildcard CORS in production
            for origin in self.ALLOWED_ORIGINS:
                if origin == "*" or "localhost" in origin or "127.0.0.1" in origin:
                    raise ValueError(
                        f"CRITICAL: Insecure CORS origin '{origin}' is not permitted in production."
                    )

        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

