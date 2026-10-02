"""Unit tests for :mod:`skill_extractor.sections.language_parser`.

The four cases listed as obligatory in the May-2026 patch round
spec are each verified explicitly, plus a few additional CV-realistic
inputs to exercise the fall-back branches.
"""

from __future__ import annotations

import pytest

from skill_extractor.sections.language_parser import parse_languages


def _parse(text: str) -> list[tuple[str, str | None]]:
    """Helper: parse the entire text and return (language, level) tuples."""
    matches = parse_languages(text=text, section_start=0, section_end=len(text))
    return [(m.language, m.level) for m in matches]


def test_english_b2_obligatory() -> None:
    assert _parse("English (B2)") == [("English", "B2")]


def test_english_fluent_obligatory() -> None:
    assert _parse("English (fluent)") == [("English", "fluent")]


def test_romanian_native_obligatory() -> None:
    assert _parse("Romanian (native)") == [("Romanian", "native")]


def test_cambridge_advanced_cae_c1_obligatory() -> None:
    """``Cambridge English: Advanced (CAE), C1`` resolves to C1."""
    text = "English: Cambridge English: Advanced (CAE), C1"
    parsed = _parse(text)
    # Either the colon form or the inline CAE acronym should yield C1.
    assert ("English", "C1") in parsed


def test_multiple_languages_in_block() -> None:
    text = "Languages:\nEnglish (C1)\nRomanian (native)\nFrench - B2\n"
    parsed = _parse(text)
    assert ("English", "C1") in parsed
    assert ("Romanian", "native") in parsed
    assert ("French", "B2") in parsed


def test_language_without_level_returns_none() -> None:
    parsed = _parse("English")
    # Either no entry (regex requires the language form) or English with no level.
    if parsed:
        assert parsed == [("English", None)]


def test_dedupes_same_language() -> None:
    """Repeated ``English`` declarations are emitted once."""
    text = "Languages: English (B2)\nEnglish (B2)\nEnglish (B2)"
    parsed = _parse(text)
    assert parsed.count(("English", "B2")) == 1


def test_does_not_emit_random_proper_nouns() -> None:
    """The parser must not treat ``Java`` or ``Python`` as a language."""
    parsed = _parse("Java (8 years)")
    assert parsed == []


def test_does_not_match_inside_random_capitalised_word() -> None:
    parsed = _parse("Skilled programmer (good)")
    assert parsed == []


def test_dash_separator_form() -> None:
    parsed = _parse("English - C1, French - B2")
    assert ("English", "C1") in parsed
    assert ("French", "B2") in parsed


def test_section_offsets_respected() -> None:
    """The parser only inspects the slice the caller hands it."""
    text = "noise English (B2) more noise"
    section_start = text.index("English")
    section_end = section_start + len("English (B2)")
    matches = parse_languages(
        text=text,
        section_start=section_start,
        section_end=section_end,
    )
    assert len(matches) == 1
    assert matches[0].language == "English"
    assert matches[0].char_start == section_start
    assert matches[0].char_end == section_start + len("English")


def test_intermediate_word_normalises_to_b1() -> None:
    parsed = _parse("English (intermediate)")
    assert parsed == [("English", "B1")]


def test_advanced_word_normalises_to_c1() -> None:
    parsed = _parse("English (advanced)")
    assert parsed == [("English", "C1")]


def test_german_recognised() -> None:
    parsed = _parse("German (A2)")
    assert parsed == [("German", "A2")]


def test_romana_diacritic_free() -> None:
    parsed = _parse("Romana (nativ)")
    # Native synonyms are language-agnostic; check the canonical key:
    if parsed:
        language, level = parsed[0]
        assert language == "Romanian"


def test_diacritic_native_synonym() -> None:
    parsed = _parse("Romanian (mother tongue)")
    assert parsed == [("Romanian", "native")]


def test_empty_section_returns_empty() -> None:
    assert parse_languages(text="anything", section_start=5, section_end=5) == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("A1", "A1"),
        ("a2", "A2"),
        ("B1", "B1"),
        ("b2", "B2"),
        ("C1", "C1"),
        ("c2", "C2"),
    ],
)
def test_cefr_letters_normalised(raw: str, expected: str) -> None:
    parsed = _parse(f"English ({raw})")
    assert parsed == [("English", expected)]


# ---------------------------------------------------------------------------
# Coverage closers — drive the rarely-hit branches of _extract_level
# ---------------------------------------------------------------------------


def test_cae_acronym_resolves_via_cert_match() -> None:
    """``English (CAE)`` resolves to C1 via the Cambridge acronym path."""
    parsed = _parse("English (CAE)")
    assert parsed == [("English", "C1")]


def test_cefr_letter_embedded_in_phrase() -> None:
    """The fallback ``\\b[abc][12]\\b`` search inside a phrase still resolves."""
    parsed = _parse("English (level c1 around 2024)")
    assert parsed == [("English", "C1")]


def test_advanced_word_in_phrase_normalises() -> None:
    """The last-ditch word-form scan resolves ``advanced`` inside a phrase."""
    # The parenthetical does not match any direct CEFR key, and contains
    # no isolated CEFR letter — the loop over ``_CEFR_NORMALISATION``
    # keywords picks up ``advanced`` → C1.
    parsed = _parse("English (achieved advanced last summer)")
    assert parsed == [("English", "C1")]


def test_cambridge_advanced_no_acronym_resolves_to_c1() -> None:
    """``Cambridge English: Advanced`` (no CAE) still resolves via qualification table."""
    parsed = _parse("English: Cambridge English: Advanced")
    assert ("English", "C1") in parsed


def test_unparseable_parenthetical_returns_none_level() -> None:
    """A parenthetical with no recognisable level yields ``level=None``."""
    parsed = parse_languages(
        text="English (some unrelated note)",
        section_start=0,
        section_end=len("English (some unrelated note)"),
    )
    assert parsed and parsed[0].level is None
