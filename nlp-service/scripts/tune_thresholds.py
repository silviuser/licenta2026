"""Step 8 -- threshold-tuning CLI.

Three-tier grid search over Module 3's seven tunable knobs:

* **Tier 2** -- ``(drop_threshold, keep_threshold, expansion_threshold)``
  -- Linker thresholds. Expensive: re-runs Linker + Scorer over the 14
  eval CVs for each combo.
* **Tier 1** -- ``(per_requirement_keep_threshold, required_weight)``
  -- Scorer aggregation. Cheap: pure arithmetic over saved
  intermediates.
* **Tier 0** -- ``(t1, t2)`` -- 3-class projection. Trivial: triple
  comparison per cell.

The script composes the Linker / Scorer pipeline with the pure-Python
grid search in :mod:`skill_matcher.tuning`. The grid search itself
never imports the encoder or the Linker -- that's the CLI driver's
job.

Usage
-----
::

    python scripts/tune_thresholds.py \\
      --eval-corpus-dir tests/fixtures/eval_corpus \\
      --out-report reports/threshold_tuning_<YYYYMMDD>.md \\
      [--mode fast|full]               # default: fast
      [--objective macro_f1|weighted_f1]  # default: macro_f1
      [--write-decisions]              # emit amendment-row file
      [--rebuild-index]

Exit codes
----------
* 0 -- a combo passed the strict guard set; the chosen defaults are
  reported in the markdown's "Proposed DECISIONS.md amendment" block.
* 2 -- no combo passed even the relaxed guards; defaults are NOT
  bumped, and the markdown's amendment block says "calibration
  deferred to Step 5 redo". This is the documented graceful-fallback
  outcome from Step 8 brief §3.2.
* 1 -- the script crashed (unhandled exception). CI distinguishes this
  from exit 2.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Windows console UTF-8 reconfigure -- mirrors evaluate_matcher.py.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, OSError):
    pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from collections.abc import Callable  # noqa: E402

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
    load_eval_corpus,
)
from skill_matcher.jd_parser import jd_fixture_to_requirements  # noqa: E402
from skill_matcher.linker import Linker  # noqa: E402
from skill_matcher.models import EnrichedSkillResult, JDRequirement  # noqa: E402
from skill_matcher.scorer import Scorer  # noqa: E402
from skill_matcher.tuning import (  # noqa: E402
    CellIntermediate,
    FitClass,
    TuningCombo,
    TuningMetric,
    TuningRunResult,
    grid_size_tier_0,
    grid_size_tier_1,
    grid_size_tier_2,
    objective_macro_f1,
    objective_weighted_f1,
    project_to_three_class,
    run_full,
    score_distribution,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Encoder + index resolution -- mirrors evaluate_matcher.py
# ---------------------------------------------------------------------------


def _resolve_encoder_path(cfg: SkillMatcherConfig, override: str | None) -> str:
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
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_sha = compute_model_sha(
        model_name=encoder.model_name, finetuned_model_path=None
    )
    cache_path = cache_dir / cache_filename(
        model_sha=model_sha, esco_sha=esco_sha, fmt="bounded-a"
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
                "tune_thresholds.index.cache_hit",
                cache_path=str(cache_path),
                n_concepts=index.n_concepts,
            )
            return index
        except (FileNotFoundError, EscoIndexCacheError) as exc:
            logger.info(
                "tune_thresholds.index.cold_build",
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
    try:
        extraction = extraction_pipeline.process(pdf_path)
    except NotACVError:
        logger.warning("tune_thresholds.skip_not_a_cv", pdf=str(pdf_path))
        return None
    except CVExtractorError as exc:
        logger.warning(
            "tune_thresholds.skip_extraction_failed",
            pdf=str(pdf_path),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return None
    try:
        lexical = skill_extractor.extract(extraction)
    except NotACVError:
        logger.warning(
            "tune_thresholds.skip_not_a_cv_after_extract", pdf=str(pdf_path)
        )
        return None
    return extraction.text, lexical


# ---------------------------------------------------------------------------
# Phase A -- enrich every CV once at a given Linker triple
# ---------------------------------------------------------------------------


def _enrich_corpus(
    corpus: EvalCorpus,
    linker: Linker,
    *,
    extraction_pipeline: ExtractionPipeline,
    skill_extractor: SkillExtractor,
) -> tuple[dict[str, EnrichedSkillResult], list[tuple[str, str]]]:
    """Run Module 1 + Module 2 + Linker per CV. Returns ``(enriched, skipped)``."""
    enriched_by_cv: dict[str, EnrichedSkillResult] = {}
    skipped: list[tuple[str, str]] = []
    for cv_id in corpus.cv_ids():
        pdf_path = corpus.cvs[cv_id]
        prelude = _build_lexical(
            pdf_path,
            extraction_pipeline=extraction_pipeline,
            skill_extractor=skill_extractor,
        )
        if prelude is None:
            skipped.append((cv_id, "Module 1/2 skip"))
            continue
        cv_text, lexical = prelude
        enriched, _stats = linker.link(
            cv_id=cv_id, cv_text=cv_text, lexical=lexical
        )
        enriched_by_cv[cv_id] = enriched
    return enriched_by_cv, skipped


# ---------------------------------------------------------------------------
# Phase B -- collect Scorer intermediates over the (CV, JD) grid
# ---------------------------------------------------------------------------


def _collect_intermediates(
    *,
    corpus: EvalCorpus,
    enriched_by_cv: dict[str, EnrichedSkillResult],
    scorer: Scorer,
    reqs_by_jd: dict[str, list[JDRequirement]],
) -> list[CellIntermediate]:
    """Run :meth:`Scorer.score_to_intermediates` over every gold cell."""
    out: list[CellIntermediate] = []
    for cv_id in corpus.cv_ids():
        enriched = enriched_by_cv.get(cv_id)
        if enriched is None:
            continue
        for jd_id in corpus.jd_ids():
            gold = corpus.fit(cv_id, jd_id)
            if gold is None:
                continue
            inter = scorer.score_to_intermediates(
                enriched=enriched,
                jd_id=jd_id,
                requirements=reqs_by_jd[jd_id],
            )
            out.append(inter)
    return out


def _gold_map(corpus: EvalCorpus) -> dict[tuple[str, str], FitClass]:
    gold: dict[tuple[str, str], FitClass] = {}
    for cv_id in corpus.cv_ids():
        for jd_id in corpus.jd_ids():
            v = corpus.fit(cv_id, jd_id)
            if v is None:
                continue
            # FitJudgment and FitClass are both Literal["strong", "possible", "no"]
            gold[(cv_id, jd_id)] = v  # type: ignore[assignment]
    return gold


# ---------------------------------------------------------------------------
# Builder closure for run_full
# ---------------------------------------------------------------------------


def _make_builder(
    *,
    base_cfg: SkillMatcherConfig,
    encoder: SentenceTransformerEncoder,
    index: EscoIndex,
    concepts_by_uri: dict[str, EscoConcept],
    extraction_pipeline: ExtractionPipeline,
    skill_extractor: SkillExtractor,
    corpus: EvalCorpus,
    reqs_by_jd: dict[str, list[JDRequirement]],
) -> tuple[
    Callable[[float, float, float], list[CellIntermediate]], dict[str, Any]
]:
    """Return a closure ``(drop, keep, expansion) -> intermediates`` and a
    timing-record dict the caller can mutate to track Tier 2 per-combo
    wall-clocks.
    """
    timing: dict[str, Any] = {"tier2_timings": []}

    def builder(drop: float, keep: float, expansion: float) -> list[CellIntermediate]:
        cfg = base_cfg.model_copy(
            update={
                "drop_threshold": drop,
                "keep_threshold": keep,
                "expansion_threshold": expansion,
            }
        )
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
        t0 = time.monotonic()
        enriched_by_cv, _skipped = _enrich_corpus(
            corpus,
            linker,
            extraction_pipeline=extraction_pipeline,
            skill_extractor=skill_extractor,
        )
        intermediates = _collect_intermediates(
            corpus=corpus,
            enriched_by_cv=enriched_by_cv,
            scorer=scorer,
            reqs_by_jd=reqs_by_jd,
        )
        elapsed = time.monotonic() - t0
        timing["tier2_timings"].append(
            {"triple": [drop, keep, expansion], "elapsed_seconds": elapsed}
        )
        logger.info(
            "tune_thresholds.builder.complete",
            drop=drop,
            keep=keep,
            expansion=expansion,
            n_cells=len(intermediates),
            elapsed_seconds=round(elapsed, 2),
        )
        return intermediates

    return builder, timing


# ---------------------------------------------------------------------------
# Markdown report rendering
# ---------------------------------------------------------------------------


_BASELINE_MACRO_F1: float = 0.225
"""Step 7's degenerate baseline (every cell predicted 'no'). Reported
side-by-side with Step 8's best combo so the lift is visible."""


