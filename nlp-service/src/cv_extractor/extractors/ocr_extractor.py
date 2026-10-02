"""Last-resort OCR extractor for scanned / image-based PDFs.

Flow:
  1. Convert each PDF page to a PIL Image at the configured DPI (default 300).
  2. Run pytesseract on the image with the configured language string.
  3. Aggregate per-page text and metadata.

Requires:
  - Tesseract binary installed on the system (or path set in config).
  - ``pdf2image`` and ``pillow`` Python packages.
"""

from pathlib import Path

import pytesseract
import structlog
from pdf2image import convert_from_path
from pdf2image.exceptions import (
    PDFInfoNotInstalledError,
    PDFPageCountError,
    PDFSyntaxError,
)
from PIL.Image import Image

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import (
    ExtractionFailedError,
    PDFCorruptError,
)
from cv_extractor.extractors.base import TextExtractor
from cv_extractor.models import ExtractionMethod, PageInfo, RawExtraction

log = structlog.get_logger(__name__)


class OCRExtractor(TextExtractor):
    """Extract text from scanned PDFs via Tesseract OCR."""

    def __init__(self, config: ExtractorConfig | None = None) -> None:
        self._config = config or ExtractorConfig()
        if self._config.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._config.tesseract_cmd

    @property
    def name(self) -> str:
        return "ocr_tesseract"

    def extract(self, pdf_path: Path) -> RawExtraction:
        """Convert PDF pages to images and run Tesseract OCR.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            RawExtraction with OCR text and per-page metadata.

        Raises:
            PDFCorruptError: pdf2image cannot process the file.
            ExtractionFailedError: No images were rendered.
        """
        log.info("ocr_extraction_start", path=str(pdf_path), dpi=self._config.ocr_dpi)

        try:
            images: list[Image] = convert_from_path(  # type: ignore[assignment]
                str(pdf_path),
                dpi=self._config.ocr_dpi,
            )
        except (PDFSyntaxError, PDFPageCountError, PDFInfoNotInstalledError) as exc:
            raise PDFCorruptError(f"pdf2image cannot process PDF: {pdf_path}") from exc
        except Exception as exc:
            raise PDFCorruptError(
                f"Unexpected error during PDF-to-image conversion: {exc}"
            ) from exc

        if not images:
            raise ExtractionFailedError(f"No pages rendered from PDF: {pdf_path}")

        pages_text: list[str] = []
        pages_info: list[PageInfo] = []

        for page_num, image in enumerate(images, start=1):
            page_text, page_info = self._ocr_page(image, page_num)
            pages_text.append(page_text)
            pages_info.append(page_info)

        full_text = "\n\n".join(t for t in pages_text if t.strip())
        log.info("ocr_extraction_done", chars=len(full_text), pages=len(pages_info))

        return RawExtraction(
            text=full_text,
            method=ExtractionMethod.OCR_TESSERACT,
            pages_info=pages_info,
        )

    def _ocr_page(self, image: Image, page_num: int) -> tuple[str, PageInfo]:
        """Run Tesseract on a single page image.

        Args:
            image:    PIL Image of the page.
            page_num: 1-based page number for metadata.

        Returns:
            Tuple of (ocr_text, PageInfo).
        """
        width, height = image.size

        try:
            text: str = pytesseract.image_to_string(
                image,
                lang=self._config.tesseract_lang,
                config="--psm 3",  # fully automatic page segmentation
            )
        except pytesseract.TesseractError as exc:
            log.warning("tesseract_page_error", page=page_num, error=str(exc))
            text = ""

        word_count = len(text.split())
        page_info = PageInfo(
            page_number=page_num,
            # pdf2image returns pixel dimensions; store as float for consistency.
            width=float(width),
            height=float(height),
            is_multi_column=False,  # OCR doesn't do column detection
            word_count=word_count,
        )
        return text, page_info
