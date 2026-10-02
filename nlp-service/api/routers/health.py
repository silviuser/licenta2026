"""``GET /v1/health`` (liveness) and ``GET /v1/readyz`` (readiness).

Liveness reports only that the Python process is up enough to answer
HTTP. Readiness reports whether the three pipeline singletons have
been instantiated — i.e. whether the next request will pay the warm-
up cost or not.

The contract:

* ``/v1/health`` always 200 if the process can respond.
* ``/v1/readyz`` returns 200 with ``status="ok"`` when the three
  singletons are warm, and 503 with ``status="not_ready"`` otherwise
  (same body schema, different status code).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from api.adapters import utc_now
from api.deps import (
    get_extraction_pipeline,
    get_skill_extractor,
    get_skill_matcher,
)
from api.schemas import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description=(
        "Returns 200 if the Python process can answer HTTP. Does not "
        "exercise model components — use ``/v1/readyz`` for that."
    ),
)
def health() -> HealthResponse:
    """Liveness probe. Always returns ``status='ok'``."""
    return HealthResponse(status="ok", timestamp=utc_now())


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Returns 200 + ``status='ok'`` if the three pipeline "
        "singletons (cv_extractor, skill_extractor, skill_matcher) "
        "have already been constructed. Returns 503 + "
        "``status='not_ready'`` otherwise."
    ),
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse},
    },
)
def readyz(request: Request, response: Response) -> ReadinessResponse:
    """Readiness probe — inspects LRU cache state of the three singletons."""
    loaded: list[str] = []
    if get_extraction_pipeline.cache_info().currsize > 0:
        loaded.append("extraction_pipeline")
    if get_skill_extractor.cache_info().currsize > 0:
        loaded.append("skill_extractor")
    if get_skill_matcher.cache_info().currsize > 0:
        loaded.append("skill_matcher")

    all_loaded = len(loaded) == 3
    api_state = getattr(request.app.state, "api_state", None)
    warmup_complete = bool(getattr(api_state, "warmup_complete", False))

    if all_loaded and warmup_complete:
        return ReadinessResponse(
            status="ok",
            components_loaded=loaded,
            timestamp=utc_now(),
        )

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="not_ready",
        components_loaded=loaded,
        timestamp=utc_now(),
    )


__all__ = ["router"]
