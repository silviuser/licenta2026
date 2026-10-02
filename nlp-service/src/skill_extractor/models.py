"""Pydantic v2 domain models for the skill extraction pipeline.

This module defines:

* :class:`EscoSkill` — internal DTO produced by the ESCO loader, fed to
  the matcher builder. Not part of the public API but exposed for
  testing.
* :class:`SkillMatch` — a single skill detected in the CV text, with all
  its evidence (URI, label, surface form, spans, section, frequency,
  confidence).
* :class:`SkillExtractionResult` — the public output of
  :class:`skill_extractor.pipeline.SkillExtractor.extract`.

Type aliases :data:`Language`, :data:`SkillType` and :data:`SectionLabel`
are exported so callers can use them in their own type annotations.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Language = Literal["en", "ro"]
"""ISO 639-1 codes for the languages Module 2 supports."""

SkillType = Literal["knowledge", "skill/competence", "language"]
"""ESCO skill type. ``"language"`` is overlaid from
``languageSkillsCollection_en.csv`` on top of the native ``skillType``
values from ``skills_en.csv`` (which only ever has ``"knowledge"`` or
``"skill/competence"``)."""

SectionLabel = Literal[
    "skills", "experience", "education", "profile", "languages", "other"
]
"""CV section labels detected by :class:`skill_extractor.sections.detector.SectionDetector`."""

CefrLevel = Literal["A1", "A2", "B1", "B2", "C1", "C2", "native", "fluent"]
"""Common European Framework levels plus the two informal labels CV
authors routinely write (``"fluent"``, ``"native"``). The language-
section parser normalises every observed surface form into one of these
values."""

MatchKind = Literal["exact", "alt", "lemma"]
"""How the match was produced — used by the confidence scorer:

* ``"exact"`` — surface form matches the ESCO ``preferredLabel``.
* ``"alt"`` — surface form matches one of the ``altLabels``.
* ``"lemma"`` — surface form differs but lemmatised form matches a
  preferred / alt label (e.g. ``"developing"`` → ``"develop"``).
"""

ESCO_VERSION = "1.2.1"
"""Version of the ESCO taxonomy bundled with this build."""


# ---------------------------------------------------------------------------
# Internal DTOs
# ---------------------------------------------------------------------------


class EscoSkill(BaseModel):
    """A single ESCO skill, as parsed from ``skills_en.csv`` and friends.

    Notes
    -----
    ``alt_labels`` is normalised by the loader: deduplicated, lower-cased
    on the splitter side (the original casing is preserved in the
    pattern strings we feed to spaCy).

    ``is_custom`` is ``True`` for entries provided by the
    ``custom_concepts.json`` overlay rather than the official ESCO
    bundle. Their ``concept_uri`` starts with the ``CUST:`` prefix.
    """

    concept_uri: str = Field(min_length=1)
    preferred_label: str = Field(min_length=1)
    alt_labels: list[str] = Field(default_factory=list)
    skill_type: SkillType
    description: str = ""
    reuse_level: str = ""
    is_custom: bool = False

    @field_validator("alt_labels")
    @classmethod
    def _strip_empty(cls, v: list[str]) -> list[str]:
        """Drop empty strings that can sneak in from CSV multi-line cells."""
        return [s.strip() for s in v if s and s.strip()]


# ---------------------------------------------------------------------------
# Public result models
# ---------------------------------------------------------------------------


class SkillMatch(BaseModel):
    """A single skill detected in the CV text.

    A ``SkillMatch`` represents one logical skill (one ESCO concept URI)
    even when the same skill is mentioned multiple times: ``frequency``
    records the count and ``spans`` records every occurrence. ``section``
    is the *primary* section the skill was assigned to (the highest-
    weight section among its occurrences — ``"skills"`` beats
    ``"experience"`` beats ``"profile"``).

    ``matched_text`` is one representative surface form; useful for
    explainability in the UI ("we matched ``Pyhton`` against
    ``Python``") but not necessarily the only surface form seen.
    """

    esco_uri: str = Field(min_length=1)
    preferred_label: str = Field(min_length=1)
    matched_text: str = Field(min_length=1)
    skill_type: SkillType
    spans: list[tuple[int, int]] = Field(min_length=1)
    section: SectionLabel
    frequency: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    is_custom: bool = False
    """``True`` when the URI refers to a custom (non-ESCO) concept
    loaded via the ``custom_concepts.json`` overlay. Useful for
    downstream telemetry and for the validation reports which break
    metrics down by source."""
    cefr_level: CefrLevel | None = None
    """For ``skill_type='language'`` matches produced by the dedicated
    language-section parser: the proficiency level extracted from the
    surrounding parenthetical (``"English (B2)"`` → ``"B2"``,
    ``"Romanian (native)"`` → ``"native"``). ``None`` for non-language
    matches and for languages without a parsed level."""

    @field_validator("spans")
    @classmethod
    def _validate_spans(cls, v: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Each span must have ``start < end`` and both >= 0."""
        for start, end in v:
            if start < 0 or end <= start:
                raise ValueError(
                    f"Invalid span ({start}, {end}): require 0 <= start < end."
                )
        return v


class SkillExtractionResult(BaseModel):
    """The public result returned by :meth:`SkillExtractor.extract`.

    Attributes
    ----------
    language
        Language of the input text (echoes the validated input).
    skills
        Deduplicated list of detected skills, one entry per ESCO URI.
    skill_count
        ``len(skills)`` — convenience for callers that don't want to
        traverse the list.
    processing_time_ms
        Wall-clock time spent inside :meth:`SkillExtractor.extract`,
        excluding lazy first-call costs (model load, matcher build).
    warnings
        Non-fatal issues encountered during extraction (e.g. ``"NER
        model unavailable, disambiguation skipped"``).
    esco_version
        Version of the ESCO taxonomy used. Pinned at build time.
    """

    language: Language
    skills: list[SkillMatch] = Field(default_factory=list)
    skill_count: int = Field(ge=0)
    processing_time_ms: float = Field(ge=0.0)
    warnings: list[str] = Field(default_factory=list)
    esco_version: str = ESCO_VERSION

    @field_validator("skill_count")
    @classmethod
    def _count_matches(cls, v: int, info: object) -> int:
        """Defensive check — ``skill_count`` must equal ``len(skills)``."""
        # ``info.data`` access pattern for pydantic v2.
        data = getattr(info, "data", {})
        skills = data.get("skills")
        if skills is not None and v != len(skills):
            raise ValueError(
                f"skill_count={v} does not match len(skills)={len(skills)}."
            )
        return v
