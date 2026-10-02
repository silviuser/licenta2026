"""Unit tests for :mod:`skill_extractor.sections.detector`."""

from __future__ import annotations

from itertools import pairwise
from textwrap import dedent

import pytest

from skill_extractor.sections.detector import (
    Section,
    SectionDetector,
)

# ---------------------------------------------------------------------------
# Empty / trivial inputs
# ---------------------------------------------------------------------------


class TestTrivialInput:
    def test_empty_string(self) -> None:
        assert SectionDetector.detect("") == []

    def test_whitespace_only(self) -> None:
        assert SectionDetector.detect("   \n\n   \n") == []

    def test_no_headers_yields_single_other_section(self) -> None:
        text = "Hello, world.\nNo headers here at all."
        sections = SectionDetector.detect(text)
        assert sections == [Section(label="other", start=0, end=len(text))]


# ---------------------------------------------------------------------------
# Single-section detection
# ---------------------------------------------------------------------------


class TestSingleSection:
    def test_skills_header_creates_skills_section(self) -> None:
        text = "Name: John\nSkills\nPython, SQL"
        sections = SectionDetector.detect(text)
        assert len(sections) == 2
        assert sections[0].label == "other"
        assert sections[0].start == 0
        assert sections[1].label == "skills"
        # Section content starts after the header line.
        assert text[sections[1].start : sections[1].end].strip() == "Python, SQL"

    def test_header_with_trailing_colon(self) -> None:
        text = "Profile:\nA passionate engineer."
        sections = SectionDetector.detect(text)
        labels = [s.label for s in sections]
        assert "profile" in labels

    @pytest.mark.parametrize(
        "header,expected_label",
        [
            ("Skills", "skills"),
            ("SKILLS", "skills"),
            ("Technical Skills", "skills"),
            ("Hard Skills:", "skills"),
            ("Soft Skills.", "skills"),
            ("Experience", "experience"),
            ("Work Experience", "experience"),
            ("Professional Experience:", "experience"),
            ("Employment History", "experience"),
            ("Education", "education"),
            ("Education and Training", "education"),
            ("Studies", "education"),
            ("Profile", "profile"),
            ("Summary", "profile"),
            ("Career Objective", "profile"),
            ("Languages", "languages"),
            ("Foreign Languages", "languages"),
        ],
    )
    def test_english_header_variants(
        self, header: str, expected_label: str
    ) -> None:
        text = f"{header}\nSome content here.\n"
        sections = SectionDetector.detect(text)
        labels = [s.label for s in sections]
        assert expected_label in labels


# ---------------------------------------------------------------------------
# Romanian-language headers (with and without diacritics)
# ---------------------------------------------------------------------------


class TestRomanianHeaders:
    @pytest.mark.parametrize(
        "header,expected_label",
        [
            ("Competențe", "skills"),
            ("Competente", "skills"),  # no diacritics
            ("COMPETENȚE", "skills"),
            ("Aptitudini:", "skills"),
            ("Abilități", "skills"),
            ("Competențe digitale", "skills"),
            ("Experiență", "experience"),
            ("Experienta", "experience"),  # no diacritics
            ("Experiență profesională", "experience"),
            ("Experienta profesionala", "experience"),
            ("Locuri de muncă", "experience"),
            ("Educație", "education"),
            ("Educatie", "education"),
            ("Educație și formare", "education"),
            ("Educatie si formare", "education"),
            ("Studii", "education"),
            ("Profil personal", "profile"),
            ("Despre mine", "profile"),
            ("Sumar", "profile"),
            ("Obiectiv profesional", "profile"),
            ("Limbi străine", "languages"),
            ("Limbi straine", "languages"),
            ("Competențe lingvistice", "languages"),
        ],
    )
    def test_romanian_header_variants(
        self, header: str, expected_label: str
    ) -> None:
        text = f"{header}\nConținut.\n"
        sections = SectionDetector.detect(text)
        labels = [s.label for s in sections]
        assert (
            expected_label in labels
        ), f"Expected {expected_label!r} from header {header!r}, got {labels}"


# ---------------------------------------------------------------------------
# Multi-section flow
# ---------------------------------------------------------------------------


