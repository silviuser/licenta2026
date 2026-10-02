"""Zero-shot baseline evaluator for the Module 3 expansion stack.

Runs the encoder + ESCO index against the held-out eval CVs and
reports retrieval metrics versus the gold skill labels. The number
this produces is the floor Step 5 fine-tuning must beat to justify
the AI artefact in the thesis.

Pipeline (per CV)
-----------------
1. Module 1 ``ExtractionPipeline.process(pdf_path)`` → full CV text.
2. Module 2 ``SkillExtractor.extract(result)`` → lexical control
   (set of ESCO URIs Module 2 produced).
3. Sliding-window tokenise the CV text → list of windows.
4. Batch-encode all window texts.
5. ``EscoIndex.query_batch(...)`` → per-window top-k retrievals.
6. Aggregate: for each ESCO URI, take the maximum similarity over
   any window that retrieved it. Apply the configured threshold to
   produce the "semantic" URI set. Top-k variants are reported.

Metrics (per CV)
----------------
* **Gold set views** — two are emitted per CV (Q4 decision):
    - ``high`` — only ``confidence_expected: high`` labels.
    - ``high+medium`` — both confidence buckets.
* Lexical (Module 2) P/R/F1 against each view — *control*.
* Semantic (Module 3 expansion stack) P/R/F1 against each view at
  the chosen threshold.
* Ensemble (lexical union semantic) P/R/F1 against each view — the
  *ceiling* for Module 3.

Aggregate metrics
-----------------
* **Macro** — unweighted mean of per-CV scores. Robust to outliers.
* **Micro** — global pool of (TP, FP, FN) across CVs. Reflects
  recruiter-realistic performance on a corpus.

The headline number reported in :class:`BaselineMetrics.macro_f1`
uses the ``high+medium`` gold view at the chosen threshold (Q4).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import structlog

from cv_extractor.exceptions import CVExtractorError
from cv_extractor.pipeline import ExtractionPipeline
from skill_extractor.exceptions import NotACVError
from skill_extractor.models import SkillExtractionResult
from skill_extractor.pipeline import SkillExtractor
from skill_matcher.encoder import Encoder
from skill_matcher.esco_index import EscoIndex
from skill_matcher.eval_corpus import CVLabels, EvalCorpus, load_eval_corpus
from skill_matcher.sliding_window import generate_windows

logger = structlog.get_logger(__name__)


GoldView = Literal["high", "high_plus_medium"]
"""Which subset of the CV gold labels counts as the positive set.

