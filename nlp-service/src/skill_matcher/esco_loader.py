"""Adapter from Module 2's ESCO loader to Module 3's :class:`EscoConcept`.

The single point at which :mod:`skill_matcher` reaches into
:mod:`skill_extractor`. Everything else in Module 3 depends only on
:class:`EscoConcept` and on the :mod:`skill_matcher.encoder` Protocol.

Per ``DECISIONS.md`` D8 the ESCO source is shared with Module 2 —
this module does **not** re-parse the ESCO CSV bundle. It reuses
:class:`skill_extractor.esco.loader.EscoLoader`,
:func:`skill_extractor.overlays.custom.load_custom_overlay` and
:func:`skill_extractor.overlays.custom.merge_custom_concepts` so the
two modules can never drift on ESCO content or custom-concept
membership.

Two SHA helpers
---------------
:func:`compute_esco_file_sha` reuses
:func:`skill_extractor.esco.cache.compute_esco_hash` to hash the raw
CSV / JSON file bytes. It is the *cache invalidation key* used by
:class:`skill_matcher.esco_index.EscoIndex`: any byte-level change to
ESCO / custom-concepts triggers a fresh embedding build.

:func:`compute_esco_sha` hashes a stable tuple representation of the
parsed :class:`EscoConcept` list. It is used by unit tests to assert
loader determinism — two calls in different working directories must
produce the same digest. The two hashes serve different purposes and
are not interchangeable.

EscoConcept shape (locked at Step 4 Pre-Flight, Q1/Q2)
------------------------------------------------------
Mirrors :class:`skill_extractor.models.EscoSkill` minus
``reuse_level`` (Module 3 has no use for the ESCO reuse-level
metadata). ``skill_type`` is preserved verbatim from Module 2 —
``"knowledge"`` / ``"skill/competence"`` / ``"language"`` — because
the ``"language"`` value is load-bearing for Step 7's JD weighting.
``is_custom`` is a separate boolean (rather than collapsing custom
into ``skill_type``) so callers can filter independently of the
ESCO taxonomy axis.

``broader_uri`` is deliberately NOT carried in Step 4 — the
zero-shot baseline does not consume hierarchy. Step 6 (Linker) will
add the field by lifting the hierarchy parser already present in
``scripts/build_training_dataset.py`` rather than writing a second
parser.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.esco.cache import compute_esco_hash
from skill_extractor.esco.loader import EscoLoader
from skill_extractor.models import EscoSkill
from skill_extractor.overlays.custom import (
    load_custom_overlay,
    merge_custom_concepts,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EscoConcept:
    """One ESCO (or custom-overlay) concept consumed by Module 3.

    Mirrors :class:`skill_extractor.models.EscoSkill` minus the
    ``reuse_level`` field which Module 3 has no use for.

    Attributes
    ----------
    uri
        Stable identifier. Native ESCO URIs use the official
        ``http://data.europa.eu/esco/skill/<uuid>`` scheme; custom
        overlay concepts use the ``CUST:`` prefix.
    pref_label
        Canonical label (ESCO ``preferredLabel`` or the equivalent
        custom-concept field).
    alt_labels
        Deduplicated case-insensitive variants. May be empty for
        concepts that ESCO ships without altLabels.
    description
        Free-text definition. May be empty.
    skill_type
        Mirrors Module 2's ``SkillType`` literal —
        ``"knowledge"`` / ``"skill/competence"`` / ``"language"``.
        Preserved verbatim because the ``"language"`` value is
        load-bearing for Step 7's JD weighting.
    is_custom
        ``True`` iff the concept came from the custom-concepts overlay
        (i.e. ``uri.startswith("CUST:")``). Carried as a separate
        boolean so consumers can filter custom-vs-ESCO independently
        of the taxonomy axis.
    """

    uri: str
    pref_label: str
    alt_labels: tuple[str, ...]  # immutable so the dataclass stays hashable
    description: str
    skill_type: Literal["knowledge", "skill/competence", "language"]
    is_custom: bool

    @classmethod
    def from_skill(cls, skill: EscoSkill) -> EscoConcept:
        """Project a Module 2 :class:`EscoSkill` onto Module 3's view."""
        return cls(
            uri=skill.concept_uri,
            pref_label=skill.preferred_label,
            alt_labels=tuple(skill.alt_labels),
            description=skill.description,
            skill_type=skill.skill_type,
            is_custom=skill.is_custom,
        )