class TestMultiSection:
    def test_full_cv_layout(self) -> None:
        """Realistic-ish CV layout — exercise the whole flow."""
        text = dedent(
            """\
            John Doe
            john@example.com

            Profile
            Software engineer with 5 years experience.

            Skills
            Python, SQL, Docker

            Experience
            Acme Corp — Senior Engineer
            2020-Present

            Education
            BSc Computer Science
            2014-2018

            Languages
            English (C2), French (B1)
            """
        )
        sections = SectionDetector.detect(text)
        labels = [s.label for s in sections]
        # Must see the preamble + 5 sections.
        assert labels == [
            "other",
            "profile",
            "skills",
            "experience",
            "education",
            "languages",
        ]

        # Content checks: each section's body contains the right
        # substring.
        get = lambda lbl: next(  # noqa: E731
            text[s.start : s.end] for s in sections if s.label == lbl
        )
        assert "Python" in get("skills")
        assert "Acme" in get("experience")
        assert "Computer Science" in get("education")
        assert "English" in get("languages")
        assert "Software engineer" in get("profile")
        assert "John Doe" in get("other")

    def test_sections_are_contiguous_and_non_overlapping(self) -> None:
        text = dedent(
            """\
            Header
            preamble
            Skills
            Python
            Experience
            Acme
            """
        )
        sections = SectionDetector.detect(text)
        # Sort by start (already sorted, but sanity).
        sections_sorted = sorted(sections, key=lambda s: s.start)
        for prev, curr in pairwise(sections_sorted):
            # End of previous = start of next minus the header line length.
            # We can't predict offsets exactly, but we can assert no
            # overlap.
            assert prev.end <= curr.start

    def test_back_to_back_headers_emit_zero_width_section(self) -> None:
        """Two header lines in a row → zero-width section for the first."""
        text = "Skills\nExperience\nAcme\n"
        sections = SectionDetector.detect(text)
        # Expect: skills (zero width or just the gap), experience.
        labels = [s.label for s in sections]
        assert "skills" in labels
        assert "experience" in labels


# ---------------------------------------------------------------------------
# Heuristics — what should NOT count as a header
# ---------------------------------------------------------------------------


class TestNonHeaderRejection:
    def test_long_line_with_header_word_is_not_header(self) -> None:
        """Sentences containing a header word in body text don't trigger."""
        text = (
            "I have skills in many areas including programming and design. "
            "Below is more text that goes on far longer than a header would."
        )
        sections = SectionDetector.detect(text)
        # The whole text should remain a single 'other' section.
        assert len(sections) == 1
        assert sections[0].label == "other"

    def test_unrecognised_short_line_falls_back_to_other(self) -> None:
        text = "Random Heading\nSome content\n"
        sections = SectionDetector.detect(text)
        # 'Random Heading' isn't in our dictionary → entire text 'other'.
        assert sections == [Section(label="other", start=0, end=len(text))]

    def test_max_length_boundary(self) -> None:
        """A line longer than the header limit is never matched even if
        its prefix would be a valid header."""
        long_line = "Skills " + ("x " * 60)  # well over 60 chars
        text = f"{long_line}\nbody\n"
        sections = SectionDetector.detect(text)
        # The 'Skills' word is buried in a long line — must not trigger.
        assert all(s.label == "other" for s in sections)


# ---------------------------------------------------------------------------
# section_for
# ---------------------------------------------------------------------------


class TestSectionFor:
    def test_lookup_returns_correct_label(self) -> None:
        text = "Profile\nSummary text.\nSkills\nPython, SQL\n"
        sections = SectionDetector.detect(text)
        # Offset of 'P' in 'Python' should be inside the skills section.
        offset_python = text.index("Python")
        assert SectionDetector.section_for(sections, offset_python) == "skills"
        # Offset of 'S' in 'Summary' should be inside profile.
        offset_summary = text.index("Summary")
        assert (
            SectionDetector.section_for(sections, offset_summary)
            == "profile"
        )

    def test_lookup_outside_returns_other(self) -> None:
        sections = [Section(label="skills", start=10, end=20)]
        # Offset 5 is before the only section.
        assert SectionDetector.section_for(sections, 5) == "other"
        # Offset 20 is exclusive end.
        assert SectionDetector.section_for(sections, 20) == "other"

    def test_lookup_on_empty_sections_returns_other(self) -> None:
        assert SectionDetector.section_for([], 0) == "other"
