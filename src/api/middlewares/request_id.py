"""Request ID Traceability Middleware.

Generates or validates a unique UUIDv4 per request, stores it in contextvars
and request state, and attaches it to response headers.
"""

import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable accessible across async tasks and logging formatters
request_id_ctx_var: ContextVar[str | None] = ContextVar("request_id_ctx_var", default=None)

# Pattern to validate existing client-provided X-Request-ID to prevent header injection
SAFE_REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns and propagates a unique request_id across the request-response lifecycle."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process incoming request, set request ID, and attach to response headers."""
        incoming_id = request.headers.get("X-Request-ID")
        if incoming_id and SAFE_REQUEST_ID_REGEX.match(incoming_id):
            request_id = incoming_id
        else:
            request_id = str(uuid4())

        # Set in context variable and request state
        token = request_id_ctx_var.set(request_id)
        request.state.request_id = request_id

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx_var.reset(token)
