"""FastAPI application entry point for Attendance Auditor."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.middlewares.logging_filter import setup_secure_logging
from src.api.middlewares.request_id import RequestIDMiddleware
from src.api.middlewares.security_headers import SecurityHeadersMiddleware
from src.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and shutdown procedures."""
    settings = get_settings()
    setup_secure_logging(level=settings.LOG_LEVEL)
    yield


def create_application() -> FastAPI:
    """Instantiate and configure the FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title="Attendance Auditor API",
        description="Vectorized Attendance Auditing and Labor Reconciliation Service",
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    # 1. Traceability Middleware (Generates/Propagates X-Request-ID)
    app.add_middleware(RequestIDMiddleware)

    # 2. HTTP Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # 3. Restricted CORS Middleware (Strictly Cloudflare Pages & Local Dev)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.get("/health", tags=["Health"])
    async def health_check(request: Request) -> JSONResponse:
        """Liveness probe returning service status and active request ID."""
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "environment": settings.ENVIRONMENT,
                "request_id": request_id,
            },
        )

    # Include domain routers
    from src.api.routers.attendance import router as attendance_router
    from src.api.routers.auth import router as auth_router

    app.include_router(auth_router)
    app.include_router(attendance_router)

    return app


app = create_application()
