"""Segment slash-joined skill tokens into individual tokens.

Motivation
----------
The May-2026 validation report (section 6, false-negative pattern #1)
identified ``C/C++`` as a five-fixture FN family: spaCy's default
tokenizer treats slash-joined identifiers as a single token, and the
PhraseMatcher therefore never sees plain ``C`` or ``C++`` patterns
firing on these strings.

The fix is the *minimum-invasive* one: pre-process the text before the
spaCy ``Doc`` is built, inserting a separator inside slash-joined
tokens whose left and right sides are both known skills. We only
rewrite when the rewrite is safe — ``client/server`` stays untouched
because neither side is a recognised skill, and ``and/or``,
``yes/no``, ``http/https``, ``in/out`` all fall in the same
"don't touch" bucket.

This module is deliberately not a spaCy custom-tokenizer extension:

* spaCy tokenizer rules are global and would affect every downstream
  step, including the negation filter's regex windows.
* The current pipeline already exposes character-level spans
  (``char_start`` / ``char_end``) — keeping the rewrite at the
  pre-tokeniser stage is enough.

The segmenter preserves character indices of every retained character;
the inserted whitespace just shifts the right-side run by one
character. The validation pipeline does not rely on stable indices
across pre-processing — every match is re-extracted from the rewritten
text. Tests in ``tests/skill_extractor/test_slash_segmenter.py`` lock
the contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

# Match a maximal slash-joined run. Each side must be one "token-like"
# string — letters, digits, ``#``, ``+``, ``.``, ``_``, ``-`` — and the
# string must contain at least one slash that joins two such runs. We
# match the maximal run greedily so ``X/Y/Z`` is captured in one go.
_SLASH_RUN_RE = re.compile(r"(?<![\w])([\w.#+\-]+(?:/[\w.#+\-]+)+)(?![\w])")


@dataclass(slots=True)
class SlashSegmenter:
    """Insert separators inside slash-joined runs of known skill tokens.

    The lookup set is plain lower-cased strings. The pipeline supplies
    it once (after loading ESCO + custom + alias overlays) and reuses
    the segmenter across every extraction.
    """

    known_skills: frozenset[str]
    """Lower-cased surface forms that count as "known skills". Every
    side of a slash-joined run that matches one of these is considered
    safe to split."""

    separator: str = " / "
    """The character(s) inserted between the parts. ``" / "`` is
    sufficient for spaCy's default tokenizer to produce three tokens
    (``X``, ``/``, ``Y``) which the PhraseMatcher handles naturally."""

    def segment(self, text: str) -> str:
        """Return ``text`` with slash-joined runs replaced where safe.

        A run is rewritten only when **every** part of the run is in
        ``known_skills`` (case-insensitive). Mixed runs — like
        ``client/server`` or ``HTML/whatever`` — are left intact to
        avoid false positives.
        """
        if not text or "/" not in text:
            return text

        rewrites = 0

        def _replace(match: re.Match[str]) -> str:
            nonlocal rewrites
            run = match.group(1)
            parts = run.split("/")
            # All parts must be non-empty and in the known set.
            if any(not p for p in parts):
                return run
            if not all(p.lower() in self.known_skills for p in parts):
                return run
            rewrites += 1
            return self.separator.join(parts)

        rewritten = _SLASH_RUN_RE.sub(_replace, text)
        if rewrites:
            logger.debug(
                "slash_segmenter.rewrote",
                rewrites=rewrites,
                separator=self.separator,
            )
        return rewritten

    @classmethod
    def from_surface_lists(
        cls,
        *surface_lists: list[str] | set[str] | frozenset[str],
        separator: str = " / ",
    ) -> SlashSegmenter:
        """Build a segmenter from one or more iterables of surface forms.

        Concatenates the lists, lower-cases each entry, and freezes
        the result. Useful for assembling the known-skill set from the
        loaded :class:`~skill_extractor.models.EscoSkill` collection
        plus the tech aliases.
        """
        merged: set[str] = set()
        for lst in surface_lists:
            for s in lst:
                if isinstance(s, str) and s.strip():
                    merged.add(s.strip().lower())
        return cls(known_skills=frozenset(merged), separator=separator)
