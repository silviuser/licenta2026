"""Unit tests for :mod:`skill_extractor.esco.matcher`.

These tests need spaCy installed (it's a hard dep of the package) but
deliberately avoid downloaded language models. ``spacy.blank("en")``
ships with the ``spacy`` PyPI package and is enough to tokenise text.

The matcher is built with ``attr="LOWER"`` rather than the production
default ``attr="LEMMA"`` because the blank pipeline has no lemmatiser.
This is good test design: it verifies the matcher / cache mechanics
without coupling the tests to a 600 MB model download.
"""

from __future__ import annotations

from pathlib import Path

import pytest

spacy = pytest.importorskip("spacy")

from skill_extractor.config import SkillExtractorConfig  # noqa: E402
from skill_extractor.esco.cache import MatchMeta  # noqa: E402
from skill_extractor.esco.matcher import (  # noqa: E402
    BuiltMatcher,
    EscoMatcherBuilder,
    compute_match_kind,
)
from skill_extractor.models import EscoSkill  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def nlp_blank_en() -> spacy.Language:  # type: ignore[name-defined]
    """A bare-bones English tokenizer — no model download required."""
    return spacy.blank("en")


@pytest.fixture
def sample_skills() -> list[EscoSkill]:
    return [
        EscoSkill(
            concept_uri="uri:python",
            preferred_label="Python",
            alt_labels=["Python3", "py"],
            skill_type="knowledge",
        ),
        EscoSkill(
            concept_uri="uri:sql",
            preferred_label="SQL",
            alt_labels=[],
            skill_type="knowledge",
        ),
        EscoSkill(
            concept_uri="uri:write-en",
            preferred_label="write English",
            alt_labels=["correspond in written English"],
            skill_type="language",
        ),
    ]


@pytest.fixture
def builder(tmp_path: Path) -> EscoMatcherBuilder:
    config = SkillExtractorConfig(cache_dir=tmp_path / "cache")
    return EscoMatcherBuilder(config=config)


# ---------------------------------------------------------------------------
# Build path
# ---------------------------------------------------------------------------


class TestBuildFresh:
    def test_returns_built_matcher(
        self,
        builder: EscoMatcherBuilder,
        nlp_blank_en: spacy.Language,  # type: ignore[name-defined]
        sample_skills: list[EscoSkill],
    ) -> None:
        built = builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash000fresh",
            phrase_attr="LOWER",
            use_cache=False,
        )
        assert isinstance(built, BuiltMatcher)
        assert built.phrase_attr == "LOWER"
        # 3 preferred + 2 with altLabels → 5 keys (uri:sql has no alt key)
        assert len(built.label_map) == 5

    def test_label_map_keys_follow_convention(
        self,
        builder: EscoMatcherBuilder,
        nlp_blank_en: spacy.Language,  # type: ignore[name-defined]
        sample_skills: list[EscoSkill],
    ) -> None:
        built = builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash000keys",
            phrase_attr="LOWER",
            use_cache=False,
        )
        assert "uri:python|preferred" in built.label_map
        assert "uri:python|alt" in built.label_map
        assert "uri:sql|preferred" in built.label_map
        assert "uri:sql|alt" not in built.label_map  # no alt labels
        meta = built.label_map["uri:python|preferred"]
        assert isinstance(meta, MatchMeta)
        assert meta.concept_uri == "uri:python"
        assert meta.preferred_label == "Python"
        assert meta.label_kind == "preferred"
        assert meta.skill_type == "knowledge"

    def test_matcher_finds_preferred_label(
        self,
        builder: EscoMatcherBuilder,
        nlp_blank_en: spacy.Language,  # type: ignore[name-defined]
        sample_skills: list[EscoSkill],
    ) -> None:
        built = builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash000match",
            phrase_attr="LOWER",
            use_cache=False,
        )
        doc = built.nlp("I write Python and SQL daily.")
        matches = built.matcher(doc)
        assert len(matches) >= 2
        match_keys = {
            built.nlp.vocab.strings[m_id] for m_id, _, _ in matches
        }
        assert "uri:python|preferred" in match_keys
        assert "uri:sql|preferred" in match_keys

    def test_matcher_finds_alt_label(
        self,
        builder: EscoMatcherBuilder,
        nlp_blank_en: spacy.Language,  # type: ignore[name-defined]
        sample_skills: list[EscoSkill],
    ) -> None:
        built = builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash000alt",
            phrase_attr="LOWER",
            use_cache=False,
        )
        doc = built.nlp("Experience with py scripting.")
        matches = built.matcher(doc)
        match_keys = {
            built.nlp.vocab.strings[m_id] for m_id, _, _ in matches
        }
        # 'py' is an altLabel for uri:python.
        assert "uri:python|alt" in match_keys


# ---------------------------------------------------------------------------
# compute_match_kind
# ---------------------------------------------------------------------------


