"""Custom exception hierarchy for the CV extractor module.

All exceptions inherit from CVExtractorError so callers can catch the base
class when they don't need to distinguish specific failure modes.
"""


class CVExtractorError(Exception):
    """Base class for all CV extractor errors."""


class PDFCorruptError(CVExtractorError):
    """Raised when the PDF file is corrupt or cannot be parsed."""


class PDFEncryptedError(CVExtractorError):
    """Raised when the PDF is password-protected and no password is provided."""


class ExtractionFailedError(CVExtractorError):
    """Raised when all extractors fail to produce any usable text."""


class LowQualityExtractionError(CVExtractorError):
    """Raised when extracted text does not meet the minimum quality threshold.

    Attach the partial quality_score so callers can decide whether to use
    the low-quality output or reject it entirely.
    """

    def __init__(self, message: str, quality_score: float) -> None:
        super().__init__(message)
        self.quality_score = quality_score
