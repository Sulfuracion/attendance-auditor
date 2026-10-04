"""Unit tests for configuration loading and validation."""

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_valid_configuration() -> None:
    """Test valid configuration settings."""
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db?sslmode=require",
        JWT_SECRET="a" * 32,
        CORS_ORIGINS=["https://my-app.pages.dev"],
    )
    assert settings.ENVIRONMENT == "development"
    assert settings.docs_enabled is True
    assert settings.is_production is False


def test_settings_requires_ssl_for_database_in_production() -> None:
    """Test that DATABASE_URL without SSL enforcement is rejected in production."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db",
            JWT_SECRET="a" * 32,
            CORS_ORIGINS=["https://my-app.pages.dev"],
        )
    assert "DATABASE_URL must enforce TLS" in str(exc_info.value)


def test_settings_allows_local_sqlite_in_development() -> None:
    """Test that SQLite without SSL is permitted in development mode."""
    settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="sqlite+aiosqlite:///./test_dev.db",
        JWT_SECRET="a" * 32,
        CORS_ORIGINS=["https://my-app.pages.dev"],
    )
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./test_dev.db"


def test_settings_jwt_secret_min_length() -> None:
    """Test that short JWT secrets are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="development",
            DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db?sslmode=require",
            JWT_SECRET="short_secret",
            CORS_ORIGINS=["https://my-app.pages.dev"],
        )
    assert "JWT_SECRET" in str(exc_info.value)


def test_settings_cors_origins_validation() -> None:
    """Test that arbitrary unauthorized domains are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="development",
            DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db?sslmode=require",
            JWT_SECRET="a" * 32,
            CORS_ORIGINS=["https://malicious-site.com"],
        )
    assert "Cloudflare Pages" in str(exc_info.value)


def test_settings_production_disables_docs() -> None:
    """Test that production mode disables public OpenAPI docs."""
    settings = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db?sslmode=require",
        JWT_SECRET="a" * 32,
        CORS_ORIGINS=["https://attendance-auditor.pages.dev"],
    )
    assert settings.is_production is True
    assert settings.docs_enabled is False
