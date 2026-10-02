"""Abstract base class that all concrete extractors must implement."""

from abc import ABC, abstractmethod
from pathlib import Path

from cv_extractor.models import RawExtraction


class TextExtractor(ABC):
    """Contract for all PDF text extractors.

    A concrete extractor receives a PDF path and returns a ``RawExtraction``
    containing the raw (not yet post-processed) text plus per-page metadata.
    It must NOT perform post-processing — that is the pipeline's job.
    """

    @abstractmethod
    def extract(self, pdf_path: Path) -> RawExtraction:
        """Extract raw text from a PDF file.

        Args:
            pdf_path: Absolute path to the PDF file.

        Returns:
            A ``RawExtraction`` with text and per-page metadata.

        Raises:
            PDFCorruptError:  The file cannot be opened as a PDF.
            PDFEncryptedError: The PDF is password-protected.
            ExtractionFailedError: Extraction produced no usable content.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable extractor identifier used in logs and metadata."""
