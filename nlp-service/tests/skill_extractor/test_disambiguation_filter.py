"""Unit tests for :mod:`skill_extractor.filters.disambiguation`.

These tests pass synthetic ``EntitySpan`` lists rather than running a
real spaCy pipeline. The filter is pure-Python by design.
"""

from __future__ import annotations

import pytest

from skill_extractor.filters.disambiguation import (
    EntitySpan,
    NerDisambiguationFilter,
)


@pytest.fixture
def filter_default() -> NerDisambiguationFilter:
    return NerDisambiguationFilter()


# ---------------------------------------------------------------------------
# Skills section is always trusted
# ---------------------------------------------------------------------------


class TestSkillsSectionExempt:
    def test_skills_section_keeps_match_even_with_overlapping_org(
        self, filter_default: NerDisambiguationFilter
    ) -> None:
        text = "Java, Python, SQL"
        # Pretend NER tagged Java as ORG (this happens — Java is the
        # name of multiple companies).
        ents = [EntitySpan(start_char=0, end_char=4, label="ORG")]
        # In skills section we keep it regardless.
        assert (
            filter_default.is_misclassified_proper_noun(
                text=text,
                entities=ents,
                match_start=0,
                match_end=4,
                section="skills",
            )
            is False
        )


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------


class TestWhitelist:
    @pytest.mark.parametrize(
        "surface",
        ["Python", "JAVA", "Kubernetes", "Docker", "AWS", "C++", "Spring Boot"],
    )
    def test_whitelisted_surfaces_are_kept(
        self, surface: str, filter_default: NerDisambiguationFilter
    ) -> None:
        text = f"I worked at Google with {surface} extensively."
        start = text.index(surface)
        end = start + len(surface)
        # Pretend NER tagged the surface as ORG.
        ents = [EntitySpan(start_char=start, end_char=end, label="ORG")]
        # Outside skills section, but in whitelist → keep.
        assert (
            filter_default.is_misclassified_proper_noun(
                text=text,
                entities=ents,
                match_start=start,
                match_end=end,
                section="experience",
            )
            is False
        )

    def test_custom_whitelist_overrides_default(self) -> None:
        custom = frozenset({"acme"})
        fil = NerDisambiguationFilter(tech_whitelist=custom)
        text = "I worked at Acme Corp."
        ents = [EntitySpan(start_char=12, end_char=16, label="ORG")]
        # 'Acme' is in the custom whitelist → keep.
        assert (
            fil.is_misclassified_proper_noun(
                text=text,
                entities=ents,
                match_start=12,
                match_end=16,
                section="experience",
            )
            is False
        )
        # Python is NOT in the custom whitelist → drop on NER overlap.
        text2 = "Working with Python."
        ents2 = [EntitySpan(start_char=13, end_char=19, label="ORG")]
        assert (
            fil.is_misclassified_proper_noun(
                text=text2,
                entities=ents2,
                match_start=13,
                match_end=19,
                section="experience",
            )
            is True
        )


# ---------------------------------------------------------------------------
# Drop labels — what gets dropped, what doesn't
# ---------------------------------------------------------------------------


class TestDropLabels:
    @pytest.mark.parametrize(
        "label", ["ORG", "GPE", "LOC", "PERSON", "FAC", "NORP"]
    )
    def test_drop_label_overlapping_match_drops(
        self, label: str, filter_default: NerDisambiguationFilter
    ) -> None:
        # Surface 'Acme' is not in the tech whitelist.
        text = "Worked at Acme on stuff"
        ents = [EntitySpan(start_char=10, end_char=14, label=label)]
        assert (
            filter_default.is_misclassified_proper_noun(
                text=text,
                entities=ents,
                match_start=10,
                match_end=14,
                section="experience",
            )
            is True
        )

    @pytest.mark.parametrize(
        "label", ["DATE", "TIME", "MONEY", "PERCENT", "EVENT", "WORK_OF_ART"]
    )
    def test_non_drop_label_is_ignored(
        self, label: str, filter_default: NerDisambiguationFilter
    ) -> None:
        text = "Worked at Acme on stuff"
        ents = [EntitySpan(start_char=10, end_char=14, label=label)]
        assert (
            filter_default.is_misclassified_proper_noun(
                text=text,
                entities=ents,
                match_start=10,
                match_end=14,
                section="experience",
            )
            is False
        )


# ---------------------------------------------------------------------------
# Overlap geometry
# ---------------------------------------------------------------------------


class TestOverlapGeometry:
    def test_no_entities_keeps_match(
        self, filter_default: NerDisambiguationFilter
    ) -> None:
        assert (
            filter_default.is_misclassified_proper_noun(
                text="some text",
                entities=[],
                match_start=0,
                match_end=4,
                section="experience",
            )
            is False
        )

    def test_disjoint_entity_keeps_match(
        self, filter_default: NerDisambiguationFilter
    ) -> None:
        # Entity at [0, 5), match at [10, 14) — disjoint.
        text = "Acme   Foobar"
        ents = [EntitySpan(start_char=0, end_char=4, label="ORG")]
        assert (
            filter_default.is_misclassified_proper_noun(
                text=text,
                entities=ents,
                match_start=7,
                match_end=13,
                section="experience",
            )
            is False
        )

    def test_partial_overlap_drops_match(
        self, filter_default: NerDisambiguationFilter
    ) -> None:
        # Entity at [0, 8), match at [4, 12) — partial overlap on [4, 8).
        text = "AcmeMega Corp"
        ents = [EntitySpan(start_char=0, end_char=8, label="ORG")]
        assert (
            filter_default.is_misclassified_proper_noun(
                text=text,
                entities=ents,
                match_start=4,
                match_end=12,
                section="experience",
            )
            is True
        )

    def test_adjacent_non_overlapping_keeps_match(
        self, filter_default: NerDisambiguationFilter
    ) -> None:
        """Half-open overlap test: ent.end_char == match_start is NOT
        an overlap (they share a single boundary point)."""
        ents = [EntitySpan(start_char=0, end_char=10, label="ORG")]
        assert (
            filter_default.is_misclassified_proper_noun(
                text="X" * 20,
                entities=ents,
                match_start=10,
                match_end=15,
                section="experience",
            )
            is False
        )


# ---------------------------------------------------------------------------
# Profile / education / other sections behave the same way as experience
# ---------------------------------------------------------------------------


class TestNonSkillsSectionsTreatedUniformly:
    @pytest.mark.parametrize(
        "section", ["experience", "education", "profile", "languages", "other"]
    )
    def test_org_overlap_drops_outside_skills(
        self, section: str, filter_default: NerDisambiguationFilter
    ) -> None:
        text = "I attended Acme University."
        ents = [EntitySpan(start_char=11, end_char=15, label="ORG")]
        # 'Acme' is NOT in tech whitelist → dropped.
        assert (
            filter_default.is_misclassified_proper_noun(
                text=text,
                entities=ents,
                match_start=11,
                match_end=15,
                section=section,  # type: ignore[arg-type]
            )
            is True
        )
