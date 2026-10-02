"""Fallback extractor using PyMuPDF (fitz).

PyMuPDF is faster than pdfplumber and uses a different internal algorithm,
making it a useful fallback when pdfplumber produces poor results.  We use
the ``"blocks"`` extraction mode which preserves paragraph structure better
than the default mode.
"""

from pathlib import Path

import fitz  # PyMuPDF
import structlog

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import (
    ExtractionFailedError,
    PDFCorruptError,
    PDFEncryptedError,
)
from cv_extractor.extractors.base import TextExtractor
from cv_extractor.models import ExtractionMethod, PageInfo, RawExtraction
from cv_extractor.utils.layout import detect_columns

log = structlog.get_logger(__name__)


class PyMuPDFExtractor(TextExtractor):
    """Extract text from PDFs using PyMuPDF (fitz)."""

    def __init__(self, config: ExtractorConfig | None = None) -> None:
        self._config = config or ExtractorConfig()

    @property
    def name(self) -> str:
        return "pymupdf"

    def extract(self, pdf_path: Path) -> RawExtraction:
        """Extract text using PyMuPDF block extraction.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            RawExtraction with text and per-page metadata.

        Raises:
            PDFCorruptError: File cannot be opened.
            PDFEncryptedError: PDF is password-protected.
            ExtractionFailedError: No pages found.
        """
        log.info("pymupdf_extraction_start", path=str(pdf_path))

        try:
            doc = fitz.open(str(pdf_path))
        except fitz.FileDataError as exc:
            raise PDFCorruptError(f"PyMuPDF cannot open PDF: {pdf_path}") from exc
        except Exception as exc:
            raise PDFCorruptError(f"Unexpected error opening PDF: {pdf_path} — {exc}") from exc

        with doc:
            if doc.is_encrypted:
                if not doc.authenticate(""):
                    raise PDFEncryptedError(f"PDF is password-protected: {pdf_path}")

            if doc.page_count == 0:
                raise ExtractionFailedError(f"PDF has no pages: {pdf_path}")

            pages_text: list[str] = []
            pages_info: list[PageInfo] = []

            for page_num in range(doc.page_count):
                page = doc[page_num]
                page_text, page_info = self._extract_page(page, page_num + 1)
                pages_text.append(page_text)
                pages_info.append(page_info)

        full_text = "\n\n".join(t for t in pages_text if t.strip())
        log.info(
            "pymupdf_extraction_done",
            chars=len(full_text),
            pages=len(pages_info),
        )
        return RawExtraction(
            text=full_text,
            method=ExtractionMethod.PYMUPDF,
            pages_info=pages_info,
        )

    def _extract_page(self, page: fitz.Page, page_num: int) -> tuple[str, PageInfo]:
        """Extract text from a single PyMuPDF page.

        Uses ``get_text("blocks")`` which groups text into rectangular blocks
        and sorts them by vertical position, giving better paragraph separation
        than the raw character stream.

        Returns:
            Tuple of (page_text, PageInfo).
        """
        rect = page.rect
        page_width = float(rect.width)
        page_height = float(rect.height)

        # Collect word x-coordinates for column detection.
        words = page.get_text("words")  # returns (x0,y0,x1,y1,word,block,line,word_num)
        x_coords = [float(w[0]) for w in words]

        boundary = detect_columns(
            word_x_coords=x_coords,
            page_width=page_width,
            column_gap_ratio=self._config.column_gap_ratio,
            min_words=self._config.column_min_words,
        )

        if boundary is not None:
            # Extract left and right halves via clipping rectangles.
            left_rect = fitz.Rect(0, 0, boundary.gap_start_x, page_height)
            right_rect = fitz.Rect(boundary.gap_end_x, 0, page_width, page_height)

            left_text = page.get_textbox(left_rect)
            right_text = page.get_textbox(right_rect)
            text = f"{left_text}\n{right_text}".strip()
            is_multi = True
        else:
            blocks = page.get_text("blocks")
            # Each block: (x0, y0, x1, y1, text, block_no, block_type)
            # block_type 0 = text, 1 = image
            text_blocks = [b[4] for b in blocks if b[6] == 0]
            text = "\n".join(text_blocks).strip()
            is_multi = False

        word_count = len(text.split())
        page_info = PageInfo(
            page_number=page_num,
            width=page_width,
            height=page_height,
            is_multi_column=is_multi,
            word_count=word_count,
        )
        return text, page_info
