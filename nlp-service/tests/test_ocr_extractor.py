"""Unit tests for OCRExtractor."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image as PILImage

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import ExtractionFailedError, PDFCorruptError
from cv_extractor.extractors.ocr_extractor import OCRExtractor
from cv_extractor.models import ExtractionMethod


def _make_blank_image(width: int = 595, height: int = 842) -> PILImage.Image:
    return PILImage.new("RGB", (width, height), color=(255, 255, 255))


class TestOCRExtractorUnit:
    """Unit tests with mocked pdf2image and pytesseract."""

    def test_returns_ocr_method(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "scanned.pdf"
        pdf_file.write_bytes(b"dummy")
        images = [_make_blank_image()]

        with (
            patch("cv_extractor.extractors.ocr_extractor.convert_from_path", return_value=images),
            patch(
                "cv_extractor.extractors.ocr_extractor.pytesseract.image_to_string",
                return_value="Experience Education Skills",
            ),
        ):
            result = OCRExtractor(extractor_config).extract(pdf_file)

        assert result.method == ExtractionMethod.OCR_TESSERACT

    def test_text_from_ocr_is_returned(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "scanned.pdf"
        pdf_file.write_bytes(b"dummy")
        images = [_make_blank_image()]
        ocr_text = "John Doe\nSoftware Engineer\nExperience: 5 years"

        with (
            patch("cv_extractor.extractors.ocr_extractor.convert_from_path", return_value=images),
            patch(
                "cv_extractor.extractors.ocr_extractor.pytesseract.image_to_string",
                return_value=ocr_text,
            ),
        ):
            result = OCRExtractor(extractor_config).extract(pdf_file)

        assert "John Doe" in result.text

    def test_multiple_pages_produce_multiple_page_infos(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "multi.pdf"
        pdf_file.write_bytes(b"dummy")
        images = [_make_blank_image(), _make_blank_image()]

        with (
            patch("cv_extractor.extractors.ocr_extractor.convert_from_path", return_value=images),
            patch(
                "cv_extractor.extractors.ocr_extractor.pytesseract.image_to_string",
                return_value="some text",
            ),
        ):
            result = OCRExtractor(extractor_config).extract(pdf_file)

        assert len(result.pages_info) == 2
        assert result.pages_info[0].page_number == 1
        assert result.pages_info[1].page_number == 2

    def test_raises_pdf_corrupt_when_conversion_fails(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        from pdf2image.exceptions import PDFSyntaxError

        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"garbage")

        with patch(
            "cv_extractor.extractors.ocr_extractor.convert_from_path",
            side_effect=PDFSyntaxError,
        ):
            with pytest.raises(PDFCorruptError):
                OCRExtractor(extractor_config).extract(pdf_file)

    def test_raises_extraction_failed_when_no_images(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_bytes(b"dummy")

        with patch("cv_extractor.extractors.ocr_extractor.convert_from_path", return_value=[]):
            with pytest.raises(ExtractionFailedError):
                OCRExtractor(extractor_config).extract(pdf_file)

    def test_tesseract_error_on_page_returns_empty_string(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        """A per-page Tesseract error should be tolerated — empty string for that page."""
        import pytesseract as tess

        pdf_file = tmp_path / "flaky.pdf"
        pdf_file.write_bytes(b"dummy")
        images = [_make_blank_image()]

        with (
            patch("cv_extractor.extractors.ocr_extractor.convert_from_path", return_value=images),
            patch(
                "cv_extractor.extractors.ocr_extractor.pytesseract.image_to_string",
                side_effect=tess.TesseractError(1, "error"),
            ),
        ):
            result = OCRExtractor(extractor_config).extract(pdf_file)

        # Should not raise; text may be empty
        assert isinstance(result.text, str)

    def test_tesseract_cmd_is_set_from_config(self, tmp_path: Path) -> None:
        config = ExtractorConfig(tesseract_cmd="/usr/local/bin/tesseract")
        import pytesseract

        OCRExtractor(config)
        assert pytesseract.pytesseract.tesseract_cmd == "/usr/local/bin/tesseract"
