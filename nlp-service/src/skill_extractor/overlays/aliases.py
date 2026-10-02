"""Loader for the surface→ESCO-URI alias overlay.

The YAML file under :data:`skill_extractor.config.DEFAULT_TECH_ALIASES_PATH`
adds extra ``altLabel``-style surface forms to existing ESCO concepts.
This is a *non-destructive* augmentation: the underlying
:class:`~skill_extractor.models.EscoSkill` is rewritten only to extend
its ``alt_labels`` list, preserving the original ``concept_uri`` /
``preferred_label`` / ``skill_type``.

A single :func:`apply_aliases` call is performed by
:class:`~skill_extractor.esco.loader.EscoLoader` immediately after the
primary skills CSV is parsed, so every cache key downstream
(``compute_esco_hash`` etc.) stays unchanged — the alias file content
is not yet folded into the matcher cache hash, but its contribution
goes into the in-process matcher build and that is what the validation
script runs against.

Failure mode
------------
The overlay is **optional**. A missing file is silently treated as an
empty alias list (logged at INFO level). A malformed file raises
:class:`~skill_extractor.exceptions.EscoLoadError` — failing fast is
the safer choice since broken aliases would otherwise silently
under-perform with no visible signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog
import yaml

from skill_extractor.exceptions import EscoLoadError
from skill_extractor.models import EscoSkill

logger = structlog.get_logger(__name__)


@dataclass(slots=True, frozen=True)
class TechAlias:
    """One ``target_uri`` plus its newly-attached surface forms."""

    target_uri: str
    preferred_label: str
    surfaces: tuple[str, ...]
    reason: str = ""


@dataclass(slots=True)
class AliasOverlay:
    """Parsed ``tech_aliases.yaml`` ready to fold into an ``EscoSkill`` list."""

    aliases: list[TechAlias] = field(default_factory=list)

    def surfaces_by_uri(self) -> dict[str, list[str]]:
        """Group surface forms by their target ESCO URI for fast lookup."""
        out: dict[str, list[str]] = {}
        for alias in self.aliases:
            out.setdefault(alias.target_uri, []).extend(alias.surfaces)
        return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_alias_overlay(path: Path) -> AliasOverlay:
    """Parse the YAML alias file into an :class:`AliasOverlay`.

    Parameters
    ----------
    path
        Path to the YAML file. If the path does not exist an empty
        overlay is returned (logged at INFO).

    Raises
    ------
    EscoLoadError
        If the file is malformed (not a mapping, missing required keys,
        surfaces not a list, etc.).
    """
    if not path.exists():
        logger.info("aliases.overlay_missing", path=str(path))
        return AliasOverlay()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EscoLoadError(
            f"YAML parse error in {path}: {exc}", path=str(path)
        ) from exc

    if raw is None:
        return AliasOverlay()
    if not isinstance(raw, dict):
        raise EscoLoadError(
            f"Top-level YAML in {path} must be a mapping; got {type(raw).__name__}",
            path=str(path),
        )

    raw_aliases = raw.get("aliases", [])
    if not isinstance(raw_aliases, list):
        raise EscoLoadError(
            f"`aliases` key in {path} must be a list; got {type(raw_aliases).__name__}",
            path=str(path),
        )

    aliases: list[TechAlias] = []
    for idx, entry in enumerate(raw_aliases):
        if not isinstance(entry, dict):
            raise EscoLoadError(
                f"alias entry #{idx} in {path} is not a mapping",
                path=str(path),
            )
        target_uri = str(entry.get("target_uri") or "").strip()
        preferred_label = str(entry.get("preferred_label") or "").strip()
        surfaces_raw = entry.get("surfaces", [])
        if not target_uri:
            raise EscoLoadError(
                f"alias entry #{idx} in {path} missing target_uri",
                path=str(path),
            )
        if not isinstance(surfaces_raw, list) or not surfaces_raw:
            raise EscoLoadError(
                f"alias entry #{idx} in {path} must have a non-empty `surfaces` list",
                path=str(path),
            )
        cleaned_surfaces = tuple(
            s.strip() for s in surfaces_raw if isinstance(s, str) and s.strip()
        )
        if not cleaned_surfaces:
            raise EscoLoadError(
                f"alias entry #{idx} in {path} surfaces are all empty",
                path=str(path),
            )
        aliases.append(
            TechAlias(
                target_uri=target_uri,
                preferred_label=preferred_label,
                surfaces=cleaned_surfaces,
                reason=str(entry.get("reason") or ""),
            )
        )

    logger.info(
        "aliases.loaded",
        path=str(path),
        aliases=len(aliases),
        surfaces=sum(len(a.surfaces) for a in aliases),
    )
    return AliasOverlay(aliases=aliases)


def apply_aliases(
    skills: list[EscoSkill],
    overlay: AliasOverlay,
) -> list[EscoSkill]:
    """Return a new ``EscoSkill`` list with overlay surfaces folded in.

    The function does **not** mutate its input. Skills whose URI is
    referenced by the overlay are rebuilt with extended ``alt_labels``;
    every other skill is returned untouched. Surfaces already present
    in ``alt_labels`` (case-insensitive) are skipped to keep the
    PhraseMatcher pattern set deduplicated.

    Surfaces referencing a URI not in the input list are dropped with
    a single ``WARNING`` log entry — they typically signal a typo in
    the YAML and the user wants to know.

    Parameters
    ----------
    skills
        Output of :meth:`EscoLoader._load_skills_csv` (URI-deduped).
    overlay
        Output of :func:`load_alias_overlay`.

    Returns
    -------
    list[EscoSkill]
        A new list, same order as the input.
    """
    if not overlay.aliases:
        return list(skills)

    surfaces_by_uri = overlay.surfaces_by_uri()
    skill_by_uri = {s.concept_uri: s for s in skills}

    unknown_uris: list[str] = []
    rebuilt: list[EscoSkill] = []
    augmented = 0
    new_surfaces = 0
    for skill in skills:
        extra = surfaces_by_uri.get(skill.concept_uri)
        if not extra:
            rebuilt.append(skill)
            continue
        existing_lower = {a.lower() for a in skill.alt_labels} | {
            skill.preferred_label.lower()
        }
        merged = list(skill.alt_labels)
        for s in extra:
            if s.lower() in existing_lower:
                continue
            existing_lower.add(s.lower())
            merged.append(s)
            new_surfaces += 1
        if merged != list(skill.alt_labels):
            rebuilt.append(skill.model_copy(update={"alt_labels": merged}))
            augmented += 1
        else:
            rebuilt.append(skill)

    for uri in surfaces_by_uri:
        if uri not in skill_by_uri:
            unknown_uris.append(uri)
    if unknown_uris:
        logger.warning(
            "aliases.unknown_target_uris",
            uris=unknown_uris,
            hint="if the concept is not in ESCO, define it in custom_concepts.json",
        )

    logger.info(
        "aliases.applied",
        augmented_skills=augmented,
        new_surfaces=new_surfaces,
        unknown_uris=len(unknown_uris),
    )
    return rebuilt
