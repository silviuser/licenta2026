"""Public request / response schemas for the HR Helper NLP API.

**This file is a pure data contract.** It must NOT import from
``cv_extractor``, ``skill_extractor`` or ``skill_matcher``: those
internal types are intentionally hidden from the API surface so the
two versioning surfaces (internal package versions and ``v1`` API)
can evolve independently. All conversion between API schemas and
internal types lives in :mod:`api.adapters`.

Why hand-rolled schemas instead of re-exporting internal pydantic
models:

* The API contract is what Java Spring Boot will speak; coupling it
  to internal model evolution would force a coordinated change every
  time we tweak ``MatchCandidate``.
* OpenAPI auto-generated from FastAPI uses these models verbatim —
  the schema names visible to client generators are exactly the
  class names here.
* A breaking internal change (e.g. renaming
  ``MatchCandidate.skill_uri`` to ``concept_uri``) does not break
  the API: the adapter absorbs the rename.

Naming convention: every model is suffixed ``Request`` /
``Response`` / ``Schema`` so the OpenAPI viewer cleanly separates
the I/O contract from auxiliary types.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared type aliases (mirror the internal Literals; redeclared so this
# module imports nothing from src/skill_matcher).
# ---------------------------------------------------------------------------

LanguageCode = Literal["en", "ro"]
"""ISO 639-1 language codes Module 3 supports."""

CandidateSourceLiteral = Literal["lexical_kept", "lexical_dropped", "expansion"]
"""Provenance of a Module 3 candidate."""

ImportanceLiteral = Literal["required", "nice_to_have"]
"""Hard vs soft JD requirement."""

OverallClassLiteral = Literal["strong", "possible", "no"]
"""3-class projection of ``overall_score`` at the locked T1 / T2 cuts."""


# ---------------------------------------------------------------------------
# Candidate (CV-side skill)
# ---------------------------------------------------------------------------


class CandidateSchema(BaseModel):
    """One CV-side skill candidate produced by Module 1 + 2 + 3 Linker."""

    model_config = ConfigDict(extra="forbid")

    esco_uri: str = Field(
        min_length=1,
        description=(
            "ESCO URI or custom-concept URI (``CUST:...``) for the "
            "matched skill."
        ),
    )
    skill_label: str = Field(
        min_length=1,
        description="Canonical preferred label for the skill.",
    )
    surface_form: str = Field(
        min_length=1,
        description=(
            "CV-side evidence snippet that triggered the match. For "
            "``lexical_*`` sources this is the surface form Module 2 "
            "matched; for ``expansion`` candidates it is the sliding "
            "window text the encoder retrieved against."
        ),
    )
    section: str = Field(
        min_length=1,
        description=(
            "CV section the evidence appears in (``skills``, "
            "``experience``, ``profile``, ``education``, …). For "
            "``expansion`` candidates the section is reported as "
            "``unknown`` because window-based retrieval does not "
            "preserve section affinity."
        ),
    )
    source: CandidateSourceLiteral = Field(
        description=(
            "How this candidate was produced — see "
            "``CandidateSourceLiteral`` for the three values."
        ),
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Module 3's final confidence after re-scoring, in ``[0, 1]``."
        ),
    )
    semantic_similarity: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Raw cosine similarity between the evidence and the skill "
            "embedding. Useful for downstream debugging and threshold "
            "tuning; not used directly in aggregation."
        ),
    )


# ---------------------------------------------------------------------------
# /v1/extract
# ---------------------------------------------------------------------------


class ContactSchema(BaseModel):
    """Contact details mined from the raw CV text (REWORK 4 D40 / D41).

    Additive surface: the regex runs over Module 1's already-extracted
    text (no extra PDF parse). The field is intentionally extensible —
    phone / LinkedIn could land here later without another schema bump.
    """

    model_config = ConfigDict(extra="forbid")

    emails: list[str] = Field(
        default_factory=list,
        description=(
            "All syntactically-valid addresses found, lowercased and "
            "deduplicated, in document order."
        ),
    )
    primary_email: str | None = Field(
        default=None,
        description=(
            "First address in document order (typically the CV header); "
            "``None`` when no address was found."
        ),
    )


class ExtractResponse(BaseModel):
    """Result of ``POST /v1/extract`` — Module 1 + 2 + 3 Linker output."""

    model_config = ConfigDict(extra="forbid")

    cv_id: str = Field(min_length=1, max_length=128)
    detected_language: LanguageCode | None = Field(
        default=None,
        description=(
            "Echoed from ``ExtractionResult.detected_language`` "
            "(Module 1). ``None`` when the lingua-based detector "
            "abstains (typically: text too short)."
        ),
    )
    candidates: list[CandidateSchema] = Field(
        default_factory=list,
        description=(
            "All Module 3 candidates including ``lexical_dropped`` "
            "ones — filtering is the consumer's responsibility."
        ),
    )
    pipeline_version: str = Field(
        min_length=1,
        description=(
            "Format: ``skill_matcher@<semver>+encoder=<model-tag>``. "
            "Cite this in any downstream analysis."
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Non-fatal issues from any of the three modules (e.g. "
            "low quality extraction, NER model unavailable)."
        ),
    )
    contact: ContactSchema = Field(
        default_factory=ContactSchema,
        description=(
            "Contact details extracted from the raw CV text (REWORK 4). "
            "Strictly additive: older payloads without this field "
            "re-validate to an empty contact, so the field is permitted "
            "on the ``MatchRequest.enriched`` re-validation path too."
        ),
    )


# ---------------------------------------------------------------------------
# /v1/extract-jd
# ---------------------------------------------------------------------------


class ExtractJdRequest(BaseModel):
    """Request body for ``POST /v1/extract-jd``.

    The recruiter writes a Job Description as free text; this endpoint
    runs the same lexical + Linker pipeline used for CVs to surface
    candidate skill requirements. The backend then lets the recruiter
    edit the list (add/remove, flip ``required`` / ``nice_to_have``)
    — importance is intentionally *not* decided here (REWORK 1 D18).
    """

    model_config = ConfigDict(extra="forbid")

    jd_id: str = Field(
        min_length=1,
        max_length=128,
        description="Stable identifier for the JD (echoed back in the response).",
    )
    text: str = Field(
        min_length=1,
        description="Free-text Job Description (title + description body).",
    )
    language: LanguageCode | None = Field(
        default=None,
        description=(
            "Optional language override. When ``None`` (the default) the "
            "service auto-detects the language with lingua and falls back "
            "to ``en`` if detection abstains (e.g. text too short)."
        ),
    )


class JdRequirementSchema(BaseModel):
    """One candidate requirement extracted from a JD.

    Mirrors :class:`RequirementSchema` minus ``importance`` — the NLP
    service does not decide hard-vs-soft (REWORK 1 D18). The backend
    defaults every extracted requirement to ``required`` and lets the
    recruiter adjust.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        min_length=1,
        description="Surface form matched in the JD text, kept verbatim.",
    )
    skill_uri: str | None = Field(
        default=None,
        description="Resolved ESCO URI (or ``CUST:...``) for the skill, if any.",
    )
    skill_label: str | None = Field(
        default=None,
        description="Canonical preferred label of the resolved skill, if any.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Linker confidence for this candidate, in ``[0, 1]``.",
    )


