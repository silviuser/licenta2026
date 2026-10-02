"""Request-ID + timing middlewares.

Both are tiny pure-ASGI implementations so they don't pull in
additional starlette deps. They run in the order:

1. ``RequestIDMiddleware`` first: extract or mint a request ID,
   stash it on ``request.state``, bind it to structlog's contextvars
   so every log line for this request carries the same correlation
   ID. Echo back on the response header.
2. ``TimingMiddleware`` second: measure wall-clock time, emit one
   INFO log per request, set ``X-Process-Time-Ms`` on the response.

The order matters: timing wraps the (ID-bound) handler so the timing
log line carries the request_id field, and the response header order
is stable.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.requests import Request


logger = structlog.get_logger("api.request")


# ---------------------------------------------------------------------------
# RequestIDMiddleware
# ---------------------------------------------------------------------------


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Bind a correlation ID to every request.

    Reads the configured request-ID header from the incoming request
    (falling back to a generated UUID4 when absent), stashes the ID
    on ``request.state.request_id`` and on structlog's contextvars,
    and echoes the ID back on the response under the same header
    name.
    """

    def __init__(self, app: ASGIApp, *, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get(self.header_name)
        request_id = incoming if incoming else uuid.uuid4().hex
        request.state.request_id = request_id

        # Bind to structlog so every log line in this request carries
        # the same correlation field. ``bind_contextvars`` is
        # task-local under asyncio, so concurrent requests don't bleed.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers[self.header_name] = request_id
        return response


# ---------------------------------------------------------------------------
# TimingMiddleware
# ---------------------------------------------------------------------------


class TimingMiddleware(BaseHTTPMiddleware):
    """Measure wall-clock time per request.

    Emits one INFO log line per request with ``(method, path, status,
    duration_ms)`` and adds an ``X-Process-Time-Ms`` header to the
    response.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        logger.info(
            "api.request.handled",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=elapsed_ms,
        )
        return response


__all__ = ["RequestIDMiddleware", "TimingMiddleware"]
