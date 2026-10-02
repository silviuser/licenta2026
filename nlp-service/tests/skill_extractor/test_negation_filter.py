"""Unit tests for :mod:`skill_extractor.filters.negation`."""

from __future__ import annotations

import pytest

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.filters.negation import NegationFilter
from skill_extractor.models import Language


@pytest.fixture
def filter_default() -> NegationFilter:
    return NegationFilter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _negate(text: str, target: str, lang: Language, *, fil: NegationFilter) -> bool:
    """Convenience: locate ``target`` in ``text`` and return is_negated."""
    start = text.index(target)
    return fil.is_negated(text=text, match_start=start, language=lang)


# ---------------------------------------------------------------------------
# English negation patterns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "context",
    [
        "I have no experience with ",
        "I have no knowledge of ",
        "I had no exposure to ",
        "Not familiar with ",
        "Not proficient in ",
        "Lack of experience with ",
        "Without any experience in ",
        "Unfamiliar with ",
        "Never used ",
        "Never worked with ",
        "Zero experience with ",
    ],
)
def test_english_negation_drops_match(
    context: str, filter_default: NegationFilter
) -> None:
    text = f"{context}Python."
    assert _negate(text, "Python", "en", fil=filter_default) is True


@pytest.mark.parametrize(
    "context",
    [
        "Proficient in ",
        "I have 5 years of experience with ",
        "Worked extensively with ",
        "Strong knowledge of ",
        "Expert in ",
    ],
)
def test_english_positive_context_keeps_match(
    context: str, filter_default: NegationFilter
) -> None:
    text = f"{context}Python."
    assert _negate(text, "Python", "en", fil=filter_default) is False


# ---------------------------------------------------------------------------
# Romanian negation patterns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "context",
    [
        "Nu am lucrat cu ",
        "Nu am lucrat in ",
        "Nu am experiență cu ",
        "Nu am experienta cu ",  # no diacritics
        "Nu am cunoștințe despre ",
        "Nu am cunostinte despre ",  # no diacritics
        "Nu am folosit ",
        "Nu cunosc ",
        "Fără experiență cu ",
        "Fara experienta cu ",  # no diacritics
        "Lipsa de experiență cu ",
        "Nu sunt familiarizat cu ",
        "Nu sunt familiarizată cu ",  # feminine form
    ],
)
def test_romanian_negation_drops_match(
    context: str, filter_default: NegationFilter
) -> None:
    text = f"{context}Python."
    assert _negate(text, "Python", "ro", fil=filter_default) is True


@pytest.mark.parametrize(
    "context",
    [
        "Experiență cu ",
        "Experienta in ",
        "Cunoștințe avansate de ",
        "Am lucrat 5 ani cu ",
        "Folosesc zilnic ",
    ],
)
def test_romanian_positive_context_keeps_match(
    context: str, filter_default: NegationFilter
) -> None:
    text = f"{context}Python."
    assert _negate(text, "Python", "ro", fil=filter_default) is False


# ---------------------------------------------------------------------------
# Window boundary
# ---------------------------------------------------------------------------


def test_negation_outside_window_is_ignored() -> None:
    """A negation phrase further than ``window_chars`` chars before the
    match must not flag the match."""
    fil = NegationFilter(SkillExtractorConfig(negation_window_chars=20))
    # "no experience with" is 18 chars; add 25 chars of padding before
    # the target so the negation falls outside the window.
    padding = "X" * 25
    text = f"no experience with {padding} Python"
    assert _negate(text, "Python", "en", fil=fil) is False


def test_negation_at_window_edge_is_caught() -> None:
    """Negation that ends right at the start of the window is still
    caught — that's the whole point of anchoring the regex at ``$``."""
    fil = NegationFilter(SkillExtractorConfig(negation_window_chars=30))
    text = "no experience with Python"
    assert _negate(text, "Python", "en", fil=fil) is True


def test_match_at_offset_zero_is_never_negated(
    filter_default: NegationFilter,
) -> None:
    """If the match is at the very start of the text, there's no
    preceding context to negate it."""
    text = "Python is great."
    assert (
        filter_default.is_negated(text=text, match_start=0, language="en")
        is False
    )


# ---------------------------------------------------------------------------
# Anchoring — the "list-form negation" known limitation
# ---------------------------------------------------------------------------


def test_list_form_negation_only_catches_first_item(
    filter_default: NegationFilter,
) -> None:
    """``"no experience with X, Y, Python"`` — only ``X`` is adjacent to
    the negation. The patterns are anchored, so ``Python`` is NOT
    flagged. Documented limitation; Module 3 will close this gap."""
    text = "I have no experience with Java, SQL, and Python today."
    # 'Java' should be dropped (immediately follows the negation).
    assert _negate(text, "Java", "en", fil=filter_default) is True
    # 'Python' should NOT be flagged — too far from the negation.
    assert _negate(text, "Python", "en", fil=filter_default) is False


def test_negation_in_unrelated_sentence_does_not_leak(
    filter_default: NegationFilter,
) -> None:
    """A negation in a different sentence (separated by the window
    distance) does not flag a later match."""
    text = (
        "Earlier in my career I had no experience with COBOL. "
        "I now spend most of my day writing Python and SQL."
    )
    assert _negate(text, "Python", "en", fil=filter_default) is False


# ---------------------------------------------------------------------------
# Window property
# ---------------------------------------------------------------------------


def test_window_chars_property_reflects_config() -> None:
    fil = NegationFilter(SkillExtractorConfig(negation_window_chars=99))
    assert fil.window_chars == 99
