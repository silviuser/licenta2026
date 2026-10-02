"""Step 4 zero-shot baseline runner.

Builds (or reloads) the ESCO embedding index, runs the baseline over
the held-out 15-CV eval corpus, and writes the markdown +
machine-readable JSON reports under ``nlp-service/reports/``.

Usage (Windows PowerShell, from ``nlp-service/``)::

    .\\.venv\\Scripts\\Activate.ps1
    python scripts\\run_zero_shot_baseline.py `
      --eval-corpus-dir tests\\fixtures\\eval_corpus `
      --out-report reports\\skill_matcher_baseline_20260516.md

The script is idempotent: cached index files at
``nlp-service/.cache/embeddings/esco_<model_sha>_<esco_sha>_<fmt>.npz``
are reused. Pass ``--rebuild-index`` to force a cold encode.

Concept-text format
-------------------
Defaults to ``bounded-a``. The Step 4 *ablation* run sweeps all three
locked formats and reports headline numbers per variant (see
``--ablation``); the chosen winner is recorded in
``src/skill_matcher/DECISIONS.md`` as an amendment-log row.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# stdout reconfigure for Windows cp1252 console — Romanian filenames break it.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, OSError):
    pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

import structlog  # noqa: E402

from cv_extractor import ExtractionPipeline  # noqa: E402

from skill_extractor import SkillExtractor  # noqa: E402
from skill_matcher import __version__ as SKILL_MATCHER_VERSION  # noqa: E402
from skill_matcher.baseline import (  # noqa: E402
    BaselineMetrics,
    PRF,
    run_baseline,
    threshold_sweep,
)
from skill_matcher.config import SkillMatcherConfig  # noqa: E402
from skill_matcher.encoder import SentenceTransformerEncoder  # noqa: E402
from skill_matcher.esco_index import (  # noqa: E402
    ConceptTextFormat,
    EscoIndex,
    EscoIndexCacheError,
    cache_filename,
    compute_model_sha,
)
from skill_matcher.esco_loader import (  # noqa: E402
    EscoConcept,
    compute_esco_file_sha,
    load_esco_concepts,
)
from skill_matcher.eval_corpus import (  # noqa: E402
    DEFAULT_EVAL_CORPUS_ROOT,
    load_eval_corpus,
)

logger = structlog.get_logger("run_zero_shot_baseline")


# Threshold ablation: extended down to 0.40 so the headline pick has
# room below the original 0.55 floor. The first real-baseline run
# (2026-05-16) showed macro-F1 = 0.073 at threshold 0.65 (P=0.48,
# R=0.05) — the threshold is the binding constraint, not the encoder.
THRESHOLD_ABLATION = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75)
TOP_K_ABLATION = (1, 3, 5, 10)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Module 3 zero-shot baseline."
    )
    parser.add_argument(
        "--eval-corpus-dir",
        type=Path,
        default=DEFAULT_EVAL_CORPUS_ROOT,
        help="Eval-corpus root (defaults to tests/fixtures/eval_corpus).",
    )
    parser.add_argument(
        "--out-report",
        type=Path,
        default=None,
        help=(
            "Markdown report path. Defaults to "
            "reports/skill_matcher_baseline_<YYYYMMDD>.md."
        ),
    )
    parser.add_argument(
        "--window-size-tokens",
        type=int,
        default=30,
        help="Sliding-window width in tokens (default: 30).",
    )
    parser.add_argument(
        "--window-stride-tokens",
        type=int,
        default=15,
        help="Sliding-window stride in tokens (default: 15).",
    )
    parser.add_argument(
        "--semantic-threshold",
        type=float,
        default=0.65,
        help="Cosine-similarity threshold for the headline metric (default: 0.65).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Top-k retrievals per sliding window (default: 5).",
    )
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "auto"],
        default="cpu",
        help="Encoder device (default: cpu).",
    )
    parser.add_argument(
        "--concept-text-format",
        choices=["bounded-a", "b", "c"],
        default="bounded-a",
        help="Concept-text format for the index (default: bounded-a).",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Force a fresh cold build of the embedding index.",
    )
    parser.add_argument(
        "--ablation",
        action="store_true",
        help=(
            "Run the Step 4 concept-text + stride ablations. Builds "
            "three indexes (bounded-a/b/c) and runs baseline on each "
            "at strides {8, 15, 30}. Adds an Ablation section to the "
            "report."
        ),
    )
    return parser.parse_args(argv)


def default_report_path() -> Path:
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    return _REPO_ROOT / "reports" / f"skill_matcher_baseline_{today}.md"


def get_or_build_index(
    *,
    encoder: SentenceTransformerEncoder,
    concepts: list[EscoConcept],
    cache_dir: Path,
    fmt: ConceptTextFormat,
    esco_sha: str,
    rebuild: bool,
) -> tuple[EscoIndex, float, bool]:
    """Return (index, elapsed_seconds, was_cold_build)."""
    model_sha = compute_model_sha(
        model_name=encoder.model_name,
        finetuned_model_path=None,
    )
    cache_path = cache_dir / cache_filename(
        model_sha=model_sha, esco_sha=esco_sha, fmt=fmt
    )
    index = EscoIndex(encoder=encoder, cache_dir=cache_dir)

    if not rebuild and cache_path.exists():
        try:
            t0 = time.monotonic()
            index.load(
                cache_path,
                expected_esco_sha=esco_sha,
                expected_format=fmt,
            )
            elapsed = time.monotonic() - t0
            logger.info(
                "index.warm_load",
                path=str(cache_path),
                elapsed_seconds=round(elapsed, 3),
            )
            return index, elapsed, False
        except EscoIndexCacheError as exc:
            logger.warning(
                "index.cache_invalid",
                path=str(cache_path),
                error=str(exc),
            )

    t0 = time.monotonic()
    index.build(concepts, fmt=fmt, batch_size=64)
    index.save(
        cache_path,
        esco_sha=esco_sha,
        skill_matcher_version=SKILL_MATCHER_VERSION,
    )
    elapsed = time.monotonic() - t0
    logger.info(
        "index.cold_build",
        path=str(cache_path),
        n_concepts=index.n_concepts,
        elapsed_seconds=round(elapsed, 3),
    )
    return index, elapsed, True


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _prf_to_dict(prf: PRF) -> dict[str, float]:
    return {
        "precision": round(prf.precision, 4),
        "recall": round(prf.recall, 4),
        "f1": round(prf.f1, 4),
    }


def metrics_to_json(
    metrics: BaselineMetrics,
    *,
    environment: dict[str, Any],
    index_timing: dict[str, Any],
    ablation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render BaselineMetrics into a machine-readable JSON-able dict."""
    out: dict[str, Any] = {
        "environment": environment,
        "index_timing": index_timing,
        "config": metrics.config,
        "headline": {
            "view": metrics.headline.view,
            "threshold": metrics.headline.threshold,
            "top_k": metrics.headline.top_k,
            "lexical_macro": _prf_to_dict(metrics.headline.lexical_macro),
            "semantic_macro": _prf_to_dict(metrics.headline.semantic_macro),
            "ensemble_macro": _prf_to_dict(metrics.headline.ensemble_macro),
            "lexical_micro": _prf_to_dict(metrics.headline.lexical_micro),
            "semantic_micro": _prf_to_dict(metrics.headline.semantic_micro),
            "ensemble_micro": _prf_to_dict(metrics.headline.ensemble_micro),
        },
        "by_view": {
            view_name: {
                "view": view.view,
                "threshold": view.threshold,
                "top_k": view.top_k,
                "lexical_macro": _prf_to_dict(view.lexical_macro),
                "semantic_macro": _prf_to_dict(view.semantic_macro),
                "ensemble_macro": _prf_to_dict(view.ensemble_macro),
                "lexical_micro": _prf_to_dict(view.lexical_micro),
                "semantic_micro": _prf_to_dict(view.semantic_micro),
                "ensemble_micro": _prf_to_dict(view.ensemble_micro),
                "per_cv_semantic": {
                    cv_id: _prf_to_dict(prf)
                    for cv_id, prf in sorted(view.per_cv_semantic.items())
                },
            }
            for view_name, view in metrics.by_view.items()
        },
        "per_cv": [
            {
                "cv_id": r.cv_id,
                "text_length": r.text_length,
                "n_windows": r.n_windows,
                "elapsed_seconds": round(r.elapsed_seconds, 3),
                "lexical_count": len(r.lexical_uris),
                "gold_high_count": len(r.gold_high),
                "gold_high_plus_medium_count": len(r.gold_high_plus_medium),
                "semantic_count_default_threshold": sum(
                    1
                    for s in r.semantic_max_similarity.values()
                    if s >= metrics.headline.threshold
                ),
            }
            for r in metrics.per_cv
        ],
    }
    if ablation is not None:
        out["ablation"] = ablation
    return out


