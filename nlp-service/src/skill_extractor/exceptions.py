"""Custom exception hierarchy for the skill_extractor module.

All exceptions inherit from :class:`SkillExtractorError` so callers can catch
the base class when they don't need to distinguish specific failure modes.

The hierarchy mirrors the one in :mod:`cv_extractor.exceptions` for
consistency across modules.
"""


class SkillExtractorError(Exception):
    """Base class for all skill extractor errors."""


class UnsupportedLanguageError(SkillExtractorError):
    """Raised when the input language is not in the supported set.

    Module 2 currently supports English (``"en"``) and Romanian (``"ro"``).
    Any other value — including ``None`` from
    :class:`cv_extractor.models.ExtractionMetadata.detected_language` —
    raises this error.
    """

    def __init__(self, language: object) -> None:
        super().__init__(
            f"Unsupported language: {language!r}. "
            "Supported languages: 'en', 'ro'."
        )
        self.language = language


class NotACVError(SkillExtractorError):
    """Raised when the input is not classified as a CV.

    Module 1 emits the warning
    ``"Document may not be a CV — few CV-specific keywords found."``
    when its keyword heuristic decides the document is likely a cover
    letter or other non-CV. Module 2 treats that warning as a hard
    filter: skill extraction on a cover letter would produce misleading
    matches (e.g. the candidate's name as a skill, or company names from
    the addressee block).
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "Input is not classified as a CV "
            "(Module 1 quality check warning present)."
        )


class EscoLoadError(SkillExtractorError):
    """Raised when the ESCO taxonomy CSV files cannot be parsed.

    Carries the offending path so the user can locate the problem file.
    """

    def __init__(self, message: str, path: str | None = None) -> None:
        super().__init__(message)
        self.path = path


class MatcherCacheError(SkillExtractorError):
    """Raised when the on-disk PhraseMatcher cache cannot be read or written.

    The error is non-fatal at the application level: the matcher can
    always be rebuilt from source. Callers that catch this exception
    should rebuild and proceed.
    """
