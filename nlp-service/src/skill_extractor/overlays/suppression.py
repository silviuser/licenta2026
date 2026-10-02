"""Suppression rules — drop known-bad (surface, target URI) matches.

The May-2026 validation report classifies 14 false-positive families
sharing a common pattern: an ESCO concept matches a surface form whose
CV usage is decisively *not* that concept (``.NET`` matched to ``Visual
Basic``; ``design`` matched to the ``think creatively`` soft skill;
``It`` matched to ``computer technology`` because the pronoun looks
like the abbreviation). The :class:`SuppressionFilter` reads
``suppression_rules.yaml`` and drops the offending raw hits before
they reach the scorer.

Rule schema
-----------
A rule is an object with:

``surface_pattern``
    Exact string the matched surface must equal (after stripping leading
    / trailing whitespace). ``case_sensitive: true`` makes the
    comparison case-sensitive; otherwise it is lower-cased on both
    sides.

``target_concept_uri``
    The ESCO (or ``CUST:``) URI the surface was mapped to.

``reason``
    Free-text annotation used in logging and the validation report.
    Not consulted at runtime.

``context_required`` (optional)
    A mapping that further narrows the rule to specific CV sections or
    surrounding-text terms:

    ``allowed_sections``
        If present, the rule fires ONLY when the match is in one of
        these sections. Other sections keep the match.

    ``forbidden_sections``
        If present, the rule fires UNLESS the match is in one of these
        sections. Listed sections keep the match.

    ``surrounding_terms_any``
        If present, the rule fires only when at least one of the listed
        terms appears within ``surrounding_window_chars`` characters of
        the match. Case-insensitive substring test.

    ``forbidden_surrounding_terms_any``
        Mirror of the above: the rule fires only when none of the listed
        terms is in the window.

``surrounding_window_chars``
    Window size for the surrounding-terms checks. Defaults to 60
    characters on each side.

Design notes
------------
* The filter is intentionally rule-based and side-effect-free. No NER
  or POS tagging happens here — those are higher-cost dependencies and
  the FP catalogue is small enough that hand-written rules outperform
  generic models on this corpus.
* Each rule is keyed in an index by ``(surface_lower, target_uri)`` so
  the hot path is a single dict lookup per raw hit. Section /
  surrounding-term checks run only when an index hit fires.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from skill_extractor.exceptions import EscoLoadError
from skill_extractor.models import SectionLabel

logger = structlog.get_logger(__name__)

_DEFAULT_WINDOW_CHARS = 60


@dataclass(slots=True, frozen=True)
class ContextRequirement:
    """Optional context narrowing for a suppression rule."""

    allowed_sections: tuple[SectionLabel, ...] = ()
    forbidden_sections: tuple[SectionLabel, ...] = ()
    surrounding_terms_any: tuple[str, ...] = ()
    forbidden_surrounding_terms_any: tuple[str, ...] = ()
    window_chars: int = _DEFAULT_WINDOW_CHARS


@dataclass(slots=True, frozen=True)
class SuppressionRule:
    """A single (surface, target URI) suppression rule."""

    surface_pattern: str
    target_concept_uri: str
    case_sensitive: bool = False
    context: ContextRequirement | None = None
    reason: str = ""


@dataclass(slots=True)
class SuppressionRuleSet:
    """Loaded rules, indexed for O(1) lookup at match time."""

    rules: list[SuppressionRule] = field(default_factory=list)
    # ``slots=True`` requires every assignable attribute to be declared
    # up-front. The lookup index is populated by ``__post_init__``; it
    # is excluded from ``__init__`` and ``__repr__`` so callers
    # construct ``SuppressionRuleSet(rules=[...])`` as before.
    _index: dict[tuple[str, str], list[SuppressionRule]] = field(
        init=False, default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        # Index: case-sensitive surface uses the original; case-insensitive uses lower.
        for rule in self.rules:
            surface_key = (
                rule.surface_pattern
                if rule.case_sensitive
                else rule.surface_pattern.lower()
            )
            key = (surface_key, rule.target_concept_uri)
            self._index.setdefault(key, []).append(rule)

    def lookup(self, *, surface: str, target_uri: str) -> list[SuppressionRule]:
        """Return the rules that could apply to ``(surface, target_uri)``.

        Returns every rule whose surface pattern matches the surface
        (case-sensitive rules and case-insensitive rules are both
        consulted). The caller then runs the per-rule context check.
        """
        hits = list(self._index.get((surface, target_uri), ()))
        if surface.lower() != surface:
            hits.extend(self._index.get((surface.lower(), target_uri), ()))
        else:
            # Already lower; the case-sensitive entry (if any) was consulted above
            # only if surface preserves casing — handle the other half.
            extra = self._index.get((surface, target_uri), ())
            for r in extra:
                if r not in hits:
                    hits.append(r)
        return hits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_suppression_rules(path: Path) -> SuppressionRuleSet:
    """Read ``path`` into a :class:`SuppressionRuleSet`.

    Empty / missing files yield an empty rule set (the feature is
    optional). Malformed files raise :class:`EscoLoadError`.
    """
    if not path.exists():
        logger.info("suppression.rules_missing", path=str(path))
        return SuppressionRuleSet()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EscoLoadError(
            f"YAML parse error in {path}: {exc}", path=str(path)
        ) from exc

    if raw is None:
        return SuppressionRuleSet()
    if not isinstance(raw, dict):
        raise EscoLoadError(
            f"Top-level YAML in {path} must be a mapping; got {type(raw).__name__}",
            path=str(path),
        )

    raw_rules = raw.get("rules", [])
    if not isinstance(raw_rules, list):
        raise EscoLoadError(
            f"`rules` key in {path} must be a list; got {type(raw_rules).__name__}",
            path=str(path),
        )

    rules: list[SuppressionRule] = []
    for idx, entry in enumerate(raw_rules):
        rules.append(_parse_rule(entry, path=path, idx=idx))

    logger.info("suppression.loaded", path=str(path), rules=len(rules))
    return SuppressionRuleSet(rules=rules)


class SuppressionFilter:
    """Decide whether a raw hit should be dropped based on the rules.

    The filter is stateless beyond the indexed rule set. One instance
    is constructed by the pipeline at startup and reused for every
    extraction.
    """

    def __init__(self, ruleset: SuppressionRuleSet | None = None) -> None:
        self._ruleset = ruleset or SuppressionRuleSet()

    @property
    def ruleset(self) -> SuppressionRuleSet:
        return self._ruleset

    def should_suppress(
        self,
        *,
        text: str,
        surface: str,
        target_uri: str,
        section: SectionLabel,
        char_start: int,
        char_end: int,
    ) -> SuppressionRule | None:
        """Return the rule that suppresses this match, or ``None``.

        Returning the rule (rather than a bool) lets callers log
        ``rule.reason`` for telemetry and debugging.
        """
        candidates = self._ruleset.lookup(surface=surface, target_uri=target_uri)
        for rule in candidates:
            if not self._surface_matches(rule=rule, surface=surface):
                continue
            if rule.context is None or self._context_satisfied(
                ctx=rule.context,
                text=text,
                section=section,
                char_start=char_start,
                char_end=char_end,
            ):
                return rule
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _surface_matches(*, rule: SuppressionRule, surface: str) -> bool:
        """Surface comparison honouring the rule's case-sensitivity flag."""
        if rule.case_sensitive:
            return surface == rule.surface_pattern
        return surface.lower() == rule.surface_pattern.lower()

    @staticmethod
    def _context_satisfied(
        *,
        ctx: ContextRequirement,
        text: str,
        section: SectionLabel,
        char_start: int,
        char_end: int,
    ) -> bool:
        """Return True if the optional context narrowing allows the rule to fire."""
        if ctx.allowed_sections and section not in ctx.allowed_sections:
            return False
        if ctx.forbidden_sections and section in ctx.forbidden_sections:
            return False

        if ctx.surrounding_terms_any or ctx.forbidden_surrounding_terms_any:
            window_start = max(0, char_start - ctx.window_chars)
            window_end = min(len(text), char_end + ctx.window_chars)
            window = text[window_start:window_end].lower()

            if ctx.surrounding_terms_any and not any(
                term.lower() in window for term in ctx.surrounding_terms_any
            ):
                return False
            if ctx.forbidden_surrounding_terms_any and any(
                term.lower() in window
                for term in ctx.forbidden_surrounding_terms_any
            ):
                return False

        return True