``"high"`` — only ``confidence_expected: high`` labels.
``"high_plus_medium"`` — both buckets. This is the *headline* view
per Step 4 Pre-Flight Q4."""


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PRF:
    """Precision / recall / F1 triple. All in ``[0.0, 1.0]``."""

    precision: float
    recall: float
    f1: float

    @classmethod
    def from_sets(cls, predicted: set[str], gold: set[str]) -> PRF:
        """Compute P/R/F1 by set membership.

        Conventions when one side is empty:

        * empty gold, empty predicted → P=R=F1=1.0 (a vacuously
          perfect prediction). Logged so reviewers know what
          happened.
        * empty gold, non-empty predicted → P=0, R=1, F1=0. The
          recall denominator is convention here (0/0 → 1); precision
          is 0 because every predicted item is a false positive.
        * empty predicted, non-empty gold → P=1, R=0, F1=0. Same
          logic in reverse.
        """
        if not predicted and not gold:
            return cls(1.0, 1.0, 1.0)
        if not predicted:
            return cls(1.0, 0.0, 0.0)
        if not gold:
            return cls(0.0, 1.0, 0.0)
        tp = len(predicted & gold)
        p = tp / len(predicted) if predicted else 0.0
        r = tp / len(gold) if gold else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        return cls(p, r, f1)


@dataclass(frozen=True, slots=True)
class CVBaselineResult:
    """Per-CV outputs from one baseline run.

    Holds enough state to be re-aggregated (different thresholds /
    top-k cuts) without re-encoding the CV. The expensive Step is
    ``semantic_max_similarity`` — once that's computed, threshold
    sweeps are pure dict-comprehension.
    """

    cv_id: str

    # Module 1 / Module 2 byproducts
    text_length: int
    n_windows: int
    lexical_uris: set[str]

    # Gold-label views
    gold_high: set[str]
    gold_high_plus_medium: set[str]
    forbidden_uris: set[str]
    """URIs in ``skills_definitely_not_in_cv``. Counted as false
    positives if they ever surface (lexical or semantic)."""

    # Semantic retrieval: per-URI maximum similarity across windows.
    # The threshold sweep + top-k bookkeeping is computed from this.
    semantic_max_similarity: dict[str, float]

    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class ViewMetrics:
    """Aggregate per-view (high / high+medium) metric block."""

    view: GoldView
    threshold: float
    top_k: int
    lexical_macro: PRF
    semantic_macro: PRF
    ensemble_macro: PRF
    lexical_micro: PRF
    semantic_micro: PRF
    ensemble_micro: PRF
    per_cv_semantic: dict[str, PRF] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BaselineMetrics:
    """End-to-end output of :func:`run_baseline`.

    Contains both gold-set views per Q4 plus the raw per-CV state
    needed by the report generator for threshold ablations.
    """

    config: dict[str, Any]
    per_cv: list[CVBaselineResult]
    headline: ViewMetrics
    """Convenience: the ``high+medium`` view at the configured
    threshold and top_k. Reported as the macro-F1 floor."""

    by_view: dict[GoldView, ViewMetrics]
    """Both views indexed by name. ``by_view["high"]`` and
    ``by_view["high_plus_medium"]`` are always present."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_baseline(
    *,
    eval_corpus: EvalCorpus | None = None,
    eval_corpus_dir: Path | None = None,
    encoder: Encoder,
    index: EscoIndex,
    skill_extractor: SkillExtractor | None = None,
    extraction_pipeline: ExtractionPipeline | None = None,
    window_size_tokens: int = 30,
    window_stride_tokens: int = 15,
    semantic_threshold: float = 0.65,
    top_k_per_window: int = 5,
) -> BaselineMetrics:
    """Run the zero-shot baseline over the eval corpus.

    Parameters
    ----------
    eval_corpus
        Pre-loaded :class:`EvalCorpus`. Optional — if ``None`` one
        is loaded from ``eval_corpus_dir`` (or the default location).
    eval_corpus_dir
        Override the default eval-corpus directory. Ignored when
        ``eval_corpus`` is supplied.
    encoder
        Any :class:`~skill_matcher.encoder.Encoder` implementation
        (real SBERT or a fixture mock).
    index
        A *built* :class:`EscoIndex`. Caller is responsible for
        construction so the ablation pass can swap concept-text
        formats without re-encoding everything from scratch.
    skill_extractor
        Optional pre-constructed Module 2 :class:`SkillExtractor`.
        Re-used across CVs to amortise spaCy model load (~500 ms).
    extraction_pipeline
        Optional pre-constructed Module 1 :class:`ExtractionPipeline`.
        Re-used for the same reason.
    window_size_tokens / window_stride_tokens
        Sliding-window geometry. See :mod:`skill_matcher.sliding_window`.
    semantic_threshold
        Cosine-similarity threshold above which a retrieved URI is
        counted in the semantic prediction set.
    top_k_per_window
        Top-k retrievals per sliding window. Larger ``k`` increases
        recall at the cost of more URIs to threshold-filter.
    """
    if not index.is_built:
        raise RuntimeError(
            "Index passed to run_baseline is not built; "
            "call EscoIndex.build() or .load() first."
        )

    corpus = eval_corpus or load_eval_corpus(eval_root=eval_corpus_dir)
    if not corpus.cvs:
        raise RuntimeError(
            f"No CV PDFs found in {eval_corpus_dir or 'default fixtures'}; "
            "the eval corpus is required for the baseline."
        )

    ex_pipeline = extraction_pipeline or ExtractionPipeline()
    sx = skill_extractor or SkillExtractor()

    per_cv: list[CVBaselineResult] = []
    for cv_id in corpus.cv_ids():
        pdf_path = corpus.cvs[cv_id]
        labels = corpus.cv_labels.get(cv_id)
        if labels is None:
            # Unlabelled CV — skip but log. The eval corpus invariant
            # is that every CV in fixtures has a labels YAML; missing
            # ones are corpus-construction bugs.
            logger.warning("baseline.skip_unlabelled", cv_id=cv_id)
            continue

        try:
            result = _process_one_cv(
                cv_id=cv_id,
                pdf_path=pdf_path,
                labels=labels,
                encoder=encoder,
                index=index,
                skill_extractor=sx,
                extraction_pipeline=ex_pipeline,
                window_size_tokens=window_size_tokens,
                window_stride_tokens=window_stride_tokens,
                top_k_per_window=top_k_per_window,
            )
        except NotACVError:
            logger.warning("baseline.skip_not_a_cv", cv_id=cv_id)
            continue
        except CVExtractorError as exc:
            # Module 1 couldn't extract the PDF — typical cause on
            # Windows is the OCR fallback failing because Poppler is
            # not on PATH (see project_module1_limitations memory).
            # Skip the CV rather than crashing the whole baseline; the
            # report's `n_cvs` will reflect the smaller denominator
            # and the omission shows up in the per-CV table.
            logger.warning(
                "baseline.skip_extraction_failed",
                cv_id=cv_id,
                pdf_path=str(pdf_path),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            continue
        per_cv.append(result)

    if not per_cv:
        raise RuntimeError(
            "Baseline produced zero per-CV results; check fixture paths."
        )

    # Build with explicit cast so mypy narrows ``str`` keys to the
    # ``GoldView`` literal type. The dict literal would otherwise be
    # inferred as ``dict[str, ViewMetrics]``.
    by_view = cast(
        "dict[GoldView, ViewMetrics]",
        {
            "high": _aggregate_view(
                per_cv,
                view="high",
                threshold=semantic_threshold,
                top_k=top_k_per_window,
            ),
            "high_plus_medium": _aggregate_view(
                per_cv,
                view="high_plus_medium",
                threshold=semantic_threshold,
                top_k=top_k_per_window,
            ),
        },
    )
    headline = by_view["high_plus_medium"]

    config = {
        "n_cvs": len(per_cv),
        "n_concepts": index.n_concepts,
        "embedding_dim": index.embedding_dim,
        "concept_text_format": index.concept_text_format,
        "window_size_tokens": window_size_tokens,
        "window_stride_tokens": window_stride_tokens,
        "semantic_threshold": semantic_threshold,
        "top_k_per_window": top_k_per_window,
    }

    logger.info(
        "baseline.complete",
        n_cvs=len(per_cv),
        macro_f1_high_plus_medium=headline.semantic_macro.f1,
        macro_p_high_plus_medium=headline.semantic_macro.precision,
        macro_r_high_plus_medium=headline.semantic_macro.recall,
    )

    return BaselineMetrics(
        config=config,
        per_cv=per_cv,
        headline=headline,
        by_view=by_view,
    )


def threshold_sweep(
    metrics: BaselineMetrics,
    thresholds: Iterable[float],
    *,
    view: GoldView = "high_plus_medium",
) -> dict[float, PRF]:
    """Compute macro PRF at a series of thresholds without re-encoding.

    Used by the report generator's threshold-ablation table. Operates
    purely on the cached :attr:`CVBaselineResult.semantic_max_similarity`
    of each CV — encoding has already happened.
    """
    out: dict[float, PRF] = {}
    for t in thresholds:
        agg = _aggregate_view(
            metrics.per_cv,
            view=view,
            threshold=t,
            top_k=metrics.config.get("top_k_per_window", 5),
        )
        out[float(t)] = agg.semantic_macro
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _process_one_cv(
    *,
    cv_id: str,
    pdf_path: Path,
    labels: CVLabels,
    encoder: Encoder,
    index: EscoIndex,
    skill_extractor: SkillExtractor,
    extraction_pipeline: ExtractionPipeline,
    window_size_tokens: int,
    window_stride_tokens: int,
    top_k_per_window: int,
) -> CVBaselineResult:
    """Run the full per-CV pipeline. Pure-ish — only side effect is logs."""
    t0 = time.monotonic()

    # Module 1 → text.
    extraction = extraction_pipeline.process(pdf_path)
    cv_text = extraction.text

    # Module 2 → lexical control. Empty result is allowed (e.g. Romanian
    # CV with sparse skills surfaced) and falls through to an empty set.
    lexical_result: SkillExtractionResult = skill_extractor.extract(extraction)
    lexical_uris = {m.esco_uri for m in lexical_result.skills}

    # Sliding windows over CV text.
    windows = generate_windows(
        cv_text,
        window_size_tokens=window_size_tokens,
        stride_tokens=window_stride_tokens,
    )
    n_windows = len(windows)

    semantic_max_similarity: dict[str, float] = {}
    if windows:
        window_texts = [w.text for w in windows]
        # One batched encode + one batched query — both vectorised.
        window_embeddings = encoder.encode(window_texts, batch_size=32)
        per_window_topk = index.query_batch(
            window_embeddings, top_k=top_k_per_window
        )
        for hits in per_window_topk:
            for uri, sim in hits:
                prev = semantic_max_similarity.get(uri, -1.0)
                if sim > prev:
                    semantic_max_similarity[uri] = sim

    # Gold + forbidden sets from labels YAML.
    gold_high: set[str] = set()
    gold_high_plus_medium: set[str] = set()
    for gold in labels.gold_skills:
        gold_high_plus_medium.add(gold.skill_uri)
        if gold.confidence_expected == "high":
            gold_high.add(gold.skill_uri)
    # ``skills_definitely_not_in_cv`` is recorded as free-form text in
    # the YAML; only the entries that *happen to be ESCO URIs* are
    # actionable here. We pass through as-is so the forbidden set can
    # be cross-checked at report time.
    forbidden_uris = set(labels.skills_definitely_not_in_cv)

    elapsed = time.monotonic() - t0
    logger.info(
        "baseline.cv_processed",
        cv_id=cv_id,
        text_length=len(cv_text),
        n_windows=n_windows,
        lexical_count=len(lexical_uris),
        semantic_count=len(semantic_max_similarity),
        gold_high=len(gold_high),
        gold_high_plus_medium=len(gold_high_plus_medium),
        elapsed_seconds=round(elapsed, 3),
    )
    return CVBaselineResult(
        cv_id=cv_id,
        text_length=len(cv_text),
        n_windows=n_windows,
        lexical_uris=lexical_uris,
        gold_high=gold_high,
        gold_high_plus_medium=gold_high_plus_medium,
        forbidden_uris=forbidden_uris,
        semantic_max_similarity=semantic_max_similarity,
        elapsed_seconds=elapsed,
    )


def _semantic_uris(
    result: CVBaselineResult, *, threshold: float
) -> set[str]:
    """URIs whose max similarity across windows clears ``threshold``."""
    return {
        uri
        for uri, sim in result.semantic_max_similarity.items()
        if sim >= threshold
    }


def _select_gold(result: CVBaselineResult, view: GoldView) -> set[str]:
    return result.gold_high if view == "high" else result.gold_high_plus_medium


def _aggregate_view(
    per_cv: list[CVBaselineResult],
    *,
    view: GoldView,
    threshold: float,
    top_k: int,
) -> ViewMetrics:
    """Pool the per-CV results into macro + micro PRF for one gold view."""
    per_cv_semantic: dict[str, PRF] = {}
    lex_prfs: list[PRF] = []
    sem_prfs: list[PRF] = []
    ens_prfs: list[PRF] = []

    # Micro-pool counters.
    lex_tp = lex_fp = lex_fn = 0
    sem_tp = sem_fp = sem_fn = 0
    ens_tp = ens_fp = ens_fn = 0

    for r in per_cv:
        gold = _select_gold(r, view)
        sem = _semantic_uris(r, threshold=threshold)
        ens = r.lexical_uris | sem

        lex_prf = PRF.from_sets(r.lexical_uris, gold)
        sem_prf = PRF.from_sets(sem, gold)
        ens_prf = PRF.from_sets(ens, gold)

        lex_prfs.append(lex_prf)
        sem_prfs.append(sem_prf)
        ens_prfs.append(ens_prf)
        per_cv_semantic[r.cv_id] = sem_prf

        lex_tp += len(r.lexical_uris & gold)
        lex_fp += len(r.lexical_uris - gold)
        lex_fn += len(gold - r.lexical_uris)

        sem_tp += len(sem & gold)
        sem_fp += len(sem - gold)
        sem_fn += len(gold - sem)

        ens_tp += len(ens & gold)
        ens_fp += len(ens - gold)
        ens_fn += len(gold - ens)

    def _macro(prfs: list[PRF]) -> PRF:
        if not prfs:
            return PRF(0.0, 0.0, 0.0)
        return PRF(
            precision=float(np.mean([p.precision for p in prfs])),
            recall=float(np.mean([p.recall for p in prfs])),
            f1=float(np.mean([p.f1 for p in prfs])),
        )

    def _micro(tp: int, fp: int, fn: int) -> PRF:
        if tp + fp + fn == 0:
            return PRF(1.0, 1.0, 1.0)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        return PRF(p, r, f1)

    return ViewMetrics(
        view=view,
        threshold=threshold,
        top_k=top_k,
        lexical_macro=_macro(lex_prfs),
        semantic_macro=_macro(sem_prfs),
        ensemble_macro=_macro(ens_prfs),
        lexical_micro=_micro(lex_tp, lex_fp, lex_fn),
        semantic_micro=_micro(sem_tp, sem_fp, sem_fn),
        ensemble_micro=_micro(ens_tp, ens_fp, ens_fn),
        per_cv_semantic=per_cv_semantic,
    )


__all__ = [
    "PRF",
    "BaselineMetrics",
    "CVBaselineResult",
    "GoldView",
    "ViewMetrics",
    "run_baseline",
    "threshold_sweep",
]
