"""Adapters between API schemas (``api.schemas``) and internal types.

All conversion logic between the public REST contract and the
internal pydantic types of ``cv_extractor`` / ``skill_extractor`` /
``skill_matcher`` lives in this single module so:

* The router files stay focused on HTTP concerns (status codes, DI,
  error translation).
* When the internal types evolve, this is the only file that needs
  to change — the public contract stays frozen.
* The adapters can be unit-tested in isolation without spinning up
  a FastAPI TestClient.

Direction:
    * ``*_to_response`` / ``*_to_schema`` — internal → API
      (server-side serialisation).
    * ``*_from_request`` / ``*_to_internal`` — API → internal
      (request validation has already happened at the pydantic
      boundary; these adapters trust the schemas).

Schemas are intentionally narrower than the internal types in a few
places (e.g. ``LanguageCode`` excludes anything other than ``"en"``
or ``"ro"`` even though ``ExtractionMetadata.detected_language`` is
unconstrained ``str | None``); the adapter clamps the value.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast, get_args

from api.contact import extract_contact
from api.schemas import (
    CandidateSchema,
    CandidateSourceLiteral,
    ExtractJdResponse,
    ExtractResponse,
    FullResponse,
    ImportanceLiteral,
    JdRequirementSchema,
    LanguageCode,
    MatchedRequirementSchema,
    MatchResponse,
    OverallClassLiteral,
    RequirementSchema,
)
from cv_extractor.models import ExtractionResult
from skill_matcher import __version__ as skill_matcher_version
from skill_matcher.models import (
    EnrichedSkillResult,
    JDRequirement,
    MatchCandidate,
    MatchResult,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_LANGUAGES: frozenset[str] = frozenset(get_args(LanguageCode))
"""``{"en", "ro"}`` — set form of the ``LanguageCode`` literal for fast
membership check."""

_UNKNOWN_SECTION = "unknown"
"""Section label for ``expansion`` candidates whose evidence came from
the sliding window rather than a known CV section."""


# ---------------------------------------------------------------------------
# Module 3 candidate -> API CandidateSchema
# ---------------------------------------------------------------------------


def candidate_to_schema(candidate: MatchCandidate) -> CandidateSchema:
    """Map a :class:`MatchCandidate` to a :class:`CandidateSchema`.

    The internal model carries an optional ``cv_evidence_offset`` and
    a ``lexical_confidence`` field that are not part of the API
    contract (they belong to the internal debugging surface). The
    section field is filled with ``"unknown"`` for expansion
    candidates — the internal model does not carry section affinity
    for window-based retrieval.
    """
    # Module 3's ``MatchCandidate`` does not carry a section field
    # (sections are a Module 2 concept; expansion candidates were
    # never anchored to a CV section). The convention for the API
    # surface is to surface ``"unknown"`` for expansion and to back-
    # fill from the lexical surface for lexical_kept / lexical_dropped
    # — but the back-fill data is not on ``MatchCandidate`` either.
    # Use ``"unknown"`` uniformly for now; the production JD parser
    # path (future) will propagate sections via
    # ``MatchCandidate.cv_evidence_text``-keyed lookup.
    section = _UNKNOWN_SECTION

    return CandidateSchema(
        esco_uri=candidate.skill_uri,
        skill_label=candidate.skill_label,
        surface_form=candidate.cv_evidence_text,
        section=section,
        source=cast(CandidateSourceLiteral, candidate.source),
        confidence=candidate.confidence,
        semantic_similarity=candidate.similarity_score,
    )


def schema_to_candidate(schema: CandidateSchema) -> MatchCandidate:
    """Map a :class:`CandidateSchema` back to a :class:`MatchCandidate`.

    Used by ``POST /v1/match`` when re-hydrating the ``enriched``
    field from the client (the client passes back what
    ``/v1/extract`` returned). Section information is dropped on the
    way in — it is API-only metadata; the Scorer does not consume it.
    """
    return MatchCandidate(
        skill_uri=schema.esco_uri,
        skill_label=schema.skill_label,
        confidence=schema.confidence,
        source=schema.source,
        cv_evidence_text=schema.surface_form,
        cv_evidence_offset=None,
        similarity_score=schema.semantic_similarity,
        lexical_confidence=None,
    )


# ---------------------------------------------------------------------------
# Pipeline version string
# ---------------------------------------------------------------------------


def build_pipeline_version(encoder_path: str | None) -> str:
    """Return the canonical pipeline version string.

    Format::

        skill_matcher@<semver>+encoder=<basename-or-id>

    The encoder tag is a stable identifier the recruiter UI can show
    next to the score so two runs from different models are
    distinguishable. For HuggingFace IDs the tag is the bare ID; for
    local paths it is the final path component (the run-dir name).
    """
    encoder_tag = "unknown"
    if encoder_path:
        # Treat slashes uniformly — HF IDs use ``/``, Windows paths use
        # ``\``, POSIX paths use ``/``. The basename is the run-dir
        # name for local paths or the model name for HF IDs.
        normalised = encoder_path.replace("\\", "/")
        tail = normalised.rsplit("/", 1)[-1]
        encoder_tag = tail or normalised
    return f"skill_matcher@{skill_matcher_version}+encoder={encoder_tag}"


# ---------------------------------------------------------------------------
# Module 1 + 3 -> ExtractResponse
# ---------------------------------------------------------------------------


def _coerce_language(value: str | None) -> LanguageCode | None:
    """Coerce Module 1's free ``str | None`` to the API's narrower literal.

    Any value outside ``{"en", "ro"}`` is reported as ``None`` —
    Module 3 is only validated against EN + RO, so surfacing a third
    language would be a contract lie.
    """
    if value is None:
        return None
    if value in _VALID_LANGUAGES:
        return cast(LanguageCode, value)
    return None


def enriched_to_response(
    *,
    cv_id: str,
    extraction: ExtractionResult,
    enriched: EnrichedSkillResult,
    extra_warnings: list[str] | None = None,
) -> ExtractResponse:
    """Compose a :class:`ExtractResponse` from upstream module outputs."""
    warnings = list(extraction.warnings)
    if extra_warnings:
        warnings.extend(extra_warnings)
    return ExtractResponse(
        cv_id=cv_id,
        detected_language=_coerce_language(extraction.metadata.detected_language),
        candidates=[candidate_to_schema(c) for c in enriched.candidates],
        pipeline_version=enriched.pipeline_version,
        warnings=warnings,
        # REWORK 4 (D40): mine contact details from the same raw text the
        # Linker consumed — additive, single composition point, so every
        # path that builds an ExtractResponse gets it for free.
        contact=extract_contact(extraction.text),
    )


def enriched_to_jd_response(
    *,
    jd_id: str,
    language: str | None,
    enriched: EnrichedSkillResult,
    extra_warnings: list[str] | None = None,
) -> ExtractJdResponse:
    """Compose an :class:`ExtractJdResponse` from Linker output.

    Unlike :func:`enriched_to_response` this never touches Module 1
    (JDs arrive as free text, not PDFs). Two shaping rules turn the
    raw candidate stream into a clean editable requirement list:

    1. ``lexical_dropped`` candidates are filtered out — they are
       carried in the extract surface purely for transparency, but a
       requirement the Linker suppressed below the keep threshold
       should not be proposed to the recruiter.
    2. Candidates are deduplicated by ``skill_uri`` (the Linker emits
       one candidate per evaluation event, so the same skill can
       appear several times); the highest-confidence occurrence wins.

    The surviving candidates are sorted by descending confidence
    (ties broken by skill label) for a stable, reviewable order.
    """
    best_by_uri: dict[str, MatchCandidate] = {}
    for candidate in enriched.candidates:
        if candidate.source == "lexical_dropped":
            continue
        existing = best_by_uri.get(candidate.skill_uri)
        if existing is None or candidate.confidence > existing.confidence:
            best_by_uri[candidate.skill_uri] = candidate

    ordered = sorted(
        best_by_uri.values(),
        key=lambda c: (-c.confidence, c.skill_label),
    )
    requirements = [
        JdRequirementSchema(
            text=c.cv_evidence_text,
            skill_uri=c.skill_uri,
            skill_label=c.skill_label,
            confidence=c.confidence,
        )
        for c in ordered
    ]

    return ExtractJdResponse(
        jd_id=jd_id,
        detected_language=_coerce_language(language),
        requirements=requirements,
        pipeline_version=enriched.pipeline_version,
        warnings=list(extra_warnings or []),
    )


def response_to_enriched(response: ExtractResponse) -> EnrichedSkillResult:
    """Re-hydrate :class:`EnrichedSkillResult` from a client-sent response.

    Used by ``POST /v1/match`` — the client returns the
    ``ExtractResponse`` they got from ``/v1/extract``. The Scorer
    only consumes ``candidates`` and ``cv_id`` so the round-trip is
    lossy w.r.t. ``warnings`` and ``detected_language``, which is
    correct: those fields are for the recruiter UI, not the Scorer.
    """
    return EnrichedSkillResult(
        cv_id=response.cv_id,
        candidates=[schema_to_candidate(c) for c in response.candidates],
        detected_language=response.detected_language,
        pipeline_version=response.pipeline_version,
    )


# ---------------------------------------------------------------------------
# RequirementSchema <-> JDRequirement
# ---------------------------------------------------------------------------


def requirement_schema_to_internal(req: RequirementSchema) -> JDRequirement:
    """Map a :class:`RequirementSchema` to a :class:`JDRequirement`."""
    return JDRequirement(
        text=req.text,
        skill_uri=req.skill_uri,
        skill_label=req.skill_label,
        importance=req.importance,
        confidence=req.confidence,
    )


def requirement_internal_to_schema(req: JDRequirement) -> RequirementSchema:
    """Map a :class:`JDRequirement` back to a :class:`RequirementSchema`."""
    return RequirementSchema(
        text=req.text,
        skill_uri=req.skill_uri,
        skill_label=req.skill_label,
        importance=cast(ImportanceLiteral, req.importance),
        confidence=req.confidence,
    )


# ---------------------------------------------------------------------------
# MatchResult -> MatchResponse
# ---------------------------------------------------------------------------


def project_overall_class(
    score: float, *, t1: float, t2: float
) -> OverallClassLiteral:
    """3-class projection at the locked T1 / T2 thresholds.

    Mirrors :func:`skill_matcher.tuning.project_to_three_class` but
    redeclared here to keep ``api.adapters`` standalone (the
    ``tuning`` submodule is heavy and pulls extra dependencies). The
    invariant ``t2 < t1`` is enforced upstream by
    :class:`skill_matcher.config.SkillMatcherConfig`.
    """
    if score >= t1:
        return "strong"
    if score >= t2:
        return "possible"
    return "no"


def match_result_to_response(
    result: MatchResult,
    *,
    t1_strong_threshold: float,
    t2_possible_threshold: float,
) -> MatchResponse:
    """Map a :class:`MatchResult` to a :class:`MatchResponse`."""
    return MatchResponse(
        cv_id=result.cv_id,
        jd_id=result.jd_id,
        overall_score=result.overall_score,
        overall_class=project_overall_class(
            result.overall_score,
            t1=t1_strong_threshold,
            t2=t2_possible_threshold,
        ),
        required_coverage=result.required_coverage,
        nice_to_have_coverage=result.nice_to_have_coverage,
        matched_required=[
            MatchedRequirementSchema(
                requirement=requirement_internal_to_schema(m.requirement),
                cv_candidate=candidate_to_schema(m.cv_candidate),
                match_score=m.match_score,
            )
            for m in result.matched_required
        ],
        matched_nice_to_have=[
            MatchedRequirementSchema(
                requirement=requirement_internal_to_schema(m.requirement),
                cv_candidate=candidate_to_schema(m.cv_candidate),
                match_score=m.match_score,
            )
            for m in result.matched_nice_to_have
        ],
        unmatched_required=[
            requirement_internal_to_schema(r) for r in result.unmatched_required
        ],
        unmatched_nice_to_have=[
            requirement_internal_to_schema(r) for r in result.unmatched_nice_to_have
        ],
        timestamp=result.timestamp,
        pipeline_version=result.pipeline_version,
    )


def match_result_to_full_response(
    result: MatchResult,
    *,
    t1_strong_threshold: float,
    t2_possible_threshold: float,
) -> FullResponse:
    """Same as :func:`match_result_to_response` but returns ``FullResponse``."""
    base = match_result_to_response(
        result,
        t1_strong_threshold=t1_strong_threshold,
        t2_possible_threshold=t2_possible_threshold,
    )
    # ``FullResponse`` is a structural copy of ``MatchResponse``;
    # round-trip via ``model_dump`` so any future divergence is caught
    # by pydantic's own validator rather than a missing-field error.
    return FullResponse.model_validate(base.model_dump())


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """Return a UTC ``datetime``. Centralised so tests can patch it."""
    return datetime.now(tz=UTC)


__all__ = [
    "build_pipeline_version",
    "candidate_to_schema",
    "enriched_to_response",
    "match_result_to_full_response",
    "match_result_to_response",
    "project_overall_class",
    "requirement_internal_to_schema",
    "requirement_schema_to_internal",
    "response_to_enriched",
    "schema_to_candidate",
    "utc_now",
]
