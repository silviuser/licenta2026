"""Structlog setup for the FastAPI service.

Mirrors :func:`cv_extractor.utils.logging.configure_logging` so log
output from Module 1 / Module 2 / Module 3 / the API surface all flow
through the same renderer and share fields (``timestamp``,
``logger_name``, ``level``). Called once from ``create_app`` (and
again per-test from the ``conftest.py`` fixtures); ``structlog`` is
idempotent under re-configuration.

The console renderer is used in all environments. JSON output is left
to the reverse proxy / log shipper (e.g. Vector, Promtail) — keeping
the service-side format human-readable simplifies dev-box debugging
and avoids leaking a renderer choice into the public contract.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "info") -> None:
    """Configure structlog with a console renderer rooted at ``level``.

    Args:
        level: Standard log level — ``"debug"``, ``"info"``,
            ``"warning"``, ``"error"``. Case-insensitive.
    """
    level_upper = level.upper()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Clear stale handlers so repeat calls (per-test) don't double-emit.
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, level_upper, logging.INFO))


__all__ = ["configure_logging"]
