"""FastAPI application construction.

The brief mandates a ``create_app()`` factory: tests build isolated
apps per TestClient (so dependency overrides don't bleed between
tests), while production runs use the module-level ``app`` instance
built from default settings.

App composition order (matters for middleware semantics):

1. Logging configured first so the lifespan startup messages render.
2. Middlewares added in the order documented in
   :mod:`api.middleware` — RequestID first, Timing second.
3. CORS added last (and only when ``settings.cors_allow_origins`` is
   non-empty) so it wraps everything.
4. Routers mounted under ``/v1``.

The OpenAPI doc surfaces the Romanian thesis title in the
description per the Step 10 sign-off (Q3 decision).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.lifespan import create_lifespan
from api.logging_config import configure_logging
from api.middleware import RequestIDMiddleware, TimingMiddleware
from api.routers import (
    extract_jd_router,
    extract_router,
    full_router,
    health_router,
    info_router,
    match_router,
)
from api.settings import ApiSettings

_OPENAPI_DESCRIPTION = (
    "HTTP service for CV ↔ Job Description semantic matching. "
    "Thesis project: „APLICAȚIE DE ANALIZĂ ȘI EVALUARE AUTOMATĂ "
    "A CV-URILOR BAZATĂ PE INTELIGENȚĂ ARTIFICIALĂ\" "
    "(ASE / CSIE Bucharest, 2026)."
)


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build and return the FastAPI application.

    Args:
        settings: Optional override. When ``None`` (the production
            default), settings load from env vars with prefix
            ``HRHELPER_API_``.

    Returns:
        A fully wired FastAPI app. Idempotent: each call returns a
        fresh app instance so tests can run dependency-override
        cycles in isolation.
    """
    settings = settings if settings is not None else ApiSettings()
    configure_logging(settings.log_level)

    # ``api.__version__`` is the OpenAPI ``info.version`` field — the
    # API surface's own version, independent of skill_matcher's.
    from api import __version__ as api_version

    app = FastAPI(
        title="HR Helper NLP Service",
        version=api_version,
        description=_OPENAPI_DESCRIPTION,
        lifespan=create_lifespan(settings),
    )

    # Middlewares — order is significant. starlette adds middlewares
    # in reverse-execution order: the last ``add_middleware`` runs
    # first on the way in. We want RequestID to run first so the
    # timing log line and the response header both see the bound ID,
    # so RequestID is added LAST.
    app.add_middleware(TimingMiddleware)
    app.add_middleware(
        RequestIDMiddleware,
        header_name=settings.request_id_header,
    )

    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

    # Routers — all under /v1.
    app.include_router(health_router, prefix="/v1", tags=["health"])
    app.include_router(info_router, prefix="/v1", tags=["info"])
    app.include_router(extract_router, prefix="/v1", tags=["extract"])
    app.include_router(extract_jd_router, prefix="/v1", tags=["extract"])
    app.include_router(match_router, prefix="/v1", tags=["match"])
    app.include_router(full_router, prefix="/v1", tags=["full"])

    return app


# Module-level production instance — what ``uvicorn api.main:app``
# loads.
app = create_app()


__all__ = ["app", "create_app"]
