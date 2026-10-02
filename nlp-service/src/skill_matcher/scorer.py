"""Phase B -- CV <-> JD scoring (Step 7 deliverable; Step 8 additive).

The :class:`Scorer` consumes an
:class:`~skill_matcher.models.EnrichedSkillResult` (one CV's Linker
output) and a ``list[JDRequirement]`` (one JD's parsed requirements)
and produces a final :class:`~skill_matcher.models.MatchResult` whose
``overall_score`` is the single number the recruiter UI shows.

Step 8 adds one **additive** public method
:meth:`Scorer.score_to_intermediates`. It returns the per-requirement
``(req_conf, cand_conf, uri_similarity)`` tuples BEFORE the
per-requirement keep-threshold gate, so the threshold-tuning grid
search in :mod:`skill_matcher.tuning` can re-aggregate at any
``per_requirement_keep_threshold`` and ``required_weight`` combo
without re-encoding. ``score()`` is byte-identical to the Step 7
release; the new method shares the same internal helpers
(``_filter_and_dedup_candidates``, ``_resolve_requirements_batched``,
``_encode_uris``, ``_semantic_fallback``).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np
import structlog

from skill_matcher.esco_index import format_concept_text
from skill_matcher.models import (
    EnrichedSkillResult,
    JDRequirement,
    MatchCandidate,
    MatchedRequirement,
    MatchResult,
)
from skill_matcher.tuning import CellIntermediate, ReqIntermediate

if TYPE_CHECKING:
    from skill_matcher.config import SkillMatcherConfig
    from skill_matcher.encoder import Encoder
    from skill_matcher.esco_index import EscoIndex
    from skill_matcher.esco_loader import EscoConcept

logger = structlog.get_logger(__name__)


# Aggregation weights -- see DECISIONS.md Step 7 amendment for the
# 0.8/0.2 rationale (HR-literature convention; Step 8 may tune via the
# ``required_weight`` knob on the tuning grid -- this constant is the
# legacy default used by ``Scorer.score`` and is untouched by Step 8).
_REQUIRED_WEIGHT: float = 0.8
_NICE_WEIGHT: float = 0.2


@dataclass(frozen=True, slots=True)
class ScorerStats:
    """Diagnostic counters returned alongside a :class:`MatchResult`."""

    n_candidates_filtered: int
    n_candidates_after_dedup: int
    n_req_resolved_online: int
    n_req_matched_exact: int
    n_req_matched_semantic: int
    n_req_unmatched: int
    n_required_total: int
    n_nice_total: int
    elapsed_seconds: float


def _default_clock() -> datetime:
    return datetime.now(tz=UTC)


def _default_concept_text(concept: EscoConcept) -> str:
    return format_concept_text(concept, "bounded-a")


def _source_priority(source: str) -> int:
    return 0 if source == "lexical_kept" else 1


class Scorer:
    """CV <-> JD scoring engine (Phase B)."""

    def __init__(
        self,
        config: SkillMatcherConfig,
        encoder: Encoder,
        index: EscoIndex,
        concepts_by_uri: dict[str, EscoConcept],
        *,
        concept_text_builder: Callable[[EscoConcept], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        pipeline_version: str | None = None,
    ) -> None:
        self.config = config
        self.encoder = encoder
        self.index = index
        self.concepts_by_uri = concepts_by_uri
        self._concept_text_builder: Callable[[EscoConcept], str] = (
            concept_text_builder
            if concept_text_builder is not None
            else _default_concept_text
        )
        self._clock: Callable[[], datetime] = (
            clock if clock is not None else _default_clock
        )
        self._pipeline_version: str = (
            pipeline_version
            if pipeline_version is not None
            else self._build_pipeline_version()
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        enriched: EnrichedSkillResult,
        jd_id: str,
        requirements: list[JDRequirement],
    ) -> tuple[MatchResult, ScorerStats]:
        """Aggregate per-requirement matches into a :class:`MatchResult`."""
        t0 = time.monotonic()

        cv_by_uri = self._filter_and_dedup_candidates(enriched)
        n_filtered = self._count_after_source_filter(enriched)
        n_dedup = len(cv_by_uri)

        resolved_requirements, n_resolved_online = (
            self._resolve_requirements_batched(requirements)
        )

        req_uri_embs = self._encode_uris(
            [r.skill_uri for r in resolved_requirements if r.skill_uri is not None]
        )
        cv_uri_list = sorted(cv_by_uri.keys())
        cv_uri_embs = self._encode_uris(cv_uri_list)
        cv_uri_to_row: dict[str, int] = {
            uri: i for i, uri in enumerate(cv_uri_list)
        }

        req_uri_to_row: dict[int, int] = {}
        row = 0
        for i, req in enumerate(resolved_requirements):
            if req.skill_uri is not None:
                req_uri_to_row[i] = row
                row += 1

        matched_required: list[MatchedRequirement] = []
        matched_nice: list[MatchedRequirement] = []
        unmatched_required: list[JDRequirement] = []
        unmatched_nice: list[JDRequirement] = []
        n_exact = 0
        n_semantic = 0

        for i, req in enumerate(resolved_requirements):
            matched, was_exact, was_semantic = self._match_one_requirement(
                req=req,
                cv_by_uri=cv_by_uri,
                req_emb_row=req_uri_to_row.get(i),
                req_uri_embs=req_uri_embs,
                cv_uri_embs=cv_uri_embs,
                cv_uri_to_row=cv_uri_to_row,
            )
            if matched is not None:
                if was_exact:
                    n_exact += 1
                if was_semantic:
                    n_semantic += 1
                if req.importance == "required":
                    matched_required.append(matched)
                else:
                    matched_nice.append(matched)
            else:
                if req.importance == "required":
                    unmatched_required.append(req)
                else:
                    unmatched_nice.append(req)

        required_total = sum(
            1 for r in resolved_requirements if r.importance == "required"
        )
        nice_total = sum(
            1 for r in resolved_requirements if r.importance == "nice_to_have"
        )
        overall, req_cov, nice_cov = self._aggregate(
            matched_required=matched_required,
            matched_nice=matched_nice,
            required_total=required_total,
            nice_total=nice_total,
        )

        result = MatchResult(
            cv_id=enriched.cv_id,
            jd_id=jd_id,
            overall_score=overall,
            required_coverage=req_cov,
            nice_to_have_coverage=nice_cov,
            matched_required=matched_required,
            matched_nice_to_have=matched_nice,
            unmatched_required=unmatched_required,
            unmatched_nice_to_have=unmatched_nice,
            timestamp=self._clock(),
            pipeline_version=self._pipeline_version,
        )

        n_unmatched = len(unmatched_required) + len(unmatched_nice)
        elapsed = time.monotonic() - t0
        stats = ScorerStats(
            n_candidates_filtered=n_filtered,
            n_candidates_after_dedup=n_dedup,
            n_req_resolved_online=n_resolved_online,
            n_req_matched_exact=n_exact,
            n_req_matched_semantic=n_semantic,
            n_req_unmatched=n_unmatched,
            n_required_total=required_total,
            n_nice_total=nice_total,
            elapsed_seconds=elapsed,
        )

        return result, stats

    def score_to_intermediates(
        self,
        enriched: EnrichedSkillResult,
        jd_id: str,
        requirements: list[JDRequirement],
    ) -> CellIntermediate:
        """Extract per-requirement ``(req_conf, cand_conf, uri_sim)`` tuples.

        Step 8 (threshold tuning) only. Runs the same setup work as
        :meth:`score` but STOPS before the per-requirement keep-threshold
        gate and the aggregation step. The returned
        :class:`~skill_matcher.tuning.CellIntermediate` carries every
        requirement's three multiplicative factors so the tuning grid
        search can re-apply the gate at any threshold and re-aggregate
        with any required / nice weighting WITHOUT re-encoding.

        The Scorer's ``keep_threshold`` semantic-fallback gate IS still
        applied: a fallback below ``keep_threshold`` yields
        ``(cand_conf=0.0, uri_sim=0.0)``, equivalent to "unmatched".
        ``keep_threshold`` is a Tier 2 knob (Step 8 brief §2.6) --
        moving it requires re-encoding, which is the CLI driver's job,
        not this method's.

        Behavioural equivalence: aggregating the result via
        :func:`tuning.aggregate_from_intermediates` with
        ``per_requirement_keep_threshold = self.config.per_requirement_keep_threshold``
        and ``required_weight = 0.8`` produces the same
        ``overall_score`` as :meth:`score`.
        """
        cv_by_uri = self._filter_and_dedup_candidates(enriched)
        resolved_requirements, _n_resolved_online = (
            self._resolve_requirements_batched(requirements)
        )
        req_uri_embs = self._encode_uris(
            [r.skill_uri for r in resolved_requirements if r.skill_uri is not None]
        )
        cv_uri_list = sorted(cv_by_uri.keys())
        cv_uri_embs = self._encode_uris(cv_uri_list)
        cv_uri_to_row: dict[str, int] = {
            uri: i for i, uri in enumerate(cv_uri_list)
        }

        req_uri_to_row: dict[int, int] = {}
        row = 0
        for i, req in enumerate(resolved_requirements):
            if req.skill_uri is not None:
                req_uri_to_row[i] = row
                row += 1

        intermediates: list[ReqIntermediate] = []
        for i, req in enumerate(resolved_requirements):
            cand_conf, uri_sim = self._collect_match_factors(
                req=req,
                cv_by_uri=cv_by_uri,
                req_emb_row=req_uri_to_row.get(i),
                req_uri_embs=req_uri_embs,
                cv_uri_embs=cv_uri_embs,
                cv_uri_to_row=cv_uri_to_row,
            )
            intermediates.append(
                ReqIntermediate(
                    req_text=req.text,
                    importance=req.importance,
                    req_confidence=float(req.confidence),
                    candidate_confidence=float(cand_conf),
                    uri_similarity=float(uri_sim),
                )
            )

        return CellIntermediate(
            cv_id=enriched.cv_id,
            jd_id=jd_id,
            requirements=tuple(intermediates),
            linker_thresholds=(
                self.config.drop_threshold,
                self.config.keep_threshold,
                self.config.expansion_threshold,
            ),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_pipeline_version(self) -> str:
        from skill_matcher import __version__

        tag = getattr(self.encoder, "model_name", None) or type(
            self.encoder
        ).__name__
        return f"skill_matcher@{__version__}+encoder={tag}"

    def _count_after_source_filter(
        self, enriched: EnrichedSkillResult
    ) -> int:
        return sum(
            1
            for c in enriched.candidates
            if c.source in ("lexical_kept", "expansion")
        )

    def _filter_and_dedup_candidates(
        self, enriched: EnrichedSkillResult
    ) -> dict[str, MatchCandidate]:
        best_by_uri: dict[str, MatchCandidate] = {}
        for cand in enriched.candidates:
            # REWORK-EVAL (2026-06-08): also admit high-confidence ``lexical_dropped``
            # candidates. The Linker drops a *lexically* matched skill when its
            # semantic similarity to the (sometimes weakly-embedded custom) ESCO
            # concept is below drop_threshold — but a clean lexical hit such as
            # "Docker"/"Git" (lexical confidence ~1.0) is real and must remain
            # matchable. lexical_kept / expansion still win during dedup via
            # _source_priority.
            allowed = cand.source in ("lexical_kept", "expansion") or (
                cand.source == "lexical_dropped" and cand.confidence >= 0.6
            )
            if not allowed:
                continue
            current = best_by_uri.get(cand.skill_uri)
            if current is None or self._dedup_prefers(cand, current):
                best_by_uri[cand.skill_uri] = cand
                if current is not None:
                    logger.debug(
                        "scorer.dedup_replaced",
                        uri=cand.skill_uri,
                        kept_conf=cand.confidence,
                        kept_sim=cand.similarity_score,
                        kept_source=cand.source,
                        kept_offset=cand.cv_evidence_offset,
                        replaced_conf=current.confidence,
                        replaced_sim=current.similarity_score,
                        replaced_source=current.source,
                        replaced_offset=current.cv_evidence_offset,
                    )
        return best_by_uri

    @staticmethod
    def _dedup_prefers(cand: MatchCandidate, current: MatchCandidate) -> bool:
        cand_offset = cand.cv_evidence_offset or (-1, -1)
        cur_offset = current.cv_evidence_offset or (-1, -1)
        cand_key = (
            -cand.confidence,
            -cand.similarity_score,
            _source_priority(cand.source),
            cand_offset[0],
            cand_offset[1],
        )
        cur_key = (
            -current.confidence,
            -current.similarity_score,
            _source_priority(current.source),
            cur_offset[0],
            cur_offset[1],
        )
        return cand_key < cur_key

    def _resolve_requirements_batched(
        self, requirements: list[JDRequirement]
    ) -> tuple[list[JDRequirement], int]:
        unresolved_indices: list[int] = []
        unresolved_texts: list[str] = []
        for i, req in enumerate(requirements):
            if req.skill_uri is None:
                unresolved_indices.append(i)
                unresolved_texts.append(req.text)

        if not unresolved_indices:
            return list(requirements), 0

        embs = self.encoder.encode(unresolved_texts, batch_size=32)
        resolved: list[JDRequirement] = list(requirements)

        for slot, i in enumerate(unresolved_indices):
            hits = self.index.query(embs[slot], top_k=1)
            if not hits:
                logger.warning(
                    "scorer.requirement_resolution_empty",
                    text=requirements[i].text,
                )
                continue
            uri, sim = hits[0]
            concept = self.concepts_by_uri.get(uri)
            label = concept.pref_label if concept is not None else None
            base_conf = requirements[i].confidence
            new_conf = base_conf if base_conf > 0.0 else float(sim)
            resolved[i] = requirements[i].model_copy(
                update={
                    "skill_uri": uri,
                    "skill_label": label,
                    "confidence": new_conf,
                }
            )

        return resolved, len(unresolved_indices)

    def _encode_uris(self, uris: list[str]) -> np.ndarray:
        if not uris:
            return np.zeros((0, self.encoder.embedding_dim), dtype=np.float32)

        texts: list[str] = []
        zero_rows: list[int] = []
        for i, uri in enumerate(uris):
            concept = self.concepts_by_uri.get(uri)
            if concept is None:
                logger.warning("scorer.unknown_uri_in_encode", uri=uri)
                texts.append("")
                zero_rows.append(i)
                continue
            texts.append(self._concept_text_builder(concept))

        embs = self.encoder.encode(texts, batch_size=32)
        if zero_rows:
            for r in zero_rows:
                embs[r] = np.zeros(self.encoder.embedding_dim, dtype=np.float32)
        return embs

    def _match_one_requirement(
        self,
        *,
        req: JDRequirement,
        cv_by_uri: dict[str, MatchCandidate],
        req_emb_row: int | None,
        req_uri_embs: np.ndarray,
        cv_uri_embs: np.ndarray,
        cv_uri_to_row: dict[str, int],
    ) -> tuple[MatchedRequirement | None, bool, bool]:
        # Path 1: exact URI match.
        if req.skill_uri is not None and req.skill_uri in cv_by_uri:
            cand = cv_by_uri[req.skill_uri]
            uri_sim = 1.0
            # REWORK-EVAL : uri_sim already gated entry to this branch
            # (exact URI, or semantic >= keep_threshold). The *score* of a satisfied
            # requirement is how confident we are the CV actually holds the skill
            # (cand.confidence). Multiplying by uri_sim again double-penalised genuine
            # cross-lingual / synonym matches (e.g. RO CV skill vs EN JD term).
            match_score = cand.confidence
            if match_score >= self.config.per_requirement_keep_threshold:
                logger.debug(
                    "scorer.req_matched_exact",
                    req_text=req.text,
                    uri=req.skill_uri,
                    match_score=match_score,
                )
                return (
                    MatchedRequirement(
                        requirement=req,
                        cv_candidate=cand,
                        match_score=float(match_score),
                    ),
                    True,
                    False,
                )

        # Path 2: semantic fallback.
        fallback = self._semantic_fallback(
            req=req,
            cv_by_uri=cv_by_uri,
            req_emb_row=req_emb_row,
            req_uri_embs=req_uri_embs,
            cv_uri_embs=cv_uri_embs,
            cv_uri_to_row=cv_uri_to_row,
        )
        if fallback is not None:
            cand, uri_sim = fallback
            # REWORK-EVAL : uri_sim already gated entry to this branch
            # (exact URI, or semantic >= keep_threshold). The *score* of a satisfied
            # requirement is how confident we are the CV actually holds the skill
            # (cand.confidence). Multiplying by uri_sim again double-penalised genuine
            # cross-lingual / synonym matches (e.g. RO CV skill vs EN JD term).
            match_score = cand.confidence
            if match_score >= self.config.per_requirement_keep_threshold:
                logger.debug(
                    "scorer.req_matched_semantic",
                    req_text=req.text,
                    req_uri=req.skill_uri,
                    cand_uri=cand.skill_uri,
                    uri_sim=uri_sim,
                    match_score=match_score,
                )
                return (
                    MatchedRequirement(
                        requirement=req,
                        cv_candidate=cand,
                        match_score=float(match_score),
                    ),
                    False,
                    True,
                )

        logger.debug(
            "scorer.req_unmatched",
            req_text=req.text,
            req_uri=req.skill_uri,
            importance=req.importance,
        )
        return None, False, False

    def _collect_match_factors(
        self,
        *,
        req: JDRequirement,
        cv_by_uri: dict[str, MatchCandidate],
        req_emb_row: int | None,
        req_uri_embs: np.ndarray,
        cv_uri_embs: np.ndarray,
        cv_uri_to_row: dict[str, int],
    ) -> tuple[float, float]:
        """Return ``(candidate_confidence, uri_similarity)`` pre-gate.

        Step 8 helper for :meth:`score_to_intermediates`. Walks the
        same exact-vs-semantic cascade as :meth:`_match_one_requirement`
        but returns the raw match factors instead of a gated
        :class:`MatchedRequirement`. Unmatched -> ``(0.0, 0.0)``.
        """
        if req.skill_uri is not None and req.skill_uri in cv_by_uri:
            cand = cv_by_uri[req.skill_uri]
            return float(cand.confidence), 1.0

        fallback = self._semantic_fallback(
            req=req,
            cv_by_uri=cv_by_uri,
            req_emb_row=req_emb_row,
            req_uri_embs=req_uri_embs,
            cv_uri_embs=cv_uri_embs,
            cv_uri_to_row=cv_uri_to_row,
        )
        if fallback is not None:
            cand, uri_sim = fallback
            return float(cand.confidence), float(uri_sim)

        return 0.0, 0.0

    def _semantic_fallback(
        self,
        *,
        req: JDRequirement,
        cv_by_uri: dict[str, MatchCandidate],
        req_emb_row: int | None,
        req_uri_embs: np.ndarray,
        cv_uri_embs: np.ndarray,
        cv_uri_to_row: dict[str, int],
    ) -> tuple[MatchCandidate, float] | None:
        if req_emb_row is None or not cv_by_uri:
            return None
        if cv_uri_embs.shape[0] == 0 or req_uri_embs.shape[0] == 0:
            return None

        req_vec = req_uri_embs[req_emb_row]
        sims = cv_uri_embs @ req_vec

        best_uri: str | None = None
        best_sim: float = -np.inf
        for uri, row in cv_uri_to_row.items():
            sim = float(sims[row])
            if sim > best_sim or (sim == best_sim and (best_uri is None or uri < best_uri)):
                best_sim = sim
                best_uri = uri

        if best_uri is None:
            return None

        best_sim = max(0.0, min(1.0, best_sim))

        if best_sim < self.config.keep_threshold:
            return None

        return cv_by_uri[best_uri], best_sim

    def _aggregate(
        self,
        *,
        matched_required: list[MatchedRequirement],
        matched_nice: list[MatchedRequirement],
        required_total: int,
        nice_total: int,
    ) -> tuple[float, float, float]:
        if required_total == 0 and nice_total == 0:
            logger.error("scorer.jd_has_no_requirements_at_all")
            return 0.0, 0.0, 0.0

        if required_total > 0:
            required_score = (
                sum(m.match_score for m in matched_required) / required_total
            )
        else:
            required_score = 0.0

        if nice_total > 0:
            nice_score = (
                sum(m.match_score for m in matched_nice) / nice_total
            )
        else:
            nice_score = 0.0

        if required_total == 0:
            logger.warning(
                "scorer.jd_has_no_required",
                nice_total=nice_total,
                msg=(
                    "Falling back to nice_weight=1.0; "
                    "JDs with no required skills are a data-quality smell."
                ),
            )
            overall = nice_score
        else:
            # Step 8 wiring: the required/nice weighting reads from
            # ``self.config.required_weight`` so the locked default actually
            # reaches the Scorer. The module-level ``_REQUIRED_WEIGHT`` /
            # ``_NICE_WEIGHT`` constants are kept only as the legacy
            # default value that ``SkillMatcherConfig.required_weight``
            # inherits when callers don't pin it; nothing in the runtime
            # path reads them.
            r_w = self.config.required_weight
            n_w = 1.0 - r_w
            overall = r_w * required_score + n_w * nice_score

        overall = max(0.0, min(1.0, overall))

        required_coverage = (
            len(matched_required) / required_total if required_total > 0 else 0.0
        )
        nice_coverage = (
            len(matched_nice) / nice_total if nice_total > 0 else 0.0
        )
        return overall, required_coverage, nice_coverage


__all__ = ["Scorer", "ScorerStats"]
