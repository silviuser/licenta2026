"""Pydantic round-trip tests for the API schemas + adapter pure functions."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from api.adapters import (
    build_pipeline_version,
    candidate_to_schema,
    enriched_to_response,
    match_result_to_full_response,
    match_result_to_response,
    project_overall_class,
    requirement_internal_to_schema,
    requirement_schema_to_internal,
    response_to_enriched,
    schema_to_candidate,
)
from api.schemas import (
    CandidateSchema,
    ExtractResponse,
    FullResponse,
    InfoResponse,
    MatchRequest,
    MatchResponse,
    MatchedRequirementSchema,
    RequirementSchema,
)


# ---------------------------------------------------------------------------
# Schema round-trips
# ---------------------------------------------------------------------------


def test_candidate_schema_round_trip() -> None:
    """``CandidateSchema`` dump → validate is identity."""
    original = CandidateSchema(
        esco_uri="http://data.europa.eu/esco/skill/python",
        skill_label="Python",
        surface_form="Python",
        section="skills",
        source="lexical_kept",
        confidence=0.85,
        semantic_similarity=0.72,
    )
    dumped = original.model_dump()
    restored = CandidateSchema.model_validate(dumped)
    assert original == restored


def test_requirement_schema_default_confidence_is_half() -> None:
    """Default ``confidence`` is 0.5 (matches ``jd_fixture_to_requirements``)."""
    r = RequirementSchema(text="Python", importance="required")
    assert r.confidence == 0.5


def test_requirement_schema_rejects_out_of_range_confidence() -> None:
    """``confidence`` outside [0, 1] raises."""
    with pytest.raises(ValidationError):
        RequirementSchema(text="Python", importance="required", confidence=1.5)


def test_match_request_rejects_empty_requirements() -> None:
    """``requirements`` requires min_length=1."""
    extract = ExtractResponse(
        cv_id="alice",
        detected_language="en",
        candidates=[],
        pipeline_version="skill_matcher@0.7.0+encoder=test",
        warnings=[],
    )
    with pytest.raises(ValidationError):
        MatchRequest(
            cv_id="alice",
            enriched=extract,
            jd_id="jd1",
            requirements=[],
        )


def test_match_response_overall_class_must_be_literal() -> None:
    """``overall_class`` outside the three literals raises."""
    with pytest.raises(ValidationError):
        MatchResponse(
            cv_id="alice",
            jd_id="jd1",
            overall_score=0.5,
            overall_class="maybe",  # type: ignore[arg-type]
            required_coverage=0.5,
            nice_to_have_coverage=0.5,
            timestamp=dt.datetime.now(tz=dt.timezone.utc),
            pipeline_version="skill_matcher@0.7.0+encoder=test",
        )


def test_info_response_round_trip() -> None:
    """``InfoResponse`` round-trip with realistic values."""
    info = InfoResponse(
        nlp_service_version="0.1.0",
        skill_matcher_version="0.7.0",
        skill_extractor_version="0.2.0",
        cv_extractor_version="0.2.0",
        encoder_path="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        encoder_sha="abcdef123456",
        esco_sha="deadbeef0000",
        locked_thresholds={
            "drop_threshold": 0.40,
            "keep_threshold": 0.50,
            "expansion_threshold": 0.75,
            "per_requirement_keep_threshold": 0.085,
            "required_weight": 0.50,
            "t1_strong_threshold": 0.060,
            "t2_possible_threshold": 0.005,
        },
        placeholder_caveat="X" * 100,
    )
    restored = InfoResponse.model_validate(info.model_dump())
    assert restored == info


# ---------------------------------------------------------------------------
# Adapter pure-function tests
# ---------------------------------------------------------------------------


def test_project_overall_class_at_thresholds() -> None:
    """3-class projection boundary checks."""
    assert project_overall_class(0.5, t1=0.4, t2=0.1) == "strong"
    assert project_overall_class(0.4, t1=0.4, t2=0.1) == "strong"
    assert project_overall_class(0.3, t1=0.4, t2=0.1) == "possible"
    assert project_overall_class(0.1, t1=0.4, t2=0.1) == "possible"
    assert project_overall_class(0.05, t1=0.4, t2=0.1) == "no"


def test_build_pipeline_version_extracts_basename() -> None:
    """Encoder tag is the basename of the path, not the full path."""
    v = build_pipeline_version("/models/skill_matcher/mnrl_sw_v1_20260516")
    assert v.endswith("encoder=mnrl_sw_v1_20260516")
    assert v.startswith("skill_matcher@")


def test_build_pipeline_version_handles_hf_id() -> None:
    """HuggingFace IDs use the suffix after the last slash."""
    v = build_pipeline_version("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    assert v.endswith("encoder=paraphrase-multilingual-MiniLM-L12-v2")


def test_build_pipeline_version_handles_none() -> None:
    """``None`` encoder path → ``encoder=unknown``."""
    assert build_pipeline_version(None).endswith("encoder=unknown")


def test_build_pipeline_version_handles_windows_path() -> None:
    """Backslash-style Windows paths produce the same basename."""
    v = build_pipeline_version(r"C:\models\skill_matcher\run_20260516")
    assert v.endswith("encoder=run_20260516")


def test_candidate_round_trip_via_adapters(
    sample_enriched_result: object,  # type: ignore[reportMissingParameterType]
) -> None:
    """Internal MatchCandidate → CandidateSchema → MatchCandidate is faithful."""
    # Local import to avoid hard-coupling at module-load time.
    from skill_matcher.models import EnrichedSkillResult

    assert isinstance(sample_enriched_result, EnrichedSkillResult)
    candidate = sample_enriched_result.candidates[0]
    schema = candidate_to_schema(candidate)
    round_trip = schema_to_candidate(schema)
    # Source + URI + confidence preserved; section info dropped on the
    # internal side (the internal MatchCandidate has no section field).
    assert round_trip.skill_uri == candidate.skill_uri
    assert round_trip.skill_label == candidate.skill_label
    assert round_trip.confidence == candidate.confidence
    assert round_trip.source == candidate.source
    assert round_trip.cv_evidence_text == candidate.cv_evidence_text
    assert round_trip.similarity_score == candidate.similarity_score


def test_requirement_round_trip_via_adapters() -> None:
    """``RequirementSchema`` <-> ``JDRequirement`` is identity."""
    schema = RequirementSchema(
        text="Python",
        skill_uri="http://data.europa.eu/esco/skill/python",
        skill_label="Python",
        importance="required",
        confidence=0.9,
    )
    internal = requirement_schema_to_internal(schema)
    back = requirement_internal_to_schema(internal)
    assert back == schema


def test_enriched_to_response_uses_extraction_metadata(
    sample_extraction_result: object,  # type: ignore[reportMissingParameterType]
    sample_enriched_result: object,  # type: ignore[reportMissingParameterType]
) -> None:
    """``enriched_to_response`` carries language and warnings through."""
    from cv_extractor import ExtractionResult
    from skill_matcher.models import EnrichedSkillResult

    assert isinstance(sample_extraction_result, ExtractionResult)
    assert isinstance(sample_enriched_result, EnrichedSkillResult)

    response = enriched_to_response(
        cv_id="alice",
        extraction=sample_extraction_result,
        enriched=sample_enriched_result,
        extra_warnings=["NER model unavailable"],
    )
    assert response.cv_id == "alice"
    assert response.detected_language == "en"
    assert "NER model unavailable" in response.warnings
    assert len(response.candidates) == 3


def test_response_to_enriched_round_trip(
    sample_extraction_result: object,  # type: ignore[reportMissingParameterType]
    sample_enriched_result: object,  # type: ignore[reportMissingParameterType]
) -> None:
    """``ExtractResponse`` → ``EnrichedSkillResult`` preserves cv_id + URIs."""
    from cv_extractor import ExtractionResult
    from skill_matcher.models import EnrichedSkillResult

    assert isinstance(sample_extraction_result, ExtractionResult)
    assert isinstance(sample_enriched_result, EnrichedSkillResult)

    response = enriched_to_response(
        cv_id="alice",
        extraction=sample_extraction_result,
        enriched=sample_enriched_result,
    )
    back = response_to_enriched(response)
    assert back.cv_id == response.cv_id
    assert len(back.candidates) == len(response.candidates)
    for c1, c2 in zip(back.candidates, response.candidates, strict=True):
        assert c1.skill_uri == c2.esco_uri


def test_match_result_to_response_invokes_projection(
    sample_match_result: object,  # type: ignore[reportMissingParameterType]
) -> None:
    """The ``overall_class`` reflects the T1/T2 cuts."""
    from skill_matcher.models import MatchResult

    assert isinstance(sample_match_result, MatchResult)
    # Mocked overall_score is 0.072. At Step 8 lock T1=0.060, that's strong.
    resp = match_result_to_response(
        sample_match_result,
        t1_strong_threshold=0.060,
        t2_possible_threshold=0.005,
    )
    assert resp.overall_class == "strong"
    # Bump T1 above 0.072 → projection drops to "possible".
    resp2 = match_result_to_response(
        sample_match_result,
        t1_strong_threshold=0.10,
        t2_possible_threshold=0.005,
    )
    assert resp2.overall_class == "possible"


def test_match_result_to_full_response_returns_full(
    sample_match_result: object,  # type: ignore[reportMissingParameterType]
) -> None:
    """``FullResponse`` is structurally identical to ``MatchResponse``."""
    from skill_matcher.models import MatchResult

    assert isinstance(sample_match_result, MatchResult)
    full = match_result_to_full_response(
        sample_match_result,
        t1_strong_threshold=0.060,
        t2_possible_threshold=0.005,
    )
    assert isinstance(full, FullResponse)
    assert full.overall_score == sample_match_result.overall_score


def test_matched_requirement_schema_round_trip() -> None:
    """``MatchedRequirementSchema`` round-trip preserves nested types."""
    req = RequirementSchema(text="Python", importance="required", confidence=0.9)
    cand = CandidateSchema(
        esco_uri="http://data.europa.eu/esco/skill/python",
        skill_label="Python",
        surface_form="Python",
        section="skills",
        source="lexical_kept",
        confidence=0.85,
        semantic_similarity=0.72,
    )
    m = MatchedRequirementSchema(
        requirement=req, cv_candidate=cand, match_score=0.5
    )
    restored = MatchedRequirementSchema.model_validate(m.model_dump())
    assert restored == m


def test_extract_response_rejects_extra_fields() -> None:
    """``extra='forbid'`` prevents silent contract drift."""
    payload = {
        "cv_id": "alice",
        "detected_language": "en",
        "candidates": [],
        "pipeline_version": "skill_matcher@0.7.0+encoder=test",
        "warnings": [],
        "leaked_internal_field": "oops",
    }
    with pytest.raises(ValidationError):
        ExtractResponse.model_validate(payload)
