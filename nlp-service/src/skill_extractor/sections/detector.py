"""Detect CV section headers in extracted text.

The :class:`SectionDetector` walks the input line-by-line, normalises
each line (lower-case, trailing-punctuation strip, diacritic strip)
and matches it against a curated dictionary of English and Romanian
section headers. Detected headers split the text into contiguous
non-overlapping :class:`Section` ranges that downstream code uses to
boost or penalise the confidence of skill matches.

Why a hand-crafted regex / dictionary, not an ML classifier?
------------------------------------------------------------
Section detection in CVs is a textbook *high-precision, deterministic*
task: 95 % of CV authors use one of a small set of section headers
verbatim. A classifier would add training data, version skew and
opacity for negligible recall gain. The thesis defence wants
**interpretability**, and "we matched the literal string ``Skills`` on
its own line" is the clearest possible justification.

What this module deliberately does **not** do
---------------------------------------------
* It does NOT try to detect column boundaries (Module 1's
  ``utils/layout.py`` already returns reading-order text; we trust it).
* It does NOT classify free-text paragraphs that lack a header — those
  are tagged ``"other"`` and downstream scoring uses the lowest
  section weight on them.
* It does NOT recognise *every* possible header variant in the wild;
  it covers the common ones, and unknown headers degrade gracefully
  to ``"other"``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import structlog

from skill_extractor.models import SectionLabel

logger = structlog.get_logger(__name__)

# Maximum length for a line to even be considered a header. CV section
# headers in the wild are 1-4 words; 60 characters is generous.
_MAX_HEADER_LINE_LENGTH = 60

# Strip a trailing run of punctuation / dashes / box-drawing characters
# that some CV templates attach decoratively after a header
# (``Education:``, ``Skills.``, ``EDUCATION ──``, ``EXPERIENCE ━━━``).
# ``[^\w\s]`` is Unicode-aware in Python 3 and excludes letters / digits
# / underscore / whitespace, so it matches symbols and punctuation
# without us having to enumerate every decorative codepoint we might
# encounter in the wild.
_TERMINAL_PUNCT_RE = re.compile(r"[^\w\s]+\s*$")

# Map of *normalised* header strings → section label. Normalisation
# (see :func:`_normalise`) lower-cases and strips diacritics, so the
# keys here must already be lower-case ASCII.
#
# This dictionary is the source of truth. Add more variants to extend
# coverage; downstream code never branches on the section label outside
# the values defined in :data:`SectionLabel`.
_HEADERS_BY_NORMAL_FORM: dict[str, SectionLabel] = {
    # --- Skills (EN + RO) ---
    "skills": "skills",
    "key skills": "skills",
    "core skills": "skills",
    "technical skills": "skills",
    "professional skills": "skills",
    "hard skills": "skills",
    "soft skills": "skills",
    "computer skills": "skills",
    "it skills": "skills",
    "digital skills": "skills",
    "competente": "skills",  # competențe (Romanian)
    "competente personale": "skills",
    "competente profesionale": "skills",
    "competente digitale": "skills",
    "competente tehnice": "skills",
    "aptitudini": "skills",
    "abilitati": "skills",
    # --- Experience (EN + RO) ---
    "experience": "experience",
    "work experience": "experience",
    "working experience": "experience",
    "professional experience": "experience",
    "employment": "experience",
    "employment history": "experience",
    "career": "experience",
    "career history": "experience",
    "experienta": "experience",
    "experienta profesionala": "experience",
    "experienta de munca": "experience",
    "experienta in munca": "experience",
    "locuri de munca": "experience",
    # --- Education (EN + RO) ---
    "education": "education",
    "education and training": "education",
    "academic background": "education",
    "academic": "education",
    "studies": "education",
    "qualifications": "education",
    "educatie": "education",  # educație
    "formare": "education",
    "studii": "education",
    "educatie si formare": "education",
    "educatie si formare profesionala": "education",
    # --- Profile / Summary (EN + RO) ---
    "profile": "profile",
    "personal profile": "profile",
    "summary": "profile",
    "professional summary": "profile",
    "career summary": "profile",
    "about": "profile",
    "about me": "profile",
    "career objective": "profile",
    "objective": "profile",
    "profil": "profile",
    "profil personal": "profile",
    "despre mine": "profile",
    "sumar": "profile",
    "rezumat": "profile",
    "obiectiv": "profile",
    "obiectiv profesional": "profile",
    # --- Languages (EN + RO) ---
    "languages": "languages",
    "language skills": "languages",
    "languages spoken": "languages",
    "foreign languages": "languages",
    "limbi": "languages",
    "limbi straine": "languages",  # limbi străine
    "limbi cunoscute": "languages",
    "competente lingvistice": "languages",
}


def _strip_diacritics(text: str) -> str:
    """Remove combining marks (NFKD decomposition).

    ``"competențe"`` → ``"competente"``; ``"experiență"`` →
    ``"experienta"``. Romanian CVs are routinely typed without
    diacritics, so the detector matches both forms with a single
    dictionary entry.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _normalise(line: str) -> str | None:
    """Reduce a line to a canonical lookup key, or ``None`` if it
    cannot be a header.

    Returns ``None`` for empty / whitespace-only lines and for lines
    longer than :data:`_MAX_HEADER_LINE_LENGTH` characters after
    trimming. Otherwise returns lower-cased, diacritic-free, trailing-
    punctuation-stripped text.
    """
    stripped = _TERMINAL_PUNCT_RE.sub("", line.strip()).strip()
    if not stripped or len(stripped) > _MAX_HEADER_LINE_LENGTH:
        return None
    return _strip_diacritics(stripped.lower())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Section:
    """A contiguous range of the text classified as a single section.

    ``start`` and ``end`` are character offsets into the original text
    (``end`` is exclusive). ``[start, end)`` covers the section's
    *content*: the header line itself is excluded so that skill
    matches landing on the header word don't get falsely attributed
    to the section they introduce.
    """

    label: SectionLabel
    start: int
    end: int

    def contains(self, offset: int) -> bool:
        """Return True if ``offset`` falls within this section."""
        return self.start <= offset < self.end


