"""Regex parser for the CV ``Languages`` section.

Why a dedicated parser?
------------------------
The May-2026 validation report (section 6, false-negative pattern #4)
showed that Module 2 systematically misses declared languages —
``English (B2)``, ``English (fluent)``, ``Romanian (native)``,
``Cambridge English: Advanced (CAE), C1``. The bare PhraseMatcher
indexes the ESCO language overlay but is keyed on the LANGUAGE name
alone; it has no notion of the *parenthetical level* that almost every
CV attaches. Worse, the CV's Languages section is often a tight
``Language: Level`` list that defeats the section weighting, since
each line is a hit-with-no-context for the matcher.

The dedicated parser runs ONLY inside the section that
:class:`~skill_extractor.sections.detector.SectionDetector` labels
``"languages"`` (deliberately not over the whole CV — that would
re-introduce the false-positive families like ``"Java"`` being parsed
as a language). It emits one :class:`LanguageMatch` per language /
level pair, with the surface form, the canonical language name and
the normalised CEFR level (``A1``/.../``C2``, plus ``"fluent"`` and
``"native"`` as informal levels).

The output is fed into the same aggregation path as the PhraseMatcher
hits — language matches become :class:`~skill_extractor.models.SkillMatch`
instances with ``skill_type="language"`` and a populated
``cefr_level`` field.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import structlog

from skill_extractor.models import CefrLevel

logger = structlog.get_logger(__name__)

# Canonical English language names we recognise. Add more here as the
# fixture corpus grows — we deliberately do not pull from a huge
# external taxonomy because the parser's value comes from precision,
# not coverage.
_KNOWN_LANGUAGES: dict[str, str] = {
    # English variants
    "english": "English",
    "engleza": "English",
    # Romanian
    "romanian": "Romanian",
    "romana": "Romanian",
    "roumain": "Romanian",
    # Common others — keep this list short and curated. Any language
    # not in this dict is still emitted (rare cases) as long as the
    # surrounding pattern fires; see ``_LANGUAGE_PATTERN``.
    "french": "French",
    "franceza": "French",
    "german": "German",
    "germana": "German",
    "deutsch": "German",
    "spanish": "Spanish",
    "spaniola": "Spanish",
    "italian": "Italian",
    "italiana": "Italian",
    "portuguese": "Portuguese",
    "russian": "Russian",
    "rusa": "Russian",
    "japanese": "Japanese",
    "chinese": "Chinese",
    "korean": "Korean",
    "arabic": "Arabic",
    "dutch": "Dutch",
    "polish": "Polish",
    "hungarian": "Hungarian",
    "turkish": "Turkish",
}

# Map of surface forms (lower-case, ASCII) to CEFR levels. The order
# below is significant only for the fallback ``"english"`` lookup; the
# regex pattern below combines all variants explicitly. ``"fluent"`` and
# ``"native"`` are informal levels that CV authors use freely; we keep
# them as-is rather than coercing to a CEFR letter.
_CEFR_NORMALISATION: dict[str, CefrLevel] = {
    "a1": "A1",
    "a2": "A2",
    "b1": "B1",
    "b2": "B2",
    "c1": "C1",
    "c2": "C2",
    "beginner": "A1",
    "elementary": "A2",
    "pre-intermediate": "A2",
    "intermediate": "B1",
    "upper-intermediate": "B2",
    "upper intermediate": "B2",
    "advanced": "C1",
    "proficient": "C2",
    "proficiency": "C2",
    "mastery": "C2",
    "fluent": "fluent",
    "fluency": "fluent",
    "native": "native",
    "mother tongue": "native",
    "mother-tongue": "native",
    "first language": "native",
    "limba materna": "native",
}

# Cambridge / IELTS / TOEFL / DELF qualification → CEFR.
_QUALIFICATION_CEFR: dict[str, CefrLevel] = {
    "ket": "A2",
    "pet": "B1",
    "fce": "B2",
    "cae": "C1",
    "cpe": "C2",
    "advanced": "C1",  # Cambridge English: Advanced
    "proficiency": "C2",  # Cambridge English: Proficiency
    "preliminary": "B1",
    "first": "B2",
    "delf b1": "B1",
    "delf b2": "B2",
    "dalf c1": "C1",
    "dalf c2": "C2",
}

# Main pattern: one language name followed (optionally) by a level in
# parentheses or after a dash / colon. The level itself can be a CEFR
# letter, a level word, or a Cambridge tag.
_LANGUAGE_LINE_RE = re.compile(
    r"""
    \b
    (?P<lang>[A-Za-z\-]{3,30})           # language name
    \s*
    (?:
        \(                                # ( level )
            \s*(?P<paren_level>[^()]+?)\s*
        \)
      |
        [-–—:]\s*                         # - level  OR  : level
            (?P<dash_level>[A-Za-z0-9 +/]+?)
            (?=\s*(?:[,;\n]|$))
    )?
    """,
    re.VERBOSE,
)

# Inline Cambridge / certification pattern, used after the main one
# fires on a "Cambridge English" prefix. We look for ``CAE``, ``CPE``,
# ``FCE``, ``B2 First``, ``C1 Advanced``, etc.
_CERT_RE = re.compile(
    r"""
    \b
    (?:
        (?P<cefr1>[ABCabc][12])\s+
        (?:Advanced|Proficiency|First|Preliminary|Key)
      |
        (?:Advanced|Proficiency|First|Preliminary|Key)
        (?:\s*\(?\s*(?P<cefr2>[ABCabc][12])\s*\)?)?
      |
        (?P<acronym>KET|PET|FCE|CAE|CPE|DELF|DALF)
    )
    """,
    re.VERBOSE,
)


@dataclass(slots=True, frozen=True)
class LanguageMatch:
    """One language declaration parsed from the CV's Languages section.

    Attributes
    ----------
    language
        Canonical English name (``"English"``, ``"Romanian"``).
    surface
        The exact surface form the language name appeared as.
    level
        Normalised CEFR level (``"A1"``..``"C2"``) or the informal
        labels ``"fluent"`` / ``"native"``; ``None`` if no level was
        parseable.
    char_start, char_end
        Character offsets of the language name in the *original* text
        (not the slice fed to the parser).
    """

    language: str
    surface: str
    level: CefrLevel | None
    char_start: int
    char_end: int


def parse_languages(
    *,
    text: str,
    section_start: int,
    section_end: int,
) -> list[LanguageMatch]:
    """Run the parser over ``text[section_start:section_end]``.

    The function never raises; unparseable input simply returns an
    empty list. Each returned :class:`LanguageMatch` carries the
    char offsets in the FULL text (the offsets are translated from
    the slice).
    """
    if section_start >= section_end:
        return []
    slice_ = text[section_start:section_end]
    results: list[LanguageMatch] = []
    seen_languages: set[str] = set()
    for m in _LANGUAGE_LINE_RE.finditer(slice_):
        lang_surface = m.group("lang") or ""
        lang_key = _normalise_lookup(lang_surface)
        if lang_key in _CEFR_NORMALISATION:
            # The "lang" slot matched a level word like "fluent"; that
            # is not a language name, skip.
            continue
        canonical = _KNOWN_LANGUAGES.get(lang_key)
        if canonical is None:
            # We deliberately do NOT fall back to a heuristic for
            # unknown words: the language section is the high-precision
            # path of Module 2, and admitting "Java (8 years)" or
            # "Skilled programmer (good)" as a language hit would
            # re-introduce exactly the kind of FP family the parser
            # exists to suppress.
            continue

        level = _extract_level(m, slice_)
        # Also scan for an inline Cambridge / certification phrase if
        # we haven't found a level yet.
        if level is None and canonical == "English":
            level = _scan_certification(slice_=slice_, start=m.end())

        char_start = section_start + m.start("lang")
        char_end = section_start + m.end("lang")

        # Dedupe identical language declarations within a section —
        # CV authors sometimes repeat headers (``Languages: English``)
        # right before each line.
        key = canonical.lower()
        if key in seen_languages:
            continue
        seen_languages.add(key)

        results.append(
            LanguageMatch(
                language=canonical,
                surface=lang_surface,
                level=level,
                char_start=char_start,
                char_end=char_end,
            )
        )

    logger.debug(
        "language_parser.parsed",
        languages=len(results),
        section_start=section_start,
        section_end=section_end,
    )
    return results


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _normalise_lookup(token: str) -> str:
    """Lower-case + strip diacritics for the language-name dictionary."""
    decomposed = unicodedata.normalize("NFKD", token)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _extract_level(m: re.Match[str], _slice: str) -> CefrLevel | None:
    """Return the normalised CEFR level captured by the main regex."""
    raw = m.group("paren_level") or m.group("dash_level")
    if not raw:
        return None
    key = raw.strip().lower()
    # Direct hit.
    if key in _CEFR_NORMALISATION:
        return _CEFR_NORMALISATION[key]
    # ``Cambridge English: Advanced (CAE), C1`` carries the level
    # inline; try the certification regex on the parenthetical too.
    cert = _CERT_RE.search(raw)
    if cert is not None:
        return _level_from_cert_match(cert)
    # Last-ditch: any CEFR token embedded in the string.
    cefr = re.search(r"\b([abc][12])\b", key)
    if cefr is not None:
        return _CEFR_NORMALISATION.get(cefr.group(1).lower())
    # Word forms ("fluent", "advanced") inside a phrase.
    for kw, lvl in _CEFR_NORMALISATION.items():
        if re.search(rf"\b{re.escape(kw)}\b", key):
            return lvl
    return None


def _scan_certification(*, slice_: str, start: int) -> CefrLevel | None:
    """Look for a Cambridge / acronym certification after position ``start``."""
    window = slice_[start : start + 120]
    cert = _CERT_RE.search(window)
    if cert is None:
        return None
    return _level_from_cert_match(cert)


def _level_from_cert_match(cert: re.Match[str]) -> CefrLevel | None:
    """Resolve a :class:`re.Match` from :data:`_CERT_RE` to a CEFR level."""
    acro = (cert.group("acronym") or "").lower()
    if acro in _QUALIFICATION_CEFR:
        return _QUALIFICATION_CEFR[acro]
    explicit = cert.group("cefr1") or cert.group("cefr2")
    if explicit is not None:
        return _CEFR_NORMALISATION.get(explicit.lower())
    # Cambridge English: Advanced / Proficiency without an explicit
    # letter — fall back to the qualification table.
    word_match = re.search(
        r"\b(Advanced|Proficiency|First|Preliminary|Key)\b",
        cert.group(0),
        re.IGNORECASE,
    )
    if word_match is not None:
        return _QUALIFICATION_CEFR.get(word_match.group(1).lower())
    return None
