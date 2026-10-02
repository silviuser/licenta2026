"""Pydantic domain models for the CV extraction pipeline.

``RawExtraction`` is an internal DTO passed between pipeline stages.
``ExtractionResult`` is the public output returned to callers.
"""

from enum import Enum

from pydantic import BaseModel, Field


class ExtractionMethod(str, Enum):
    """Identifies which extractor produced a given result."""

    PDFPLUMBER = "pdfplumber"
    PYMUPDF = "pymupdf"
    OCR_TESSERACT = "ocr_tesseract"


class PageInfo(BaseModel):
    """Per-page metadata collected during extraction."""

    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    is_multi_column: bool
    word_count: int = Field(ge=0)


class ExtractionMetadata(BaseModel):
    """Aggregate metadata produced by the pipeline after extraction."""

    method_used: ExtractionMethod
    total_pages: int = Field(ge=0)
    processing_time_ms: int = Field(ge=0)
    detected_language: str | None = None
    is_scanned: bool
    quality_score: float = Field(ge=0.0, le=1.0)
    pages: list[PageInfo]


class RawExtraction(BaseModel):
    """Internal output from a single extractor before post-processing."""

    text: str
    method: ExtractionMethod
    pages_info: list[PageInfo]


class ExtractionResult(BaseModel):
    """Final public output of the extraction pipeline.

    This is the object returned to all callers (FastAPI layer, scripts, tests).
    """

    text: str
    metadata: ExtractionMetadata
    warnings: list[str] = Field(default_factory=list)
