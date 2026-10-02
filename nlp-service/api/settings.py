"""Runtime configuration for the HR Helper NLP FastAPI service.

Step 10 deliverable. All knobs are env-var overridable with the
``HRHELPER_API_`` prefix so deployment platforms (systemd, Docker,
Kubernetes ConfigMap) can configure the service without code changes.
Defaults are tuned for a single-process dev box; production
deployments override ``host``, ``port``, ``workers`` and
``cors_allow_origins`` as needed.

The settings object is the single source of truth for ``create_app``.
Tests pass a hand-constructed ``ApiSettings(...)`` to ``create_app``
so they can opt out of warm-up (``warmup_on_startup=False``) and
exercise per-test isolation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Runtime configuration for the FastAPI service.

    Environment variable prefix: ``HRHELPER_API_``. Example::

        HRHELPER_API_PORT=8080 HRHELPER_API_WARMUP_ON_STARTUP=false \\
            uvicorn api.main:app
    """

    model_config = SettingsConfigDict(
        env_prefix="HRHELPER_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Network ---------------------------------------------------------
    host: str = Field(
        default="0.0.0.0",  # noqa: S104 — binding to all interfaces is the
        # canonical default for a containerised HTTP service; restrict via
        # firewall / reverse proxy at deploy time.
        description="Interface uvicorn binds to.",
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description=(
            "TCP port. Default 8000 is the FastAPI canonical port. The "
            "future Java Spring Boot backend uses 8080 in dev, so the "
            "two services do not collide when both run locally."
        ),
    )
    workers: int = Field(
        default=1,
        ge=1,
        le=64,
        description=(
            "Number of uvicorn workers. Defaults to 1: each worker "
            "loads its own copy of the encoder (~500 MB) so increasing "
            "this multiplies the memory footprint. Scale horizontally "
            "across hosts before scaling workers within one host."
        ),
    )

    # --- Lifecycle -------------------------------------------------------
    warmup_on_startup: bool = Field(
        default=True,
        description=(
            "Eagerly load Module 1 / Module 2 / Module 3 components in "
            "the FastAPI lifespan startup hook. Pays the ~5-10 s warm "
            "cache cost (or ~30-60 s cold cache cost) once at process "
            "start instead of on the first request. Disable during "
            "development with ``uvicorn --reload`` to avoid paying it "
            "on every reload."
        ),
    )

    # --- Logging ---------------------------------------------------------
    log_level: Literal["debug", "info", "warning", "error"] = Field(
        default="info",
        description="Root structlog log level.",
    )

    # --- Request metadata ------------------------------------------------
    request_id_header: str = Field(
        default="X-Request-ID",
        min_length=1,
        description=(
            "HTTP header carrying the per-request correlation ID. "
            "Echoed back on the response so callers can correlate "
            "their client-side logs with the service-side structured "
            "logs."
        ),
    )

    # --- Upload limits ---------------------------------------------------
    max_pdf_size_mb: int = Field(
        default=20,
        ge=1,
        le=200,
        description=(
            "Maximum upload size for ``POST /v1/extract`` and "
            "``POST /v1/full``. Default 20 MB is generous: the largest "
            "fixture in the eval corpus is ~340 KB, so 20 MB allows "
            "for very high-DPI scans without further tuning."
        ),
    )

    # --- CORS ------------------------------------------------------------
    cors_allow_origins: list[str] = Field(
        default_factory=list,
        description=(
            "Allowed CORS origins. Empty (default) disables CORS "
            "entirely — production deployments go behind a reverse "
            "proxy that handles CORS itself. Override at dev time "
            'with e.g. ``HRHELPER_API_CORS_ALLOW_ORIGINS=\'["http://'
            'localhost:3000"]\'`` for a React/Vue frontend.'
        ),
    )

    @property
    def max_pdf_size_bytes(self) -> int:
        """Convenience: ``max_pdf_size_mb`` in bytes."""
        return self.max_pdf_size_mb * 1024 * 1024


__all__ = ["ApiSettings"]
