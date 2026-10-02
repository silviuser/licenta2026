"""Phase A -- semantic skill linking.

The :class:`Linker` is the inference-time entry point of Module 3. It
takes Module 2's :class:`~skill_extractor.models.SkillExtractionResult`
and the CV's raw text, semantically re-scores every lexical candidate
against its ESCO concept embedding, and optionally expands the
candidate set by sliding-window retrieval against the ESCO embedding
index. The output is a typed
:class:`~skill_matcher.models.EnrichedSkillResult` consumed downstream
by Step 7's :class:`~skill_matcher.scorer.Scorer`.

Conceptual model (Step 6 brief, section 3.1)
--------------------------------------------
For each Module 2 :class:`~skill_extractor.models.SkillMatch`::

    sim = cos_sim(encoder.encode(anchor), encoder.encode(concept_text(uri)))
        if sim >= keep_threshold        -> "lexical_kept"    (boosted)
        if drop_threshold <= sim < keep -> "lexical_kept"    (demoted; ambiguous)
        if sim < drop_threshold         -> "lexical_dropped" (audit-only)

For each sliding window over CV text (size=30 tokens, stride=15)::

    For each (uri, sim) in top_k:
        if uri NOT already in lexical AND sim >= expansion_threshold:
            emit MatchCandidate(source="expansion", confidence=sim)

Band-assignment design (DECISIONS.md Step 6 amendment)
------------------------------------------------------
The Step 1 design treats the ambiguous band as ``"lexical_kept"`` with
demoted confidence, not as a separate source bucket. Two scalars cleanly
encode the information: ``source`` records *whether* semantic was
confident, ``confidence`` records *how* confident. Step 7's Scorer sees
a single boolean source partition (kept + expansion => positive,
dropped => audit-only). The :class:`LinkerStats` carries
``n_lexical_ambiguous`` as a derived counter for evaluation reports.

Confidence math (DECISIONS.md Step 6 amendment, defensible at viva)
-------------------------------------------------------------------
Boost (``sim >= keep_threshold``)::

    new = clamp(0.5 * orig + 0.5 * sim, 0.0, 1.0)

Equal-weight blend - agreement of lexical + semantic gets >= either
individual signal.

Demote (``drop_threshold <= sim < keep_threshold``)::

    new = orig * (sim / keep_threshold)

Linear in ``sim``; at ``sim == keep_threshold`` returns exactly
``orig`` (continuity at the band boundary).

Dropped (``sim < drop_threshold``)::

    new = orig

Preserved verbatim; the source marker tells Step 7 to ignore the
candidate.

Expansion (semantic-only)::

    new = sim

Raw cosine; expansion has no lexical confirmation, so the encoder
similarity is the only evidence. Step 8 may add a discount factor.

Determinism (DECISIONS.md D10)
------------------------------
Two consecutive ``link()`` calls on identical inputs produce a
byte-identical :class:`EnrichedSkillResult`. Tie-breaking is fixed:
sort within source bucket by ``(-confidence, skill_uri,
cv_evidence_offset)``; concatenate buckets in the fixed order
``kept -> dropped -> expansion``. No ``time.time()``, no
``os.urandom()``, no hidden state.

Encoder-agnostic by design
--------------------------
The Linker takes an :class:`Encoder` Protocol instance - it does NOT
load the model itself. Tests use :class:`MockEncoder`; production uses
:class:`SentenceTransformerEncoder` pointed at whatever checkpoint
``SkillMatcherConfig.finetuned_model_path`` resolves to. When Step 5 is
re-done with a larger training corpus, the only Linker-side change is
constructing a different encoder.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import structlog

from skill_extractor.models import SkillExtractionResult, SkillMatch
from skill_matcher.esco_index import format_concept_text
from skill_matcher.esco_loader import EscoConcept
from skill_matcher.models import EnrichedSkillResult, MatchCandidate
from skill_matcher.sliding_window import generate_windows
from skill_matcher.training_data import ANCHOR_HARD_CAP_CHARS

if TYPE_CHECKING:
    from skill_matcher.config import SkillMatcherConfig
    from skill_matcher.encoder import Encoder
    from skill_matcher.esco_index import EscoIndex

logger = structlog.get_logger(__name__)


# Top-k retrievals per sliding window during expansion. Matches Step 4
# baseline's default; expansion candidates are then filtered against
# ``expansion_threshold`` so this only caps how many URIs we *consider*
# per window - not how many we ultimately emit.
_EXPANSION_TOP_K = 5

# Maximum length of an expansion candidate's ``cv_evidence_text``. The
# field is shown directly in the recruiter UI; longer than this and the
# UI line-wraps awkwardly. The full window slice is still available via
# the ``cv_evidence_offset`` field so nothing is lost.
_EXPANSION_EVIDENCE_CHAR_LIMIT = 100


@dataclass(frozen=True, slots=True)
class _SpanWork:
    """One unit of re-scoring work: a Module 2 span + its anchor text.

    Module-private. Materialising the work list up front lets the
    Linker batch-encode every anchor in a single
    :meth:`Encoder.encode` call rather than paying the per-call
    overhead N times.
    """

    match: SkillMatch
    span: tuple[int, int]
    anchor_text: str


@dataclass(frozen=True, slots=True)
class LinkerStats:
    """Diagnostic counters returned alongside an :class:`EnrichedSkillResult`."""

    n_lexical_kept: int
    n_lexical_ambiguous: int
    n_lexical_dropped: int
    n_expansion: int
    n_windows: int
    n_unknown_uris: int
    elapsed_seconds: float


class Linker:
    """Semantic skill linker (Phase A). Encoder-agnostic by design."""

    def __init__(
        self,
        config: SkillMatcherConfig,
        encoder: Encoder,
        index: EscoIndex,
        concepts_by_uri: dict[str, EscoConcept],
        *,
        concept_text_builder: Callable[[EscoConcept], str] | None = None,
    ) -> None:
        self.config = config
        self.encoder = encoder
        self.index = index
        self.concepts_by_uri = concepts_by_uri
        self._concept_text_builder: Callable[[EscoConcept], str] = (
            concept_text_builder
            if concept_text_builder is not None
            else _default_concept_text_builder
        )

        if not (
            0.0
            <= config.drop_threshold
            <= config.keep_threshold
            <= config.expansion_threshold
            <= 1.0
        ):
            raise ValueError(
                "Threshold band ordering violated: require "
                "0.0 <= drop_threshold <= keep_threshold <= "
                "expansion_threshold <= 1.0; got "
                f"drop={config.drop_threshold}, "
                f"keep={config.keep_threshold}, "
                f"expansion={config.expansion_threshold}."
            )

    def link(
        self,
        cv_id: str,
        cv_text: str,
        lexical: SkillExtractionResult,
    ) -> tuple[EnrichedSkillResult, LinkerStats]:
        """Run Phase A -- skill linking. Deterministic, encoder-agnostic."""
        from skill_matcher import __version__

        t0 = time.monotonic()

        kept_candidates, ambiguous_subcount, dropped_candidates, n_unknown = (
            self._rescore_candidates(lexical, cv_text)
        )

        already_present: set[str] = {m.esco_uri for m in lexical.skills}
        expansion_candidates, n_windows = self._expand_via_retrieval(
            cv_text, already_present
        )

        all_candidates = (
            kept_candidates + dropped_candidates + expansion_candidates
        )

        model_tag = getattr(self.encoder, "model_name", None) or type(
            self.encoder
        ).__name__
        pipeline_version = f"skill_matcher@{__version__}+encoder={model_tag}"

        result = EnrichedSkillResult(
            cv_id=cv_id,
            candidates=all_candidates,
            detected_language=lexical.language,
            pipeline_version=pipeline_version,
        )

        elapsed = time.monotonic() - t0
        stats = LinkerStats(
            n_lexical_kept=len(kept_candidates),
            n_lexical_ambiguous=ambiguous_subcount,
            n_lexical_dropped=len(dropped_candidates),
            n_expansion=len(expansion_candidates),
            n_windows=n_windows,
            n_unknown_uris=n_unknown,
            elapsed_seconds=elapsed,
        )

        logger.info(
            "linker.link.complete",
            cv_id=cv_id,
            cv_chars=len(cv_text),
            n_lexical_in=len(lexical.skills),
            n_lexical_kept=stats.n_lexical_kept,
            n_lexical_ambiguous=stats.n_lexical_ambiguous,
            n_lexical_dropped=stats.n_lexical_dropped,
            n_expansion=stats.n_expansion,
            n_windows=stats.n_windows,
            n_unknown_uris=stats.n_unknown_uris,
            elapsed_seconds=round(elapsed, 3),
        )

        return result, stats

    def _rescore_candidates(
        self,
        lexical: SkillExtractionResult,
        cv_text: str,
    ) -> tuple[list[MatchCandidate], int, list[MatchCandidate], int]:
        """Re-score every Module 2 candidate; emit one MatchCandidate per (uri, span)."""
        cfg = self.config

        work: list[_SpanWork] = []
        n_unknown_uris = 0
        unique_uris_ordered: list[str] = []
        seen_uris: set[str] = set()
        skipped_uris: set[str] = set()

        for match in lexical.skills:
            uri = match.esco_uri
            if uri not in self.concepts_by_uri:
                if uri not in skipped_uris:
                    logger.warning(
                        "linker.unknown_uri",
                        uri=uri,
                        matched_text=match.matched_text,
                        section=match.section,
                    )
                    skipped_uris.add(uri)
                n_unknown_uris += 1
                continue

            if uri not in seen_uris:
                unique_uris_ordered.append(uri)
                seen_uris.add(uri)

            for span in match.spans:
                anchor_text = _build_anchor_text(cv_text, span)
                work.append(
                    _SpanWork(match=match, span=span, anchor_text=anchor_text)
                )

        if not work:
            return [], 0, [], n_unknown_uris

        anchor_texts = [w.anchor_text for w in work]
        concept_texts = [
            self._concept_text_builder(self.concepts_by_uri[uri])
            for uri in unique_uris_ordered
        ]

        anchor_embs = self.encoder.encode(anchor_texts, batch_size=32)
        concept_embs = self.encoder.encode(concept_texts, batch_size=32)

        uri_to_row: dict[str, int] = {
            uri: i for i, uri in enumerate(unique_uris_ordered)
        }

        kept_candidates: list[MatchCandidate] = []
        dropped_candidates: list[MatchCandidate] = []
        ambiguous_subcount = 0

        for i, w in enumerate(work):
            uri = w.match.esco_uri
            anchor_vec = anchor_embs[i]
            concept_vec = concept_embs[uri_to_row[uri]]
            sim = float(np.dot(anchor_vec, concept_vec))
            sim = max(0.0, min(1.0, sim))

            evidence_text = _section_evidence_text(
                w.match.matched_text, w.match.section
            )

            if sim >= cfg.keep_threshold:
                candidate = MatchCandidate(
                    skill_uri=uri,
                    skill_label=w.match.preferred_label,
                    confidence=self._boost_confidence(w.match.confidence, sim),
                    source="lexical_kept",
                    cv_evidence_text=evidence_text,
                    cv_evidence_offset=w.span,
                    similarity_score=sim,
                    lexical_confidence=w.match.confidence,
                )
                kept_candidates.append(candidate)
            elif sim >= cfg.drop_threshold:
                candidate = MatchCandidate(
                    skill_uri=uri,
                    skill_label=w.match.preferred_label,
                    confidence=self._demote_confidence(w.match.confidence, sim),
                    source="lexical_kept",
                    cv_evidence_text=evidence_text,
                    cv_evidence_offset=w.span,
                    similarity_score=sim,
                    lexical_confidence=w.match.confidence,
                )
                kept_candidates.append(candidate)
                ambiguous_subcount += 1
            else:
                candidate = MatchCandidate(
                    skill_uri=uri,
                    skill_label=w.match.preferred_label,
                    confidence=w.match.confidence,
                    source="lexical_dropped",
                    cv_evidence_text=evidence_text,
                    cv_evidence_offset=w.span,
                    similarity_score=sim,
                    lexical_confidence=w.match.confidence,
                )
                dropped_candidates.append(candidate)

        kept_candidates.sort(key=_candidate_sort_key)
        dropped_candidates.sort(key=_candidate_sort_key)
        return (
            kept_candidates,
            ambiguous_subcount,
            dropped_candidates,
            n_unknown_uris,
        )

    def _expand_via_retrieval(
        self,
        cv_text: str,
        already_present: set[str],
    ) -> tuple[list[MatchCandidate], int]:
        """Sliding-window retrieval -> expansion candidates."""
        cfg = self.config
        if not cfg.enable_expansion:
            return [], 0

        windows = generate_windows(
            cv_text,
            window_size_tokens=cfg.expansion_window_size,
            stride_tokens=cfg.expansion_window_stride,
        )
        if not windows:
            return [], 0

        window_texts = [w.text for w in windows]
        window_embs = self.encoder.encode(window_texts, batch_size=32)
        per_window_topk = self.index.query_batch(
            window_embs, top_k=_EXPANSION_TOP_K
        )

        best_per_uri: dict[str, tuple[float, int]] = {}
        for window_idx, hits in enumerate(per_window_topk):
            for uri, sim in hits:
                if uri in already_present:
                    continue
                prev = best_per_uri.get(uri)
                if prev is None or sim > prev[0]:
                    best_per_uri[uri] = (sim, window_idx)

        expansion: list[MatchCandidate] = []
        for uri, (sim, window_idx) in best_per_uri.items():
            if sim < cfg.expansion_threshold:
                continue
            concept = self.concepts_by_uri.get(uri)
            if concept is None:
                logger.warning(
                    "linker.expansion_unknown_uri",
                    uri=uri,
                    similarity=sim,
                )
                continue

            w = windows[window_idx]
            evidence_text = w.text.strip()
            if len(evidence_text) > _EXPANSION_EVIDENCE_CHAR_LIMIT:
                evidence_text = evidence_text[:_EXPANSION_EVIDENCE_CHAR_LIMIT]
            if not evidence_text:
                evidence_text = (w.text[:1] if w.text else "") or "?"

            expansion.append(
                MatchCandidate(
                    skill_uri=uri,
                    skill_label=concept.pref_label,
                    confidence=float(sim),
                    source="expansion",
                    cv_evidence_text=evidence_text,
                    cv_evidence_offset=(w.start, w.end),
                    similarity_score=float(sim),
                    lexical_confidence=None,
                )
            )

        expansion.sort(key=_candidate_sort_key)
        return expansion, len(windows)

    def _boost_confidence(self, original: float, sim: float) -> float:
        """Boost: equal-weight blend, clamped to ``[0.0, 1.0]``."""
        return max(0.0, min(1.0, 0.5 * original + 0.5 * sim))

    def _demote_confidence(self, original: float, sim: float) -> float:
        """Demote: linear in ``sim``; returns ``original`` at keep boundary."""
        keep = self.config.keep_threshold
        if keep <= 0.0:
            return original
        scaled = original * (sim / keep)
        return max(0.0, min(1.0, scaled))


def _default_concept_text_builder(concept: EscoConcept) -> str:
    """Default concept-text formatter -- bounded-a (DECISIONS.md 2026-05-16)."""
    return format_concept_text(concept, "bounded-a")


def _build_anchor_text(cv_text: str, span: tuple[int, int]) -> str:
    """Inference-time anchor for one Module 2 span (Q1 default)."""
    start, end = span
    lo = max(0, start - 50)
    hi = min(len(cv_text), end + 50)
    text = cv_text[lo:hi].strip()
    if len(text) > ANCHOR_HARD_CAP_CHARS:
        text = text[:ANCHOR_HARD_CAP_CHARS]
    if not text:
        text = cv_text[start:end].strip() or "?"
    return text


# Non-informative section sentinels. These carry no useful signal for a
# recruiter (``other`` is the catch-all bucket assigned to free-text / JD prose;
# ``unknown`` is the expansion-candidate fallback), so they are NOT appended to
# the surface form — only real sections (``skills``, ``experience``, …) are.
_NONINFORMATIVE_SECTIONS = frozenset({"", "other", "unknown"})


def _section_evidence_text(matched_text: str, section: str) -> str:
    """Compose the UI-facing evidence string for a lexical candidate.

    The ``(section)`` tag is appended only when the section is
    informative. Non-informative sentinels (``other`` / ``unknown``)
    and blank sections are omitted so the surface form stays clean.
    """
    surface = (matched_text or "?").strip() or "?"
    if (section or "").strip().lower() in _NONINFORMATIVE_SECTIONS:
        return surface
    return f"{surface} ({section})"


def _candidate_sort_key(
    cand: MatchCandidate,
) -> tuple[float, str, int, int]:
    """Sort key: (-confidence, skill_uri, off_start, off_end)."""
    off = cand.cv_evidence_offset or (-1, -1)
    return (-cand.confidence, cand.skill_uri, off[0], off[1])


__all__ = [
    "Linker",
    "LinkerStats",
]