def load_esco_concepts(
    *,
    include_custom_overlay: bool = True,
    config: SkillExtractorConfig | None = None,
) -> list[EscoConcept]:
    """Load ESCO (and optionally the custom overlay) as :class:`EscoConcept`.

    Reuses Module 2's loader plumbing (D8) so Module 3 cannot drift on
    ESCO content. Output is sorted by URI for deterministic ordering;
    cache keys derived from this list are therefore stable across
    runs and across working directories.

    Parameters
    ----------
    include_custom_overlay
        When ``True`` (the default), the 74-entry custom-concepts
        overlay shipped under ``skill_extractor/data/custom_concepts.json``
        is folded in. Set to ``False`` for ablation studies that need
        the pure-ESCO universe.
    config
        Override the default :class:`SkillExtractorConfig`. Useful
        for tests that point at fixture CSVs. ``None`` (default) means
        "use the production defaults".

    Returns
    -------
    list[EscoConcept]
        Deterministic order: sorted by ``uri``.
    """
    cfg = config or SkillExtractorConfig()

    skills = EscoLoader(cfg).load()
    if include_custom_overlay:
        overlay = load_custom_overlay(cfg.custom_concepts_path)
        skills = merge_custom_concepts(skills, overlay)

    concepts = [EscoConcept.from_skill(s) for s in skills]
    concepts.sort(key=lambda c: c.uri)

    type_counts: dict[str, int] = {}
    custom_count = 0
    for c in concepts:
        type_counts[c.skill_type] = type_counts.get(c.skill_type, 0) + 1
        if c.is_custom:
            custom_count += 1

    logger.info(
        "esco_loader.loaded",
        total=len(concepts),
        custom=custom_count,
        by_type=type_counts,
        include_custom_overlay=include_custom_overlay,
    )
    return concepts


def compute_esco_file_sha(
    *,
    config: SkillExtractorConfig | None = None,
    include_custom_overlay: bool = True,
) -> str:
    """SHA digest over the raw ESCO / custom-concepts source files.

    This is the *cache invalidation* key used by
    :class:`skill_matcher.esco_index.EscoIndex`. Any byte-level
    change in the source files (a new ESCO bundle, an updated
    custom-concepts JSON) produces a different digest, which in turn
    invalidates the on-disk embedding cache.

    Reuses :func:`skill_extractor.esco.cache.compute_esco_hash`
    (12-hex-char SHA-256 prefix, path-sorted, missing files silently
    skipped — the file presence is already validated by the loader).
    """
    cfg = config or SkillExtractorConfig()
    paths: list[Path] = [
        cfg.esco_dir / EscoLoader.SKILLS_FILE,
        cfg.esco_dir / EscoLoader.LANGUAGE_FILE,
    ]
    if include_custom_overlay:
        paths.append(cfg.custom_concepts_path)
    return compute_esco_hash(*paths)


def compute_esco_sha(concepts: list[EscoConcept]) -> str:
    """SHA-256 digest over a stable tuple representation of ``concepts``.

    Distinct from :func:`compute_esco_file_sha` — this hashes the
    *parsed* concept set, not the source files. Used by unit tests
    that assert loader determinism: two calls to
    :func:`load_esco_concepts` (in different working directories,
    across processes) must produce the same digest.

    The hash inputs are the concept tuple
    ``(uri, pref_label, sorted alt_labels, description, skill_type, is_custom)``
    for each concept, with the outer list pre-sorted by URI by the
    loader. Returns the full 64-char hex digest (callers truncate if
    they need a shorter form for a filename).
    """
    h = hashlib.sha256()
    for c in concepts:
        # ``sorted(alt_labels)`` defends against altLabel-order drift
        # in the source CSV — the digest depends only on the *set* of
        # altLabels, not on the order they happened to be listed in.
        parts = (
            c.uri,
            c.pref_label,
            "|".join(sorted(c.alt_labels)),
            c.description,
            c.skill_type,
            "1" if c.is_custom else "0",
        )
        h.update("\x1f".join(parts).encode("utf-8"))
        h.update(b"\x1e")  # record separator
    return h.hexdigest()


__all__ = [
    "EscoConcept",
    "compute_esco_file_sha",
    "compute_esco_sha",
    "load_esco_concepts",
]
