"""Romanian-label overlay — fold ESCO RO surface forms onto EN concepts.

ESCO publishes the *same* ``conceptUri`` in every language. This overlay
reads the Romanian skills bundle (``skills_ro.csv``) and attaches each
concept's Romanian ``preferredLabel`` + ``altLabels`` to the matching
English :class:`~skill_extractor.models.EscoSkill` (keyed by URI) as extra
``alt_labels``.

Effect: the Module 2 PhraseMatcher now also recognises Romanian surface
forms (e.g. ``"baze de date"``) and resolves them to the *same* ESCO URI
as the English form (``"database"``). Everything downstream — the Module 3
Linker, the Scorer and the embedding index — is unchanged, because the URI
and the canonical English ``preferred_label`` are preserved. A Romanian
hit is therefore classified as an ``alt`` match (confidence weight 0.85),
which is the correct tier for a non-preferred surface form.

Non-destructive: only ``alt_labels`` is extended; ``concept_uri`` /
``preferred_label`` / ``skill_type`` stay exactly as the English bundle
defined them. The function mirrors
:func:`skill_extractor.overlays.aliases.apply_aliases` so the merge /
dedupe semantics are identical to the existing alias overlay.

Failure mode
------------
The overlay is **optional**. A missing file is treated as an empty
overlay (logged at WARNING) so the pipeline degrades gracefully to
English-only matching. A structurally malformed file (missing required
columns / unreadable CSV) raises
:class:`~skill_extractor.exceptions.EscoLoadError` — failing fast is the
safer choice since a silently-empty overlay would under-perform with no
visible signal.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

import structlog

from skill_extractor.exceptions import EscoLoadError
from skill_extractor.models import EscoSkill

logger = structlog.get_logger(__name__)

# Filename of the Romanian skills bundle inside ``config.esco_ro_dir``.
RO_SKILLS_FILENAME = "skills_ro.csv"

# Same separators the EN loader accepts inside an ``altLabels`` cell:
# ``\n`` (newlines in quoted CSV cells), `` | `` and ``;``.
_ALT_LABEL_SEPARATOR_REGEX = re.compile(r"\s*[|\n;]\s*")

# Mirror the EN loader's raised per-field cap (long ESCO descriptions).
_MAX_FIELD_SIZE = 4 * 1024 * 1024

# Only these three columns are consulted; the RO bundle ships extra ones
# (conceptType, hiddenLabels, definition, ...) which we ignore.
_REQUIRED_COLUMNS = {"conceptUri", "preferredLabel", "altLabels"}


def load_ro_label_surfaces(path: Path) -> dict[str, list[str]]:
    """Read ``skills_ro.csv`` into ``{conceptUri: [romanian surfaces]}``.

    Each concept contributes its Romanian preferred label followed by its
    Romanian alt labels (split on ``\\n`` / ``|`` / ``;``). Surfaces are
    de-duplicated case-insensitively while preserving first-seen casing
    (the PhraseMatcher keys on ``LOWER`` so casing is cosmetic, but we keep
    the source casing for readable pattern strings).

    Parameters
    ----------
    path
        Path to ``skills_ro.csv``. A non-existent path yields an empty
        mapping (logged at WARNING) rather than raising.

    Returns
    -------
    dict[str, list[str]]
        URI → ordered, de-duplicated Romanian surface forms.

    Raises
    ------
    EscoLoadError
        If the file exists but is missing required columns or cannot be
        parsed as CSV.
    """
    if not path.exists():
        logger.warning("ro_labels.overlay_missing", path=str(path))
        return {}

    try:
        csv.field_size_limit(_MAX_FIELD_SIZE)
    except OverflowError:  # pragma: no cover — 32-bit platforms only
        csv.field_size_limit(2**31 - 1)

    surfaces_by_uri: dict[str, list[str]] = {}
    try:
        with path.open(encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            header = set(reader.fieldnames or [])
            missing = _REQUIRED_COLUMNS - header
            if missing:
                raise EscoLoadError(
                    f"Missing required columns in {path.name}: "
                    f"{sorted(missing)}. Found: {sorted(header)}",
                    path=str(path),
                )
            for row in reader:
                uri = (row.get("conceptUri") or "").strip()
                if not uri:
                    continue
                pref = (row.get("preferredLabel") or "").strip()
                alts_raw = row.get("altLabels") or ""

                surfaces: list[str] = []
                seen: set[str] = set()
                for candidate in (pref, *_split_alt_labels(alts_raw)):
                    for variant in _surface_variants(candidate):
                        key = variant.lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        surfaces.append(variant)
                if surfaces:
                    surfaces_by_uri[uri] = surfaces
    except csv.Error as exc:  # pragma: no cover — defensive
        raise EscoLoadError(
            f"CSV parse error in {path}: {exc}", path=str(path)
        ) from exc

    logger.info(
        "ro_labels.loaded",
        path=str(path),
        concepts=len(surfaces_by_uri),
        surfaces=sum(len(v) for v in surfaces_by_uri.values()),
    )
    return surfaces_by_uri


def apply_ro_labels(
    skills: list[EscoSkill],
    surfaces_by_uri: dict[str, list[str]],
) -> list[EscoSkill]:
    """Return a new skill list with Romanian surfaces folded into alt_labels.

    Non-destructive: the input list is not mutated. Only concepts whose
    URI appears in ``surfaces_by_uri`` are rebuilt (via ``model_copy``),
    with the Romanian surfaces appended to ``alt_labels``. Surfaces already
    present — checked case-insensitively against the preferred label and
    existing alt labels — are skipped so the PhraseMatcher pattern set stays
    de-duplicated.

    Romanian-only URIs (present in the RO bundle but not in the English
    one) are counted and skipped: this overlay augments English concepts,
    it does not introduce new ones (that is the job of
    ``custom_concepts.json``).

    Parameters
    ----------
    skills
        The English skill list, post alias + custom overlays.
    surfaces_by_uri
        Output of :func:`load_ro_label_surfaces`.

    Returns
    -------
    list[EscoSkill]
        A new list, same order as the input.
    """
    if not surfaces_by_uri:
        return list(skills)

    known_uris = {s.concept_uri for s in skills}
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
        for surface in extra:
            if surface.lower() in existing_lower:
                continue
            existing_lower.add(surface.lower())
            merged.append(surface)
            new_surfaces += 1
        if merged != list(skill.alt_labels):
            rebuilt.append(skill.model_copy(update={"alt_labels": merged}))
            augmented += 1
        else:
            rebuilt.append(skill)

    ro_only_uris = sum(1 for uri in surfaces_by_uri if uri not in known_uris)
    logger.info(
        "ro_labels.applied",
        augmented_skills=augmented,
        new_surfaces=new_surfaces,
        ro_only_uris_skipped=ro_only_uris,
    )
    return rebuilt


def _split_alt_labels(raw: str) -> list[str]:
    """Split an ESCO ``altLabels`` cell on any known separator."""
    if not raw or not raw.strip():
        return []
    parts = _ALT_LABEL_SEPARATOR_REGEX.split(raw)
    return [p.strip() for p in parts if p and p.strip()]


# Surfaces that are pure numbers / punctuation (the RO bundle has a few
# stray cells such as ``"0.0"``) — never useful as match patterns and a
# false-positive risk, so they are dropped on load.
_JUNK_SURFACE_RE = re.compile(r"^[\d.,;:|/\\\s-]+$")


def _is_junk_surface(text: str) -> bool:
    """True for empty, single-character, or numeric-/punctuation-only text."""
    return len(text) < 2 or bool(_JUNK_SURFACE_RE.match(text))


def _strip_diacritics(text: str) -> str:
    """ASCII-fold via NFKD decomposition (``"bază"`` → ``"baza"``)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _surface_variants(raw: str) -> list[str]:
    """Return the cleaned surface plus its diacritic-free variant.

    Romanian CVs are routinely typed without diacritics, so for every
    accented label we also emit an ASCII-folded variant (``"bază de
    date"`` → ``"baza de date"``) as a separate PhraseMatcher pattern —
    the same diacritic-insensitivity the section detector already relies
    on. Junk surfaces (see :func:`_is_junk_surface`) are dropped.
    """
    cleaned = (raw or "").strip()
    if _is_junk_surface(cleaned):
        return []
    variants = [cleaned]
    folded = _strip_diacritics(cleaned)
    if folded != cleaned and not _is_junk_surface(folded):
        variants.append(folded)
    return variants


__all__ = ["RO_SKILLS_FILENAME", "apply_ro_labels", "load_ro_label_surfaces"]