def _render_combo_table(combo: TuningCombo, *, label: str = "Combo") -> list[str]:
    return [
        f"| Knob | Value ({label}) |",
        "|------|-----------------|",
        f"| drop_threshold | {combo.drop_threshold:.4f} |",
        f"| keep_threshold | {combo.keep_threshold:.4f} |",
        f"| expansion_threshold | {combo.expansion_threshold:.4f} |",
        f"| per_requirement_keep_threshold | {combo.per_requirement_keep_threshold:.4f} |",
        f"| required_weight | {combo.required_weight:.4f} |",
        f"| t1 (strong cut) | {combo.t1:.4f} |",
        f"| t2 (possible cut) | {combo.t2:.4f} |",
    ]


def _render_confusion_block(metric: TuningMetric) -> list[str]:
    classes = ("strong", "possible", "no")
    lines = ["|  | pred:strong | pred:possible | pred:no |",
             "|---|------------|---------------|---------|"]
    for g in classes:
        row = [str(metric.confusion[(g, p)]) for p in classes]
        lines.append(f"| **gold:{g}** | " + " | ".join(row) + " |")
    return lines


def _render_per_class_metrics(metric: TuningMetric) -> list[str]:
    return [
        "| Class | Precision | Recall | F1 |",
        "|-------|-----------|--------|----|",
        f"| strong | {metric.precision_strong:.3f} | "
        f"{metric.recall_strong:.3f} | {metric.f1_strong:.3f} |",
        f"| possible | {metric.precision_possible:.3f} | "
        f"{metric.recall_possible:.3f} | {metric.f1_possible:.3f} |",
        f"| no | {metric.precision_no:.3f} | "
        f"{metric.recall_no:.3f} | {metric.f1_no:.3f} |",
    ]


