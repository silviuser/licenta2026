"""``python -m api`` entry point.

Thin uvicorn driver that reads :class:`api.settings.ApiSettings`
from the environment and starts the server. Production deployments
typically run ``uvicorn api.main:app`` directly (so the supervisor
can manage workers / reloads) — this module exists for local dev
convenience and as a documented entry point in
``api/README.md``.
"""

from __future__ import annotations


def _run() -> None:  # pragma: no cover — exercised only as a script.
    """Start uvicorn with the configured host / port / worker count."""
    import uvicorn

    from api.settings import ApiSettings

    settings = ApiSettings()
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        log_level=settings.log_level,
    )


if __name__ == "__main__":  # pragma: no cover
    _run()
