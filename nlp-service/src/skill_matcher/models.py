"""Pydantic v2 domain models for the semantic skill matcher (Module 3).

This module defines the **public** types of Module 3:

* :class:`MatchCandidate` — a single skill match produced by Module 3,
  carrying both lexical and semantic provenance.
* :class:`EnrichedSkillResult` — output of Phase A (skill linking):
  Module 2's lexical candidates re-scored + expansion candidates added.
* :class:`JDRequirement` — one requirement parsed from a Job Description.
* :class:`MatchedRequirement` — pairing of a JD requirement with the
  CV evidence that satisfies it (used inside :class:`MatchResult`).
* :class:`MatchResult` — the final output of Phase B (CV ↔ JD scoring).

Design notes
------------
* All confidences live in the closed interval ``[0.0, 1.0]``, mirroring
  Module 2's ``SkillMatch.confidence`` convention.
* Evidence spans (character offsets in
  :attr:`cv_extractor.models.ExtractionResult.text`) are required for
  "kept" lexical candidates and optional for expansion candidates,
  where the encoder retrieved the skill from a sliding window rather
  than an exact lexical span.
* ``pipeline_version`` is carried on the top-level result types so the
  thesis defence can answer "which model produced this result?" by
  reading the JSON output alone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Language = Literal["en", "ro"]
"""ISO 639-1 codes for the languages Module 3 supports.

Mirrors :data:`skill_extractor.models.Language`. Re-declared here rather
than re-exported so consumers can ``from skill_matcher import Language``
without depending on Module 2's symbol layout."""

CandidateSource = Literal["lexical_kept", "lexical_dropped", "expansion"]
"""Provenance of a :class:`MatchCandidate`:

* ``"lexical_kept"`` — Module 2 lexical candidate that Module 3's
  semantic re-scoring kept (or boosted).
* ``"lexical_dropped"`` — Module 2 lexical candidate that Module 3's
  semantic re-scoring suppressed below the keep threshold. Carried in
  the result for transparency (the validation report uses it).
* ``"expansion"`` — recovered by Module 3's sliding-window retrieval
  against the ESCO embedding index; not present in Module 2 output.
"""

RequirementImportance = Literal["required", "nice_to_have"]
"""Whether a JD requirement is hard ("must-have") or soft ("nice-to-have").
Drives the weight applied during overall-score aggregation."""


# ---------------------------------------------------------------------------
# Public result models
# ---------------------------------------------------------------------------


class MatchCandidate(BaseModel):
    """A single skill match produced by Module 3.

    A ``MatchCandidate`` represents one ``(skill, evidence)`` pairing.
    Unlike Module 2's :class:`~skill_extractor.models.SkillMatch` (which
    deduplicates by ESCO URI and lists every span), Module 3 emits one
    candidate per evaluation event so the downstream scorer can weight
    each piece of evidence independently. Aggregation across multiple
    candidates with the same URI happens in :class:`Scorer`.
    """

    skill_uri: str = Field(
        min_length=1,
        description="ESCO URI or custom-concept URI (``CUST:...``).",
    )
    skill_label: str = Field(
        min_length=1,
        description="Canonical preferred label for the skill.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Module 3's final confidence after re-scoring. Comparable "
            "across candidate sources."
        ),
    )
    source: CandidateSource
    cv_evidence_text: str = Field(
        min_length=1,
        description=(
            "Snippet of CV text shown to the recruiter as the reason "
            "this skill was matched. For ``lexical_*`` sources this is "
            "the surface form Module 2 matched; for ``expansion`` "
            "candidates it is the sliding window the encoder retrieved "
            "against."
        ),
    )
    cv_evidence_offset: tuple[int, int] | None = Field(
        default=None,
        description=(
            "``(start, end)`` character offsets in "
            "``ExtractionResult.text`` for the evidence snippet. "
            "Required for lexical candidates (always known). ``None`` "
            "is permitted for expansion candidates where window "
            "boundaries are approximate."
        ),
    )
    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Raw cosine similarity from the encoder between the "
            "evidence snippet and the skill embedding. Exposed for "
            "debugging and threshold tuning; not used directly in "
            "aggregation."
        ),
    )
    lexical_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Module 2's ``SkillMatch.confidence`` for this candidate "
            "if it came from Module 2. ``None`` for ``expansion`` "
            "candidates."
        ),
    )

    @field_validator("cv_evidence_offset")
    @classmethod
    def _validate_offset(
        cls, v: tuple[int, int] | None
    ) -> tuple[int, int] | None:
        """``(start, end)`` must satisfy ``0 <= start < end``."""
        if v is None:
            return v
        start, end = v
        if start < 0 or end <= start:
            raise ValueError(
                f"Invalid offset ({start}, {end}): require 0 <= start < end."
            )
        return v