# ---------------------------------------------------------------------------
# Internals: YAML parsing
# ---------------------------------------------------------------------------


def _parse_rule(entry: Any, *, path: Path, idx: int) -> SuppressionRule:
    """Convert one ``rules[idx]`` mapping into a :class:`SuppressionRule`."""
    if not isinstance(entry, dict):
        raise EscoLoadError(
            f"suppression rule #{idx} in {path} is not a mapping",
            path=str(path),
        )

    surface = str(entry.get("surface_pattern") or "").strip()
    target = str(entry.get("target_concept_uri") or "").strip()
    if not surface:
        raise EscoLoadError(
            f"suppression rule #{idx} in {path} missing surface_pattern",
            path=str(path),
        )
    if not target:
        raise EscoLoadError(
            f"suppression rule #{idx} in {path} missing target_concept_uri",
            path=str(path),
        )

    case_sensitive = bool(entry.get("case_sensitive", False))

    ctx_raw = entry.get("context_required")
    window_chars_top = entry.get("surrounding_window_chars")
    context: ContextRequirement | None = None
    if isinstance(ctx_raw, dict):
        context = _parse_context(
            raw=ctx_raw,
            top_level_window=window_chars_top,
            path=path,
            idx=idx,
        )
    elif ctx_raw is not None:
        raise EscoLoadError(
            f"suppression rule #{idx} in {path} context_required must be a mapping",
            path=str(path),
        )

    return SuppressionRule(
        surface_pattern=surface,
        target_concept_uri=target,
        case_sensitive=case_sensitive,
        context=context,
        reason=str(entry.get("reason") or ""),
    )


