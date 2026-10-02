"""Integration and unit tests for ExtractionPipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import (
    ExtractionFailedError,
    LowQualityExtractionError,
    PDFCorruptError,
)
from cv_extractor.extractors.base import TextExtractor
from cv_extractor.models import ExtractionMethod, PageInfo, RawExtraction
from cv_extractor.pipeline import ExtractionPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_extractor(
    name: str,
    text: str,
    method: ExtractionMethod = ExtractionMethod.PDFPLUMBER,
    *,
    raises: type[Exception] | None = None,
) -> TextExtractor:
    """Build a stub TextExtractor that returns a fixed RawExtraction."""
    extractor = MagicMock(spec=TextExtractor)
    extractor.name = name
    page_info = PageInfo(
        page_number=1, width=595.0, height=842.0, is_multi_column=False, word_count=len(text.split())
    )
    raw = RawExtraction(text=text, method=method, pages_info=[page_info])
    if raises:
        extractor.extract.side_effect = raises("simulated error")
    else:
        extractor.extract.return_value = raw
    return extractor  # type: ignore[return-value]


_GOOD_CV_TEXT = (
    "John Doe\n\nExperience\nSenior Software Engineer at ACME Corp, 2019–2024\n"
    "Designed and maintained distributed backend systems.\n\n"
    "Education\nB.Sc. Computer Science, University of Bucharest, 2015–2019\n\n"
    "Skills\nPython, Java, Docker, Kubernetes, PostgreSQL\n\n"
    "Languages\nEnglish (C1), Romanian (native)\n\n"
    "Contact\njohn.doe@example.com | LinkedIn: linkedin.com/in/johndoe"
)


# ---------------------------------------------------------------------------
# Unit tests — injected stub extractors
# ---------------------------------------------------------------------------

class TestPipelineWithStubs:

    def test_returns_extraction_result_on_success(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")
        pipeline = ExtractionPipeline(
            extractors=[_make_extractor("plumber", _GOOD_CV_TEXT)],
            config=extractor_config,
        )
        result = pipeline.process(pdf_file)
        assert "John Doe" in result.text
        assert result.metadata.method_used == ExtractionMethod.PDFPLUMBER

    def test_falls_back_to_second_extractor_on_low_quality(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")

        bad = _make_extractor("bad", "x", ExtractionMethod.PDFPLUMBER)
        good = _make_extractor("good", _GOOD_CV_TEXT, ExtractionMethod.PYMUPDF)

        config = ExtractorConfig(min_quality_score=0.3)
        pipeline = ExtractionPipeline(extractors=[bad, good], config=config)
        result = pipeline.process(pdf_file)

        assert result.metadata.method_used == ExtractionMethod.PYMUPDF
        good.extract.assert_called_once()

    def test_warnings_include_fallback_message(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")

        bad = _make_extractor("bad", "x", ExtractionMethod.PDFPLUMBER)
        good = _make_extractor("good", _GOOD_CV_TEXT, ExtractionMethod.PYMUPDF)

        config = ExtractorConfig(min_quality_score=0.3)
        pipeline = ExtractionPipeline(extractors=[bad, good], config=config)
        result = pipeline.process(pdf_file)

        assert any("low-quality" in w for w in result.warnings)

    def test_raises_extraction_failed_when_all_produce_empty(
        self, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")

        # All extractors raise ExtractionFailedError
        e1 = _make_extractor("e1", "", raises=ExtractionFailedError)
        config = ExtractorConfig(min_quality_score=0.5)
        pipeline = ExtractionPipeline(extractors=[e1], config=config)

        with pytest.raises(ExtractionFailedError):
            pipeline.process(pdf_file)

    def test_raises_pdf_corrupt_immediately(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")

        corrupt = _make_extractor("c1", "", raises=PDFCorruptError)
        pipeline = ExtractionPipeline(extractors=[corrupt], config=ExtractorConfig())

        with pytest.raises(PDFCorruptError):
            pipeline.process(pdf_file)

    def test_file_not_found_raises_extraction_failed(
        self, extractor_config: ExtractorConfig
    ) -> None:
        pipeline = ExtractionPipeline(config=extractor_config)
        with pytest.raises(ExtractionFailedError, match="File not found"):
            pipeline.process(Path("/nonexistent/file.pdf"))

    def test_low_quality_result_returned_when_flag_false(
        self, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")

        bad = _make_extractor("bad", "hello", ExtractionMethod.PDFPLUMBER)
        config = ExtractorConfig(min_quality_score=0.99)
        pipeline = ExtractionPipeline(
            extractors=[bad], config=config, raise_on_low_quality=False
        )
        result = pipeline.process(pdf_file)
        assert any("low-quality" in w for w in result.warnings)

    def test_low_quality_raises_when_flag_true(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")

        bad = _make_extractor("bad", "hello", ExtractionMethod.PDFPLUMBER)
        config = ExtractorConfig(min_quality_score=0.99)
        pipeline = ExtractionPipeline(
            extractors=[bad], config=config, raise_on_low_quality=True
        )
        with pytest.raises(LowQualityExtractionError) as exc_info:
            pipeline.process(pdf_file)
        assert exc_info.value.quality_score < 0.99

    def test_metadata_processing_time_is_non_negative(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")
        pipeline = ExtractionPipeline(
            extractors=[_make_extractor("p", _GOOD_CV_TEXT)],
            config=extractor_config,
        )
        result = pipeline.process(pdf_file)
        assert result.metadata.processing_time_ms >= 0

    def test_scanned_flag_set_for_ocr_method(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")
        ocr = _make_extractor("ocr", _GOOD_CV_TEXT, ExtractionMethod.OCR_TESSERACT)
        pipeline = ExtractionPipeline(extractors=[ocr], config=extractor_config)
        result = pipeline.process(pdf_file)
        assert result.metadata.is_scanned is True

    def test_not_scanned_for_pdfplumber_method(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")
        plumber = _make_extractor("plumber", _GOOD_CV_TEXT, ExtractionMethod.PDFPLUMBER)
        pipeline = ExtractionPipeline(extractors=[plumber], config=extractor_config)
        result = pipeline.process(pdf_file)
        assert result.metadata.is_scanned is False

    def test_non_cv_document_adds_warning(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "cv.pdf"
        pdf_file.write_bytes(b"dummy")
        # Text with no CV keywords
        extractor = _make_extractor(
            "p",
            "The quick brown fox jumps over the lazy dog. " * 20,
        )
        pipeline = ExtractionPipeline(extractors=[extractor], config=extractor_config)
        result = pipeline.process(pdf_file)
        assert any("CV" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Integration tests — real PDF fixtures
# ---------------------------------------------------------------------------

class TestPipelineIntegration:

    def test_processes_single_column_pdf(self, single_column_pdf: Path) -> None:
        pipeline = ExtractionPipeline(config=ExtractorConfig(min_quality_score=0.1))
        result = pipeline.process(single_column_pdf)
        assert len(result.text) > 30
        assert result.metadata.total_pages >= 1

    def test_corrupt_pdf_raises_pdf_corrupt_error(self, corrupt_pdf: Path) -> None:
        pipeline = ExtractionPipeline()
        with pytest.raises(PDFCorruptError):
            pipeline.process(corrupt_pdf)
