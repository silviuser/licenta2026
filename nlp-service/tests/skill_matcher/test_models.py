"""Pydantic round-trip and validation tests for :mod:`skill_matcher.models`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skill_matcher.models import (
    EnrichedSkillResult,
    JDRequirement,
    MatchCandidate,
    MatchedRequirement,
    MatchResult,
)

# ---------------------------------------------------------------------------
# MatchCandidate
# ---------------------------------------------------------------------------


def test_match_candidate_minimal_roundtrip() -> None:
    """Constructing with full fields and round-tripping JSON works."""
    candidate = MatchCandidate(
        skill_uri="http://data.europa.eu/esco/skill/python",
        skill_label="Python",
        confidence=0.92,
        source="lexical_kept",
        cv_evidence_text="3 years of Python development",
        cv_evidence_offset=(124, 154),
        similarity_score=0.88,
        lexical_confidence=0.85,
    )
    dumped = candidate.model_dump()
    re_loaded = MatchCandidate.model_validate(dumped)
    assert re_loaded == candidate


def test_match_candidate_expansion_allows_missing_offset_and_lexical() -> None:
    """Expansion candidates may omit both ``cv_evidence_offset`` and
    ``lexical_confidence`` because they did not come from Module 2."""
    candidate = MatchCandidate(
        skill_uri="CUST:fastapi",
        skill_label="FastAPI",
        confidence=0.81,
        source="expansion",
        cv_evidence_text="built async REST APIs in Python",
        cv_evidence_offset=None,
        similarity_score=0.79,
        lexical_confidence=None,
    )
    assert candidate.cv_evidence_offset is None
    assert candidate.lexical_confidence is None


def test_match_candidate_invalid_offset_raises() -> None:
    """An offset with ``end <= start`` is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        MatchCandidate(
            skill_uri="http://data.europa.eu/esco/skill/python",
            skill_label="Python",
            confidence=0.5,
            source="lexical_kept",
            cv_evidence_text="Python",
            cv_evidence_offset=(50, 50),
            similarity_score=0.5,
            lexical_confidence=0.5,
        )
    assert "Invalid offset" in str(exc_info.value)


def test_match_candidate_confidence_out_of_range_raises() -> None:
    """Confidence must lie in ``[0.0, 1.0]``."""
    with pytest.raises(ValidationError):
        MatchCandidate(
            skill_uri="x",
            skill_label="X",
            confidence=1.5,
            source="lexical_kept",
            cv_evidence_text="x",
            cv_evidence_offset=(0, 1),
            similarity_score=0.5,
            lexical_confidence=None,
        )


# ---------------------------------------------------------------------------
# EnrichedSkillResult
# ---------------------------------------------------------------------------


def test_enriched_skill_result_empty_candidates_allowed() -> None:
    """An empty candidates list is valid (e.g. a CV with no detectable skills)."""
    result = EnrichedSkillResult(
        cv_id="alice",
        candidates=[],
        detected_language="en",
        pipeline_version="skill_matcher@0.1.0",
    )
    assert result.candidates == []
    assert result.detected_language == "en"


def test_enriched_skill_result_language_optional() -> None:
    """``detected_language`` may be ``None`` when upstream detection abstains."""
    result = EnrichedSkillResult(
        cv_id="bob",
        candidates=[],
        detected_language=None,
        pipeline_version="skill_matcher@0.1.0",
    )
    assert result.detected_language is None


# ---------------------------------------------------------------------------
# JDRequirement
# ---------------------------------------------------------------------------


def test_jd_requirement_unanchored_is_valid() -> None:
    """A requirement without a resolved URI is allowed (free-text ask)."""
    req = JDRequirement(
        text="strong opinions on REST API design",
        skill_uri=None,
        skill_label=None,
        importance="nice_to_have",
        confidence=0.4,
    )
    assert req.skill_uri is None
    assert req.skill_label is None


# ---------------------------------------------------------------------------
# MatchResult
# ---------------------------------------------------------------------------


def test_match_result_full_construction_and_roundtrip() -> None:
    """End-to-end construction of a non-trivial MatchResult, JSON round-trip."""
    cand = MatchCandidate(
        skill_uri="http://data.europa.eu/esco/skill/python",
        skill_label="Python",
        confidence=0.92,
        source="lexical_kept",
        cv_evidence_text="3 years of Python development",
        cv_evidence_offset=(124, 154),
        similarity_score=0.88,
        lexical_confidence=0.85,
    )
    req = JDRequirement(
        text="Python (5+ years)",
        skill_uri="http://data.europa.eu/esco/skill/python",
        skill_label="Python",
        importance="required",
        confidence=0.95,
    )
    matched = MatchedRequirement(
        requirement=req,
        cv_candidate=cand,
        match_score=0.88,
    )
    result = MatchResult(
        cv_id="alice",
        jd_id="role-42",
        overall_score=0.78,
        required_coverage=1.0,
        nice_to_have_coverage=0.5,
        matched_required=[matched],
        matched_nice_to_have=[],
        unmatched_required=[],
        timestamp=datetime(2026, 5, 11, 12, 0, 0, tzinfo=UTC),
        pipeline_version="skill_matcher@0.1.0",
    )
    assert result.required_coverage == 1.0
    assert len(result.matched_required) == 1
    # Full JSON round-trip
    assert MatchResult.model_validate(result.model_dump()) == result


def test_match_result_unmatched_nice_to_have_default_and_carry() -> None:
    """Step 7 amendment: ``unmatched_nice_to_have`` defaults to ``[]`` and
    survives a JSON round-trip when populated."""
    soft_req = JDRequirement(
        text="GraphQL",
        skill_uri=None,
        skill_label=None,
        importance="nice_to_have",
        confidence=0.5,
    )
    result = MatchResult(
        cv_id="alice",
        jd_id="role-42",
        overall_score=0.42,
        required_coverage=0.6,
        nice_to_have_coverage=0.0,
        timestamp=datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC),
        pipeline_version="skill_matcher@0.5.0",
    )
    # Default
    assert result.unmatched_nice_to_have == []
    result2 = result.model_copy(update={"unmatched_nice_to_have": [soft_req]})
    assert MatchResult.model_validate(result2.model_dump()) == result2


def test_match_result_coverage_out_of_range_raises() -> None:
    """Coverage fractions are rejected outside ``[0.0, 1.0]``."""
    with pytest.raises(ValidationError):
        MatchResult(
            cv_id="alice",
            jd_id="role-42",
            overall_score=0.5,
            required_coverage=1.5,  # invalid
            nice_to_have_coverage=0.5,
            timestamp=datetime(2026, 5, 11, tzinfo=UTC),
            pipeline_version="skill_matcher@0.1.0",
        )
