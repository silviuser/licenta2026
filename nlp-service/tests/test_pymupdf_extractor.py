"""Unit tests for PyMuPDFExtractor."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import ExtractionFailedError, PDFCorruptError, PDFEncryptedError
from cv_extractor.extractors.pymupdf_extractor import PyMuPDFExtractor
from cv_extractor.models import ExtractionMethod


class TestPyMuPDFExtractorUnit:
    """Unit tests with mocked fitz internals."""

    def _make_mock_doc(self, page_texts: list[str], *, encrypted: bool = False) -> MagicMock:
        """Build a minimal fitz.Document mock."""
        doc = MagicMock()
        doc.is_encrypted = encrypted
        doc.authenticate.return_value = 0 if encrypted else 1
        doc.page_count = len(page_texts)

        pages = []
        for i, text in enumerate(page_texts):
            page = MagicMock()
            page.rect = MagicMock(width=595.0, height=842.0)
            words = [
                (float(j * 40), 100.0, float(j * 40 + 30), 120.0, w, 0, 0, 0)
                for j, w in enumerate(text.split())
            ]
            page.get_text.side_effect = lambda mode, page=page, text=text, words=words: (
                text if mode == "blocks" else words if mode == "words" else []
            )
            # For "blocks" mode: return list of block tuples
            page.get_text.side_effect = None  # reset
            page.get_text = MagicMock(side_effect=lambda mode, _text=text, _words=words: (
                [(_words[0][0] if _words else 0, 0, 500, 200, _text, 0, 0)] if mode == "blocks"
                else _words if mode == "words"
                else _text
            ))
            page.get_textbox.return_value = text
            pages.append(page)

        doc.__getitem__ = lambda self, idx: pages[idx]
        doc.__enter__ = lambda s: s
        doc.__exit__ = MagicMock(return_value=False)
        return doc

    def test_returns_correct_method(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"dummy")
        mock_doc = self._make_mock_doc(["Experience Education Skills Python Java"])

        with patch("cv_extractor.extractors.pymupdf_extractor.fitz.open", return_value=mock_doc):
            result = PyMuPDFExtractor(extractor_config).extract(pdf_file)

        assert result.method == ExtractionMethod.PYMUPDF

    def test_raises_pdf_corrupt_on_open_failure(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        import fitz
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"not a pdf")

        with patch(
            "cv_extractor.extractors.pymupdf_extractor.fitz.open",
            side_effect=fitz.FileDataError("corrupt"),
        ):
            with pytest.raises(PDFCorruptError):
                PyMuPDFExtractor(extractor_config).extract(pdf_file)

    def test_raises_extraction_failed_on_empty_doc(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_bytes(b"dummy")
        mock_doc = self._make_mock_doc([])

        with patch("cv_extractor.extractors.pymupdf_extractor.fitz.open", return_value=mock_doc):
            with pytest.raises(ExtractionFailedError):
                PyMuPDFExtractor(extractor_config).extract(pdf_file)

    def test_raises_encrypted_when_auth_fails(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "enc.pdf"
        pdf_file.write_bytes(b"dummy")
        mock_doc = self._make_mock_doc(["text"], encrypted=True)

        with patch("cv_extractor.extractors.pymupdf_extractor.fitz.open", return_value=mock_doc):
            with pytest.raises(PDFEncryptedError):
                PyMuPDFExtractor(extractor_config).extract(pdf_file)

    def test_multi_page_builds_multiple_page_infos(
        self, extractor_config: ExtractorConfig, tmp_path: Path
    ) -> None:
        pdf_file = tmp_path / "multi.pdf"
        pdf_file.write_bytes(b"dummy")
        mock_doc = self._make_mock_doc(["Page one text", "Page two text"])

        with patch("cv_extractor.extractors.pymupdf_extractor.fitz.open", return_value=mock_doc):
            result = PyMuPDFExtractor(extractor_config).extract(pdf_file)

        assert len(result.pages_info) == 2
        assert result.pages_info[0].page_number == 1
        assert result.pages_info[1].page_number == 2


class TestPyMuPDFExtractorIntegration:
    """Integration tests using real generated PDFs."""

    def test_single_column_extracts_text(self, single_column_pdf: Path) -> None:
        result = PyMuPDFExtractor().extract(single_column_pdf)
        assert len(result.text) > 20
        assert result.method == ExtractionMethod.PYMUPDF

    def test_corrupt_pdf_raises(self, corrupt_pdf: Path) -> None:
        with pytest.raises(PDFCorruptError):
            PyMuPDFExtractor().extract(corrupt_pdf)
