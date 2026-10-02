"""FastAPI lifespan handler — model warm-up and shutdown plumbing.

The lifespan is an async context manager FastAPI calls once at
process start (before the first request) and once at shutdown (after
the last response). We use it to:

* **Startup** — eagerly call the three ``get_*`` singletons so the
  encoder + ESCO index load cost is paid before the first request
  arrives (when ``settings.warmup_on_startup=True``, the default).
* **Startup** — pre-compute the ESCO concept SHA and stash it on
  ``app.state`` for cheap ``GET /v1/info`` reads.
* **Shutdown** — flush structlog buffers and clear the dependency
  caches so a graceful restart starts cold.

The lifespan is a closure over the settings so tests can build a
lifespan with ``warmup_on_startup=False`` for fast TestClient
instantiation.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from api.deps import (
    clear_dependency_caches,
    get_extraction_pipeline,
    get_skill_extractor,
    get_skill_matcher,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from api.settings import ApiSettings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Mutable state stashed on app.state
# ---------------------------------------------------------------------------


@dataclass
class ApiState:
    """Shared mutable state persisted on ``app.state``.

    Used by routers that need cheap reads of warm-startup-computed
    values (e.g. the ESCO SHA on ``/v1/info``). Computed in the
    lifespan startup branch when ``warmup_on_startup=True``; left
    ``None`` and lazily filled on first request otherwise.
    """

    esco_sha: str | None = None
    encoder_path: str | None = None
    warmup_complete: bool = False


# ---------------------------------------------------------------------------
# Lifespan factory
# ---------------------------------------------------------------------------


def create_lifespan(
    settings: ApiSettings,
) -> Callable[["FastAPI"], AbstractAsyncContextManager[None]]:
    """Return a FastAPI-compatible lifespan async context manager.

    The factory closure captures ``settings`` so test-time apps can
    build a lifespan with ``warmup_on_startup=False`` for cheap
    TestClient instantiation while production apps keep eager warm-up.
    """

    @asynccontextmanager
    async def lifespan(app: "FastAPI") -> AsyncIterator[None]:
        # --- Startup ---------------------------------------------------
        state = ApiState()
        app.state.api_state = state

        if settings.warmup_on_startup:
            start = time.monotonic()
            logger.info("api.lifespan.warmup_start")

            extractor = get_extraction_pipeline()
            skills = get_skill_extractor()
            matcher = get_skill_matcher()

            try:
                matcher._ensure_ready()  # noqa: SLF001 — startup hook.
            except Exception as exc:  # pragma: no cover — defensive.
                logger.warning(
                    "api.lifespan.encoder_warmup_failed", error=str(exc)
                )

            # Exercise the lexical pipeline once so the FIRST real
            # ``/v1/extract`` or ``/v1/extract-jd`` does not pay the spaCy
            # model load + ESCO PhraseMatcher build cost (130s-390s cold on
            # this hardware — observed in the REWORK 1 live smoke test, well
            # beyond the backend's NLP timeout). After this warm-up, real
            # extract calls complete in ~1-3s.
            try:
                _warm_text = "Python developer with Java, SQL and Docker experience."
                _lexical = skills.extract((_warm_text, "en"))
                matcher.link(cv_id="__warmup__", cv_text=_warm_text, lexical=_lexical)
            except Exception as exc:  # pragma: no cover — defensive.
                logger.warning(
                    "api.lifespan.extractor_warmup_failed", error=str(exc)
                )

            # Warm the ROMANIAN PhraseMatcher too. The EN pass above only builds the
            # English matcher; the first Romanian CV would otherwise pay the full
            # ~14k-pattern RO build inline (observed at 2m+ when the on-disk cache was
            # cold after an ESCO refresh), stalling the single-process service and
            # tripping the backend's NLP timeout mid-bulk. Best-effort: a failure here
            # only forgoes the warm-up, it does not block startup.
            try:
                _warm_text_ro = (
                    "Dezvoltator Python cu experiență în Java, SQL și Docker."
                )
                _lexical_ro = skills.extract((_warm_text_ro, "ro"))
                matcher.link(
                    cv_id="__warmup_ro__", cv_text=_warm_text_ro, lexical=_lexical_ro
                )
            except Exception as exc:  # pragma: no cover — defensive.
                logger.warning(
                    "api.lifespan.extractor_warmup_ro_failed", error=str(exc)
                )

            try:
                from skill_matcher.esco_loader import (
                    compute_esco_sha,
                    load_esco_concepts,
                )

                state.esco_sha = compute_esco_sha(load_esco_concepts())[:12]
            except Exception as exc:  # pragma: no cover — defensive.
                logger.warning(
                    "api.lifespan.esco_sha_failed", error=str(exc)
                )

            state.encoder_path = getattr(matcher, "_resolved_model_name", None)
            state.warmup_complete = True

            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "api.lifespan.warmup_complete",
                elapsed_ms=elapsed_ms,
                extractor=type(extractor).__name__,
                skills=type(skills).__name__,
                matcher=type(matcher).__name__,
                encoder_path=state.encoder_path,
                esco_sha=state.esco_sha,
            )
        else:
            logger.info(
                "api.lifespan.lazy_mode",
                reason="warmup_on_startup=False; first request pays the load cost",
            )

        yield  # Application runs.

        # --- Shutdown --------------------------------------------------
        logger.info("api.lifespan.shutdown_start")
        clear_dependency_caches()
        logger.info("api.lifespan.shutdown_complete")

    return lifespan


__all__ = ["ApiState", "create_lifespan"]