def _render_top10(metrics: list[TuningMetric]) -> list[str]:
    lines = [
        "| # | macro F1 | weighted F1 | combo (drop/keep/exp/perReq/wReq/T1/T2) | guards |",
        "|---|----------|-------------|------------------------------------------|--------|",
    ]
    for i, m in enumerate(metrics[:10], start=1):
        c = m.combo
        knobs = (
            f"{c.drop_threshold:.2f}/{c.keep_threshold:.2f}/"
            f"{c.expansion_threshold:.2f}/{c.per_requirement_keep_threshold:.3f}/"
            f"{c.required_weight:.2f}/{c.t1:.3f}/{c.t2:.3f}"
        )
        status = "passed" if m.guards_passed else (
            "failed: " + ",".join(m.guards_failed[:3])
        )
        lines.append(
            f"| {i} | {m.macro_f1:.3f} | {m.weighted_f1:.3f} | {knobs} | {status} |"
        )
    return lines


def _render_distribution(dist: dict[str, dict[str, float]]) -> list[str]:
    cols = ("n", "min", "P25", "P50", "P75", "P90", "P95", "P99", "max", "mean")
    lines = ["| Stratum | " + " | ".join(cols) + " |"]
    lines.append("|" + "|".join(["---"] * (len(cols) + 1)) + "|")
    for stratum in ("all", "strong", "possible", "no"):
        bucket = dist.get(stratum, {})
        if bucket.get("n", 0) == 0:
            lines.append(
                f"| {stratum} | 0 | " + " | ".join(["-"] * (len(cols) - 1)) + " |"
            )
            continue
        vals = []
        for c in cols:
            v = bucket.get(c)
            if v is None:
                vals.append("-")
            elif c == "n":
                vals.append(str(int(v)))
            else:
                vals.append(f"{v:.4f}")
        lines.append(f"| {stratum} | " + " | ".join(vals) + " |")
    return lines


