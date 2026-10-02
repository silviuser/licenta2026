"""Parser for the ESCO v1.2.1 EN CSV bundle.

This module reads the two source files we need for skill extraction:

* ``skills_en.csv`` — the primary list of ~13.9k skills, with multi-line
  ``altLabels`` cells (separator: ``\\n``).
* ``languageSkillsCollection_en.csv`` — a curated subset of language-
  related skills (separator: `` | ``). The URIs in this file are
  overlaid on the primary list to override the native ``skillType``
  (``"knowledge"`` / ``"skill/competence"``) with the more specific
  ``"language"`` value used by Module 2.

The result is a deduplicated list of :class:`~skill_extractor.models.EscoSkill`
ready to feed the PhraseMatcher builder.

Robust altLabel splitting
-------------------------
The two ESCO source files use different separators in the same ``altLabels``
column. Rather than special-case each file, the splitter accepts any of
``\\n``, ``|`` (with optional surrounding whitespace) and ``;`` so it remains
tolerant of future ESCO bundle variations. Empty fragments are discarded
and per-skill altLabels are deduplicated case-insensitively while
preserving the first-seen casing (which is what spaCy will use as a
pattern).
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from pathlib import Path

import structlog

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.exceptions import EscoLoadError
from skill_extractor.models import EscoSkill, SkillType

logger = structlog.get_logger(__name__)

# ``\n`` (newlines inside quoted CSV cells), `` | `` and ``;`` are the
# separators we have observed in ESCO bundles. Any of these splits an
# altLabels cell into individual labels.
_ALT_LABEL_SEPARATOR_REGEX = re.compile(r"\s*[|\n;]\s*")

# Maximum CSV cell size we accept (defends against pathological files).
# csv.field_size_limit defaults to ~131k bytes which can be exceeded by
# rare skills with very long descriptions; bumping to 4 MiB is safe.
_MAX_FIELD_SIZE = 4 * 1024 * 1024


class EscoLoader:
    """Reads the ESCO CSV bundle into a deduplicated list of skills.

    Parameters
    ----------
    config
        Optional :class:`SkillExtractorConfig`. The only field consulted
        is :attr:`SkillExtractorConfig.esco_dir`. If omitted, defaults
        from the config are used.

    Notes
    -----
    The loader is stateless: each :meth:`load` call re-reads the files.
    Caching is the responsibility of the caller (typically the
    pipeline orchestrator that holds a long-lived
    :class:`~skill_extractor.esco.matcher.EscoMatcherBuilder`).

    Examples
    --------
    >>> loader = EscoLoader()
    >>> skills = loader.load()  # doctest: +SKIP
    >>> len(skills)             # doctest: +SKIP
    13939
    """

    SKILLS_FILE = "skills_en.csv"
    LANGUAGE_FILE = "languageSkillsCollection_en.csv"

    def __init__(self, config: SkillExtractorConfig | None = None) -> None:
        self._config = config or SkillExtractorConfig()
        # Some of the ESCO description cells run very long; raise the
        # csv module's per-field cap once at import time.
        try:
            csv.field_size_limit(_MAX_FIELD_SIZE)
        except OverflowError:
            # 32-bit Python limit — fall back to whatever max the platform
            # supports; the ESCO data still fits in practice.
            csv.field_size_limit(2**31 - 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> list[EscoSkill]:
        """Load and merge the ESCO bundle.

        Returns
        -------
        list[EscoSkill]
            Deterministic order: sorted by ``concept_uri`` so cache
            invalidation hashes are stable across runs.

        Raises
        ------
        EscoLoadError
            If either CSV file is missing, empty or malformed.
        """
        skills_path = self._config.esco_dir / self.SKILLS_FILE
        language_path = self._config.esco_dir / self.LANGUAGE_FILE

        primary = self._load_skills_csv(skills_path)
        primary = self._apply_language_overlay(primary, language_path)

        result = sorted(primary.values(), key=lambda s: s.concept_uri)

        type_counts: dict[str, int] = {}
        for s in result:
            type_counts[s.skill_type] = type_counts.get(s.skill_type, 0) + 1

        logger.info(
            "esco.loader.loaded",
            skills_path=str(skills_path),
            language_path=str(language_path),
            total=len(result),
            by_type=type_counts,
        )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_skills_csv(self, path: Path) -> dict[str, EscoSkill]:
        """Parse ``skills_en.csv`` into a URI-keyed dict."""
        if not path.exists():
            raise EscoLoadError(
                f"ESCO skills file not found: {path}", path=str(path)
            )

        result: dict[str, EscoSkill] = {}
        try:
            with path.open(encoding="utf-8", newline="") as fp:
                reader = csv.DictReader(fp)
                self._require_columns(
                    reader,
                    {
                        "conceptUri",
                        "skillType",
                        "preferredLabel",
                        "altLabels",
                        "description",
                        "reuseLevel",
                    },
                    path,
                )
                for row in reader:
                    skill = self._row_to_skill(row)
                    if skill is None:
                        continue
                    # If the bundle ever has duplicate URIs (it shouldn't),
                    # last-write-wins is fine — they'd be identical.
                    result[skill.concept_uri] = skill
        except csv.Error as exc:  # pragma: no cover — defensive
            raise EscoLoadError(
                f"CSV parse error in {path}: {exc}", path=str(path)
            ) from exc

        if not result:
            raise EscoLoadError(
                f"ESCO skills file contained zero rows: {path}",
                path=str(path),
            )
        return result

    def _apply_language_overlay(
        self,
        primary: dict[str, EscoSkill],
        path: Path,
    ) -> dict[str, EscoSkill]:
        """Apply the language-collection overlay onto the primary dict.

        For URIs already in ``primary``, the ``skill_type`` is rewritten
        to ``"language"``. URIs present only in the overlay are added as
        new :class:`EscoSkill` instances so we don't lose coverage if
        the two files ever disagree.
        """
        if not path.exists():
            # Language overlay is optional; degrade gracefully.
            logger.warning(
                "esco.loader.language_overlay_missing", path=str(path)
            )
            return primary

        added = 0
        overridden = 0
        with path.open(encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            self._require_columns(
                reader,
                {"conceptUri", "preferredLabel", "altLabels"},
                path,
            )
            for row in reader:
                uri = (row.get("conceptUri") or "").strip()
                if not uri:
                    continue
                if uri in primary:
                    existing = primary[uri]
                    if existing.skill_type != "language":
                        primary[uri] = existing.model_copy(
                            update={"skill_type": "language"}
                        )
                        overridden += 1
                else:
                    # URI exists only in the language collection — synthesise
                    # an EscoSkill from the overlay row.
                    skill = self._row_to_skill(row, force_skill_type="language")
                    if skill is not None:
                        primary[uri] = skill
                        added += 1

        logger.info(
            "esco.loader.language_overlay_applied",
            overridden=overridden,
            added=added,
        )
        return primary

    def _row_to_skill(
        self,
        row: dict[str, str],
        force_skill_type: SkillType | None = None,
    ) -> EscoSkill | None:
        """Convert a CSV row into an :class:`EscoSkill`, returning None
        for rows we want to skip silently (missing URI / label).

        ``force_skill_type``, if given, overrides whatever value the row
        contained. Used by the language overlay.
        """
        uri = (row.get("conceptUri") or "").strip()
        label = (row.get("preferredLabel") or "").strip()
        if not uri or not label:
            return None

        if force_skill_type is not None:
            skill_type: SkillType = force_skill_type
        else:
            raw_type = (row.get("skillType") or "").strip()
            skill_type = self._normalise_skill_type(raw_type)

        alt_labels = self._split_alt_labels(row.get("altLabels") or "")
        # Drop the preferred label if it accidentally appears in altLabels —
        # avoids duplicate patterns later.
        alt_labels = [a for a in alt_labels if a.lower() != label.lower()]
        # Case-insensitive dedupe while keeping first-seen casing.
        seen_lower: set[str] = set()
        deduped: list[str] = []
        for a in alt_labels:
            key = a.lower()
            if key in seen_lower:
                continue
            seen_lower.add(key)
            deduped.append(a)

        return EscoSkill(
            concept_uri=uri,
            preferred_label=label,
            alt_labels=deduped,
            skill_type=skill_type,
            description=(row.get("description") or "").strip(),
            reuse_level=(row.get("reuseLevel") or "").strip(),
        )

    @staticmethod
    def _normalise_skill_type(raw: str) -> SkillType:
        """Coerce an ESCO ``skillType`` cell into our literal enum.

        ESCO uses ``"knowledge"`` and ``"skill/competence"``; anything
        else is bucketed into ``"skill/competence"`` as the safest
        default.
        """
        raw_l = raw.lower()
        if raw_l == "knowledge":
            return "knowledge"
        if raw_l == "skill/competence":
            return "skill/competence"
        # ``language`` would only appear here if applied via the overlay
        # path which sets force_skill_type — handle defensively anyway.
        if raw_l == "language":
            return "language"
        return "skill/competence"

    @staticmethod
    def _split_alt_labels(raw: str) -> list[str]:
        """Split an ESCO altLabels cell on any known separator.

        Accepts ``\\n``, ``|`` (with optional whitespace) and ``;``.
        Empty / whitespace-only fragments are discarded.
        """
        if not raw or not raw.strip():
            return []
        parts = _ALT_LABEL_SEPARATOR_REGEX.split(raw)
        return [p.strip() for p in parts if p and p.strip()]

    @staticmethod
    def _require_columns(
        reader: csv.DictReader[str],
        required: Iterable[str],
        path: Path,
    ) -> None:
        """Raise :class:`EscoLoadError` if the CSV header is missing
        required columns. This catches malformed / truncated files
        early instead of silently producing an empty result.
        """
        header = set(reader.fieldnames or [])
        missing = set(required) - header
        if missing:
            raise EscoLoadError(
                f"Missing required columns in {path.name}: "
                f"{sorted(missing)}. Found: {sorted(header)}",
                path=str(path),
            )
