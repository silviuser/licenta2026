"""``POST /v1/match`` — Phase B Scorer only.

Caller posts the ``ExtractResponse`` they received from
``/v1/extract`` plus a JD requirement list; the endpoint converts
both back to internal types, runs the Scorer, and returns a
``MatchResponse`` with the locked-T1/T2 3-class projection attached.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from skill_matcher import SkillMatcher

from api.adapters import (
    match_result_to_response,
    requirement_schema_to_internal,
    response_to_enriched,
)
from api.deps import get_skill_matcher
from api.schemas import ErrorResponse, MatchRequest, MatchResponse

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post(
    "/match",
    response_model=MatchResponse,
    status_code=status.HTTP_200_OK,
    summary="EnrichedSkillResult + JD requirements -> MatchResponse",
    description=(
        "Run the Module 3 Scorer on a previously-extracted "
        "``EnrichedSkillResult`` (sent back as the ``enriched`` "
        "field) against a JD requirement list. Locked T1 / T2 "
        "thresholds from ``SkillMatcherConfig`` drive the 3-class "
        "projection."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
def match(
    request: Request,
    body: MatchRequest,
    matcher: Annotated[SkillMatcher, Depends(get_skill_matcher)],
) -> MatchResponse:
    """Score an enriched CV against a JD requirement list."""
    if body.cv_id != body.enriched.cv_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="cv_id_mismatch",
                detail=(
                    f"Request cv_id={body.cv_id!r} does not match "
                    f"enriched.cv_id={body.enriched.cv_id!r}."
                ),
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        )

    enriched = response_to_enriched(body.enriched)
    requirements = [
        requirement_schema_to_internal(r) for r in body.requirements
    ]

    try:
        result = matcher.match(
            enriched=enriched,
            jd_id=body.jd_id,
            requirements=requirements,
        )
    except Exception as exc:
        logger.exception(
            "api.match.scorer_failed",
            cv_id=body.cv_id,
            jd_id=body.jd_id,
            n_requirements=len(requirements),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="scorer_failed",
                detail=str(exc),
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        ) from exc

    cfg = matcher.config
    return match_result_to_response(
        result,
        t1_strong_threshold=cfg.t1_strong_threshold,
        t2_possible_threshold=cfg.t2_possible_threshold,
    )


__all__ = ["router"]