class ExtractJdResponse(BaseModel):
    """Result of ``POST /v1/extract-jd`` — candidate JD requirements.

    Reuses the same lexical + Module 3 Linker stack as ``/v1/extract``
    but skips Module 1 (no PDF). ``lexical_dropped`` candidates are
    filtered out and the remaining candidates are deduplicated by
    ``skill_uri`` (highest confidence wins), so the recruiter sees a
    clean editable list rather than every evaluation event.
    """

    model_config = ConfigDict(extra="forbid")

    jd_id: str = Field(min_length=1, max_length=128)
    detected_language: LanguageCode | None = Field(
        default=None,
        description=(
            "Language used to run the pipeline (override or auto-detected)."
        ),
    )
    requirements: list[JdRequirementSchema] = Field(
        default_factory=list,
        description=(
            "Candidate requirements, sorted by descending confidence. "
            "Importance is left to the backend / recruiter (D18)."
        ),
    )
    pipeline_version: str = Field(
        min_length=1,
        description="Same format as ``ExtractResponse.pipeline_version``.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal issues from the lexical extractor / Linker.",
    )


# ---------------------------------------------------------------------------
# /v1/match
# ---------------------------------------------------------------------------


class RequirementSchema(BaseModel):
    """One JD requirement in the request body of ``/v1/match``."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        min_length=1,
        description="Original requirement phrase from the JD, verbatim.",
    )
    skill_uri: str | None = Field(
        default=None,
        description=(
            "Resolved ESCO URI for this requirement, if the JD parser "
            "found one. ``None`` is acceptable: the Scorer resolves "
            "free-text requirements against ESCO on the fly."
        ),
    )
    skill_label: str | None = Field(
        default=None,
        description="Canonical label of the resolved skill, if any.",
    )
    importance: ImportanceLiteral = Field(
        description="``required`` or ``nice_to_have``.",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence in the URI resolution. Default 0.5 mirrors "
            "the ``jd_fixture_to_requirements`` prior for eval-corpus "
            "JDs where the URI is unresolved."
        ),
    )


class MatchRequest(BaseModel):
    """Request body for ``POST /v1/match``.

    The caller passes back the ``ExtractResponse`` they received from
    ``/v1/extract`` plus the JD requirements to score against. Splits
    the cost: clients with multiple JDs to score against the same CV
    call ``/v1/extract`` once and ``/v1/match`` N times.
    """

    model_config = ConfigDict(extra="forbid")

    cv_id: str = Field(min_length=1, max_length=128)
    enriched: ExtractResponse = Field(
        description=(
            "The full ``ExtractResponse`` returned by ``/v1/extract``. "
            "Re-validated server-side; the API does not trust client "
            "tampering."
        ),
    )
    jd_id: str = Field(min_length=1, max_length=128)
    requirements: list[RequirementSchema] = Field(
        min_length=1,
        description=(
            "JD requirements to score the CV against. At least one "
            "requirement is required — an empty list is a client bug."
        ),
    )


class MatchedRequirementSchema(BaseModel):
    """One JD requirement paired with the CV evidence that satisfies it."""

    model_config = ConfigDict(extra="forbid")

    requirement: RequirementSchema
    cv_candidate: CandidateSchema
    match_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Final per-requirement match score after combining "
            "requirement confidence, candidate confidence and the "
            "requirement-to-candidate similarity."
        ),
    )


class MatchResponse(BaseModel):
    """Result of ``POST /v1/match`` — Module 3 Scorer output."""

    model_config = ConfigDict(extra="forbid")

    cv_id: str = Field(min_length=1)
    jd_id: str = Field(min_length=1)
    overall_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Composite CV ↔ JD compatibility score in ``[0, 1]``. "
            "The single number the recruiter UI surfaces."
        ),
    )
    overall_class: OverallClassLiteral = Field(
        description=(
            "3-class projection of ``overall_score`` at the locked "
            "``T1`` (strong) and ``T2`` (possible) thresholds. "
            "Convenience for clients that don't want to pick "
            "thresholds themselves."
        ),
    )
    required_coverage: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of hard requirements with a matched candidate "
            "above the per-requirement keep threshold."
        ),
    )
    nice_to_have_coverage: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Same as ``required_coverage`` but for soft requirements."
        ),
    )
    matched_required: list[MatchedRequirementSchema] = Field(default_factory=list)
    matched_nice_to_have: list[MatchedRequirementSchema] = Field(default_factory=list)
    unmatched_required: list[RequirementSchema] = Field(
        default_factory=list,
        description=(
            "Hard requirements with no candidate above the keep "
            "threshold. Surfaced to the recruiter as gaps to follow up."
        ),
    )
    unmatched_nice_to_have: list[RequirementSchema] = Field(
        default_factory=list,
        description="Symmetric to ``unmatched_required`` for soft requirements.",
    )
    timestamp: datetime = Field(
        description=(
            "Server-side UTC timestamp when the response was assembled. "
            "Echoes ``MatchResult.timestamp`` from the internal type."
        ),
    )
    pipeline_version: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# /v1/full
# ---------------------------------------------------------------------------


class FullResponse(MatchResponse):
    """Result of ``POST /v1/full`` — convenience composite endpoint.

    Same shape as :class:`MatchResponse`; declared separately so the
    OpenAPI doc names the response type accurately and so a future
    change (e.g. attaching the intermediate ``ExtractResponse``) does
    not silently bleed into ``/v1/match``.
    """


# ---------------------------------------------------------------------------
# /v1/info
# ---------------------------------------------------------------------------


class InfoResponse(BaseModel):
    """Result of ``GET /v1/info`` — service identity and provenance."""

    model_config = ConfigDict(extra="forbid")

    nlp_service_version: str = Field(
        min_length=1,
        description=(
            "Version of the API surface itself — independent of the "
            "underlying ``skill_matcher`` package version."
        ),
    )
    skill_matcher_version: str = Field(min_length=1)
    skill_extractor_version: str = Field(min_length=1)
    cv_extractor_version: str = Field(min_length=1)
    encoder_path: str = Field(
        min_length=1,
        description=(
            "Resolved encoder identifier — either a HuggingFace ID "
            "(zero-shot fallback) or a local path under "
            "``models/skill_matcher/<run-dir>``."
        ),
    )
    encoder_sha: str | None = Field(
        default=None,
        description=(
            "12-char SHA over ``encoder_path`` and the fine-tuned "
            "checkpoint path. Two responses with the same "
            "``encoder_sha`` were produced by the same model."
        ),
    )
    esco_sha: str = Field(
        min_length=12,
        max_length=12,
        description=(
            "12-char SHA over the ESCO concept set the service is "
            "indexing against. Joint with ``encoder_sha`` this is the "
            "cache key the in-memory index was loaded from."
        ),
    )
    locked_thresholds: dict[str, float] = Field(
        description=(
            "The seven thresholds locked by Step 8 (see "
            "``DECISIONS.md`` row for 2026-05-17). Surfaced so "
            "clients can audit which calibration produced their "
            "scores."
        ),
    )
    placeholder_caveat: str = Field(
        min_length=1,
        description=(
            "Free-text disclaimer that the currently-loaded encoder "
            "is the Step 5 placeholder; numbers reflect a "
            "structurally-complete pipeline at a compressed score "
            "range."
        ),
    )


# ---------------------------------------------------------------------------
# /v1/health and /v1/readyz
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Result of ``GET /v1/health`` — liveness only."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = Field(
        default="ok",
        description=(
            "Always ``ok`` when this endpoint returns 200. The "
            "process being up to answer the request is the signal."
        ),
    )
    timestamp: datetime


class ReadinessResponse(BaseModel):
    """Result of ``GET /v1/readyz`` — readiness signal.

    Returned with HTTP 200 when all three pipelines are warm, and
    with HTTP 503 (same body schema, ``status`` field reads
    ``not_ready``) when any component has not been loaded yet.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "not_ready"]
    components_loaded: list[str] = Field(
        description=(
            "Names of the pipeline singletons that have been "
            "instantiated. A non-ready response carries the empty "
            "list (or a partial list during a warm-up race)."
        ),
    )
    timestamp: datetime


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Uniform error body for all non-2xx responses."""

    model_config = ConfigDict(extra="forbid")

    error: str = Field(
        min_length=1,
        description=(
            "Machine-readable error code — e.g. ``pdf_corrupt``, "
            "``payload_too_large``, ``encoder_not_loaded``. Stable "
            "across patch releases."
        ),
    )
    detail: str = Field(
        min_length=1,
        description=(
            "Human-readable description of what went wrong. May vary "
            "between releases; do not parse."
        ),
    )
    request_id: str | None = Field(
        default=None,
        description=(
            "Correlation ID echoed from ``X-Request-ID``. Always "
            "populated when the request reached the middleware."
        ),
    )


__all__ = [
    "CandidateSchema",
    "CandidateSourceLiteral",
    "ContactSchema",
    "ErrorResponse",
    "ExtractJdRequest",
    "ExtractJdResponse",
    "ExtractResponse",
    "FullResponse",
    "HealthResponse",
    "ImportanceLiteral",
    "InfoResponse",
    "JdRequirementSchema",
    "LanguageCode",
    "MatchRequest",
    "MatchResponse",
    "MatchedRequirementSchema",
    "OverallClassLiteral",
    "ReadinessResponse",
    "RequirementSchema",
]