def _parse_context(
    *,
    raw: dict[str, Any],
    top_level_window: Any,
    path: Path,
    idx: int,
) -> ContextRequirement:
    """Parse the ``context_required`` sub-mapping into a typed dataclass."""
    allowed = _str_tuple(
        raw.get("allowed_sections"), key="allowed_sections", path=path, idx=idx
    )
    forbidden = _str_tuple(
        raw.get("forbidden_sections"),
        key="forbidden_sections",
        path=path,
        idx=idx,
    )
    surrounding = _str_tuple(
        raw.get("surrounding_terms_any"),
        key="surrounding_terms_any",
        path=path,
        idx=idx,
    )
    forbidden_surrounding = _str_tuple(
        raw.get("forbidden_surrounding_terms_any"),
        key="forbidden_surrounding_terms_any",
        path=path,
        idx=idx,
    )
    window_raw = raw.get("surrounding_window_chars", top_level_window)
    if window_raw is None:
        window = _DEFAULT_WINDOW_CHARS
    elif isinstance(window_raw, int) and window_raw > 0:
        window = window_raw
    else:
        raise EscoLoadError(
            f"suppression rule #{idx} in {path} window_chars must be a positive int",
            path=str(path),
        )

    return ContextRequirement(
        allowed_sections=allowed,  # type: ignore[arg-type]
        forbidden_sections=forbidden,  # type: ignore[arg-type]
        surrounding_terms_any=surrounding,
        forbidden_surrounding_terms_any=forbidden_surrounding,
        window_chars=window,
    )


def _str_tuple(
    value: Any,
    *,
    key: str,
    path: Path,
    idx: int,
) -> tuple[str, ...]:
    """Coerce ``value`` to a tuple of non-empty strings, or ``()``."""
    if value is None:
        return ()
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        raise EscoLoadError(
            f"suppression rule #{idx} in {path} {key} must be a list of strings",
            path=str(path),
        )
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise EscoLoadError(
                f"suppression rule #{idx} in {path} {key} contains a non-string entry",
                path=str(path),
            )
        out.append(item.strip())
    return tuple(out)
