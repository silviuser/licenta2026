"""``POST /v1/extract`` — Module 1 + Module 2 + Module 3 Linker.

Accepts a ``multipart/form-data`` upload with a ``cv_id`` text field
and a ``cv_pdf`` file. Materialises the upload to a tempfile (Module
1 backends are all path-based — see Pre-Flight §4), runs the three-
stage pipeline, and returns the enriched skill set.

Error model: all internal exceptions are translated into
``ErrorResponse`` bodies with a stable ``error`` code and a
human-readable ``detail``. Stack traces stay in the logs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from cv_extractor import (
    CVExtractorError,
    ExtractionFailedError,
    ExtractionPipeline,
    PDFCorruptError,
    PDFEncryptedError,
)
from skill_extractor import SkillExtractor
from skill_matcher import SkillMatcher

from api.adapters import enriched_to_response
from api.deps import get_pipeline
from api.schemas import ErrorResponse, ExtractResponse
from api.settings import ApiSettings

router = APIRouter()
logger = structlog.get_logger(__name__)


def _payload_too_large(
    request: Request, max_bytes: int, actual_bytes: int
) -> JSONResponse:
    """Build a uniform 413 response when the upload exceeds the cap."""
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
    "/extract",
    response_model=ExtractResponse,
    status_code=status.HTTP_200_OK,
    summary="CV PDF -> EnrichedSkillResult (Module 1 + 2 + 3 Linker)",
    description=(
        "Materialises the uploaded PDF, runs the extraction pipeline "
        "(pdfplumber → pymupdf → OCR fallback), the lexical skill "
        "extractor, and the Module 3 Linker (semantic re-scoring + "
        "sliding-window expansion). Returns an ``ExtractResponse`` "
        "carrying every candidate including the ``lexical_dropped`` "
        "ones."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def extract(
    request: Request,
    cv_id: Annotated[str, Form(min_length=1, max_length=128)],
    cv_pdf: Annotated[UploadFile, File(description="CV PDF binary")],
    pipeline: Annotated[
        tuple[ExtractionPipeline, SkillExtractor, SkillMatcher],
        Depends(get_pipeline),
    ],
) -> ExtractResponse | JSONResponse:
    """Extract enriched skills from an uploaded CV PDF."""
    settings = ApiSettings()
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

    extractor, skill_extractor, matcher = pipeline

    # Materialise the upload to disk so the path-based extractors can
    # open it. See Pre-Flight §4 for the rationale (Module 1 stays
    # untouched; tempfile lifecycle is owned by this router).
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
            logger.exception(
                "api.extract.cv_extractor_error", cv_id=cv_id
            )
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

        return enriched_to_response(
            cv_id=cv_id,
            extraction=extraction,
            enriched=enriched,
            extra_warnings=list(lexical.warnings),
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


__all__ = ["router"]
