"""``POST /v1/extract-jd`` — free-text Job Description → candidate requirements.

REWORK 1 (D18/D19). The recruiter writes a JD as free text; this
endpoint runs the *same* lexical skill extractor (Module 2) and
Module 3 Linker used for CVs, but skips Module 1 entirely (no PDF to
parse). No model is retrained — this is pure reuse of the existing
pipeline on a generic-text input.

Contract notes:
* Importance (``required`` / ``nice_to_have``) is intentionally NOT
  decided here — the backend defaults every extracted requirement to
  ``required`` and lets the recruiter adjust (D18).
* The existing ``/v1/extract``, ``/v1/match`` and ``/v1/full``
  contracts are untouched.

Error model mirrors ``api.routers.extract``: stable ``error`` codes in
an ``ErrorResponse`` body, stack traces stay in the logs.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from skill_extractor import SkillExtractor
from skill_extractor.exceptions import (
    SkillExtractorError,
    UnsupportedLanguageError,
)
from skill_matcher import SkillMatcher

from api.adapters import enriched_to_jd_response
from api.deps import get_skill_extractor, get_skill_matcher
from api.schemas import ErrorResponse, ExtractJdRequest, ExtractJdResponse

router = APIRouter()
logger = structlog.get_logger(__name__)

_DEFAULT_LANGUAGE = "en"
"""Fallback when language detection abstains (e.g. JD text too short)."""


def _resolve_language(text: str, override: str | None) -> str:
    """Pick the pipeline language: explicit override, else auto-detect.

    Reuses Module 1's lingua-based detector (``_detect_language``) so
    the JD path behaves consistently with CV language detection.
    Imported lazily and locally because it is a private helper of the
    Module 1 pipeline; the deliberate reuse is documented in REWORK 1
    PREFLIGHT §C (A4). Falls back to ``en`` when detection abstains.
    """
    if override is not None:
        return override
    # Local import: keep ``cv_extractor`` off the module import path and
    # signal the intentional reuse of a private helper at the call site.
    from cv_extractor.pipeline import _detect_language

    detected = _detect_language(text)
    if detected in ("en", "ro"):
        return detected
    return _DEFAULT_LANGUAGE


@router.post(
    "/extract-jd",
    response_model=ExtractJdResponse,
    status_code=status.HTTP_200_OK,
    summary="Free-text JD -> candidate requirements (Module 2 + 3 Linker)",
    description=(
        "Runs the lexical skill extractor and the Module 3 Linker over "
        "free Job Description text — no PDF, no Module 1. Returns a "
        "deduplicated, confidence-sorted list of candidate requirements "
        "(``lexical_dropped`` candidates filtered out). Importance is "
        "left to the caller (REWORK 1 D18)."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
def extract_jd(
    request: Request,
    payload: ExtractJdRequest,
    skill_extractor: Annotated[SkillExtractor, Depends(get_skill_extractor)],
    matcher: Annotated[SkillMatcher, Depends(get_skill_matcher)],
) -> ExtractJdResponse:
    """Extract candidate skill requirements from free JD text."""
    request_id = getattr(request.state, "request_id", None)

    text = payload.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="empty_text",
                detail="The JD text is empty.",
                request_id=request_id,
            ).model_dump(),
        )

    language = _resolve_language(text, payload.language)

    try:
        lexical = skill_extractor.extract((text, language))
        enriched = matcher.link(
            cv_id=payload.jd_id, cv_text=text, lexical=lexical
        )
    except UnsupportedLanguageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="unsupported_language",
                detail=str(exc),
                request_id=request_id,
            ).model_dump(),
        ) from exc
    except SkillExtractorError as exc:
        logger.exception("api.extract_jd.skill_extractor_error", jd_id=payload.jd_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="skill_extractor_error",
                detail=str(exc),
                request_id=request_id,
            ).model_dump(),
        ) from exc
    except Exception as exc:  # noqa: BLE001 — uniform 500 envelope
        logger.exception("api.extract_jd.unexpected_error", jd_id=payload.jd_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error="extract_jd_error",
                detail=str(exc),
                request_id=request_id,
            ).model_dump(),
        ) from exc

    return enriched_to_jd_response(
        jd_id=payload.jd_id,
        language=language,
        enriched=enriched,
        extra_warnings=list(lexical.warnings),
    )


__all__ = ["router"]
