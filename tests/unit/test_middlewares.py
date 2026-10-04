"""Unit tests for security middlewares and logging filters."""

import logging
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from src.api.middlewares.logging_filter import SensitiveDataFilter
from src.api.middlewares.request_id import RequestIDMiddleware
from src.api.middlewares.security_headers import SecurityHeadersMiddleware


@pytest.mark.asyncio
async def test_security_headers_middleware() -> None:
    """Ensure security headers middleware sets required defense-in-depth headers."""
    middleware = SecurityHeadersMiddleware(app=MagicMock())
    request = MagicMock(spec=Request)

    async def call_next(_req: Request) -> Response:
        return Response(content="ok", media_type="text/plain")

    response = await middleware.dispatch(request, call_next)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in response.headers
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_request_id_middleware_generates_id() -> None:
    """Ensure a unique request ID is generated when none is provided."""
    middleware = RequestIDMiddleware(app=MagicMock())
    request = MagicMock(spec=Request)
    request.headers = {}
    request.state = MagicMock()

    async def call_next(req: Request) -> Response:
        assert getattr(req.state, "request_id", None) is not None
        return Response(content="ok", media_type="text/plain")

    response = await middleware.dispatch(request, call_next)
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) >= 32


@pytest.mark.asyncio
async def test_request_id_middleware_preserves_valid_id() -> None:
    """Ensure a safe user-supplied request ID is preserved."""
    middleware = RequestIDMiddleware(app=MagicMock())
    request = MagicMock(spec=Request)
    custom_id = "trace-abc-12345"
    request.headers = {"X-Request-ID": custom_id}
    request.state = MagicMock()

    async def call_next(_req: Request) -> Response:
        return Response(content="ok", media_type="text/plain")

    response = await middleware.dispatch(request, call_next)
    assert response.headers["X-Request-ID"] == custom_id


def test_sensitive_data_filter_redacts_tokens_and_passwords() -> None:
    """Ensure SensitiveDataFilter redacts JWTs, Bearer tokens, and passwords."""
    log_filter = SensitiveDataFilter()
    sample_msg = (
        'User auth "password": "SuperSecretPassword123" and '
        "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.xyz"
    )
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg=sample_msg,
        args=(),
        exc_info=None,
    )

    log_filter.filter(record)
    assert "SuperSecretPassword123" not in record.msg
    assert "[REDACTED]" in record.msg
    assert "[REDACTED_TOKEN]" in record.msg or "[REDACTED_JWT]" in record.msg
