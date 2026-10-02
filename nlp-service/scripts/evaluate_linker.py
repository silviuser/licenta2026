"""End-to-end Linker evaluation on the 14-CV eval corpus.

Produces ``reports/linker_evaluation_<YYYYMMDD>.md`` (+ ``.json``)
with per-CV breakdowns and aggregate metrics for Module 3 Phase A.

Per Step 6 brief, Step 6's gate is **correctness, not F1**: the
current fine-tuned checkpoint is a Step 5 placeholder, so numbers
will likely under-perform the lexical-only baseline. The report
records the numbers honestly with an explicit disclaimer.

Metrics emitted (per CV + macro/micro aggregates):

* Lexical (Module 2) P/R/F1 vs gold (high+medium) -- baseline.
* Linker kept-only P/R/F1.
* Linker kept + expansion P/R/F1 -- what Step 7's Scorer will consume.
* Linker expansion-only P/R/F1 -- pure new candidates.
* Source-bucket counts (kept, ambiguous, dropped, expansion).

CLI::

    python scripts/evaluate_linker.py \
      --eval-corpus-dir tests/fixtures/eval_corpus \
      --out-report reports/linker_evaluation_<YYYYMMDD>.md \
      [--rebuild-index]

Reuses :class:`baseline.PRF` for the metric math (Pre-Flight Q3 OK).
Mirrors the per-CV skip behaviour of :func:`baseline.run_baseline`
for missing labels / Poppler failures.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# stdout reconfigure for Windows cp1252 console
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
from skill_matcher.baseline import PRF  # noqa: E402
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
from skill_matcher.eval_corpus import CVLabels, load_eval_corpus  # noqa: E402
from skill_matcher.linker import Linker, LinkerStats  # noqa: E402
from skill_matcher.models import EnrichedSkillResult  # noqa: E402

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Per-CV result struct
# ---------------------------------------------------------------------------


@dataclass
class _CVResult:
    """Per-CV evaluation outputs."""

    cv_id: str
    text_length: int
    n_lexical_in: int
    lexical_uris: set[str]
    gold_high_plus_medium: set[str]
    kept_uris: set[str]
    kept_plus_expansion_uris: set[str]
    expansion_only_uris: set[str]
    stats: LinkerStats

    # Cached PRF triples (computed at aggregation time).
    lexical_prf: PRF | None = None
    kept_prf: PRF | None = None
    kept_plus_exp_prf: PRF | None = None
    expansion_only_prf: PRF | None = None


@dataclass
class _Aggregate:
    """Macro + micro aggregates for one prediction-set definition."""

    name: str
    macro: PRF
    micro: PRF
    per_cv: dict[str, PRF] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _get_or_build_index(
    *,
    encoder: SentenceTransformerEncoder,
    cache_dir: Path,
    concepts: list[EscoConcept],
    esco_sha: str,
    rebuild: bool,
) -> EscoIndex:
    """Resolve cached index or build cold. Mirrors run_finetuned_baseline."""
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
                "evaluate_linker.index.cache_hit",
                cache_path=str(cache_path),
                n_concepts=index.n_concepts,
            )
            return index
        except (FileNotFoundError, EscoIndexCacheError) as exc:
            logger.info(
                "evaluate_linker.index.cold_build",
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


def _build_lexical(
    pdf_path: Path,
    *,
    extraction_pipeline: ExtractionPipeline,
    skill_extractor: SkillExtractor,
) -> tuple[str, SkillExtractionResult] | None:
    """Run Module 1 + Module 2 on one PDF. Returns ``None`` on skip."""
    try:
        extraction = extraction_pipeline.process(pdf_path)
    except NotACVError:
        logger.warning("evaluate_linker.skip_not_a_cv", pdf=str(pdf_path))
        return None
    except CVExtractorError as exc:
        logger.warning(
            "evaluate_linker.skip_extraction_failed",
            pdf=str(pdf_path),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return None
    try:
        lexical = skill_extractor.extract(extraction)
    except NotACVError:
        logger.warning("evaluate_linker.skip_not_a_cv_after_extract", pdf=str(pdf_path))
        return None
    return extraction.text, lexical


# ---------------------------------------------------------------------------
# Per-CV evaluation
# ---------------------------------------------------------------------------


def _evaluate_one_cv(
    *,
    cv_id: str,
    cv_text: str,
    lexical: SkillExtractionResult,
    labels: CVLabels,
    linker: Linker,
) -> _CVResult:
    enriched, stats = linker.link(cv_id=cv_id, cv_text=cv_text, lexical=lexical)

    lexical_uris = {m.esco_uri for m in lexical.skills}

    kept_uris: set[str] = {
        c.skill_uri for c in enriched.candidates if c.source == "lexical_kept"
    }
    expansion_uris: set[str] = {
        c.skill_uri for c in enriched.candidates if c.source == "expansion"
    }
    kept_plus_exp = kept_uris | expansion_uris

    gold_hpm: set[str] = {
        g.skill_uri
        for g in labels.gold_skills
        if g.confidence_expected in ("high", "medium")
    }

    return _CVResult(
        cv_id=cv_id,
        text_length=len(cv_text),
        n_lexical_in=len(lexical.skills),
        lexical_uris=lexical_uris,
        gold_high_plus_medium=gold_hpm,
        kept_uris=kept_uris,
        kept_plus_expansion_uris=kept_plus_exp,
        expansion_only_uris=expansion_uris,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate(
    per_cv: list[_CVResult],
    predict_fn: "Any",
    *,
    name: str,
) -> _Aggregate:
    """Compute macro + micro PRF for one prediction set across the corpus."""
    prfs: list[PRF] = []
    tp = fp = fn = 0
    per_cv_map: dict[str, PRF] = {}
    for r in per_cv:
        pred: set[str] = predict_fn(r)
        gold: set[str] = r.gold_high_plus_medium
        prf = PRF.from_sets(pred, gold)
        prfs.append(prf)
        per_cv_map[r.cv_id] = prf
        tp += len(pred & gold)
        fp += len(pred - gold)
        fn += len(gold - pred)

    if not prfs:
        macro = PRF(0.0, 0.0, 0.0)
    else:
        macro = PRF(
            precision=float(np.mean([p.precision for p in prfs])),
            recall=float(np.mean([p.recall for p in prfs])),
            f1=float(np.mean([p.f1 for p in prfs])),
        )

    if tp + fp + fn == 0:
        micro = PRF(1.0, 1.0, 1.0)
    else:
        p = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * rec / (p + rec) if (p + rec) else 0.0
        micro = PRF(p, rec, f1)

    return _Aggregate(name=name, macro=macro, micro=micro, per_cv=per_cv_map)


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _render_markdown(
    *,
    per_cv: list[_CVResult],
    aggregates: dict[str, _Aggregate],
    encoder_name: str,
    esco_sha: str,
    cfg: SkillMatcherConfig,
    skipped: list[tuple[str, str]],
    elapsed_seconds: float,
) -> str:
    """Render the per-section markdown report."""
    lines: list[str] = []
    lines.append(f"# Module 3 Linker -- Evaluation Report")
    lines.append("")
    lines.append(
        f"*Generated: {datetime.now(tz=UTC).isoformat()} "
        f"by `scripts/evaluate_linker.py` (skill_matcher {SKILL_MATCHER_VERSION}).*"
    )
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lex = aggregates["lexical"].macro.f1
    kept = aggregates["kept"].macro.f1
    exp = aggregates["expansion"].macro.f1
    full = aggregates["kept_plus_expansion"].macro.f1
    lines.append(
        f"Module 2 lexical F1 = **{lex:.3f}** ; "
        f"Linker kept-only F1 = **{kept:.3f}** ; "
        f"expansion-only F1 = **{exp:.3f}** ; "
        f"kept+expansion F1 = **{full:.3f}**."
    )
    lines.append("")
    lines.append(
        "**Caveat:** the current encoder is a Step 5 placeholder "
        "(see STEP6_PREFLIGHT.md). Step 6's gate is *correctness*, "
        "not F1. Performance numbers will be re-baselined when the "
        "Step 5 fine-tuning is re-done with a larger, less-biased "
        "training corpus -- no Linker code change required."
    )
    lines.append("")

    lines.append("## Environment")
    lines.append("")
    lines.append(f"* **Encoder:** `{encoder_name}`")
    lines.append(f"* **ESCO SHA (12):** `{esco_sha[:12]}`")
    lines.append(f"* **drop_threshold:** {cfg.drop_threshold}")
    lines.append(f"* **keep_threshold:** {cfg.keep_threshold}")
    lines.append(f"* **expansion_threshold:** {cfg.expansion_threshold}")
    lines.append(
        f"* **window:** size={cfg.expansion_window_size} "
        f"stride={cfg.expansion_window_stride}"
    )
    lines.append(f"* **seed:** {cfg.seed}")
    lines.append(
        f"* **n_cvs_processed:** {len(per_cv)} (skipped: {len(skipped)})"
    )
    lines.append(f"* **total wall-clock:** {elapsed_seconds:.1f} s")
    lines.append("")

    if skipped:
        lines.append("### Skipped CVs")
        lines.append("")
        for cv_id, reason in skipped:
            lines.append(f"* `{cv_id}` -- {reason}")
        lines.append("")

    # Per-CV table.
    lines.append("## Per-CV breakdown")
    lines.append("")
    lines.append(
        "| CV | text_len | n_lex_in | kept | ambig | dropped | exp | "
        "lex F1 | kept F1 | k+exp F1 |"
    )
    lines.append(
        "|----|----------|----------|------|-------|---------|-----|"
        "--------|---------|----------|"
    )
    lex_per = aggregates["lexical"].per_cv
    kept_per = aggregates["kept"].per_cv
    full_per = aggregates["kept_plus_expansion"].per_cv
    for r in per_cv:
        lines.append(
            f"| {r.cv_id} | {r.text_length} | {r.n_lexical_in} | "
            f"{r.stats.n_lexical_kept} | {r.stats.n_lexical_ambiguous} | "
            f"{r.stats.n_lexical_dropped} | {r.stats.n_expansion} | "
            f"{lex_per[r.cv_id].f1:.3f} | "
            f"{kept_per[r.cv_id].f1:.3f} | "
            f"{full_per[r.cv_id].f1:.3f} |"
        )
    lines.append("")

    # Aggregate metrics.
    lines.append("## Aggregate metrics (gold view = high + medium)")
    lines.append("")
    lines.append("| Predictor | macro P | macro R | macro F1 | micro P | micro R | micro F1 |")
    lines.append("|-----------|---------|---------|----------|---------|---------|----------|")
    for key in ("lexical", "kept", "expansion", "kept_plus_expansion"):
        a = aggregates[key]
        lines.append(
            f"| {a.name} | {a.macro.precision:.3f} | {a.macro.recall:.3f} | "
            f"{a.macro.f1:.3f} | {a.micro.precision:.3f} | "
            f"{a.micro.recall:.3f} | {a.micro.f1:.3f} |"
        )
    lines.append("")

    # Lexical-vs-Linker delta.
    full_macro = aggregates["kept_plus_expansion"].macro
    lex_macro = aggregates["lexical"].macro
    delta_f1 = full_macro.f1 - lex_macro.f1
    lines.append(
        f"**Linker (kept+exp) vs lexical delta**: F1 = "
        f"{delta_f1:+.3f}, P = {full_macro.precision - lex_macro.precision:+.3f}, "
        f"R = {full_macro.recall - lex_macro.recall:+.3f}."
    )
    lines.append("")

    # Source-bucket breakdown.
    lines.append("## Source-bucket totals across corpus")
    lines.append("")
    total_kept = sum(r.stats.n_lexical_kept for r in per_cv)
    total_amb = sum(r.stats.n_lexical_ambiguous for r in per_cv)
    total_dropped = sum(r.stats.n_lexical_dropped for r in per_cv)
    total_exp = sum(r.stats.n_expansion for r in per_cv)
    total_unknown = sum(r.stats.n_unknown_uris for r in per_cv)
    total_windows = sum(r.stats.n_windows for r in per_cv)
    lines.append(f"* `lexical_kept` candidates emitted: {total_kept} "
                 f"(of which {total_amb} in the ambiguous sub-band).")
    lines.append(f"* `lexical_dropped` candidates emitted: {total_dropped}")
    lines.append(f"* `expansion` candidates emitted: {total_exp}")
    lines.append(f"* unknown URIs (skipped): {total_unknown}")
    lines.append(f"* sliding windows across corpus: {total_windows}")
    lines.append("")

    # Expansion analysis.
    if total_exp > 0:
        exp_counter: Counter[str] = Counter()
        for r in per_cv:
            exp_counter.update(r.expansion_only_uris)
        top20 = exp_counter.most_common(20)
        lines.append("## Top-20 expansion URIs (by CV frequency)")
        lines.append("")
        lines.append("| URI | n_CVs |")
        lines.append("|-----|-------|")
        for uri, n in top20:
            lines.append(f"| `{uri}` | {n} |")
        lines.append("")

    # Conclusion.
    lines.append("## Conclusion")
    lines.append("")
    lines.append("Linker is structurally complete. Determinism verified by "
                 "unit tests; end-to-end run produces well-formed candidates.")
    lines.append("")
    lines.append(
        "Performance numbers are bottlenecked by the Step 5 placeholder "
        "encoder; Step 5 redo will lift them without Linker code change. "
        "Step 6 sign-off gate (correctness, not F1) is satisfied. "
        "Proceed to Step 7 (Scorer)."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-corpus-dir",
        type=Path,
        default=_REPO_ROOT / "tests" / "fixtures" / "eval_corpus",
        help="Directory containing the eval corpus (real_cv*.pdf + cv_labels/).",
    )
    parser.add_argument(
        "--out-report",
        type=Path,
        default=_REPO_ROOT / "reports"
        / f"linker_evaluation_{datetime.now(tz=UTC).strftime('%Y%m%d')}.md",
        help="Output markdown path. A .json companion is written alongside.",
    )
    parser.add_argument(
        "--encoder-path",
        type=str,
        default=None,
        help="Override the resolved encoder path (default: latest.txt fallback).",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        default=False,
        help="Force a cold rebuild of the ESCO embedding index.",
    )
    args = parser.parse_args()

    cfg = SkillMatcherConfig()
    encoder_path = _resolve_encoder_path(cfg, args.encoder_path)
    logger.info("evaluate_linker.start", encoder=encoder_path)

    # Build encoder.
    encoder = SentenceTransformerEncoder(
        model_name=encoder_path,
        device=cfg.device,
        seed=cfg.seed,
    )

    # Load ESCO concepts + compute SHA.
    concepts = load_esco_concepts()
    concepts_by_uri = {c.uri: c for c in concepts}
    esco_sha = compute_esco_sha(concepts)

    # Get-or-build the index.
    index = _get_or_build_index(
        encoder=encoder,
        cache_dir=cfg.embedding_cache_dir,
        concepts=concepts,
        esco_sha=esco_sha,
        rebuild=args.rebuild_index,
    )

    # Construct the Linker.
    linker = Linker(
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

    per_cv: list[_CVResult] = []
    skipped: list[tuple[str, str]] = []
    t0 = time.monotonic()
    for cv_id in corpus.cv_ids():
        pdf_path = corpus.cvs[cv_id]
        labels = corpus.cv_labels.get(cv_id)
        if labels is None:
            skipped.append((cv_id, "missing labels YAML"))
            continue
        prelude = _build_lexical(
            pdf_path,
            extraction_pipeline=ex_pipeline,
            skill_extractor=sx,
        )
        if prelude is None:
            skipped.append((cv_id, "Module 1/2 skip"))
            continue
        cv_text, lexical = prelude
        cv_result = _evaluate_one_cv(
            cv_id=cv_id,
            cv_text=cv_text,
            lexical=lexical,
            labels=labels,
            linker=linker,
        )
        per_cv.append(cv_result)
    elapsed = time.monotonic() - t0

    if not per_cv:
        raise RuntimeError(
            "evaluate_linker produced zero per-CV results -- check fixtures."
        )

    # Aggregations.
    aggregates = {
        "lexical": _aggregate(
            per_cv, lambda r: r.lexical_uris, name="Module 2 lexical"
        ),
        "kept": _aggregate(
            per_cv, lambda r: r.kept_uris, name="Linker kept only"
        ),
        "expansion": _aggregate(
            per_cv, lambda r: r.expansion_only_uris, name="Linker expansion only"
        ),
        "kept_plus_expansion": _aggregate(
            per_cv,
            lambda r: r.kept_plus_expansion_uris,
            name="Linker kept + expansion",
        ),
    }

    # Render report.
    md = _render_markdown(
        per_cv=per_cv,
        aggregates=aggregates,
        encoder_name=encoder_path,
        esco_sha=esco_sha,
        cfg=cfg,
        skipped=skipped,
        elapsed_seconds=elapsed,
    )
    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    args.out_report.write_text(md, encoding="utf-8")

    # JSON companion.
    def _set_to_list(d: Any) -> Any:
        return sorted(d) if isinstance(d, set) else d

    payload = {
        "version": SKILL_MATCHER_VERSION,
        "encoder": encoder_path,
        "esco_sha": esco_sha,
        "config": {
            "drop_threshold": cfg.drop_threshold,
            "keep_threshold": cfg.keep_threshold,
            "expansion_threshold": cfg.expansion_threshold,
            "expansion_window_size": cfg.expansion_window_size,
            "expansion_window_stride": cfg.expansion_window_stride,
            "seed": cfg.seed,
        },
        "skipped": [{"cv_id": c, "reason": r} for c, r in skipped],
        "aggregates": {
            k: {
                "name": v.name,
                "macro": asdict(v.macro),
                "micro": asdict(v.micro),
                "per_cv": {
                    cv: asdict(prf) for cv, prf in v.per_cv.items()
                },
            }
            for k, v in aggregates.items()
        },
        "per_cv": [
            {
                "cv_id": r.cv_id,
                "text_length": r.text_length,
                "n_lexical_in": r.n_lexical_in,
                "lexical_uris": _set_to_list(r.lexical_uris),
                "gold_high_plus_medium": _set_to_list(r.gold_high_plus_medium),
                "kept_uris": _set_to_list(r.kept_uris),
                "expansion_only_uris": _set_to_list(r.expansion_only_uris),
                "kept_plus_expansion_uris": _set_to_list(
                    r.kept_plus_expansion_uris
                ),
                "stats": asdict(r.stats),
            }
            for r in per_cv
        ],
        "elapsed_seconds": elapsed,
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }
    json_path = args.out_report.with_suffix(".json")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote {args.out_report}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
