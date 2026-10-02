"""Application configuration via Pydantic Settings.

All thresholds and tuneable parameters live here — no magic numbers
scattered across the codebase. Values are loaded from environment variables
(prefixed ``CV_EXTRACTOR_``) or from a ``.env`` file.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExtractorConfig(BaseSettings):
    """Central configuration for the CV extraction pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="CV_EXTRACTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Quality thresholds -------------------------------------------------

    min_chars_per_page: int = Field(
        default=100,
        description="Minimum character count per page for extraction to be considered successful.",
    )
    min_alpha_ratio: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Minimum ratio of alphabetic characters to total characters.",
    )
    min_quality_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum quality score (0–1) before a LowQualityExtractionError is raised.",
    )

    # --- CV keyword detection -----------------------------------------------

    # Keywords used to confirm the document is indeed a CV/résumé.
    # Covers English and Romanian.
    cv_keywords: list[str] = Field(
        default=[
            "experience",
            "education",
            "skills",
            "work",
            "employment",
            "projects",
            "languages",
            "contact",
            # Romanian
            "experiență",
            "educație",
            "competențe",
            "limbi",
            "proiecte",
            "abilități",
        ],
    )
    cv_keyword_min_matches: int = Field(
        default=2,
        description="How many CV keywords must appear for the document to be classified as a CV.",
    )

    # --- OCR settings -------------------------------------------------------

    tesseract_cmd: str = Field(
        default="",
        description="Full path to the Tesseract binary. Empty string = use system PATH.",
    )
    tesseract_lang: str = Field(
        default="eng+ron",
        description="Tesseract language string, e.g. 'eng+ron' for English + Romanian.",
    )
    ocr_dpi: int = Field(
        default=300,
        ge=72,
        le=600,
        description="DPI for rendering PDF pages to images before OCR.",
    )

    # --- Layout detection ---------------------------------------------------

    column_gap_ratio: float = Field(
        default=0.1,
        ge=0.01,
        le=0.5,
        description=(
            "Minimum gap between word clusters (as a fraction of page width) "
            "to classify a page as multi-column."
        ),
    )
    column_min_words: int = Field(
        default=10,
        description="Minimum number of words on a page to attempt column detection.",
    )

    # --- Logging ------------------------------------------------------------

    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