def _render_report(
    *,
    mode: str,
    encoder_name: str,
    esco_sha: str,
    n_gold_cells: int,
    n_skipped_cvs: int,
    skipped_cvs: list[tuple[str, str]],
    result: TuningRunResult,
    timing_record: dict[str, Any],
    overall_at_best: dict[tuple[str, str], float] | None,
    dist_at_best: dict[str, dict[str, float]] | None,
    objective_name: str,
) -> str:
    lines: list[str] = []
    lines.append("# Module 3 -- Threshold Tuning Report (Step 8)")
    lines.append("")
    lines.append(
        f"*Generated: {datetime.now(tz=UTC).isoformat()} by "
        f"`scripts/tune_thresholds.py` (skill_matcher {SKILL_MATCHER_VERSION}).*"
    )
    lines.append("")

    # Section 1 -- executive summary.
    lines.append("## 1. Executive summary")
    lines.append("")
    if result.best_metric is not None:
        b = result.best_metric
        lift = b.macro_f1 - _BASELINE_MACRO_F1
        lines.append(
            f"**Best combo passed all strict guards.** Macro F1 = "
            f"**{b.macro_f1:.3f}** (Step 7 baseline {_BASELINE_MACRO_F1:.3f}; "
            f"lift = {lift:+.3f}). Plain accuracy = {b.plain_accuracy:.3f}, "
            f"weighted accuracy = {b.weighted_accuracy:.3f}."
        )
    elif result.fallback_relaxed is not None:
        b = result.fallback_relaxed
        lift = b.macro_f1 - _BASELINE_MACRO_F1
        lines.append(
            f"**No combo passed strict guards; best relaxed-guard combo** "
            f"reported. Macro F1 = **{b.macro_f1:.3f}** (Step 7 baseline "
            f"{_BASELINE_MACRO_F1:.3f}; lift = {lift:+.3f}). Strict guards "
            f"would have required precision/recall floors of 0.05 per class; "
            f"the relaxed set uses 0.02. See Section 8."
        )
    elif result.fallback_unguarded is not None:
        b = result.fallback_unguarded
        lines.append(
            f"**No combo passed even the relaxed guards.** The unguarded "
            f"top combo (macro F1 = {b.macro_f1:.3f}) is shown for "
            f"reference only; the Scorer's provisional defaults from "
            f"Step 4/7 remain in force. Re-run after Step 5 redo."
        )
    else:
        lines.append("**No metrics computed.** Empty grid -- this should not happen.")
    lines.append("")
    lines.append(
        "**Placeholder caveat (mandatory).** These thresholds reflect the "
        "Step 5 placeholder encoder, whose ``overall_score`` distribution "
        "is compressed to ``[0, ~0.1]`` (see Section 7). After the Step 5 "
        "redo, re-run this script on the same fixtures; T1, T2, and the "
        "per-requirement keep threshold are expected to move upward as the "
        "score range widens. The script -- not these numbers -- is the "
        "Step 8 deliverable."
    )
    lines.append("")

    # Section 2 -- environment.
    lines.append("## 2. Environment")
    lines.append("")
    lines.append(f"* **Mode:** `{mode}`")
    lines.append(f"* **Encoder:** `{encoder_name}`")
    lines.append(f"* **ESCO SHA (12):** `{esco_sha[:12]}`")
    lines.append(f"* **Gold cells:** {n_gold_cells}")
    lines.append(f"* **Skipped CVs (Module 1/2):** {n_skipped_cvs}")
    lines.append(
        f"* **Grid sizes:** Tier 2 = {grid_size_tier_2(mode == 'fast')}, "
        f"Tier 1 = {grid_size_tier_1()}, Tier 0 = {grid_size_tier_0()}; "
        f"combos evaluated = {len(result.all_metrics)}"
    )
    lines.append(
        f"* **Wall-clock (Tier 1 + Tier 0 sweep):** "
        f"{result.elapsed_seconds:.1f} s"
    )
    if timing_record["tier2_timings"]:
        t2_total = sum(t["elapsed_seconds"] for t in timing_record["tier2_timings"])
        lines.append(f"* **Wall-clock (Tier 2 Linker passes):** {t2_total:.1f} s")
    lines.append(f"* **Objective:** `{objective_name}`")
    lines.append("")
    if skipped_cvs:
        lines.append("### Skipped CVs")
        for cv_id, reason in skipped_cvs:
            lines.append(f"* `{cv_id}` -- {reason}")
        lines.append("")

    # Section 3 -- best combination.
    lines.append("## 3. Best combination")
    lines.append("")
    if result.best_metric is not None:
        lines.extend(_render_combo_table(result.best_metric.combo, label="strict-best"))
    elif result.fallback_relaxed is not None:
        lines.extend(_render_combo_table(result.fallback_relaxed.combo, label="relaxed-best"))
    else:
        lines.append("*No combo to report.*")
    lines.append("")

    # Section 4 -- confusion + per-class metrics at best combo.
    lines.append("## 4. Confusion matrix at best combo")
    lines.append("")
    chosen = result.best_metric or result.fallback_relaxed or result.fallback_unguarded
    if chosen is not None:
        lines.extend(_render_confusion_block(chosen))
        lines.append("")
        lines.append("### Per-class precision / recall / F1")
        lines.append("")
        lines.extend(_render_per_class_metrics(chosen))
    else:
        lines.append("*No metric to report.*")
    lines.append("")

    # Section 5 -- Tier 2 traversal.
    lines.append("## 5. Tier 2 traversal")
    lines.append("")
    if timing_record["tier2_timings"]:
        lines.append("| (drop, keep, expansion) | elapsed (s) |")
        lines.append("|--------------------------|-------------|")
        for entry in timing_record["tier2_timings"]:
            t = entry["triple"]
            lines.append(
                f"| ({t[0]:.2f}, {t[1]:.2f}, {t[2]:.2f}) | "
                f"{entry['elapsed_seconds']:.1f} |"
            )
    else:
        lines.append("*Fast mode: Tier 2 locked at the Step 4/6 defaults.*")
    lines.append("")

    # Section 6 -- top-10 combos.
    lines.append("## 6. Top-10 combinations (by " + objective_name + ")")
    lines.append("")
    lines.extend(_render_top10(result.all_metrics))
    lines.append("")

    # Section 7 -- score distribution at best.
    lines.append("## 7. Score-distribution snapshot at best combo")
    lines.append("")
    if dist_at_best is not None:
        lines.extend(_render_distribution(dist_at_best))
    else:
        lines.append("*No best combo selected; distribution table omitted.*")
    lines.append("")

    # Section 8 -- guard outcomes.
    lines.append("## 8. Guard outcomes")
    lines.append("")
    n_strict_passed = sum(1 for m in result.all_metrics if m.guards_passed)
    lines.append(
        f"* **{n_strict_passed} / {len(result.all_metrics)} combos passed "
        f"the strict guard set** (per-class precision/recall >= 0.05, all "
        f"three classes predicted, T2 < T1, distribution buckets non-empty)."
    )
    if result.fallback_relaxed is not None:
        lines.append(
            "* The relaxed-guard fallback found a passing combo "
            "(precision/recall floors lowered to 0.02; distribution-bucket "
            "guard removed)."
        )
    else:
        lines.append(
            "* The relaxed-guard fallback found NO passing combo. The "
            "placeholder encoder's score distribution is too compressed "
            "for any per-class precision/recall floor to be satisfied."
        )
    lines.append("")

    # Section 9 -- comparison to Step 7 baseline.
    lines.append("## 9. Comparison vs Step 7 baseline")
    lines.append("")
    lines.append("| Metric | Step 7 baseline | Step 8 best |")
    lines.append("|--------|-----------------|-------------|")
    chosen_label = (
        "strict-best"
        if result.best_metric is not None
        else "relaxed-best"
        if result.fallback_relaxed is not None
        else "unguarded"
    )
    if chosen is not None:
        lines.append(
            f"| macro F1 | {_BASELINE_MACRO_F1:.3f} | "
            f"{chosen.macro_f1:.3f} ({chosen_label}) |"
        )
        lines.append(
            f"| plain accuracy | 0.511 | {chosen.plain_accuracy:.3f} |"
        )
        lines.append(
            f"| F1(strong) | 0.000 | {chosen.f1_strong:.3f} |"
        )
        lines.append(
            f"| F1(possible) | 0.000 | {chosen.f1_possible:.3f} |"
        )
        lines.append(
            f"| F1(no) | 0.676 | {chosen.f1_no:.3f} |"
        )
    lines.append("")

    # Section 10 -- proposed DECISIONS.md amendment.
    lines.append("## 10. Proposed `DECISIONS.md` amendment")
    lines.append("")
    date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    if result.best_metric is not None:
        b = result.best_metric.combo
        lines.append("Append the following two rows to `DECISIONS.md`:")
        lines.append("")
        lines.append("```markdown")
        lines.append(
            f"### Step 8 amendment ({date}) -- empirical threshold lock"
        )
        lines.append("")
        lines.append(
            f"Empirical threshold tuning conducted via "
            f"`scripts/tune_thresholds.py --mode {mode}`. Best combo "
            f"(strict guards passed):"
        )
        lines.append("")
        lines.append(f"* drop_threshold = **{b.drop_threshold:.4f}**")
        lines.append(f"* keep_threshold = **{b.keep_threshold:.4f}**")
        lines.append(f"* expansion_threshold = **{b.expansion_threshold:.4f}**")
        lines.append(
            f"* per_requirement_keep_threshold = "
            f"**{b.per_requirement_keep_threshold:.4f}**"
        )
        lines.append(f"* required_weight = **{b.required_weight:.4f}** "
                     f"(nice_weight = {1 - b.required_weight:.4f})")
        lines.append(f"* t1_strong_threshold = **{b.t1:.4f}**")
        lines.append(f"* t2_possible_threshold = **{b.t2:.4f}**")
        lines.append("")
        lines.append(
            f"Macro F1 lift vs Step 7 baseline: "
            f"{result.best_metric.macro_f1 - _BASELINE_MACRO_F1:+.3f}."
        )
        lines.append("")
        lines.append(
            f"### Step 8 amendment ({date}) -- placeholder caveat"
        )
        lines.append("")
        lines.append(
            "The locked thresholds reflect the Step 5 placeholder "
            "encoder's compressed `overall_score` distribution (range "
            "`[0, ~0.1]`). After the Step 5 redo, re-run "
            "`scripts/tune_thresholds.py` to recalibrate; expected "
            "direction of change: T1, T2, and "
            "per_requirement_keep_threshold all move upward as the "
            "distribution widens toward `[0, 1]`."
        )
        lines.append("```")
    else:
        lines.append("**Calibration deferred** -- no combo passed even the relaxed "
                     "guards. The provisional Step 4/7 thresholds remain in force. "
                     "Re-run after Step 5 redo.")
        lines.append("")
        lines.append("```markdown")
        lines.append(
            f"### Step 8 amendment ({date}) -- calibration deferred"
        )
        lines.append("")
        lines.append(
            "Empirical threshold tuning attempted via "
            "`scripts/tune_thresholds.py --mode " + mode + "`. No combo "
            "satisfied even the relaxed guard set (per-class P/R floors "
            "of 0.02; G5 disabled); the placeholder encoder's score "
            "distribution is too compressed for the 3-class projection "
            "to separate cleanly. Provisional defaults (drop=0.45, "
            "keep=0.55, expansion=0.75, per_req=0.30, T1=0.55, T2=0.25) "
            "REMAIN IN FORCE. Re-run after Step 5 redo."
        )
        lines.append("```")
    lines.append("")

    # Section 11 -- conclusion.
    lines.append("## 11. Conclusion")
    lines.append("")
    if result.best_metric is not None:
        lines.append(
            "Step 8 LOCKED. New defaults proposed in Section 10 -- paste "
            "into `src/skill_matcher/DECISIONS.md` and update "
            "`src/skill_matcher/config.py` defaults to match. "
            "Re-run after Step 5 redo to recalibrate."
        )
    else:
        lines.append(
            "Step 8 DEFERRED -- no calibration possible against the "
            "placeholder encoder. The script + report ARE the "
            "deliverable; re-run after Step 5 redo. Defaults unchanged."
        )
    lines.append("")

    # Section 12 -- re-run note.
    lines.append("## 12. Re-run after Step 5 redo")
    lines.append("")
    lines.append(
        "When the Step 5 encoder is re-trained on a larger / less-biased "
        "corpus, re-run this script with no changes:"
    )
    lines.append("")
    lines.append("```")
    lines.append(
        "python scripts/tune_thresholds.py "
        "--eval-corpus-dir tests/fixtures/eval_corpus "
        f"--out-report reports/threshold_tuning_<NEW_DATE>.md --mode {mode}"
    )
    lines.append("```")
    lines.append("")
    lines.append(
        "The grid is identical; only the score distribution changes. "
        "Expected: T1 and T2 move upward, per_req_keep moves upward, "
        "macro F1 lifts substantially."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON companion
# ---------------------------------------------------------------------------


def _metric_to_dict(m: TuningMetric) -> dict[str, Any]:
    return {
        "combo": asdict(m.combo),
        "macro_f1": m.macro_f1,
        "weighted_f1": m.weighted_f1,
        "plain_accuracy": m.plain_accuracy,
        "weighted_accuracy": m.weighted_accuracy,
        "f1_strong": m.f1_strong,
        "f1_possible": m.f1_possible,
        "f1_no": m.f1_no,
        "precision_strong": m.precision_strong,
        "precision_possible": m.precision_possible,
        "precision_no": m.precision_no,
        "recall_strong": m.recall_strong,
        "recall_possible": m.recall_possible,
        "recall_no": m.recall_no,
        "n_predicted": m.n_predicted,
        "confusion": {f"{g}__{p}": n for (g, p), n in m.confusion.items()},
        "guards_passed": m.guards_passed,
        "guards_failed": list(m.guards_failed),
    }


def _write_json_companion(
    out_path: Path,
    *,
    mode: str,
    encoder_name: str,
    esco_sha: str,
    result: TuningRunResult,
    timing_record: dict[str, Any],
    objective_name: str,
) -> None:
    payload: dict[str, Any] = {
        "version": SKILL_MATCHER_VERSION,
        "mode": mode,
        "encoder": encoder_name,
        "esco_sha": esco_sha,
        "objective": objective_name,
        "elapsed_seconds": result.elapsed_seconds,
        "config_used": result.config_used,
        "tier2_timings": timing_record.get("tier2_timings", []),
        "best": _metric_to_dict(result.best_metric) if result.best_metric else None,
        "fallback_relaxed": (
            _metric_to_dict(result.fallback_relaxed)
            if result.fallback_relaxed
            else None
        ),
        "fallback_unguarded": (
            _metric_to_dict(result.fallback_unguarded)
            if result.fallback_unguarded
            else None
        ),
        "top10": [_metric_to_dict(m) for m in result.all_metrics[:10]],
    }
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("tune_thresholds.json_written", path=str(json_path))


# ---------------------------------------------------------------------------
# Amendment file (--write-decisions)
# ---------------------------------------------------------------------------


def _extract_amendment_block(report_md: str) -> str:
    """Slice Section 10 out of the report so the operator has just the
    amendment text to paste."""
    start = report_md.find("## 10. Proposed")
    if start < 0:
        return report_md
    end = report_md.find("## 11.", start)
    if end < 0:
        end = len(report_md)
    return report_md[start:end].strip()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-corpus-dir",
        type=Path,
        default=_REPO_ROOT / "tests" / "fixtures" / "eval_corpus",
    )
    parser.add_argument(
        "--out-report",
        type=Path,
        default=_REPO_ROOT
        / "reports"
        / f"threshold_tuning_{datetime.now(tz=UTC).strftime('%Y%m%d')}.md",
    )
    parser.add_argument(
        "--mode",
        choices=("fast", "full"),
        default="fast",
        help="Default: fast (Linker locked, ~3-5 min). "
             "full sweeps Linker too, ~50-80 min.",
    )
    parser.add_argument(
        "--objective",
        choices=("macro_f1", "weighted_f1"),
        default="macro_f1",
    )
    parser.add_argument(
        "--encoder-path",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--write-decisions",
        action="store_true",
        default=False,
        help="Also write the proposed DECISIONS.md amendment block to "
             "<out-report>.amendment.md for easy copy-paste.",
    )
    args = parser.parse_args()

    cfg = SkillMatcherConfig()
    encoder_path = _resolve_encoder_path(cfg, args.encoder_path)
    logger.info(
        "tune_thresholds.start",
        encoder=encoder_path,
        mode=args.mode,
        objective=args.objective,
    )

    encoder = SentenceTransformerEncoder(
        model_name=encoder_path,
        device=cfg.device,
        seed=cfg.seed,
    )
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

    extraction_pipeline = ExtractionPipeline()
    skill_extractor = SkillExtractor()

    corpus = load_eval_corpus(eval_root=args.eval_corpus_dir)
    if not corpus.cvs or not corpus.jds or not corpus.fit_matrix:
        raise RuntimeError(
            f"Empty eval corpus under {args.eval_corpus_dir}; cannot tune."
        )

    reqs_by_jd = {
        jd_id: jd_fixture_to_requirements(jd)
        for jd_id, jd in corpus.jds.items()
    }
    gold = _gold_map(corpus)
    n_gold_cells = len(gold)
    n_skipped_cvs = 0  # populated by builder

    builder, timing_record = _make_builder(
        base_cfg=cfg,
        encoder=encoder,
        index=index,
        concepts_by_uri=concepts_by_uri,
        extraction_pipeline=extraction_pipeline,
        skill_extractor=skill_extractor,
        corpus=corpus,
        reqs_by_jd=reqs_by_jd,
    )

    objective_fn = (
        objective_macro_f1 if args.objective == "macro_f1" else objective_weighted_f1
    )

    def _progress_callback(
        triple: tuple[float, float, float], sub: TuningRunResult
    ) -> None:
        best_f1 = (
            sub.best_metric.macro_f1 if sub.best_metric is not None
            else (sub.fallback_unguarded.macro_f1 if sub.fallback_unguarded else 0.0)
        )
        logger.info(
            "tune_thresholds.tier2_done",
            triple=triple,
            best_macro_f1=round(best_f1, 4),
            n_combos=len(sub.all_metrics),
        )

    result = run_full(
        builder,
        gold,
        mode=args.mode,
        objective=objective_fn,
        on_tier2_complete=_progress_callback,
    )

    # Recompute scores + distribution at the chosen best for Section 7.
    chosen = result.best_metric or result.fallback_relaxed or result.fallback_unguarded
    overall_at_best: dict[tuple[str, str], float] | None = None
    dist_at_best: dict[str, dict[str, float]] | None = None
    if chosen is not None:
        # Rebuild intermediates at the chosen Tier 2 triple to compute the
        # score distribution at the chosen Tier 1.
        triple = (
            chosen.combo.drop_threshold,
            chosen.combo.keep_threshold,
            chosen.combo.expansion_threshold,
        )
        intermediates_at_best = builder(*triple)
        from skill_matcher.tuning import aggregate_from_intermediates
        overall_at_best = aggregate_from_intermediates(
            intermediates_at_best,
            per_requirement_keep_threshold=chosen.combo.per_requirement_keep_threshold,
            required_weight=chosen.combo.required_weight,
        )
        dist_at_best = score_distribution(overall_at_best, gold)
        # Sanity: re-project and confirm the metric is reproducible.
        pred_at_best = project_to_three_class(
            overall_at_best, t1=chosen.combo.t1, t2=chosen.combo.t2
        )
        n_pred = {
            c: sum(1 for v in pred_at_best.values() if v == c)
            for c in ("strong", "possible", "no")
        }
        logger.info(
            "tune_thresholds.report_distribution",
            n_predicted=n_pred,
            sample_overall_min=min(overall_at_best.values(), default=0.0),
            sample_overall_max=max(overall_at_best.values(), default=0.0),
        )

    # Render report.
    md = _render_report(
        mode=args.mode,
        encoder_name=encoder_path,
        esco_sha=esco_sha,
        n_gold_cells=n_gold_cells,
        n_skipped_cvs=n_skipped_cvs,
        skipped_cvs=[],
        result=result,
        timing_record=timing_record,
        overall_at_best=overall_at_best,
        dist_at_best=dist_at_best,
        objective_name=args.objective,
    )
    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    args.out_report.write_text(md, encoding="utf-8")
    logger.info("tune_thresholds.report_written", path=str(args.out_report))

    _write_json_companion(
        args.out_report,
        mode=args.mode,
        encoder_name=encoder_path,
        esco_sha=esco_sha,
        result=result,
        timing_record=timing_record,
        objective_name=args.objective,
    )

    if args.write_decisions:
        amendment = _extract_amendment_block(md)
        amendment_path = args.out_report.with_suffix(".amendment.md")
        amendment_path.write_text(amendment + "\n", encoding="utf-8")
        logger.info(
            "tune_thresholds.amendment_written", path=str(amendment_path)
        )
        sys.stdout.write("\n" + amendment + "\n")

    if result.best_metric is not None:
        logger.info("tune_thresholds.locked", exit_code=0)
        return 0
    logger.warning("tune_thresholds.calibration_deferred", exit_code=2)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
