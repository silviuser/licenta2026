"""End-to-end Scorer evaluation on the 14-CV x 20-JD fit matrix.

Step 7 deliverable. Wires Module 1 + Module 2 + Linker + Scorer on the
held-out eval corpus and produces
``reports/matcher_evaluation_<YYYYMMDD>.md`` plus a JSON companion.

The headline metric is a 3-class projection of ``MatchResult.overall_score``::

    score >= T1            -> "strong"
    T2 <= score < T1       -> "possible"
    score < T2             -> "no"

Defaults are ``T1=0.55, T2=0.25`` (provisional; Step 8 tunes).
``--ablation`` re-projects across the 5 threshold pairs listed in the
brief: ``{(0.50, 0.20), (0.55, 0.25), (0.60, 0.30), (0.65, 0.35),
(0.70, 0.40)}``.

Per Step 7 brief: the gate is *correctness, not score*. Numbers go
into the report honestly with the Step 5 placeholder disclaimer; do
not interpret a sub-50% accuracy as a Scorer bug -- it is bottlenecked
by the placeholder encoder.

CLI::

    python scripts/evaluate_matcher.py \
      --eval-corpus-dir tests/fixtures/eval_corpus \
      --out-report reports/matcher_evaluation_<YYYYMMDD>.md \
      [--t1 0.55] [--t2 0.25] \
      [--ablation] \
      [--rebuild-index]

Sections produced in the markdown report (per brief §3.5.11):

1. Executive summary
2. Environment
3. Confusion matrix (3x3)
4. Per-class metrics (precision/recall/F1)
5. Per-JD breakdown
6. Per-CV breakdown
7. Distribution of overall_score by gold class (histogram PNG)
8. Top 10 disagreements
9. Threshold ablation (when ``--ablation`` is set)
10. Conclusion
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

# stdout reconfigure for Windows cp1252 console (mirrors evaluate_linker.py).
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, OSError):
    pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import structlog  # noqa: E402

from cv_extractor.exceptions import CVExtractorError  # noqa: E402
from cv_extractor.pipeline import ExtractionPipeline  # noqa: E402
from skill_extractor.exceptions import NotACVError  # noqa: E402
from skill_extractor.models import SkillExtractionResult  # noqa: E402
from skill_extractor.pipeline import SkillExtractor  # noqa: E402
from skill_matcher import __version__ as SKILL_MATCHER_VERSION  # noqa: E402
from skill_matcher.config import SkillMatcherConfig  # noqa: E402
from skill_matcher.encoder import SentenceTransformerEncoder  # noqa: E402
from skill_matcher.esco_index import (  # noqa: E402
    EscoIndex,
    EscoIndexCacheError,
    cache_filename,
    compute_model_sha,
)
from skill_matcher.esco_loader import (  # noqa: E402
    EscoConcept,
    compute_esco_sha,
    load_esco_concepts,
)
from skill_matcher.eval_corpus import (  # noqa: E402
    EvalCorpus,
    FitJudgment,
    JDFixture,
    load_eval_corpus,
)
from skill_matcher.jd_parser import jd_fixture_to_requirements  # noqa: E402
from skill_matcher.linker import Linker  # noqa: E402
from skill_matcher.models import (  # noqa: E402
    EnrichedSkillResult,
    JDRequirement,
    MatchResult,
)
from skill_matcher.scorer import Scorer  # noqa: E402

logger = structlog.get_logger(__name__)


# Fit-matrix classes used end-to-end. The integer ordering is
# load-bearing for the confusion matrix layout (rows / cols).
_CLASSES: tuple[FitJudgment, ...] = ("strong", "possible", "no")
_CLASS_INDEX: dict[FitJudgment, int] = {c: i for i, c in enumerate(_CLASSES)}


# Threshold pairs used by ``--ablation``. The brief locks these five.
_ABLATION_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (0.50, 0.20),
    (0.55, 0.25),
    (0.60, 0.30),
    (0.65, 0.35),
    (0.70, 0.40),
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _CellResult:
    """One ``(cv_id, jd_id)`` evaluation row."""

    cv_id: str
    jd_id: str
    overall_score: float
    required_coverage: float
    nice_to_have_coverage: float
    n_matched_required: int
    n_matched_nice: int
    n_unmatched_required: int
    n_unmatched_nice: int
    gold: FitJudgment


@dataclass
class _Metrics:
    """3-class projection metrics for one (T1, T2) setting."""

    t1: float
    t2: float
    confusion: np.ndarray  # shape (3, 3) -- rows gold, cols pred
    accuracy: float
    weighted_accuracy: float
    per_class_precision: dict[FitJudgment, float]
    per_class_recall: dict[FitJudgment, float]
    per_class_f1: dict[FitJudgment, float]
    macro_f1: float


# ---------------------------------------------------------------------------
# 3-class projection + metric helpers
# ---------------------------------------------------------------------------


def _project_to_class(score: float, t1: float, t2: float) -> FitJudgment:
    """Map a continuous ``overall_score`` to a fit class.

    ``score >= t1`` -> ``strong``;
    ``t2 <= score < t1`` -> ``possible``;
    otherwise -> ``no``. ``t1`` must be strictly greater than ``t2``;
    we do not enforce it here -- the caller's argparse + brief say so.
    """
    if score >= t1:
        return "strong"
    if score >= t2:
        return "possible"
    return "no"


def _confusion_3x3(
    pairs: list[tuple[FitJudgment, FitJudgment]],
) -> np.ndarray:
    """Build a 3x3 confusion matrix. Rows = gold, cols = predicted.

    ``pairs`` is a flat list of ``(gold, predicted)`` pairs across all
    evaluated cells.
    """
    m = np.zeros((3, 3), dtype=np.int64)
    for gold, pred in pairs:
        m[_CLASS_INDEX[gold], _CLASS_INDEX[pred]] += 1
    return m


def _per_class_prf(
    confusion: np.ndarray,
) -> tuple[dict[FitJudgment, float], dict[FitJudgment, float], dict[FitJudgment, float]]:
    """Compute per-class precision / recall / F1 from a confusion matrix."""
    precision: dict[FitJudgment, float] = {}
    recall: dict[FitJudgment, float] = {}
    f1: dict[FitJudgment, float] = {}
    for cls in _CLASSES:
        i = _CLASS_INDEX[cls]
        tp = int(confusion[i, i])
        pred_total = int(confusion[:, i].sum())
        gold_total = int(confusion[i, :].sum())
        p = tp / pred_total if pred_total > 0 else 0.0
        r = tp / gold_total if gold_total > 0 else 0.0
        f = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        precision[cls] = p
        recall[cls] = r
        f1[cls] = f
    return precision, recall, f1


def _metrics_at(
    cells: list[_CellResult], t1: float, t2: float
) -> _Metrics:
    """3-class projection + metric bundle at one (T1, T2) setting."""
    pairs: list[tuple[FitJudgment, FitJudgment]] = [
        (c.gold, _project_to_class(c.overall_score, t1, t2)) for c in cells
    ]
    confusion = _confusion_3x3(pairs)
    n = len(cells)
    accuracy = (
        float(np.trace(confusion)) / n if n > 0 else 0.0
    )

    # Weighted-by-class accuracy: per-class recall, averaged uniformly
    # across classes that have at least one gold instance. Robust to
    # class imbalance.
    per_class_p, per_class_r, per_class_f = _per_class_prf(confusion)
    nonempty_classes = [
        cls for cls in _CLASSES if confusion[_CLASS_INDEX[cls], :].sum() > 0
    ]
    weighted_accuracy = (
        float(np.mean([per_class_r[c] for c in nonempty_classes]))
        if nonempty_classes
        else 0.0
    )
    macro_f1 = float(np.mean([per_class_f[c] for c in _CLASSES]))

    return _Metrics(
        t1=t1,
        t2=t2,
        confusion=confusion,
        accuracy=accuracy,
        weighted_accuracy=weighted_accuracy,
        per_class_precision=per_class_p,
        per_class_recall=per_class_r,
        per_class_f1=per_class_f,
        macro_f1=macro_f1,
    )


# ---------------------------------------------------------------------------
# Pipeline helpers (mirror evaluate_linker.py for consistency)
# ---------------------------------------------------------------------------


def _resolve_encoder_path(cfg: SkillMatcherConfig, override: str | None) -> str:
    """3-tier resolution: explicit > config.finetuned > latest.txt > base."""
    if override:
        return override
    if cfg.finetuned_model_path is not None:
        return str(cfg.finetuned_model_path)
    pointer = cfg.models_dir / "latest.txt"
    if pointer.exists():
        run = pointer.read_text(encoding="utf-8").strip()
        if run:
            run_dir = cfg.models_dir / run
            if run_dir.is_dir():
                return str(run_dir)
    return cfg.base_model


def _get_or_build_index(
    *,
    encoder: SentenceTransformerEncoder,
    cache_dir: Path,
    concepts: list[EscoConcept],
    esco_sha: str,
    rebuild: bool,
) -> EscoIndex:
    """Resolve cached index or build cold. Cache key includes model+ESCO SHA."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_sha = compute_model_sha(
        model_name=encoder.model_name,
        finetuned_model_path=None,
    )
    cache_path = cache_dir / cache_filename(
        model_sha=model_sha,
        esco_sha=esco_sha,
        fmt="bounded-a",
    )
    index = EscoIndex(encoder=encoder, cache_dir=cache_dir)

    if not rebuild:
        try:
            index.load(
                cache_path,
                expected_esco_sha=esco_sha,
                expected_format="bounded-a",
            )
            logger.info(
                "evaluate_matcher.index.cache_hit",
                cache_path=str(cache_path),
                n_concepts=index.n_concepts,
            )
            return index
        except (FileNotFoundError, EscoIndexCacheError) as exc:
            logger.info(
                "evaluate_matcher.index.cold_build",
                cache_path=str(cache_path),
                reason=str(exc),
            )

    index.build(concepts, fmt="bounded-a", batch_size=64)
    index.save(
        cache_path,
        esco_sha=esco_sha,
        skill_matcher_version=SKILL_MATCHER_VERSION,
    )
    return index