class EnrichedSkillResult(BaseModel):
    """Public output of Module 3 Phase A — skill linking.

    Produced by :class:`skill_matcher.linker.Linker.link`. Builds on top
    of Module 2's :class:`~skill_extractor.models.SkillExtractionResult`:
    every candidate carries explicit provenance via
    :attr:`MatchCandidate.source`.
    """

    cv_id: str = Field(
        min_length=1,
        description=(
            "Stable identifier for the CV — usually the source filename "
            "without extension. Used to join with JD requirements in "
            "Phase B and for telemetry."
        ),
    )
    candidates: list[MatchCandidate] = Field(
        default_factory=list,
        description=(
            "All Module 3 candidates, including those marked "
            "``lexical_dropped``. Filtering by ``source`` is the "
            "responsibility of the consumer."
        ),
    )
    detected_language: Language | None = Field(
        default=None,
        description=(
            "Language echoed from ``ExtractionResult.detected_language``. "
            "``None`` if the upstream language detector abstained."
        ),
    )
    pipeline_version: str = Field(
        min_length=1,
        description=(
            "Version string of the Module 3 pipeline that produced this "
            "result. Format ``skill_matcher@<semver>[-<model-tag>]``."
        ),
    )


class JDRequirement(BaseModel):
    """A single requirement parsed from a Job Description.

    Job Descriptions arrive as free text, YAML, or structured input.
    The JD parser (introduced in a later step) emits one
    ``JDRequirement`` per atomic skill/competence mentioned, classified
    as hard or soft.
    """

    text: str = Field(
        min_length=1,
        description="Original requirement phrase from the JD, kept verbatim.",
    )
    skill_uri: str | None = Field(
        default=None,
        description=(
            "Resolved ESCO URI for this requirement, if the parser "
            "found a match. ``None`` for free-text requirements the "
            "parser could not anchor."
        ),
    )
    skill_label: str | None = Field(
        default=None,
        description="Canonical label of the resolved skill, if any.",
    )
    importance: RequirementImportance
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the URI resolution, ``[0.0, 1.0]``.",
    )


class MatchedRequirement(BaseModel):
    """Pairing of a JD requirement with the CV evidence that satisfies it.

    Carried inside :class:`MatchResult`. ``match_score`` is the combined
    score used by the aggregator: it accounts for the requirement's
    importance, the candidate's confidence, and the similarity between
    the requirement and the matched skill.
    """

    requirement: JDRequirement
    cv_candidate: MatchCandidate
    match_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Final per-requirement match score after combining "
            "``requirement.confidence``, ``cv_candidate.confidence`` "
            "and the requirement-to-candidate similarity."
        ),
    )


class MatchResult(BaseModel):
    """Public output of Module 3 Phase B — CV ↔ JD scoring.

    End-to-end output of the matcher. Carries everything the recruiter
    UI needs to render the per-CV view: overall fit, per-requirement
    coverage, evidence snippets, and a list of unmet hard requirements
    that the recruiter should follow up on.
    """

    cv_id: str = Field(min_length=1)
    jd_id: str = Field(min_length=1)
    overall_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Composite CV ↔ JD compatibility score in ``[0.0, 1.0]``. "
            "Aggregation formula is documented in ``scorer.py``."
        ),
    )
    required_coverage: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of hard requirements with a matched CV candidate "
            "above the per-requirement keep threshold."
        ),
    )
    nice_to_have_coverage: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Same as :attr:`required_coverage` but for soft requirements."
        ),
    )
    matched_required: list[MatchedRequirement] = Field(default_factory=list)
    matched_nice_to_have: list[MatchedRequirement] = Field(default_factory=list)
    unmatched_required: list[JDRequirement] = Field(
        default_factory=list,
        description=(
            "Hard requirements with no candidate above the keep "
            "threshold. Surfaced to the recruiter as 'gaps to follow "
            "up on'."
        ),
    )
    unmatched_nice_to_have: list[JDRequirement] = Field(
        default_factory=list,
        description=(
            "Soft requirements with no candidate above the keep "
            "threshold. Symmetric to :attr:`unmatched_required` so the "
            "recruiter UI can render nice-to-have gaps separately from "
            "hard-requirement gaps. Step 7 amendment: without this "
            "field nice-to-have unmatched requirements would either "
            "have to be dropped silently (forbidden by the Scorer's "
            "anti-pattern rules) or stuffed into ``unmatched_required`` "
            "(misrepresents importance)."
        ),
    )
    timestamp: datetime = Field(
        description=(
            "UTC timestamp when this result was produced. The pipeline "
            "stamps this with ``datetime.now(tz=timezone.utc)``."
        ),
    )
    pipeline_version: str = Field(min_length=1)


__all__ = [
    "CandidateSource",
    "EnrichedSkillResult",
    "JDRequirement",
    "Language",
    "MatchCandidate",
    "MatchResult",
    "MatchedRequirement",
    "RequirementImportance",
]
