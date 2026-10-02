"""Loader for the custom-concept overlay.

``data/custom_concepts.json`` adds entirely new "skills" that ESCO
v1.2.1 does not index — Docker, Kubernetes, React, MongoDB, IntelliJ
IDEA and friends. The May-2026 validation report (section 7) treats
this overlay as the primary mechanism for raising recall on the
"concrete frameworks/tools not surfaced" false-negative family.

Each custom concept is loaded as an :class:`~skill_extractor.models.EscoSkill`
instance carrying ``is_custom=True`` and an ID that starts with the
``CUST:`` prefix. The PhraseMatcher builder treats custom skills
identically to native ESCO skills; downstream code can tell the two
apart by inspecting ``is_custom`` (or by the URI prefix, equivalently).

The loader enforces a single invariant: ``CUST:`` IDs must not collide
with the URIs of the native ESCO skills passed in. Collisions raise
:class:`~skill_extractor.exceptions.EscoLoadError` so they are caught
at process startup rather than producing silent dedup bugs at match
time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from skill_extractor.exceptions import EscoLoadError
from skill_extractor.models import EscoSkill, SkillType

logger = structlog.get_logger(__name__)

CUSTOM_URI_PREFIX = "CUST:"
"""All custom-concept IDs must start with this prefix.

Chosen so that:

