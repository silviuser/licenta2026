"""Smoke tests for :mod:`skill_extractor.models`.

These tests do not exercise the pipeline; they only verify that the
pydantic v2 models accept valid input, reject invalid input with a
useful error, and that the type aliases resolve correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from skill_extractor.models import (
    ESCO_VERSION,
    EscoSkill,
    SkillExtractionResult,
    SkillMatch,
)

# ---------------------------------------------------------------------------
# EscoSkill
# ---------------------------------------------------------------------------


class TestEscoSkill:
    def test_minimal_valid(self) -> None:
        skill = EscoSkill(
            concept_uri="http://data.europa.eu/esco/skill/abc",
            preferred_label="Python",
            skill_type="knowledge",
        )
        assert skill.concept_uri == "http://data.europa.eu/esco/skill/abc"
        assert skill.preferred_label == "Python"
        assert skill.alt_labels == []
        assert skill.skill_type == "knowledge"
        assert skill.description == ""
        assert skill.reuse_level == ""

    def test_alt_labels_strip_empty(self) -> None:
        skill = EscoSkill(
            concept_uri="uri",
            preferred_label="Python",
            skill_type="knowledge",
            alt_labels=["python3", "  ", "", "py"],
        )
        # Empty + whitespace-only entries are dropped, the rest survive
        # with their whitespace trimmed.
        assert skill.alt_labels == ["python3", "py"]

    def test_invalid_skill_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EscoSkill(
                concept_uri="uri",
                preferred_label="x",
                skill_type="something-else",  # type: ignore[arg-type]
            )

    def test_empty_preferred_label_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EscoSkill(
                concept_uri="uri",
                preferred_label="",
                skill_type="knowledge",
            )


# ---------------------------------------------------------------------------
# SkillMatch
# ---------------------------------------------------------------------------


def _valid_match_kwargs() -> dict[str, object]:
    return {
        "esco_uri": "http://data.europa.eu/esco/skill/python",
        "preferred_label": "Python (computer programming)",
        "matched_text": "Python",
        "skill_type": "knowledge",
        "spans": [(10, 16)],
        "section": "skills",
        "frequency": 1,
        "confidence": 0.95,
    }


class TestSkillMatch:
    def test_minimal_valid(self) -> None:
        match = SkillMatch(**_valid_match_kwargs())  # type: ignore[arg-type]
        assert match.frequency == 1
        assert match.confidence == 0.95
        assert match.section == "skills"

    def test_confidence_clamped_to_unit_interval(self) -> None:
        kwargs = _valid_match_kwargs()
        kwargs["confidence"] = 1.5
        with pytest.raises(ValidationError):
            SkillMatch(**kwargs)  # type: ignore[arg-type]

        kwargs["confidence"] = -0.1
        with pytest.raises(ValidationError):
            SkillMatch(**kwargs)  # type: ignore[arg-type]

    def test_frequency_must_be_positive(self) -> None:
        kwargs = _valid_match_kwargs()
        kwargs["frequency"] = 0
        with pytest.raises(ValidationError):
            SkillMatch(**kwargs)  # type: ignore[arg-type]

    def test_spans_required_non_empty(self) -> None:
        kwargs = _valid_match_kwargs()
        kwargs["spans"] = []
        with pytest.raises(ValidationError):
            SkillMatch(**kwargs)  # type: ignore[arg-type]

    def test_spans_must_be_well_ordered(self) -> None:
        kwargs = _valid_match_kwargs()
        kwargs["spans"] = [(20, 10)]
        with pytest.raises(ValidationError):
            SkillMatch(**kwargs)  # type: ignore[arg-type]

    def test_invalid_section_rejected(self) -> None:
        kwargs = _valid_match_kwargs()
        kwargs["section"] = "nope"
        with pytest.raises(ValidationError):
            SkillMatch(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SkillExtractionResult
# ---------------------------------------------------------------------------


class TestSkillExtractionResult:
    def test_empty_result(self) -> None:
        result = SkillExtractionResult(
            language="en",
            skills=[],
            skill_count=0,
            processing_time_ms=12.5,
        )
        assert result.skill_count == 0
        assert result.skills == []
        assert result.warnings == []
        assert result.esco_version == ESCO_VERSION

    def test_skill_count_must_match_skills_length(self) -> None:
        match = SkillMatch(**_valid_match_kwargs())  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            SkillExtractionResult(
                language="en",
                skills=[match],
                skill_count=2,  # mismatch
                processing_time_ms=1.0,
            )

    def test_unsupported_language_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SkillExtractionResult(
                language="fr",  # type: ignore[arg-type]
                skills=[],
                skill_count=0,
                processing_time_ms=0.0,
            )

    def test_round_trip_with_match(self) -> None:
        match = SkillMatch(**_valid_match_kwargs())  # type: ignore[arg-type]
        result = SkillExtractionResult(
            language="ro",
            skills=[match],
            skill_count=1,
            processing_time_ms=42.0,
            warnings=["NER unavailable"],
        )
        dumped = result.model_dump()
        rehydrated = SkillExtractionResult.model_validate(dumped)
        assert rehydrated == result
