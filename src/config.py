"""Application configuration module using pydantic-settings.

Enforces zero-hardcoding, environment-based loading, and validation:
- Enforces strict PostgreSQL TLS ('sslmode=require') in production.
- Allows async SQLite or local PostgreSQL in development and testing.
- Restricts CORS to Cloudflare Pages (*.pages.dev) and localhost.
"""

from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Vite dev server origins for the local SPA (frontend/), allowed only outside production.
LOCAL_FRONTEND_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


class Settings(BaseSettings):
    """Application settings with environment-aware security validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Environment & Logging
    ENVIRONMENT: Literal["development", "production", "testing"] = "development"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Database Configuration (Neon.tech PostgreSQL with TLS in prod; SQLite/Postgres in dev)
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./attendance_dev.db",
        description="Async DB connection URL (TLS mandatory in production mode)",
    )

    # Security & Cryptography
    JWT_SECRET: str = Field(
        ...,
        min_length=32,
        description="Cryptographically secure key for JWT signature (min 32 chars)",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1, le=1440)

    # CORS Origins (Restricted explicitly to Cloudflare Pages domains)
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["https://attendance-auditor.pages.dev"],
        description="Allowed CORS origins list, restricted to Cloudflare Pages in production",
    )

    # Uploads limits (Directriz 5: Máx 10 MB)
    MAX_UPLOAD_SIZE_BYTES: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum allowed upload file size in bytes (default 10 MB)",
    )

    @model_validator(mode="after")
    def validate_database_url_policy(self) -> "Settings":
        """Validate database URL according to environment mode."""
        parsed = urlparse(self.DATABASE_URL)
        scheme = parsed.scheme.lower()

        if self.is_production:
            if not (scheme.startswith("postgresql") or scheme.startswith("postgres")):
                raise ValueError(
                    "In production, DATABASE_URL must be a PostgreSQL connection URL"
                )

            query_params = parse_qs(parsed.query)
            sslmode = query_params.get("sslmode", [None])[0]
            ssl = query_params.get("ssl", [None])[0]

            is_ssl_required = (
                sslmode in ("require", "verify-ca", "verify-full")
                or ssl in ("require", "true")
            )

            if not is_ssl_required:
                raise ValueError(
                    "DATABASE_URL must enforce TLS with 'sslmode=require' in production mode."
                )
        else:
            is_valid_scheme = (
                scheme.startswith("postgresql")
                or scheme.startswith("postgres")
                or scheme.startswith("sqlite")
            )
            if not is_valid_scheme:
                raise ValueError(
                    "DATABASE_URL must be a PostgreSQL or SQLite connection URL."
                )

            # Local SPA (Vite) origins are always permitted outside production.
            for dev_origin in LOCAL_FRONTEND_ORIGINS:
                if dev_origin not in self.CORS_ORIGINS:
                    self.CORS_ORIGINS.append(dev_origin)

        return self

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        """Ensure CORS origins adhere to allowed Cloudflare Pages or valid secure schemes."""
        if not origins:
            raise ValueError("CORS_ORIGINS cannot be empty")

        for origin in origins:
            parsed = urlparse(origin)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError(f"Invalid origin format: '{origin}'")

            netloc = parsed.netloc.lower()
            is_cloudflare_pages = netloc.endswith(".pages.dev")
            is_local = (
                netloc in ("localhost", "127.0.0.1")
                or netloc.startswith("localhost:")
                or netloc.startswith("127.0.0.1:")
            )

            if not (is_cloudflare_pages or is_local):
                raise ValueError(
                    f"Origin '{origin}' is not authorized. Must be Cloudflare Pages or localhost."
                )

        return origins

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == "production"

    @property
    def docs_enabled(self) -> bool:
        """Disable public OpenAPI docs and ReDoc in production mode."""
        return not self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve and cache settings singleton."""
    return Settings()