* It cannot collide with the official ESCO URI scheme (which uses
  ``http://data.europa.eu/esco/skill/<uuid>``).
* Validation reports can filter custom matches via a single
  ``startswith`` check without needing the ``is_custom`` flag.
"""

_ALLOWED_SKILL_TYPES: frozenset[str] = frozenset(
    {"knowledge", "skill/competence", "language"}
)


@dataclass(slots=True, frozen=True)
class CustomConceptOverlay:
    """In-memory parsed form of the custom-concepts JSON file."""

    concepts: list[EscoSkill] = field(default_factory=list)

    def by_uri(self) -> dict[str, EscoSkill]:
        """Return a dict keyed by ``concept_uri``."""
        return {c.concept_uri: c for c in self.concepts}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_custom_overlay(path: Path) -> CustomConceptOverlay:
    """Read ``path`` and parse it into a :class:`CustomConceptOverlay`.

    Returns an empty overlay if the file does not exist (the feature is
    optional). Raises :class:`EscoLoadError` for syntactic problems.

    The function intentionally does **not** check for collisions against
    ESCO at this stage — that is the responsibility of :func:`merge_custom_concepts`,
    which has both the custom and native lists at hand.
    """
    if not path.exists():
        logger.info("custom_overlay.missing", path=str(path))
        return CustomConceptOverlay()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EscoLoadError(
            f"JSON parse error in {path}: {exc}", path=str(path)
        ) from exc

    if not isinstance(raw, dict):
        raise EscoLoadError(
            f"Top-level JSON in {path} must be an object; got {type(raw).__name__}",
            path=str(path),
        )

    raw_concepts = raw.get("concepts", [])
    if not isinstance(raw_concepts, list):
        raise EscoLoadError(
            f"`concepts` key in {path} must be a list; got {type(raw_concepts).__name__}",
            path=str(path),
        )

    concepts: list[EscoSkill] = []
    seen_ids: set[str] = set()
    for idx, entry in enumerate(raw_concepts):
        skill = _parse_concept(entry, path=path, idx=idx)
        if skill.concept_uri in seen_ids:
            raise EscoLoadError(
                f"Duplicate custom concept id in {path}: {skill.concept_uri}",
                path=str(path),
            )
        seen_ids.add(skill.concept_uri)
        concepts.append(skill)

    logger.info(
        "custom_overlay.loaded",
        path=str(path),
        concepts=len(concepts),
    )
    return CustomConceptOverlay(concepts=concepts)


def merge_custom_concepts(
    esco_skills: list[EscoSkill],
    overlay: CustomConceptOverlay,
) -> list[EscoSkill]:
    """Return ``esco_skills`` extended with the overlay's custom concepts.

    The function does not mutate its inputs. It asserts that no custom
    concept ID equals any native ESCO URI; collisions raise
    :class:`EscoLoadError`. Custom concepts are appended after the
    native list so iteration order in tests stays deterministic
    (native first, custom last).
    """
    if not overlay.concepts:
        return list(esco_skills)

    esco_uris = {s.concept_uri for s in esco_skills}
    colliding = [c.concept_uri for c in overlay.concepts if c.concept_uri in esco_uris]
    if colliding:
        raise EscoLoadError(
            f"Custom concept IDs collide with ESCO URIs: {sorted(colliding)}. "
            "All custom IDs must start with the 'CUST:' prefix.",
            path="custom_concepts.json",
        )

    logger.info(
        "custom_overlay.merged",
        esco=len(esco_skills),
        custom=len(overlay.concepts),
        total=len(esco_skills) + len(overlay.concepts),
    )
    return list(esco_skills) + list(overlay.concepts)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _parse_concept(entry: Any, *, path: Path, idx: int) -> EscoSkill:
    """Convert one ``concepts[idx]`` dict into an :class:`EscoSkill`."""
    if not isinstance(entry, dict):
        raise EscoLoadError(
            f"custom concept #{idx} in {path} is not an object",
            path=str(path),
        )

    cid = str(entry.get("id") or "").strip()
    label = str(entry.get("preferred_label") or "").strip()
    skill_type_raw = str(entry.get("skill_type") or "knowledge").strip()
    alt_labels_raw = entry.get("alt_labels", [])
    description = str(entry.get("description") or "").strip()
    source_url = str(entry.get("source_url") or "").strip()

    if not cid:
        raise EscoLoadError(
            f"custom concept #{idx} in {path} is missing `id`",
            path=str(path),
        )
    if not cid.startswith(CUSTOM_URI_PREFIX):
        raise EscoLoadError(
            f"custom concept #{idx} id {cid!r} must start with "
            f"{CUSTOM_URI_PREFIX!r}",
            path=str(path),
        )
    if not label:
        raise EscoLoadError(
            f"custom concept #{idx} in {path} ({cid}) is missing "
            "`preferred_label`",
            path=str(path),
        )
    if skill_type_raw not in _ALLOWED_SKILL_TYPES:
        raise EscoLoadError(
            f"custom concept #{idx} in {path} ({cid}) has unknown "
            f"skill_type={skill_type_raw!r}; allowed: {sorted(_ALLOWED_SKILL_TYPES)}",
            path=str(path),
        )
    if not isinstance(alt_labels_raw, list):
        raise EscoLoadError(
            f"custom concept #{idx} in {path} ({cid}) alt_labels must be a list",
            path=str(path),
        )

    alt_labels = [
        a.strip()
        for a in alt_labels_raw
        if isinstance(a, str) and a.strip() and a.strip().lower() != label.lower()
    ]
    # Dedupe case-insensitively while keeping first-seen casing.
    seen: set[str] = set()
    deduped: list[str] = []
    for a in alt_labels:
        if a.lower() in seen:
            continue
        seen.add(a.lower())
        deduped.append(a)

    skill_type: SkillType
    if skill_type_raw == "knowledge":
        skill_type = "knowledge"
    elif skill_type_raw == "skill/competence":
        skill_type = "skill/competence"
    else:
        skill_type = "language"

    # ``source_url`` is descriptive metadata; we route it through the
    # ``reuse_level`` field on EscoSkill so the value reaches downstream
    # telemetry without requiring a new schema field. Empty string when
    # absent.
    return EscoSkill(
        concept_uri=cid,
        preferred_label=label,
        alt_labels=deduped,
        skill_type=skill_type,
        description=description,
        reuse_level=source_url,
        is_custom=True,
    )