def _fmt_prf(prf: PRF) -> str:
    return f"{prf.precision:.3f} / {prf.recall:.3f} / {prf.f1:.3f}"


def render_report(
    metrics: BaselineMetrics,
    *,
    environment: dict[str, Any],
    index_timing: dict[str, Any],
    ablation: dict[str, Any] | None = None,
) -> str:
    """Render the human-readable markdown baseline report."""
    h = metrics.by_view["high_plus_medium"]
    high = metrics.by_view["high"]
    cfg = metrics.config

    lines: list[str] = []
    lines.append("# Module 3 — Zero-Shot Baseline Report")
    lines.append("")
    lines.append(f"_Generated: {datetime.now(tz=timezone.utc).isoformat()}_")
    lines.append("")

    # 1. Executive summary
    lines.append("## 1. Executive summary")
    lines.append("")
    lines.append(
        f"Zero-shot semantic retrieval reaches **macro F1 = {h.semantic_macro.f1:.3f}** "
        f"on the 15-CV held-out eval corpus at threshold "
        f"{h.threshold:.2f} (gold view: `high + medium`). "
        "Module 2 lexical floor (May 2026 patch round) is F1 = 0.766. "
        "The Step 4 baseline establishes the floor against which "
        "Step 5 fine-tuning will be measured."
    )
    lines.append("")

    # 2. Environment
    lines.append("## 2. Environment")
    lines.append("")
    for key, value in environment.items():
        lines.append(f"- **{key}**: `{value}`")
    lines.append("")

    # 3. Index build
    lines.append("## 3. Index build")
    lines.append("")
    for key, value in index_timing.items():
        lines.append(f"- **{key}**: `{value}`")
    lines.append("")

    # 4. Per-CV table — paired high vs high+medium columns
    lines.append("## 4. Per-CV breakdown")
    lines.append("")
    lines.append(
        "| CV | windows | gold(h) | gold(h+m) | Lex P/R/F1 (h+m) "
        "| Sem P/R/F1 (h) | Sem P/R/F1 (h+m) |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|"
    )
    for r in metrics.per_cv:
        lex_prf = PRF.from_sets(r.lexical_uris, r.gold_high_plus_medium)
        sem_h = high.per_cv_semantic.get(r.cv_id, PRF(0, 0, 0))
        sem_hm = h.per_cv_semantic.get(r.cv_id, PRF(0, 0, 0))
        lines.append(
            f"| {r.cv_id} | {r.n_windows} | {len(r.gold_high)} "
            f"| {len(r.gold_high_plus_medium)} | {_fmt_prf(lex_prf)} "
            f"| {_fmt_prf(sem_h)} | {_fmt_prf(sem_hm)} |"
        )
    lines.append("")

    # 5. Aggregate metrics
    lines.append("## 5. Aggregate metrics")
    lines.append("")
    for view_name, view in metrics.by_view.items():
        lines.append(f"### View: `{view_name}` "
                     f"(threshold={view.threshold:.2f}, top_k={view.top_k})")
        lines.append("")
        lines.append("| Source | Macro P/R/F1 | Micro P/R/F1 |")
        lines.append("|---|---|---|")
        lines.append(
            f"| Lexical (Module 2) | {_fmt_prf(view.lexical_macro)} "
            f"| {_fmt_prf(view.lexical_micro)} |"
        )
        lines.append(
            f"| Semantic (Module 3 expansion) | {_fmt_prf(view.semantic_macro)} "
            f"| {_fmt_prf(view.semantic_micro)} |"
        )
        lines.append(
            f"| Ensemble (lex ∪ sem) | {_fmt_prf(view.ensemble_macro)} "
            f"| {_fmt_prf(view.ensemble_micro)} |"
        )
        lines.append("")

    # 6. Threshold ablation
    lines.append("## 6. Threshold ablation (gold view: `high + medium`)")
    lines.append("")
    sweep = threshold_sweep(
        metrics, THRESHOLD_ABLATION, view="high_plus_medium"
    )
    lines.append("| Threshold | Macro P | Macro R | Macro F1 |")
    lines.append("|---|---|---|---|")
    for t in THRESHOLD_ABLATION:
        prf = sweep[float(t)]
        lines.append(
            f"| {t:.2f} | {prf.precision:.3f} | {prf.recall:.3f} | {prf.f1:.3f} |"
        )
    lines.append("")

    # 7. Top-k ablation
    lines.append("## 7. Top-k ablation")
    lines.append("")
    lines.append(
        "_Top-k ablation requires re-running retrieval; not free at report-render time. "
        "Run the CLI with different `--top-k` values to populate this section per-row, "
        "or use `--ablation` for the full ablation pass._"
    )
    lines.append("")

    # 8. Optional ablation block (only when --ablation was used)
    if ablation is not None:
        lines.append("## 8. Step-4 ablation: concept-text format + stride")
        lines.append("")
        lines.append(
            "| Concept-text fmt | Stride | Macro P (h+m) | Macro R (h+m) | Macro F1 (h+m) |"
        )
        lines.append("|---|---|---|---|---|")
        for row in ablation["rows"]:
            lines.append(
                f"| {row['fmt']} | {row['stride']} | {row['precision']:.3f} "
                f"| {row['recall']:.3f} | {row['f1']:.3f} |"
            )
        lines.append("")
        if "winner" in ablation:
            w = ablation["winner"]
            lines.append(
                f"**Winner:** `{w['fmt']}` with stride `{w['stride']}` — "
                f"macro F1 = {w['f1']:.3f}."
            )
            lines.append("")

    # 9. Qualitative failure modes (placeholder — manually filled per CV)
    lines.append("## 9. Qualitative failure modes")
    lines.append("")
    lines.append(
        "_To populate manually: pick 5+ examples where a gold URI was "
        "NOT retrieved at any threshold and document the CV span vs the "
        "missed URI's preferred label, plus a one-line hypothesis. "
        "This feeds Step 6 expansion-stage design (Linker)._"
    )
    lines.append("")

    # 10. Conclusion
    lines.append("## 10. Conclusion")
    lines.append("")
    lines.append(
        f"Zero-shot macro F1 of {h.semantic_macro.f1:.3f} establishes the "
        "Step 4 floor. Step 5 fine-tuning proceeds regardless of this "
        "number (per DECISIONS.md D7); only post-fine-tune F1 < 0.55 "
        "triggers the conditional Step 5b cross-encoder."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _format_concepts_for_env(concepts: list[EscoConcept]) -> dict[str, int]:
    counts: dict[str, int] = {"total": len(concepts), "custom": 0}
    for c in concepts:
        if c.is_custom:
            counts["custom"] += 1
        counts[c.skill_type] = counts.get(c.skill_type, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    cfg = SkillMatcherConfig()
    cache_dir = cfg.embedding_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    out_report = args.out_report or default_report_path()
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_json = out_report.with_suffix(".json")

    logger.info(
        "run.start",
        eval_corpus_dir=str(args.eval_corpus_dir),
        out_report=str(out_report),
        out_json=str(out_json),
    )

    encoder = SentenceTransformerEncoder(
        model_name=cfg.base_model,
        device=args.device,
        seed=cfg.seed,
    )
    # Trigger lazy load early so the rest of the script has a known dim.
    _ = encoder.embedding_dim

    concepts = load_esco_concepts(include_custom_overlay=True)
    esco_sha = compute_esco_file_sha(include_custom_overlay=True)

    environment = {
        "python_version": sys.version.split()[0],
        "model_name": encoder.model_name,
        "embedding_dim": encoder.embedding_dim,
        "device": args.device,
        "concept_counts": _format_concepts_for_env(concepts),
        "esco_file_sha": esco_sha,
        "skill_matcher_version": SKILL_MATCHER_VERSION,
        "seed": cfg.seed,
    }

    # --- Headline run ----------------------------------------------------
    fmt: ConceptTextFormat = args.concept_text_format
    index, build_elapsed, was_cold = get_or_build_index(
        encoder=encoder,
        concepts=concepts,
        cache_dir=cache_dir,
        fmt=fmt,
        esco_sha=esco_sha,
        rebuild=args.rebuild_index,
    )

    index_timing = {
        "cold_build": was_cold,
        "elapsed_seconds": round(build_elapsed, 3),
        "n_concepts": index.n_concepts,
        "embedding_dim": index.embedding_dim,
        "concept_text_format": index.concept_text_format,
    }

    eval_corpus = load_eval_corpus(eval_root=args.eval_corpus_dir)
    metrics = run_baseline(
        eval_corpus=eval_corpus,
        encoder=encoder,
        index=index,
        window_size_tokens=args.window_size_tokens,
        window_stride_tokens=args.window_stride_tokens,
        semantic_threshold=args.semantic_threshold,
        top_k_per_window=args.top_k,
    )

    # --- Ablation (optional) ---------------------------------------------
    ablation_payload: dict[str, Any] | None = None
    if args.ablation:
        ablation_payload = _run_ablation(
            encoder=encoder,
            concepts=concepts,
            cache_dir=cache_dir,
            esco_sha=esco_sha,
            eval_corpus=eval_corpus,
            window_size_tokens=args.window_size_tokens,
            semantic_threshold=args.semantic_threshold,
            top_k=args.top_k,
            rebuild=args.rebuild_index,
        )

    # --- Render reports --------------------------------------------------
    report_md = render_report(
        metrics,
        environment=environment,
        index_timing=index_timing,
        ablation=ablation_payload,
    )
    out_report.write_text(report_md, encoding="utf-8")

    payload = metrics_to_json(
        metrics,
        environment=environment,
        index_timing=index_timing,
        ablation=ablation_payload,
    )
    out_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    logger.info(
        "run.complete",
        out_report=str(out_report),
        out_json=str(out_json),
        headline_macro_f1=round(metrics.headline.semantic_macro.f1, 4),
    )
    return 0


def _run_ablation(
    *,
    encoder: SentenceTransformerEncoder,
    concepts: list[EscoConcept],
    cache_dir: Path,
    esco_sha: str,
    eval_corpus: Any,
    window_size_tokens: int,
    semantic_threshold: float,
    top_k: int,
    rebuild: bool,
) -> dict[str, Any]:
    """Concept-text x stride ablation. Returns ablation payload dict."""
    fmts: tuple[ConceptTextFormat, ...] = ("bounded-a", "b", "c")
    strides = (8, 15, 30)
    rows: list[dict[str, Any]] = []
    winner: dict[str, Any] | None = None

    for fmt in fmts:
        index, _, _ = get_or_build_index(
            encoder=encoder,
            concepts=concepts,
            cache_dir=cache_dir,
            fmt=fmt,
            esco_sha=esco_sha,
            rebuild=rebuild,
        )
        for stride in strides:
            metrics = run_baseline(
                eval_corpus=eval_corpus,
                encoder=encoder,
                index=index,
                window_size_tokens=window_size_tokens,
                window_stride_tokens=stride,
                semantic_threshold=semantic_threshold,
                top_k_per_window=top_k,
            )
            prf = metrics.headline.semantic_macro
            row = {
                "fmt": fmt,
                "stride": stride,
                "precision": round(prf.precision, 4),
                "recall": round(prf.recall, 4),
                "f1": round(prf.f1, 4),
            }
            rows.append(row)
            if winner is None or prf.f1 > winner["f1"]:
                winner = row
            logger.info("ablation.row", **row)

    return {"rows": rows, "winner": winner}


if __name__ == "__main__":
    raise SystemExit(main())