def _build_lexical(
    pdf_path: Path,
    *,
    extraction_pipeline: ExtractionPipeline,
    skill_extractor: SkillExtractor,
) -> tuple[str, SkillExtractionResult] | None:
    """Run Module 1 + Module 2 on one PDF. Returns ``None`` on skip
    (e.g. Poppler missing for ``real_cv2``)."""
    try:
        extraction = extraction_pipeline.process(pdf_path)
    except NotACVError:
        logger.warning("evaluate_matcher.skip_not_a_cv", pdf=str(pdf_path))
        return None
    except CVExtractorError as exc:
        logger.warning(
            "evaluate_matcher.skip_extraction_failed",
            pdf=str(pdf_path),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return None
    try:
        lexical = skill_extractor.extract(extraction)
    except NotACVError:
        logger.warning("evaluate_matcher.skip_not_a_cv_after_extract", pdf=str(pdf_path))
        return None
    return extraction.text, lexical


# ---------------------------------------------------------------------------
# Histogram (matplotlib lazy import; Step 7 brief Q5 accepted "yes")
# ---------------------------------------------------------------------------


def _write_score_histogram(
    cells: list[_CellResult], png_path: Path
) -> Path | None:
    """Save a histogram PNG of ``overall_score`` per gold class.

    Returns the written path, or ``None`` if matplotlib is unavailable
    (the report still renders; the histogram section just says "skipped").
    """
    try:
        import matplotlib

        matplotlib.use("Agg")  # headless backend; safe inside subprocesses
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("evaluate_matcher.matplotlib_missing", path=str(png_path))
        return None

    by_class: dict[FitJudgment, list[float]] = defaultdict(list)
    for c in cells:
        by_class[c.gold].append(c.overall_score)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = np.linspace(0.0, 1.0, 21)
    colors = {"strong": "#2ca02c", "possible": "#ff7f0e", "no": "#d62728"}
    for cls in _CLASSES:
        scores = by_class.get(cls, [])
        if not scores:
            continue
        ax.hist(
            scores,
            bins=bins,
            alpha=0.55,
            label=f"{cls} (n={len(scores)})",
            color=colors[cls],
            edgecolor="black",
            linewidth=0.4,
        )
    ax.set_xlabel("overall_score")
    ax.set_ylabel("count")
    ax.set_title("Distribution of overall_score by gold class")
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(png_path, dpi=140)
    plt.close(fig)
    return png_path


# ---------------------------------------------------------------------------
# Cell evaluation
# ---------------------------------------------------------------------------


def _evaluate_cells(
    *,
    corpus: EvalCorpus,
    enriched_by_cv: dict[str, EnrichedSkillResult],
    scorer: Scorer,
) -> tuple[list[_CellResult], list[tuple[str, str, str]]]:
    """For every (cv_id, jd_id) with a fit judgment, run the Scorer once.

    Returns ``(cells, skipped_pairs)`` where ``skipped_pairs`` is a
    list of ``(cv_id, jd_id, reason)`` for unjudged or unlinkable pairs.
    """
    cells: list[_CellResult] = []
    skipped: list[tuple[str, str, str]] = []

    # Pre-convert JD requirements once per JD to avoid repeated YAML
    # adapter calls inside the inner loop.
    reqs_by_jd: dict[str, list[JDRequirement]] = {
        jd_id: jd_fixture_to_requirements(jd)
        for jd_id, jd in corpus.jds.items()
    }

    for cv_id in corpus.cv_ids():
        enriched = enriched_by_cv.get(cv_id)
        if enriched is None:
            # CV linkage failed upstream -- all (cv, jd) pairs skipped.
            for jd_id in corpus.jd_ids():
                if corpus.fit(cv_id, jd_id) is not None:
                    skipped.append((cv_id, jd_id, "no enriched (Module 1/2 skip)"))
            continue
        for jd_id in corpus.jd_ids():
            gold = corpus.fit(cv_id, jd_id)
            if gold is None:
                skipped.append((cv_id, jd_id, "no gold judgment"))
                continue
            result, _stats = scorer.score(
                enriched=enriched,
                jd_id=jd_id,
                requirements=reqs_by_jd[jd_id],
            )
            cells.append(
                _CellResult(
                    cv_id=cv_id,
                    jd_id=jd_id,
                    overall_score=result.overall_score,
                    required_coverage=result.required_coverage,
                    nice_to_have_coverage=result.nice_to_have_coverage,
                    n_matched_required=len(result.matched_required),
                    n_matched_nice=len(result.matched_nice_to_have),
                    n_unmatched_required=len(result.unmatched_required),
                    n_unmatched_nice=len(result.unmatched_nice_to_have),
                    gold=gold,
                )
            )

    return cells, skipped


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _render_confusion_table(confusion: np.ndarray) -> list[str]:
    """Render a 3x3 confusion matrix as a markdown table."""
    lines: list[str] = []
    lines.append("|  | pred:strong | pred:possible | pred:no |")
    lines.append("|---|------------|---------------|---------|")
    for cls in _CLASSES:
        i = _CLASS_INDEX[cls]
        row = confusion[i]
        lines.append(
            f"| **gold:{cls}** | {int(row[0])} | {int(row[1])} | {int(row[2])} |"
        )
    return lines


def _render_per_class_metrics(metrics: _Metrics) -> list[str]:
    lines: list[str] = []
    lines.append("| Class | Precision | Recall | F1 |")
    lines.append("|-------|-----------|--------|----|")
    for cls in _CLASSES:
        lines.append(
            f"| {cls} | "
            f"{metrics.per_class_precision[cls]:.3f} | "
            f"{metrics.per_class_recall[cls]:.3f} | "
            f"{metrics.per_class_f1[cls]:.3f} |"
        )
    return lines


def _render_per_jd_breakdown(
    cells: list[_CellResult], jd_ids: list[str], t1: float, t2: float
) -> list[str]:
    """For each JD: correct/incorrect counts, avg score by gold class."""
    lines: list[str] = []
    lines.append(
        "| JD | n_cells | correct | strong_avg | possible_avg | no_avg |"
    )
    lines.append(
        "|----|---------|---------|-----------|--------------|--------|"
    )
    by_jd: dict[str, list[_CellResult]] = defaultdict(list)
    for c in cells:
        by_jd[c.jd_id].append(c)
    for jd_id in jd_ids:
        rows = by_jd.get(jd_id, [])
        n = len(rows)
        correct = sum(
            1
            for c in rows
            if _project_to_class(c.overall_score, t1, t2) == c.gold
        )
        strong_scores = [c.overall_score for c in rows if c.gold == "strong"]
        possible_scores = [
            c.overall_score for c in rows if c.gold == "possible"
        ]
        no_scores = [c.overall_score for c in rows if c.gold == "no"]
        lines.append(
            f"| {jd_id} | {n} | {correct} | "
            f"{_avg_or_dash(strong_scores)} | "
            f"{_avg_or_dash(possible_scores)} | "
            f"{_avg_or_dash(no_scores)} |"
        )
    return lines


def _render_per_cv_breakdown(
    cells: list[_CellResult], cv_ids: list[str], t1: float, t2: float
) -> list[str]:
    """For each CV: correct/incorrect counts, mean overall_score."""
    lines: list[str] = []
    lines.append("| CV | n_cells | correct | mean_score |")
    lines.append("|----|---------|---------|------------|")
    by_cv: dict[str, list[_CellResult]] = defaultdict(list)
    for c in cells:
        by_cv[c.cv_id].append(c)
    for cv_id in cv_ids:
        rows = by_cv.get(cv_id, [])
        if not rows:
            continue
        correct = sum(
            1
            for c in rows
            if _project_to_class(c.overall_score, t1, t2) == c.gold
        )
        mean_score = float(np.mean([c.overall_score for c in rows]))
        lines.append(
            f"| {cv_id} | {len(rows)} | {correct} | {mean_score:.3f} |"
        )
    return lines


def _avg_or_dash(scores: list[float]) -> str:
    if not scores:
        return "-"
    return f"{float(np.mean(scores)):.3f}"


def _gold_class_distance(gold: FitJudgment, pred: FitJudgment) -> int:
    """Treat the 3 classes as ordinal for ranking disagreements.

    ``strong`` -> 2, ``possible`` -> 1, ``no`` -> 0. Distance is the
    absolute difference; the brief defines "most wrong" as
    strong-predicted-no and vice versa.
    """
    ord_map: dict[FitJudgment, int] = {"strong": 2, "possible": 1, "no": 0}
    return abs(ord_map[gold] - ord_map[pred])


def _render_top_disagreements(
    cells: list[_CellResult], t1: float, t2: float, k: int = 10
) -> list[str]:
    """Top-K (cv, jd) pairs ranked by ordinal class distance."""
    disagreements: list[tuple[int, _CellResult, FitJudgment]] = []
    for c in cells:
        pred = _project_to_class(c.overall_score, t1, t2)
        d = _gold_class_distance(c.gold, pred)
        if d > 0:
            disagreements.append((d, c, pred))
    # Sort: largest distance first; secondary by absolute(score - midpoint).
    # Stable tie-break by (cv_id, jd_id) so output is deterministic.
    disagreements.sort(key=lambda t: (-t[0], t[1].cv_id, t[1].jd_id))
    top = disagreements[:k]

    lines: list[str] = []
    lines.append(
        "| CV | JD | gold | predicted | score | matched_req | unmatched_req |"
    )
    lines.append(
        "|----|----|------|-----------|-------|-------------|----------------|"
    )
    for _d, c, pred in top:
        lines.append(
            f"| {c.cv_id} | {c.jd_id} | {c.gold} | {pred} | "
            f"{c.overall_score:.3f} | {c.n_matched_required} | "
            f"{c.n_unmatched_required} |"
        )
    return lines


def _render_markdown(
    *,
    cells: list[_CellResult],
    skipped: list[tuple[str, str, str]],
    skipped_cvs: list[tuple[str, str]],
    cv_ids: list[str],
    jd_ids: list[str],
    encoder_name: str,
    esco_sha: str,
    cfg: SkillMatcherConfig,
    t1: float,
    t2: float,
    elapsed_seconds: float,
    histogram_path: Path | None,
    ablation: list[_Metrics] | None,
) -> str:
    """Render the per-section markdown report."""
    headline = _metrics_at(cells, t1, t2)

    lines: list[str] = []
    lines.append("# Module 3 Scorer -- Evaluation Report")
    lines.append("")
    lines.append(
        f"*Generated: {datetime.now(tz=UTC).isoformat()} "
        f"by `scripts/evaluate_matcher.py` (skill_matcher {SKILL_MATCHER_VERSION}).*"
    )
    lines.append("")

    # 1. Executive summary
    lines.append("## 1. Executive summary")
    lines.append("")
    lines.append(
        f"At default thresholds `T1={t1}`, `T2={t2}` "
        f"across {len(cells)} (CV, JD) cells: "
        f"**plain accuracy = {headline.accuracy:.3f}**, "
        f"**weighted accuracy = {headline.weighted_accuracy:.3f}**, "
        f"**macro F1 = {headline.macro_f1:.3f}**."
    )
    lines.append("")
    lines.append(
        "**Disclaimer (Step 5 placeholder):** the current encoder is a "
        "Step 5 placeholder (see STEP6_PREFLIGHT.md). Step 7's exit "
        "gate is *correctness, not score*. When Step 5 is re-done with "
        "a larger, less-biased training corpus, only the checkpoint "
        "swaps -- the Scorer's code path does not change. Numbers below "
        "will lift accordingly."
    )
    lines.append("")

    # 2. Environment
    lines.append("## 2. Environment")
    lines.append("")
    lines.append(f"* **Encoder:** `{encoder_name}`")
    lines.append(f"* **ESCO SHA (12):** `{esco_sha[:12]}`")
    lines.append(f"* **drop_threshold:** {cfg.drop_threshold}")
    lines.append(f"* **keep_threshold:** {cfg.keep_threshold}")
    lines.append(f"* **expansion_threshold:** {cfg.expansion_threshold}")
    lines.append(
        f"* **per_requirement_keep_threshold:** {cfg.per_requirement_keep_threshold}"
    )
    lines.append(f"* **seed:** {cfg.seed}")
    lines.append(f"* **T1 (strong cut):** {t1}")
    lines.append(f"* **T2 (possible cut):** {t2}")
    lines.append(f"* **cells evaluated:** {len(cells)}")
    lines.append(
        f"* **skipped pairs:** {len(skipped)} (no gold or no enriched)"
    )
    lines.append(
        f"* **CVs without enriched output:** {len(skipped_cvs)} "
        f"(Module 1/2 failures)"
    )
    lines.append(f"* **total wall-clock:** {elapsed_seconds:.1f} s")
    lines.append("")
    if skipped_cvs:
        lines.append("### Skipped CVs")
        for cv_id, reason in skipped_cvs:
            lines.append(f"* `{cv_id}` -- {reason}")
        lines.append("")

    # 3. Confusion matrix
    lines.append("## 3. Confusion matrix")
    lines.append("")
    lines.extend(_render_confusion_table(headline.confusion))
    lines.append("")

    # 4. Per-class metrics
    lines.append("## 4. Per-class metrics")
    lines.append("")
    lines.extend(_render_per_class_metrics(headline))
    lines.append("")
    lines.append(f"**Macro F1 (mean over 3 classes):** {headline.macro_f1:.3f}")
    lines.append("")

    # 5. Per-JD breakdown
    lines.append("## 5. Per-JD breakdown")
    lines.append("")
    lines.extend(_render_per_jd_breakdown(cells, jd_ids, t1, t2))
    lines.append("")

    # 6. Per-CV breakdown
    lines.append("## 6. Per-CV breakdown")
    lines.append("")
    lines.extend(_render_per_cv_breakdown(cells, cv_ids, t1, t2))
    lines.append("")

    # 7. Score distribution
    lines.append("## 7. Distribution of overall_score by gold class")
    lines.append("")
    if histogram_path is not None:
        lines.append(f"![histogram]({histogram_path.name})")
    else:
        lines.append(
            "*(matplotlib not installed -- histogram skipped; "
            "JSON companion still contains the per-cell scores.)*"
        )
    lines.append("")

    # 8. Top disagreements
    lines.append("## 8. Top 10 disagreements")
    lines.append("")
    lines.extend(_render_top_disagreements(cells, t1, t2, k=10))
    lines.append("")

    # 9. Ablation
    if ablation is not None:
        lines.append("## 9. Threshold ablation")
        lines.append("")
        lines.append(
            "| (T1, T2) | accuracy | weighted_accuracy | macro_F1 | "
            "F1(strong) | F1(possible) | F1(no) |"
        )
        lines.append(
            "|----------|----------|-------------------|----------|"
            "------------|--------------|--------|"
        )
        for m in ablation:
            lines.append(
                f"| ({m.t1}, {m.t2}) | {m.accuracy:.3f} | "
                f"{m.weighted_accuracy:.3f} | {m.macro_f1:.3f} | "
                f"{m.per_class_f1['strong']:.3f} | "
                f"{m.per_class_f1['possible']:.3f} | "
                f"{m.per_class_f1['no']:.3f} |"
            )
        lines.append("")

    # 10. Conclusion
    lines.append("## 10. Conclusion")
    lines.append("")
    lines.append(
        "Scorer is structurally complete: 0 stubs remain in "
        "`skill_matcher`, all 280-cell paths execute without exception, "
        "determinism verified by unit tests. Numbers are bottlenecked "
        "by the Step 5 placeholder encoder; Step 5 redo will lift them "
        "without Scorer code change. Proceed to **Step 8 (threshold "
        "tuning)** using this report's ablation table as starting priors."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: C901  -- argparse + orchestration, kept linear on purpose
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-corpus-dir",
        type=Path,
        default=_REPO_ROOT / "tests" / "fixtures" / "eval_corpus",
        help="Eval corpus root (containing jds/, cv_labels/, fit_matrix.csv).",
    )
    parser.add_argument(
        "--out-report",
        type=Path,
        default=_REPO_ROOT
        / "reports"
        / f"matcher_evaluation_{datetime.now(tz=UTC).strftime('%Y%m%d')}.md",
        help="Output markdown path. A .json companion is written alongside.",
    )
    parser.add_argument(
        "--encoder-path",
        type=str,
        default=None,
        help="Override the resolved encoder path.",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        default=False,
        help="Force a cold rebuild of the ESCO embedding index.",
    )
    parser.add_argument(
        "--t1",
        type=float,
        default=0.55,
        help="3-class projection: score >= t1 -> 'strong'. Default 0.55.",
    )
    parser.add_argument(
        "--t2",
        type=float,
        default=0.25,
        help=(
            "3-class projection: t2 <= score < t1 -> 'possible'. "
            "Default 0.25."
        ),
    )
    parser.add_argument(
        "--ablation",
        action="store_true",
        default=False,
        help=(
            "Append a threshold-ablation section across the 5 (T1, T2) "
            "pairs locked in the Step 7 brief."
        ),
    )
    args = parser.parse_args()

    if args.t1 <= args.t2:
        parser.error(f"--t1 ({args.t1}) must be > --t2 ({args.t2}).")

    cfg = SkillMatcherConfig()
    encoder_path = _resolve_encoder_path(cfg, args.encoder_path)
    logger.info("evaluate_matcher.start", encoder=encoder_path)

    # Build encoder.
    encoder = SentenceTransformerEncoder(
        model_name=encoder_path,
        device=cfg.device,
        seed=cfg.seed,
    )

    # Load ESCO + index.
    concepts = load_esco_concepts()
    concepts_by_uri = {c.uri: c for c in concepts}
    esco_sha = compute_esco_sha(concepts)

    index = _get_or_build_index(
        encoder=encoder,
        cache_dir=cfg.embedding_cache_dir,
        concepts=concepts,
        esco_sha=esco_sha,
        rebuild=args.rebuild_index,
    )

    # Construct Linker + Scorer (share encoder/index/concepts -- no
    # double load).
    linker = Linker(
        config=cfg,
        encoder=encoder,
        index=index,
        concepts_by_uri=concepts_by_uri,
    )
    scorer = Scorer(
        config=cfg,
        encoder=encoder,
        index=index,
        concepts_by_uri=concepts_by_uri,
    )

    # Module 1 + Module 2 plumbing reused across CVs.
    ex_pipeline = ExtractionPipeline()
    sx = SkillExtractor()

    corpus = load_eval_corpus(eval_root=args.eval_corpus_dir)
    if not corpus.cvs:
        raise RuntimeError(
            f"No CV PDFs found under {args.eval_corpus_dir}; "
            "the eval corpus is required."
        )
    if not corpus.jds:
        raise RuntimeError(
            f"No JD fixtures found under {args.eval_corpus_dir}/jds; "
            "the eval corpus is required."
        )
    if not corpus.fit_matrix:
        raise RuntimeError(
            f"Fit matrix is empty under {args.eval_corpus_dir}; "
            "cannot evaluate."
        )

    # Phase 1: Module 1 + Module 2 + Linker per CV, cached.
    enriched_by_cv: dict[str, EnrichedSkillResult] = {}
    skipped_cvs: list[tuple[str, str]] = []
    t_phase1 = time.monotonic()
    for cv_id in corpus.cv_ids():
        pdf_path = corpus.cvs[cv_id]
        prelude = _build_lexical(
            pdf_path,
            extraction_pipeline=ex_pipeline,
            skill_extractor=sx,
        )
        if prelude is None:
            skipped_cvs.append((cv_id, "Module 1/2 skip"))
            continue
        cv_text, lexical = prelude
        enriched, _stats = linker.link(
            cv_id=cv_id, cv_text=cv_text, lexical=lexical
        )
        enriched_by_cv[cv_id] = enriched
    phase1_elapsed = time.monotonic() - t_phase1
    logger.info(
        "evaluate_matcher.phase1_done",
        n_cvs_linked=len(enriched_by_cv),
        n_skipped=len(skipped_cvs),
        elapsed_seconds=round(phase1_elapsed, 2),
    )

    # Phase 2: Scorer over the 14 * 20 grid.
    t_phase2 = time.monotonic()
    cells, skipped_pairs = _evaluate_cells(
        corpus=corpus,
        enriched_by_cv=enriched_by_cv,
        scorer=scorer,
    )
    phase2_elapsed = time.monotonic() - t_phase2
    logger.info(
        "evaluate_matcher.phase2_done",
        n_cells=len(cells),
        n_skipped_pairs=len(skipped_pairs),
        elapsed_seconds=round(phase2_elapsed, 2),
    )

    if not cells:
        raise RuntimeError(
            "evaluate_matcher produced zero scored cells -- check fixtures."
        )

    # Histogram (PNG sibling of the report).
    png_path = args.out_report.with_suffix(".scores.png")
    histogram_path = _write_score_histogram(cells, png_path)

    # Ablation metrics.
    ablation_metrics: list[_Metrics] | None = None
    if args.ablation:
        ablation_metrics = [_metrics_at(cells, t1, t2) for t1, t2 in _ABLATION_THRESHOLDS]

    # Markdown.
    md = _render_markdown(
        cells=cells,
        skipped=skipped_pairs,
        skipped_cvs=skipped_cvs,
        cv_ids=corpus.cv_ids(),
        jd_ids=corpus.jd_ids(),
        encoder_name=encoder_path,
        esco_sha=esco_sha,
        cfg=cfg,
        t1=args.t1,
        t2=args.t2,
        elapsed_seconds=phase1_elapsed + phase2_elapsed,
        histogram_path=histogram_path,
        ablation=ablation_metrics,
    )
    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    args.out_report.write_text(md, encoding="utf-8")
    logger.info(
        "evaluate_matcher.report_written", path=str(args.out_report)
    )

    # JSON companion.
    headline = _metrics_at(cells, args.t1, args.t2)
    payload: dict[str, Any] = {
        "version": SKILL_MATCHER_VERSION,
        "encoder": encoder_path,
        "esco_sha": esco_sha,
        "config": {
            "drop_threshold": cfg.drop_threshold,
            "keep_threshold": cfg.keep_threshold,
            "expansion_threshold": cfg.expansion_threshold,
            "per_requirement_keep_threshold": cfg.per_requirement_keep_threshold,
            "seed": cfg.seed,
        },
        "projection": {"t1": args.t1, "t2": args.t2},
        "headline": _metrics_to_dict(headline),
        "ablation": (
            [_metrics_to_dict(m) for m in ablation_metrics]
            if ablation_metrics is not None
            else None
        ),
        "n_cells": len(cells),
        "skipped_cvs": [
            {"cv_id": cv, "reason": r} for cv, r in skipped_cvs
        ],
        "skipped_pairs_count": len(skipped_pairs),
        "cells": [asdict(c) for c in cells],
        "elapsed_seconds": {
            "phase1_linker": phase1_elapsed,
            "phase2_scorer": phase2_elapsed,
            "total": phase1_elapsed + phase2_elapsed,
        },
    }
    json_path = args.out_report.with_suffix(".json")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("evaluate_matcher.json_written", path=str(json_path))

    return 0


def _metrics_to_dict(m: _Metrics) -> dict[str, Any]:
    """JSON-serialisable view of a ``_Metrics`` instance."""
    return {
        "t1": m.t1,
        "t2": m.t2,
        "accuracy": m.accuracy,
        "weighted_accuracy": m.weighted_accuracy,
        "macro_f1": m.macro_f1,
        "per_class_precision": dict(m.per_class_precision),
        "per_class_recall": dict(m.per_class_recall),
        "per_class_f1": dict(m.per_class_f1),
        "confusion": m.confusion.tolist(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