class SectionDetector:
    """Detect section ranges in CV text.

    The detector is stateless and thread-safe. Construct once, call
    :meth:`detect` per CV.
    """

    @staticmethod
    def detect(text: str) -> list[Section]:
        """Partition ``text`` into a list of contiguous, non-overlapping
        :class:`Section` ranges in document order.

        The first emitted section is always ``"other"`` and starts at
        offset ``0``. If at least one header is detected, subsequent
        sections cover everything from after a header line to the
        start of the next header line (or end of text). If no headers
        are detected, the result is a single ``"other"`` section
        spanning the entire text.

        An empty / whitespace-only input returns an empty list.
        """
        if not text or not text.strip():
            return []

        # Walk lines preserving offsets. ``str.splitlines`` discards the
        # line terminators, so we use a manual scan instead.
        headers: list[tuple[int, int, SectionLabel]] = []
        # (line_start, line_end, label) for each header line found.

        line_start = 0
        n = len(text)
        while line_start <= n:
            newline_pos = text.find("\n", line_start)
            if newline_pos == -1:
                line_end = n
            else:
                line_end = newline_pos
            line = text[line_start:line_end]
            label = SectionDetector._match(line)
            if label is not None:
                headers.append((line_start, line_end, label))
            if newline_pos == -1:
                break
            line_start = newline_pos + 1

        sections: list[Section] = []
        if not headers:
            sections.append(Section(label="other", start=0, end=n))
            return sections

        # Pre-header preamble (typically: name, contact info).
        first_header_start = headers[0][0]
        if first_header_start > 0:
            sections.append(
                Section(label="other", start=0, end=first_header_start)
            )

        # Each detected header → section from line_end+1 to next header start.
        for idx, (_h_start, h_end, label) in enumerate(headers):
            content_start = min(h_end + 1, n)  # skip past the header line
            if idx + 1 < len(headers):
                content_end = headers[idx + 1][0]
            else:
                content_end = n
            if content_start < content_end:
                sections.append(
                    Section(
                        label=label, start=content_start, end=content_end
                    )
                )
            else:
                # Empty section (header immediately followed by another
                # header). Emit a zero-width record anyway so the label
                # is preserved in the output for completeness.
                sections.append(
                    Section(
                        label=label,
                        start=content_start,
                        end=content_start,
                    )
                )

        logger.debug(
            "section_detector.detected",
            headers_found=len(headers),
            sections=len(sections),
            labels=[s.label for s in sections],
        )
        return sections

    @staticmethod
    def section_for(
        sections: list[Section], offset: int
    ) -> SectionLabel:
        """Return the label of the section containing ``offset``.

        If no section contains the offset (shouldn't happen with the
        output of :meth:`detect`), returns ``"other"`` as a safe
        default.
        """
        for sec in sections:
            if sec.contains(offset):
                return sec.label
        return "other"

    @staticmethod
    def _match(line: str) -> SectionLabel | None:
        """Return the section label for a line, or ``None`` if the line
        is not a recognised header."""
        key = _normalise(line)
        if key is None:
            return None
        return _HEADERS_BY_NORMAL_FORM.get(key)
