"""Primary extractor using pdfplumber.

pdfplumber gives fine-grained access to word bounding boxes, making it the
best choice for layout-aware extraction.  For multi-column pages we crop
each half independently and concatenate in reading order.
"""

from pathlib import Path
from typing import Any

import pdfplumber
import structlog

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import (
    ExtractionFailedError,
    PDFCorruptError,
    PDFEncryptedError,
)
from cv_extractor.extractors.base import TextExtractor
from cv_extractor.models import ExtractionMethod, PageInfo, RawExtraction
from cv_extractor.utils.layout import detect_columns, split_page_at_boundary

log = structlog.get_logger(__name__)


class PdfPlumberExtractor(TextExtractor):
    """Extract text from PDFs using pdfplumber with multi-column awareness."""

    def __init__(self, config: ExtractorConfig | None = None) -> None:
        self._config = config or ExtractorConfig()

    @property
    def name(self) -> str:
        return "pdfplumber"

    def extract(self, pdf_path: Path) -> RawExtraction:
        """Extract text, handling single- and double-column layouts.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            RawExtraction with concatenated page text and per-page metadata.

        Raises:
            PDFCorruptError: File cannot be opened.
            PDFEncryptedError: PDF is password-protected.
            ExtractionFailedError: No pages found.
        """
        log.info("pdfplumber_extraction_start", path=str(pdf_path))

        try:
            pdf = pdfplumber.open(str(pdf_path))
        except pdfplumber.pdfminer.pdfdocument.PDFPasswordIncorrect as exc:
            raise PDFEncryptedError(f"PDF is password-protected: {pdf_path}") from exc
        except Exception as exc:
            raise PDFCorruptError(f"Cannot open PDF: {pdf_path} — {exc}") from exc

        with pdf:
            if not pdf.pages:
                raise ExtractionFailedError(f"PDF has no pages: {pdf_path}")

            if pdf.doc.is_extractable is False:
                raise PDFEncryptedError(f"PDF text extraction not permitted: {pdf_path}")

            pages_text: list[str] = []
            pages_info: list[PageInfo] = []

            for page in pdf.pages:
                page_text, page_info = self._extract_page(page)
                pages_text.append(page_text)
                pages_info.append(page_info)

        full_text = "\n\n".join(t for t in pages_text if t.strip())
        log.info(
            "pdfplumber_extraction_done",
            chars=len(full_text),
            pages=len(pages_info),
        )
        return RawExtraction(
            text=full_text,
            method=ExtractionMethod.PDFPLUMBER,
            pages_info=pages_info,
        )

    def _extract_page(self, page: Any) -> tuple[str, PageInfo]:
        """Extract text from a single pdfplumber page object.

        Returns:
            Tuple of (page_text, PageInfo).
        """
        words = page.extract_words()
        x_coords = [float(w["x0"]) for w in words]
        page_width = float(page.width)
        page_height = float(page.height)

        boundary = detect_columns(
            word_x_coords=x_coords,
            page_width=page_width,
            column_gap_ratio=self._config.column_gap_ratio,
            min_words=self._config.column_min_words,
        )

        if boundary is not None:
            text = self._extract_two_columns(page, page_width, page_height, boundary)
            is_multi = True
        else:
            extracted = page.extract_text(x_tolerance=3, y_tolerance=3)
            text = extracted or ""
            is_multi = False

        # word_count must reflect the words *on the page* (from the layout
        # analysis), not the cropped column subset — otherwise multi-column
        # pages report a misleadingly small count.
        word_count = len(words)
        page_info = PageInfo(
            page_number=page.page_number,
            width=page_width,
            height=page_height,
            is_multi_column=is_multi,
            word_count=word_count,
        )
        return text, page_info

    def _extract_two_columns(
        self,
        page: Any,
        page_width: float,
        page_height: float,
        boundary: Any,
    ) -> str:
        """Crop and extract left and right columns separately.

        Reading order: left column top-to-bottom, then right column top-to-bottom.
        """
        (left_x0, left_x1), (right_x0, right_x1) = split_page_at_boundary(
            page_width, boundary
        )

        top = float(page.bbox[1])
        bottom = float(page.bbox[3])

        left_page = page.crop((left_x0, top, left_x1, bottom))
        right_page = page.crop((right_x0, top, right_x1, bottom))

        left_text = left_page.extract_text(x_tolerance=3, y_tolerance=3) or ""
        right_text = right_page.extract_text(x_tolerance=3, y_tolerance=3) or ""

        return f"{left_text}\n{right_text}".strip()
