"""Unit tests for :mod:`skill_extractor.pipeline`.

These tests use a tiny inline ESCO fixture and ``spacy.blank("en")`` so
they execute in seconds and do not require any downloaded language
model. The end-to-end Module-1-+-Module-2 pipeline is tested in
``test_pipeline_e2e.py``.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

spacy = pytest.importorskip("spacy")

from cv_extractor.models import (  # noqa: E402
    ExtractionMetadata,
    ExtractionMethod,
    ExtractionResult,
)
from skill_extractor.config import (  # noqa: E402
    NOT_A_CV_WARNING,
    SkillExtractorConfig,
)
from skill_extractor.esco.loader import EscoLoader  # noqa: E402
from skill_extractor.exceptions import (  # noqa: E402
    NotACVError,
    UnsupportedLanguageError,
)
from skill_extractor.pipeline import SkillExtractor  # noqa: E402

# ---------------------------------------------------------------------------
# Tiny inline ESCO bundle (only what the pipeline needs).
# ---------------------------------------------------------------------------

# Five skills cherry-picked to drive every branch:
# - Python, SQL: knowledge skills, occur in skills/experience/profile.
# - manage staff: skill/competence with multi-token preferred label.
# - write English: language overlay target.
# - Acme Corp: bogus "skill" used to test that a candidate-name-like
#   surface form gets dropped by NER (when NER is mocked).
_SKILLS_CSV = dedent(
    """\
    conceptType,conceptUri,skillType,reuseLevel,preferredLabel,altLabels,hiddenLabels,status,modifiedDate,scopeNote,definition,inScheme,description
    K,uri:python,knowledge,cross-sector,Python,"Python3
    py",,released,2024-01-01,,,scheme,The Python language.
    K,uri:sql,knowledge,cross-sector,SQL,,,released,2024-01-01,,,scheme,Structured Query Language.
    K,uri:manage-staff,skill/competence,sector,manage staff,"manage personnel
    coordinate staff",,released,2024-01-01,,,scheme,Coordinate a team of employees.
    K,uri:write-en,skill/competence,transversal,write English,"correspond in written English",,released,2024-01-01,,,scheme,Compose written English.
    K,uri:bogus,knowledge,sector,Acme,,,released,2024-01-01,,,scheme,Pretend skill name to exercise NER drop.
    """
)

_LANGUAGE_CSV = dedent(
    """\
    conceptType,conceptUri,skillType,reuseLevel,preferredLabel,status,altLabels,description,broaderConceptUri,broaderConceptPT
    K,uri:write-en,skill/competence,transversal,write English,released,correspond in written English,Compose written English.,uri:english,English
    """
)


@pytest.fixture
def esco_dir(tmp_path: Path) -> Path:
    (tmp_path / EscoLoader.SKILLS_FILE).write_text(_SKILLS_CSV, encoding="utf-8")
    (tmp_path / EscoLoader.LANGUAGE_FILE).write_text(_LANGUAGE_CSV, encoding="utf-8")
    return tmp_path


@pytest.fixture
def config(esco_dir: Path, tmp_path: Path) -> SkillExtractorConfig:
    return SkillExtractorConfig(
        esco_dir=esco_dir,
        cache_dir=tmp_path / "matcher_cache",
        phrase_attr="LOWER",  # blank pipelines have no lemmatiser
    )


@pytest.fixture
def extractor(config: SkillExtractorConfig) -> SkillExtractor:
    """Pipeline wired to mini ESCO + blank English tokenizer."""
    return SkillExtractor(
        config=config,
        nlp_factory=lambda lang: spacy.blank("en" if lang == "en" else "ro"),
    )


def _make_extraction_result(
    text: str,
    language: str | None,
    warnings: list[str] | None = None,
) -> ExtractionResult:
    """Build a minimal :class:`ExtractionResult` for input-path tests."""
    metadata = ExtractionMetadata(
        method_used=ExtractionMethod.PDFPLUMBER,
        total_pages=1,
        processing_time_ms=10,
        detected_language=language,
        is_scanned=False,
        quality_score=0.8,
        pages=[],
    )
    return ExtractionResult(
        text=text, metadata=metadata, warnings=warnings or []
    )


# ---------------------------------------------------------------------------
# Input parsing & validation
# ---------------------------------------------------------------------------


class TestInputParsing:
    def test_tuple_input_happy_path(self, extractor: SkillExtractor) -> None:
        result = extractor.extract(("Python and SQL daily.", "en"))
        assert result.language == "en"
        assert result.skill_count >= 2
        uris = {s.esco_uri for s in result.skills}
        assert "uri:python" in uris
        assert "uri:sql" in uris

    def test_extraction_result_input_happy_path(
        self, extractor: SkillExtractor
    ) -> None:
        er = _make_extraction_result("I write SQL.", language="en")
        result = extractor.extract(er)
        assert result.skill_count >= 1
        assert any(s.esco_uri == "uri:sql" for s in result.skills)

    def test_not_a_cv_warning_raises(
        self, extractor: SkillExtractor
    ) -> None:
        er = _make_extraction_result(
            "Stimate domn... [cover letter body]",
            language="en",
            warnings=[NOT_A_CV_WARNING],
        )
        with pytest.raises(NotACVError):
            extractor.extract(er)

    def test_unsupported_language_raises(
        self, extractor: SkillExtractor
    ) -> None:
        with pytest.raises(UnsupportedLanguageError):
            extractor.extract(("Some text.", "fr"))  # type: ignore[arg-type]

    def test_none_language_raises(self, extractor: SkillExtractor) -> None:
        er = _make_extraction_result("text", language=None)
        with pytest.raises(UnsupportedLanguageError):
            extractor.extract(er)

    def test_invalid_input_type_raises(
        self, extractor: SkillExtractor
    ) -> None:
        with pytest.raises(TypeError):
            extractor.extract(12345)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_text_returns_empty_result(
        self, extractor: SkillExtractor
    ) -> None:
        result = extractor.extract(("", "en"))
        assert result.skill_count == 0
        assert result.skills == []
        assert result.language == "en"

    def test_whitespace_only_text_returns_empty_result(
        self, extractor: SkillExtractor
    ) -> None:
        result = extractor.extract(("   \n  \t ", "en"))
        assert result.skill_count == 0


# ---------------------------------------------------------------------------
# Section assignment
# ---------------------------------------------------------------------------


class TestSectionAssignment:
    def test_skill_in_skills_section_gets_skills_label(
        self, extractor: SkillExtractor
    ) -> None:
        text = dedent(
            """\
            Profile
            Some preamble.

            Skills
            Python, SQL, Docker

            Experience
            Worked at Acme.
            """
        )
        result = extractor.extract((text, "en"))
        py = next(s for s in result.skills if s.esco_uri == "uri:python")
        assert py.section == "skills"

    def test_primary_section_picks_highest_weight(
        self, extractor: SkillExtractor
    ) -> None:
        """A skill mentioned in BOTH ``profile`` and ``skills`` is
        attributed to ``skills`` (the higher-weight section)."""
        text = dedent(
            """\
            Profile
            I love Python and have used it for years.

            Skills
            Python, SQL
            """
        )
        result = extractor.extract((text, "en"))
        py = next(s for s in result.skills if s.esco_uri == "uri:python")
        assert py.section == "skills"
        # Two distinct occurrences — frequency should be 2.
        assert py.frequency == 2


# ---------------------------------------------------------------------------
# Aggregation, dedupe, scoring
# ---------------------------------------------------------------------------


class TestAggregation:
    def test_repeated_skill_collapses_with_correct_frequency(
        self, extractor: SkillExtractor
    ) -> None:
        text = "Skills\nPython, SQL, Python, Python, SQL\n"
        result = extractor.extract((text, "en"))
        py = next(s for s in result.skills if s.esco_uri == "uri:python")
        sql = next(s for s in result.skills if s.esco_uri == "uri:sql")
        assert py.frequency == 3
        assert sql.frequency == 2
        # Each occurrence has its own span.
        assert len(py.spans) == 3
        assert len(sql.spans) == 2

    def test_alt_label_match_marked_appropriately(
        self, extractor: SkillExtractor
    ) -> None:
        text = "Skills\npy and SQL\n"
        result = extractor.extract((text, "en"))
        py = next(s for s in result.skills if s.esco_uri == "uri:python")
        assert py.matched_text.lower() == "py"
        # Confidence: alt match in skills, freq=1 → 0.85.
        assert py.confidence == pytest.approx(0.85, rel=1e-3)

    def test_skill_count_matches_skills_length(
        self, extractor: SkillExtractor
    ) -> None:
        result = extractor.extract(("Python, SQL", "en"))
        assert result.skill_count == len(result.skills)

    def test_results_sorted_by_confidence_descending(
        self, extractor: SkillExtractor
    ) -> None:
        text = dedent(
            """\
            Profile
            Years ago I read about Python.

            Skills
            SQL
            """
        )
        result = extractor.extract((text, "en"))
        confidences = [s.confidence for s in result.skills]
        assert confidences == sorted(confidences, reverse=True)

    def test_processing_time_is_positive(
        self, extractor: SkillExtractor
    ) -> None:
        result = extractor.extract(("Python, SQL", "en"))
        assert result.processing_time_ms > 0.0


# ---------------------------------------------------------------------------
# Negation filtering inside the pipeline
# ---------------------------------------------------------------------------


class TestNegationInPipeline:
    def test_negated_skill_is_dropped(
        self, extractor: SkillExtractor
    ) -> None:
        text = "I have no experience with Python but I write SQL daily."
        result = extractor.extract((text, "en"))
        uris = {s.esco_uri for s in result.skills}
        assert "uri:python" not in uris
        assert "uri:sql" in uris


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------


class TestPerInstanceCaching:
    def test_second_extract_call_reuses_loaded_resources(
        self, extractor: SkillExtractor
    ) -> None:
        """A second call should be fast because skills, nlp and matcher
        are cached. We don't measure time here (flaky), but we assert
        that the cached attributes are populated after the first
        call."""
        extractor.extract(("Python", "en"))
        # Internal caches now populated (pylint: protected-access OK
        # for white-box tests).
        assert extractor._skills_cache is not None
        assert "en" in extractor._nlp_cache
        assert "en" in extractor._matcher_cache
        # Second call does not crash and still returns results.
        result = extractor.extract(("SQL", "en"))
        assert result.skill_count >= 1


# ---------------------------------------------------------------------------
# SkillMatch field shape
# ---------------------------------------------------------------------------


class TestSkillMatchShape:
    def test_match_has_all_required_fields(
        self, extractor: SkillExtractor
    ) -> None:
        result = extractor.extract(("Skills\nPython", "en"))
        py = next(s for s in result.skills if s.esco_uri == "uri:python")
        assert py.esco_uri == "uri:python"
        assert py.preferred_label == "Python"
        assert py.skill_type == "knowledge"
        assert py.section == "skills"
        assert py.frequency == 1
        assert 0.0 <= py.confidence <= 1.0
        # Span recovers the original surface form.
        spans = py.spans
        assert len(spans) == 1
        start, end = spans[0]
        # Use the request text — which the result doesn't carry, so we
        # check by length sanity instead.
        assert end > start
