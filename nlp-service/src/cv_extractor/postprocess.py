"""Text post-processing and quality assessment.

All functions are pure (no I/O, no side effects) to keep them easily testable.
The pipeline calls ``postprocess_text()`` once after extraction is complete.
``QualityChecker`` is used by the pipeline to decide whether to advance to
the next extractor or accept the current result.
"""

import re
import unicodedata

import structlog

from cv_extractor.config import ExtractorConfig

log = structlog.get_logger(__name__)

# Typographic ligatures that appear in PDF text streams as single characters.
_LIGATURE_MAP: dict[str, str] = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}

# Non-breaking space and other lookalike whitespace → regular space.
_WHITESPACE_NORMALISE = re.compile(r"[\xa0 -​  　]+")

# Collapse runs of horizontal whitespace (spaces/tabs) to a single space.
_MULTI_SPACE = re.compile(r"[ \t]{2,}")

# Collapse 3+ consecutive blank lines to exactly 2 (one blank line = paragraph break).
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")

# Non-printable characters excluding normal whitespace (\n, \r, \t, space).
_NON_PRINTABLE = re.compile(r"[^\x09\x0a\x0d\x20-\x7e\x80-�]")

# OCR artefact: word-initial "rn" misread from "m".
# Applied conservatively: only matches "rn" at the *start of a word*, followed
# by another lowercase letter — e.g. "rnarket" → "market", "rnoney" → "money".
# Mid-word "rn" (as in "cornputer", "warn", "earn", "environment") is left
# alone because it is genuinely ambiguous.  \b is a zero-width assertion so it
# is compatible with Python's fixed-width lookbehind constraint.
_OCR_RN_TO_M = re.compile(r"\brn(?=[a-z])")


def postprocess_text(text: str, *, was_ocr: bool = False) -> str:
    """Clean and normalise extracted PDF text.

    Processing order matters: we fix ligatures before collapsing whitespace
    so that "ﬁ" expansions don't accidentally create double spaces.

    Args:
        text:    Raw text from an extractor.
        was_ocr: When True, apply additional OCR-specific corrections.

    Returns:
        Cleaned, normalised text string.
    """
    if not text:
        return ""

    text = _expand_ligatures(text)
    text = _normalise_whitespace(text)
    text = _remove_non_printable(text)
    text = _normalise_line_endings(text)

    if was_ocr:
        text = _fix_ocr_artifacts(text)

    return text.strip()


def _expand_ligatures(text: str) -> str:
    for ligature, replacement in _LIGATURE_MAP.items():
        text = text.replace(ligature, replacement)
    return text


def _normalise_whitespace(text: str) -> str:
    text = _WHITESPACE_NORMALISE.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text


def _remove_non_printable(text: str) -> str:
    # Keep valid Unicode (U+0080–U+FFFD covers diacritics, Cyrillic, etc.)
    return _NON_PRINTABLE.sub("", text)


def _normalise_line_endings(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _EXCESS_BLANK_LINES.sub("\n\n", text)
    return text


def _fix_ocr_artifacts(text: str) -> str:
    """Apply cautious OCR corrections.

    Only the ``rn → m`` substitution is applied, and only where the context
    makes it unambiguous (surrounded by lowercase letters).
    """
    return _OCR_RN_TO_M.sub("m", text)


# ---------------------------------------------------------------------------
# Quality checker
# ---------------------------------------------------------------------------


class QualityChecker:
    """Scores extracted text quality on a 0.0–1.0 scale.

    The score is a weighted combination of three independent signals:
      - alpha_ratio:    fraction of alphabetic characters (weight 0.4)
      - keyword_ratio:  fraction of CV keywords present (weight 0.4)
      - length_score:   whether minimum length threshold is met (weight 0.2)

    A score of 1.0 is a clean, keyword-rich text; 0.0 is garbage.
    """

    def __init__(self, config: ExtractorConfig | None = None) -> None:
        self._config = config or ExtractorConfig()

    def score(self, text: str, total_pages: int = 1) -> float:
        """Compute a quality score for extracted text.

        The formula combines content quality (alpha + keyword ratios) and
        length, but *gates* the content score by length so that very short
        text cannot earn a passing score on alpha-ratio alone.  This stops
        garbage outputs like a single character "x" — alpha_ratio=1.0 — from
        scoring above the fallback threshold.

        Args:
            text:        The (post-processed) extracted text.
            total_pages: Number of pages — used for per-page length check.

        Returns:
            Float in [0.0, 1.0].
        """
        if not text:
            return 0.0

        alpha_ratio = self._alpha_ratio(text)
        keyword_ratio = self._keyword_ratio(text)
        length_score = self._length_score(text, total_pages)

        content_score = 0.5 * alpha_ratio + 0.5 * keyword_ratio
        # Multiplicative gate: short text caps the achievable score.  Once
        # length_score == 1.0 (text >= min_chars_per_page * pages) the score
        # equals content_score; below that the score scales linearly down.
        score = length_score * content_score
        log.debug(
            "quality_score_computed",
            alpha_ratio=round(alpha_ratio, 3),
            keyword_ratio=round(keyword_ratio, 3),
            length_score=round(length_score, 3),
            content_score=round(content_score, 3),
            final_score=round(score, 3),
        )
        return round(score, 4)

    def is_sufficient(self, text: str, total_pages: int = 1) -> bool:
        """Return True if the text meets the minimum quality threshold.

        Args:
            text:        Extracted text to evaluate.
            total_pages: Page count for per-page length normalisation.
        """
        return self.score(text, total_pages) >= self._config.min_quality_score

    def is_likely_cv(self, text: str) -> bool:
        """Return True if the text contains enough CV-specific keywords."""
        lower = text.lower()
        matches = sum(1 for kw in self._config.cv_keywords if kw.lower() in lower)
        return matches >= self._config.cv_keyword_min_matches

    # --- private helpers ----------------------------------------------------

    def _alpha_ratio(self, text: str) -> float:
        total = len(text)
        if total == 0:
            return 0.0
        alpha = sum(1 for c in text if unicodedata.category(c).startswith("L"))
        return alpha / total

    def _keyword_ratio(self, text: str) -> float:
        lower = text.lower()
        matches = sum(1 for kw in self._config.cv_keywords if kw.lower() in lower)
        return min(1.0, matches / max(1, len(self._config.cv_keywords)))

    def _length_score(self, text: str, total_pages: int) -> float:
        total_pages = max(1, total_pages)
        expected_min = self._config.min_chars_per_page * total_pages
        if len(text) >= expected_min:
            return 1.0
        return len(text) / expected_min
