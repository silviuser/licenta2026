"""Extraction pipeline — orchestrates extractors in priority order.

The pipeline tries each extractor in sequence and advances to the next one
when the current result does not meet the quality threshold.  The first
result that passes quality checks is post-processed and returned.

If all extractors fail or produce low-quality output the pipeline either
raises ``LowQualityExtractionError`` or returns the best result seen so far,
depending on the ``raise_on_low_quality`` flag.
"""

import time
from pathlib import Path

import structlog

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import (
    CVExtractorError,
    ExtractionFailedError,
    LowQualityExtractionError,
)
from cv_extractor.extractors.base import TextExtractor
from cv_extractor.extractors.ocr_extractor import OCRExtractor
from cv_extractor.extractors.pdfplumber_extractor import PdfPlumberExtractor
from cv_extractor.extractors.pymupdf_extractor import PyMuPDFExtractor
from cv_extractor.models import ExtractionMetadata, ExtractionMethod, ExtractionResult, RawExtraction
from cv_extractor.postprocess import QualityChecker, postprocess_text

log = structlog.get_logger(__name__)

_METHOD_TO_ENUM: dict[str, ExtractionMethod] = {
    "pdfplumber": ExtractionMethod.PDFPLUMBER,
    "pymupdf": ExtractionMethod.PYMUPDF,
    "ocr_tesseract": ExtractionMethod.OCR_TESSERACT,
}


def build_default_pipeline(config: ExtractorConfig | None = None) -> list[TextExtractor]:
    """Return the default ordered list of extractors.

    Args:
        config: Shared config applied to every extractor.

    Returns:
        Ordered list: pdfplumber → pymupdf → ocr_tesseract.
    """
    cfg = config or ExtractorConfig()
    return [
        PdfPlumberExtractor(cfg),
        PyMuPDFExtractor(cfg),
        OCRExtractor(cfg),
    ]


class ExtractionPipeline:
    """Cascading extractor pipeline with quality gating.

    Args:
        extractors:           Ordered list of extractors to try.
        config:               Configuration (thresholds, OCR settings, …).
        raise_on_low_quality: When True, raise ``LowQualityExtractionError``
                              if the best available result is below threshold.
                              When False, return the best result with a warning.
    """

    def __init__(
        self,
        extractors: list[TextExtractor] | None = None,
        config: ExtractorConfig | None = None,
        raise_on_low_quality: bool = False,
    ) -> None:
        self._config = config or ExtractorConfig()
        self._extractors = extractors if extractors is not None else build_default_pipeline(self._config)
        self._raise_on_low_quality = raise_on_low_quality
        self._quality = QualityChecker(self._config)

    def process(self, pdf_path: Path) -> ExtractionResult:
        """Run the pipeline on a PDF file and return a clean ExtractionResult.

        Args:
            pdf_path: Absolute path to the PDF.

        Returns:
            ExtractionResult with cleaned text and full metadata.

        Raises:
            PDFCorruptError:        File cannot be opened by any extractor.
            PDFEncryptedError:      File is password-protected.
            ExtractionFailedError:  No extractor produced any text.
            LowQualityExtractionError: Best result is below quality threshold
                                       (only when raise_on_low_quality=True).
        """
        if not pdf_path.exists():
            raise ExtractionFailedError(f"File not found: {pdf_path}")

        start_ms = time.monotonic()
        warnings: list[str] = []
        best_raw: RawExtraction | None = None
        best_score = -1.0

        for extractor in self._extractors:
            log.info("pipeline_trying_extractor", extractor=extractor.name, path=str(pdf_path))
            try:
                raw = extractor.extract(pdf_path)
            except CVExtractorError:
                # Re-raise structural errors immediately — no point trying other extractors.
                raise
            except Exception as exc:
                log.warning(
                    "extractor_unexpected_error",
                    extractor=extractor.name,
                    error=str(exc),
                )
                warnings.append(f"{extractor.name} failed unexpectedly: {exc}")
                continue

            was_ocr = raw.method == ExtractionMethod.OCR_TESSERACT
            cleaned_text = postprocess_text(raw.text, was_ocr=was_ocr)
            total_pages = len(raw.pages_info)
            score = self._quality.score(cleaned_text, total_pages)

            log.info(
                "extractor_result",
                extractor=extractor.name,
                chars=len(cleaned_text),
                quality_score=score,
            )

            if score > best_score:
                best_score = score
                best_raw = raw

            if self._quality.is_sufficient(cleaned_text, total_pages):
                log.info("pipeline_accepted", extractor=extractor.name, score=score)
                return self._build_result(
                    raw=raw,
                    cleaned_text=cleaned_text,
                    quality_score=score,
                    elapsed_ms=int((time.monotonic() - start_ms) * 1000),
                    warnings=warnings,
                )

            warnings.append(
                f"{extractor.name} produced low-quality text "
                f"(score={score:.2f} < {self._config.min_quality_score}); trying next extractor."
            )

        # All extractors exhausted.
        if best_raw is None:
            raise ExtractionFailedError(f"All extractors failed for: {pdf_path}")

        was_ocr = best_raw.method == ExtractionMethod.OCR_TESSERACT
        best_text = postprocess_text(best_raw.text, was_ocr=was_ocr)
        total_pages = len(best_raw.pages_info)

        if self._raise_on_low_quality:
            raise LowQualityExtractionError(
                f"Best extraction score {best_score:.2f} is below threshold "
                f"{self._config.min_quality_score}",
                quality_score=best_score,
            )

        warnings.append(
            f"All extractors produced low-quality text. "
            f"Returning best available result (score={best_score:.2f})."
        )
        log.warning("pipeline_low_quality_result", score=best_score)

        return self._build_result(
            raw=best_raw,
            cleaned_text=best_text,
            quality_score=best_score,
            elapsed_ms=int((time.monotonic() - start_ms) * 1000),
            warnings=warnings,
        )

    def _build_result(
        self,
        raw: RawExtraction,
        cleaned_text: str,
        quality_score: float,
        elapsed_ms: int,
        warnings: list[str],
    ) -> ExtractionResult:
        """Assemble the final ExtractionResult from pipeline internals.

        Also detects language and determines whether the document was scanned.
        """
        detected_language = _detect_language(cleaned_text)
        is_scanned = raw.method == ExtractionMethod.OCR_TESSERACT

        if not self._quality.is_likely_cv(cleaned_text):
            warnings.append("Document may not be a CV — few CV-specific keywords found.")

        metadata = ExtractionMetadata(
            method_used=raw.method,
            total_pages=len(raw.pages_info),
            processing_time_ms=elapsed_ms,
            detected_language=detected_language,
            is_scanned=is_scanned,
            quality_score=quality_score,
            pages=raw.pages_info,
        )
        return ExtractionResult(text=cleaned_text, metadata=metadata, warnings=warnings)


def _detect_language(text: str) -> str | None:
    """Detect the primary language of the text using lingua.

    Returns the ISO 639-1 language code (e.g. "en", "ro") or None on failure.
    We only import lingua here to keep it optional — if not installed the
    pipeline continues without language detection.
    """
    if len(text) < 50:
        return None
    try:
        from lingua import Language, LanguageDetectorBuilder  # type: ignore[import]

        detector = (
            LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.ROMANIAN)
            .with_minimum_relative_distance(0.1)
            .build()
        )
        result = detector.detect_language_of(text[:2000])
        if result is None:
            return None
        return result.iso_code_639_1.name.lower()
    except Exception as exc:
        log.debug("language_detection_failed", error=str(exc))
        return None
