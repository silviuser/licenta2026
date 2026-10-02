"""Drop matches preceded by a negation phrase.

The PhraseMatcher returns purely positive evidence: it cannot tell
``"experienced with Kubernetes"`` from ``"no experience with Kubernetes"``.
This filter inspects the ``window_chars`` characters of context
*immediately* before a match and rejects the match if a known
negation pattern ends right before the match start.

Why anchored patterns?
----------------------
Patterns require ``\\s*$`` at the end so they only match negations
*directly adjacent* to the skill. This means a sentence like ``"I had
no experience with Java but I am proficient in Python"`` correctly
keeps ``Python`` (because ``"no experience with"`` is far from the
``Python`` match) and drops ``Java`` (because the negation is
adjacent).

Romanian
--------
Romanian patterns are written in plain ASCII; we strip diacritics from
the inspected window before matching, so ``experiență`` and
``experienta`` are treated identically.

Known limitations (will be improved in Module 3)
-------------------------------------------------
* List-form negation: ``"no experience with X, Y, Python"`` — only the
  first listed item (``X``) gets dropped because the patterns are
  anchored. The rest are kept. Module 3's semantic model handles this.
* Double negation: ``"not without experience"`` reads positively but
  this filter would still drop a match adjacent to it. We accept the
  false-negative on the (rare) double-negation case to keep the
  filter cheap and deterministic.
"""

from __future__ import annotations

import re
import unicodedata
from re import Pattern

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.models import Language

# ---------------------------------------------------------------------------
# Pattern definitions (ASCII; diacritics are stripped from the input)
# ---------------------------------------------------------------------------

# English negations that frequently precede a skill in CV / cover-letter
# text. Each pattern terminates with ``\s*$`` so it must be adjacent to
# the match.
_PATTERNS_EN: list[str] = [
    # ``exposure`` collocates with ``to``; the others typically with
    # ``with`` / ``in`` / ``of``. Allowing ``to`` everywhere is fine —
    # the rare ungrammatical combination ("no experience to X") is not
    # something we'd see in a real CV anyway.
    r"\bno\s+(experience|knowledge|familiarity|background|exposure)"
    r"\s+(with|in|of|to)\s*$",
    r"\bnot\s+(familiar|proficient|experienced|skilled|comfortable)"
    r"\s+(with|in)\s*$",
    r"\black\s+of\s+(experience|knowledge|familiarity|exposure)"
    r"(\s+(with|in|of|to))?\s*$",
    r"\bwithout\s+(any\s+)?"
    r"(experience|knowledge|background|exposure)\s+(with|in|of|to)\s*$",
    r"\bunfamiliar\s+with\s*$",
    r"\bnever\s+(used|worked\s+with|tried|touched)\s*$",
    r"\bzero\s+experience\s+(with|in)\s*$",
]

# Romanian — diacritics-free thanks to NFKD normalisation upstream.
# ``experienta`` covers both ``experiență`` and ``experienta`` in the
# input. Same for ``cunostinte`` ↔ ``cunoștințe``, ``fara`` ↔ ``fără``.
_PATTERNS_RO: list[str] = [
    r"\bnu\s+am\s+(lucrat\s+(cu|in)|"
    r"experienta\s+(cu|in)|"
    r"cunostinte\s+(cu|de|despre|in)|"
    r"folosit)\s*$",
    r"\bnu\s+cunosc\s*$",
    r"\bnu\s+sunt\s+familiariza\w+\s+cu\s*$",
    r"\bfara\s+experienta\s+(cu|in)\s*$",
    r"\blipsa\s+de\s+experienta\s+(cu|in)\s*$",
    r"\bnu\s+stiu\s*$",
]


def _compile_union(patterns: list[str]) -> Pattern[str]:
    """Combine a list of regexes into a single non-capturing alternation
    for one-pass scanning of the window."""
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def _strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class NegationFilter:
    """Decide whether a match span is preceded by a negation phrase.

    Stateless beyond the compiled regexes set up in ``__init__``;
    instances are cheap and thread-safe to share.
    """

    def __init__(self, config: SkillExtractorConfig | None = None) -> None:
        self._window = (config or SkillExtractorConfig()).negation_window_chars
        self._regex_by_lang: dict[Language, Pattern[str]] = {
            "en": _compile_union(_PATTERNS_EN),
            "ro": _compile_union(_PATTERNS_RO),
        }

    @property
    def window_chars(self) -> int:
        return self._window

    def is_negated(
        self,
        *,
        text: str,
        match_start: int,
        language: Language,
    ) -> bool:
        """Return True if a negation pattern ends within the
        ``window_chars`` immediately preceding ``match_start``.

        Both EN and RO regex unions are run against a diacritic-stripped,
        lower-cased copy of the window so the patterns can be plain
        ASCII.
        """
        if match_start <= 0:
            return False
        window_start = max(0, match_start - self._window)
        window = text[window_start:match_start]
        normalised = _strip_diacritics(window).lower()
        regex = self._regex_by_lang[language]
        return regex.search(normalised) is not None
