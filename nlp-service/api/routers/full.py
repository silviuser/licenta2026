"""``POST /v1/full`` — convenience end-to-end endpoint.

Combines ``/v1/extract`` + ``/v1/match`` into a single round trip:
PDF + JD requirements → ``FullResponse``. No new business logic;
this router simply composes the two upstream paths and translates
the result.

The ``requirements`` field is delivered as a JSON-encoded string
inside the multipart form (HTTP forms cannot carry typed lists),
parsed and validated against ``list[RequirementSchema]`` by the
adapter. This is the same convention OpenAPI tooling generates for
mixed multipart/structured endpoints.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from cv_extractor import (
    CVExtractorError,
    ExtractionFailedError,
    ExtractionPipeline,
    PDFCorruptError,
    PDFEncryptedError,
)
from skill_extractor import SkillExtractor
from skill_matcher import SkillMatcher

from api.adapters import (
    match_result_to_full_response,
    requirement_schema_to_internal,
)
from api.deps import get_pipeline
from api.schemas import ErrorResponse, FullResponse, RequirementSchema
from api.settings import ApiSettings

router = APIRouter()
logger = structlog.get_logger(__name__)

_REQUIREMENTS_ADAPTER = TypeAdapter(list[RequirementSchema])


def _payload_too_large(
    request: Request, max_bytes: int, actual_bytes: int
) -> JSONResponse:
    body = ErrorResponse(
        error="payload_too_large",
        detail=(
            f"PDF upload of {actual_bytes} bytes exceeds the "
            f"configured maximum of {max_bytes} bytes."
        ),
        request_id=getattr(request.state, "request_id", None),
    )
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        content=body.model_dump(),
    )


@router.post(
    "/full",
    response_model=FullResponse,
    status_code=status.HTTP_200_OK,
    summary="PDF + JD requirements -> MatchResponse (end-to-end)",
    description=(
        "End-to-end convenience endpoint: runs ``/v1/extract`` "
        "followed by ``/v1/match`` in a single round trip. The "
        "``requirements`` field carries a JSON-encoded "
        "``list[RequirementSchema]`` (multipart forms cannot carry "
        "structured lists natively)."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def full(
    request: Request,
    cv_id: Annotated[str, Form(min_length=1, max_length=128)],
    jd_id: Annotated[str, Form(min_length=1, max_length=128)],
    requirements: Annotated[
        str,
        Form(
            description=(
                "JSON-encoded list[RequirementSchema]. Example: "
                '``[{"text":"Python","importance":"required"}]``.'
            ),
        ),
    ],
    cv_pdf: Annotated[UploadFile, File(description="CV PDF binary")],
    pipeline: Annotated[
        tuple[ExtractionPipeline, SkillExtractor, SkillMatcher],
        Depends(get_pipeline),
    ],
) -> FullResponse | JSONResponse:
    """Run the full Module 1 + 2 + 3 pipeline end-to-end."""
    settings = ApiSettings()

    # ---- parse requirements -----------------------------------------
    try:
        parsed_raw = json.loads(requirements)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="requirements_invalid_json",
                detail=f"requirements field is not valid JSON: {exc}",
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        ) from exc

    try:
        requirements_parsed: list[RequirementSchema] = (
            _REQUIREMENTS_ADAPTER.validate_python(parsed_raw)
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="requirements_invalid_schema",
                detail=str(exc),
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        ) from exc

    if not requirements_parsed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="requirements_empty",
                detail="requirements list must contain at least one entry.",
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        )

    # ---- pdf upload size check -------------------------------------
    pdf_bytes = await cv_pdf.read()
    if len(pdf_bytes) > settings.max_pdf_size_bytes:
        return _payload_too_large(
            request, settings.max_pdf_size_bytes, len(pdf_bytes)
        )
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                error="empty_upload",
                detail="The uploaded PDF is empty.",
                request_id=getattr(request.state, "request_id", None),
            ).model_dump(),
        )

    # ---- run the three-stage pipeline ------------------------------
    extractor, skill_extractor, matcher = pipeline
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False
        ) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = Path(tmp.name)

        try:
            extraction = extractor.process(tmp_path)
        except PDFCorruptError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error="pdf_corrupt",
                    detail=str(exc),
                    request_id=getattr(request.state, "request_id", None),
                ).model_dump(),
            ) from exc
        except PDFEncryptedError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error="pdf_encrypted",
                    detail=str(exc),
                    request_id=getattr(request.state, "request_id", None),
                ).model_dump(),
            ) from exc
        except ExtractionFailedError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error="extraction_failed",
                    detail=str(exc),
                    request_id=getattr(request.state, "request_id", None),
                ).model_dump(),
            ) from exc
        except CVExtractorError as exc:
            logger.exception("api.full.cv_extractor_error", cv_id=cv_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ErrorResponse(
                    error="cv_extractor_error",
                    detail=str(exc),
                    request_id=getattr(request.state, "request_id", None),
                ).model_dump(),
            ) from exc

        lexical = skill_extractor.extract(extraction)
        enriched = matcher.link(
            cv_id=cv_id, cv_text=extraction.text, lexical=lexical
        )

        requirements_internal = [
            requirement_schema_to_internal(r) for r in requirements_parsed
        ]
        try:
            result = matcher.match(
                enriched=enriched,
                jd_id=jd_id,
                requirements=requirements_internal,
            )
        except Exception as exc:
            logger.exception(
                "api.full.scorer_failed",
                cv_id=cv_id,
                jd_id=jd_id,
                n_requirements=len(requirements_internal),
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
        return match_result_to_full_response(
            result,
            t1_strong_threshold=cfg.t1_strong_threshold,
            t2_possible_threshold=cfg.t2_possible_threshold,
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


__all__ = ["router"]
