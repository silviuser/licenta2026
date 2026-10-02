"""On-disk cache for the spaCy PhraseMatcher built from ESCO skills.

Building a PhraseMatcher over the full 13.9k ESCO skill set requires
tokenising ~30k pattern strings (preferredLabel + altLabels) through a
spaCy pipeline. On a developer laptop that takes 5-15 seconds — slow
enough to be annoying for repeated test/CLI runs.

This module persists the tokenised patterns plus a small metadata map
(``match_id → (concept_uri, preferred_label, label_kind, surface_set)``)
to disk, keyed by a SHA-256 hash of the source CSV files. Reloads take
under a second.

Cache contents and layout
-------------------------
A cache file is a single pickled :class:`MatcherCachePayload` containing:

* ``docbin_bytes`` — :class:`spacy.tokens.DocBin` serialised bytes,
  carrying every pattern Doc.
* ``pattern_names`` — names parallel to the DocBin docs; each name is
  the matcher key (``"<uri>|preferred"`` or ``"<uri>|alt"``).
* ``label_map`` — name → :class:`MatchMeta`.

Cache *invalidation* is automatic: the filename embeds an 8-hex
prefix of the SHA-256 of every source CSV. If any source file changes,
the cache filename changes, and a stale file is simply ignored.
"""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import structlog

from skill_extractor.exceptions import MatcherCacheError

logger = structlog.get_logger(__name__)

LabelKind = Literal["preferred", "alt"]
"""Whether a pattern was generated from the ESCO ``preferredLabel`` or
from one of its ``altLabels``. Used at match time to decide between
``"exact"`` and ``"alt"`` confidence tiers."""


@dataclass(slots=True)
class MatchMeta:
    """Metadata attached to one matcher key.

    A single ``MatchMeta`` covers all patterns sharing the same
    ``(concept_uri, label_kind)`` tuple — typically one for the
    preferred label and one for the bag of altLabels.
    """

    concept_uri: str
    preferred_label: str
    label_kind: LabelKind
    skill_type: str  # mirrors EscoSkill.skill_type as a string
    # Lower-cased surface forms covered by this match key. Used at match
    # time to determine whether a hit was on the exact pattern (→ "exact"
    # / "alt" confidence) or only via lemma normalisation (→ "lemma").
    surfaces: set[str] = field(default_factory=set)
    # True when the underlying EscoSkill came from the custom-concept
    # overlay (``CUST:`` URI). Propagated to ``SkillMatch.is_custom`` so
    # validation reports can break metrics down by source.
    is_custom: bool = False


@dataclass(slots=True)
class MatcherCachePayload:
    """The complete persisted form of a built matcher.

    ``language`` is stored explicitly because :attr:`spacy_model` (which
    is ``nlp.meta["name"]``, e.g. ``"core_web_lg"``) does NOT carry the
    language prefix — spaCy keeps the language separate in
    ``nlp.meta["lang"]``. Persisting the language directly avoids
    fragile string-parsing on the model name and is the canonical
    source for the cache filename.
    """

    esco_hash: str
    language: str
    spacy_model: str
    phrase_attr: str
    docbin_bytes: bytes
    pattern_names: list[str]
    label_map: dict[str, MatchMeta]


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def compute_esco_hash(*paths: Path) -> str:
    """SHA-256 over the byte contents of the given files, hex-truncated to 12.

    Sorted by path so the hash is order-independent. Missing files are
    silently skipped (the loader will raise its own error elsewhere if
    a required source is absent).
    """
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda x: str(x)):
        if not p.exists():
            continue
        with p.open("rb") as fp:
            for chunk in iter(lambda: fp.read(64 * 1024), b""):
                h.update(chunk)
    return h.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


class MatcherDiskCache:
    """Reads and writes :class:`MatcherCachePayload` pickles under a
    cache directory.

    The cache is intentionally simple: one pickle file per ``(lang,
    esco_hash)`` tuple. There's no LRU eviction; users are expected to
    delete the directory if it grows. In practice each cache file is
    a few megabytes, and the hash invalidation means stale files
    accumulate only when the ESCO bundle is upgraded — a rare event.
    """

    def __init__(self, cache_dir: Path, filename_template: str) -> None:
        self._cache_dir = cache_dir
        self._template = filename_template

    def path_for(self, *, lang: str, esco_hash: str) -> Path:
        """Return the on-disk path for the given language + hash."""
        filename = self._template.format(lang=lang, esco_hash=esco_hash)
        return self._cache_dir / filename

    def load(
        self, *, lang: str, esco_hash: str
    ) -> MatcherCachePayload | None:
        """Return the cached payload or None on any miss / read error."""
        path = self.path_for(lang=lang, esco_hash=esco_hash)
        if not path.exists():
            logger.debug(
                "matcher_cache.miss", path=str(path), reason="not_found"
            )
            return None
        try:
            with path.open("rb") as fp:
                payload = pickle.load(fp)
        except (pickle.UnpicklingError, EOFError, OSError) as exc:
            logger.warning(
                "matcher_cache.read_failed",
                path=str(path),
                error=str(exc),
            )
            return None
        if not isinstance(payload, MatcherCachePayload):
            logger.warning(
                "matcher_cache.unexpected_type",
                path=str(path),
                got=type(payload).__name__,
            )
            return None
        if payload.esco_hash != esco_hash:
            # Should never happen because the filename embeds the hash,
            # but defend against tampering anyway.
            logger.warning(
                "matcher_cache.hash_mismatch",
                path=str(path),
                expected=esco_hash,
                actual=payload.esco_hash,
            )
            return None
        logger.info(
            "matcher_cache.hit",
            path=str(path),
            patterns=len(payload.pattern_names),
        )
        return payload

    def save(self, payload: MatcherCachePayload) -> None:
        """Write the payload atomically (write to .tmp, then rename)."""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise MatcherCacheError(
                f"Cannot create cache directory {self._cache_dir}: {exc}"
            ) from exc
        path = self.path_for(
            lang=payload.language,
            esco_hash=payload.esco_hash,
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with tmp.open("wb") as fp:
                pickle.dump(payload, fp, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(path)
        except OSError as exc:
            raise MatcherCacheError(
                f"Cannot write matcher cache to {path}: {exc}"
            ) from exc
        logger.info(
            "matcher_cache.saved",
            path=str(path),
            patterns=len(payload.pattern_names),
            bytes=path.stat().st_size,
        )


# Note: a previous version parsed the language from ``spacy_model`` via
# ``.split("_", 1)[0]``. That was incorrect because spaCy stores the
# language separately in ``nlp.meta["lang"]`` — ``nlp.meta["name"]`` is
# only ``"core_web_lg"`` (for ``en_core_web_lg``), so the split yielded
# ``"core"`` and the cache filename collided across languages. The
# language is now carried explicitly on :class:`MatcherCachePayload`.