class TestComputeMatchKind:
    @pytest.fixture
    def preferred_meta(self) -> MatchMeta:
        return MatchMeta(
            concept_uri="uri:python",
            preferred_label="Python",
            label_kind="preferred",
            skill_type="knowledge",
            surfaces={"python"},
        )

    @pytest.fixture
    def alt_meta(self) -> MatchMeta:
        return MatchMeta(
            concept_uri="uri:python",
            preferred_label="Python",
            label_kind="alt",
            skill_type="knowledge",
            surfaces={"py", "python3"},
        )

    def test_exact_when_preferred_surface_matches(
        self, preferred_meta: MatchMeta
    ) -> None:
        assert compute_match_kind(surface="Python", meta=preferred_meta) == "exact"
        assert compute_match_kind(surface="python", meta=preferred_meta) == "exact"

    def test_alt_when_alt_surface_matches(
        self, alt_meta: MatchMeta
    ) -> None:
        assert compute_match_kind(surface="py", meta=alt_meta) == "alt"
        assert compute_match_kind(surface="Python3", meta=alt_meta) == "alt"

    def test_lemma_when_surface_differs(
        self, preferred_meta: MatchMeta
    ) -> None:
        # The match was found via lemmatisation: surface doesn't match
        # any recorded pattern, but spaCy's LEMMA attr brought it in.
        assert (
            compute_match_kind(surface="Pythons", meta=preferred_meta)
            == "lemma"
        )


# ---------------------------------------------------------------------------
# Cache integration
# ---------------------------------------------------------------------------


class TestCacheRoundTrip:
    def test_second_call_uses_cache(
        self,
        builder: EscoMatcherBuilder,
        nlp_blank_en: spacy.Language,  # type: ignore[name-defined]
        sample_skills: list[EscoSkill],
    ) -> None:
        """First call builds + writes the cache; second call reads it
        and produces the same matcher behaviour."""
        first = builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash000roundtrip",
            phrase_attr="LOWER",
            use_cache=True,
        )
        second = builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash000roundtrip",
            phrase_attr="LOWER",
            use_cache=True,
        )

        # Same label_map content
        assert first.label_map.keys() == second.label_map.keys()
        for key in first.label_map:
            f, s = first.label_map[key], second.label_map[key]
            assert f.concept_uri == s.concept_uri
            assert f.preferred_label == s.preferred_label
            assert f.label_kind == s.label_kind
            assert f.surfaces == s.surfaces

        # Same matches on the same input.
        text = "I write Python with py and SQL."
        first_matches = {
            (
                second.nlp.vocab.strings[m_id],
                start,
                end,
            )
            for m_id, start, end in first.matcher(first.nlp(text))
        }
        second_matches = {
            (
                second.nlp.vocab.strings[m_id],
                start,
                end,
            )
            for m_id, start, end in second.matcher(second.nlp(text))
        }
        assert first_matches == second_matches

    def test_use_cache_false_forces_rebuild(
        self,
        builder: EscoMatcherBuilder,
        nlp_blank_en: spacy.Language,  # type: ignore[name-defined]
        sample_skills: list[EscoSkill],
    ) -> None:
        """With ``use_cache=False`` we always rebuild — even if a fresh
        cache file exists. We can't directly observe the build vs.
        restore path from the public API, so we just check that the
        result is functionally correct."""
        builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash000force",
            phrase_attr="LOWER",
            use_cache=True,  # populates cache
        )
        rebuilt = builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash000force",
            phrase_attr="LOWER",
            use_cache=False,
        )
        assert "uri:python|preferred" in rebuilt.label_map

    def test_different_hash_does_not_reuse_cache(
        self,
        builder: EscoMatcherBuilder,
        nlp_blank_en: spacy.Language,  # type: ignore[name-defined]
        sample_skills: list[EscoSkill],
    ) -> None:
        """A different ``esco_hash`` produces a different cache filename,
        so a stale cache from another hash cannot pollute the result."""
        first_skills = sample_skills
        second_skills = [
            *sample_skills,
            EscoSkill(
                concept_uri="uri:kafka",
                preferred_label="Apache Kafka",
                alt_labels=["Kafka"],
                skill_type="knowledge",
            ),
        ]
        builder.load_or_build(
            skills=first_skills,
            nlp=nlp_blank_en,
            esco_hash="hash_v1",
            phrase_attr="LOWER",
            use_cache=True,
        )
        second = builder.load_or_build(
            skills=second_skills,
            nlp=nlp_blank_en,
            esco_hash="hash_v2",
            phrase_attr="LOWER",
            use_cache=True,
        )
        # The new build sees Kafka.
        assert "uri:kafka|preferred" in second.label_map

    def test_phrase_attr_change_invalidates_cache(
        self,
        builder: EscoMatcherBuilder,
        nlp_blank_en: spacy.Language,  # type: ignore[name-defined]
        sample_skills: list[EscoSkill],
    ) -> None:
        """Switching ``phrase_attr`` (e.g. LOWER → ORTH) on the same
        hash must trigger a rebuild because the cached docs are bound
        to the original attr."""
        builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash_attr",
            phrase_attr="LOWER",
            use_cache=True,
        )
        rebuilt = builder.load_or_build(
            skills=sample_skills,
            nlp=nlp_blank_en,
            esco_hash="hash_attr",
            phrase_attr="ORTH",
            use_cache=True,
        )
        assert rebuilt.phrase_attr == "ORTH"
