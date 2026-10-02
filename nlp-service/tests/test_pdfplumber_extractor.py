"""Unit tests for PdfPlumberExtractor."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import ExtractionFailedError, PDFCorruptError, PDFEncryptedError
from cv_extractor.extractors.pdfplumber_extractor import PdfPlumberExtractor
from cv_extractor.models import ExtractionMethod


class TestPdfPlumberExtractorUnit:
    """Unit tests with mocked pdfplumber internals."""

    def test_returns_raw_extraction_with_correct_method(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "dummy.pdf"
        pdf_file.write_bytes(b"dummy")

        mock_page = MagicMock()
        mock_page.page_number = 1
        mock_page.width = 595.0
        mock_page.height = 842.0
        mock_page.bbox = (0, 0, 595.0, 842.0)
        mock_page.extract_words.return_value = [
            {"x0": 50.0, "top": 100, "text": w}
            for w in ["Experience", "Education", "Skills", "Python", "Java"]
        ]
        mock_page.extract_text.return_value = "Experience Education Skills Python Java"

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.doc.is_extractable = True
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("cv_extractor.extractors.pdfplumber_extractor.pdfplumber.open", return_value=mock_pdf):
            extractor = PdfPlumberExtractor(extractor_config)
            result = extractor.extract(pdf_file)

        assert result.method == ExtractionMethod.PDFPLUMBER
        assert "Experience" in result.text
        assert len(result.pages_info) == 1

    def test_page_info_populated_correctly(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "dummy.pdf"
        pdf_file.write_bytes(b"dummy")

        mock_page = MagicMock()
        mock_page.page_number = 1
        mock_page.width = 595.0
        mock_page.height = 842.0
        mock_page.bbox = (0, 0, 595.0, 842.0)
        mock_page.extract_words.return_value = [
            {"x0": 50.0, "top": 100, "text": "word"} for _ in range(15)
        ]
        mock_page.extract_text.return_value = " ".join(["word"] * 15)

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.doc.is_extractable = True
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("cv_extractor.extractors.pdfplumber_extractor.pdfplumber.open", return_value=mock_pdf):
            result = PdfPlumberExtractor(extractor_config).extract(pdf_file)

        info = result.pages_info[0]
        assert info.page_number == 1
        assert info.width == 595.0
        assert info.height == 842.0
        assert info.word_count == 15

    def test_raises_pdf_corrupt_on_open_failure(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"not a pdf")

        with patch(
            "cv_extractor.extractors.pdfplumber_extractor.pdfplumber.open",
            side_effect=Exception("broken"),
        ):
            with pytest.raises(PDFCorruptError):
                PdfPlumberExtractor(extractor_config).extract(pdf_file)

    def test_raises_extraction_failed_on_empty_pdf(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_bytes(b"dummy")

        mock_pdf = MagicMock()
        mock_pdf.pages = []
        mock_pdf.doc.is_extractable = True
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("cv_extractor.extractors.pdfplumber_extractor.pdfplumber.open", return_value=mock_pdf):
            with pytest.raises(ExtractionFailedError):
                PdfPlumberExtractor(extractor_config).extract(pdf_file)

    def test_multicolumn_page_is_detected_and_flagged(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        """Words clustered in two distinct x-ranges should trigger two-column extraction."""
        pdf_file = tmp_path / "twocol.pdf"
        pdf_file.write_bytes(b"dummy")

        # Left column words at x≈50, right column words at x≈350 (gap at 200–300)
        left_words = [{"x0": 50.0, "top": float(i * 20), "text": "left"} for i in range(15)]
        right_words = [{"x0": 350.0, "top": float(i * 20), "text": "right"} for i in range(15)]

        mock_page = MagicMock()
        mock_page.page_number = 1
        mock_page.width = 595.0
        mock_page.height = 842.0
        mock_page.bbox = (0, 0, 595.0, 842.0)
        mock_page.extract_words.return_value = left_words + right_words
        mock_page.crop.return_value.extract_text.return_value = "left column text"

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.doc.is_extractable = True
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("cv_extractor.extractors.pdfplumber_extractor.pdfplumber.open", return_value=mock_pdf):
            result = PdfPlumberExtractor(extractor_config).extract(pdf_file)

        assert result.pages_info[0].is_multi_column is True


class TestPdfPlumberExtractorIntegration:
    """Integration tests using real generated PDFs."""

    def test_single_column_extracts_known_text(self, single_column_pdf: Path) -> None:
        result = PdfPlumberExtractor().extract(single_column_pdf)
        assert len(result.text) > 50
        assert result.method == ExtractionMethod.PDFPLUMBER
        assert result.pages_info[0].is_multi_column is False

    def test_corrupt_pdf_raises_pdf_corrupt_error(self, corrupt_pdf: Path) -> None:
        with pytest.raises(PDFCorruptError):
            PdfPlumberExtractor().extract(corrupt_pdf)

    def test_extraction_preserves_keyword_content(self, single_column_pdf: Path) -> None:
        result = PdfPlumberExtractor().extract(single_column_pdf)
        text_lower = result.text.lower()
        assert any(kw in text_lower for kw in ["experience", "education", "skills"])

    # ---------------------------------------------------------------
    # Regression test: word_count must reflect words on the page,
    # not just words found in the cropped column subset.
    # ---------------------------------------------------------------

    def test_regression_page_word_count_uses_page_words_not_cropped(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "wc.pdf"
        pdf_file.write_bytes(b"dummy")

        # 20 distinct words on the page.
        words_payload = [{"x0": 50.0, "top": float(i * 20), "text": f"w{i}"} for i in range(20)]

        mock_page = MagicMock()
        mock_page.page_number = 1
        mock_page.width = 595.0
        mock_page.height = 842.0
        mock_page.bbox = (0, 0, 595.0, 842.0)
        mock_page.extract_words.return_value = words_payload
        # Simulate that extract_text returns only some of the words.
        mock_page.extract_text.return_value = "only three words"

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.doc.is_extractable = True
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch(
            "cv_extractor.extractors.pdfplumber_extractor.pdfplumber.open",
            return_value=mock_pdf,
        ):
            result = PdfPlumberExtractor(extractor_config).extract(pdf_file)

        # word_count must come from extract_words(), not from the extracted
        # text string — otherwise multi-column pages mis-report.
        assert result.pages_info[0].word_count == 20
