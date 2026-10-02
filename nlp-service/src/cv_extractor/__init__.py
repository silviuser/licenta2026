"""cv_extractor — PDF text extraction module for HR Helper.

Public API::

    from cv_extractor.pipeline import ExtractionPipeline
    from cv_extractor.models import ExtractionResult

    pipeline = ExtractionPipeline()
    result: ExtractionResult = pipeline.process(Path("cv.pdf"))
    print(result.text)
"""

from cv_extractor.models import ExtractionResult, ExtractionMethod
from cv_extractor.pipeline import ExtractionPipeline
from cv_extractor.exceptions import (
    CVExtractorError,
    PDFCorruptError,
    PDFEncryptedError,
    ExtractionFailedError,
    LowQualityExtractionError,
)

# Step 10 (2026-05-17): introduced so the FastAPI ``GET /v1/info``
# endpoint can surface Module 1's version alongside Module 2 and
# Module 3 versions. The literal MUST match the ``[project].version``
# in ``nlp-service/pyproject.toml`` (single project version applies
# to all three packages built from this repo); a drift-detection
# test in ``tests/cv_extractor/test_version.py`` asserts this.
__version__ = "0.2.0"

__all__ = [
    "ExtractionPipeline",
    "ExtractionResult",
    "ExtractionMethod",
    "CVExtractorError",
    "PDFCorruptError",
    "PDFEncryptedError",
    "ExtractionFailedError",
    "LowQualityExtractionError",
    "__version__",
]
