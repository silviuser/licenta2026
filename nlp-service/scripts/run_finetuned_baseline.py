"""Phase Gamma — re-run the Step 4 baseline with the fine-tuned encoder.

Produces ``reports/skill_matcher_finetuned_<YYYYMMDD>.md`` with a side-by-
side comparison of zero-shot vs fine-tuned macro/micro metrics on the
held-out 15-CV eval corpus. The script is the Step 5 sign-off gate:

* Macro F1 >= 0.55 (on ``high_plus_medium`` view) -> Step 6 (Linker).
* Macro F1 <  0.55 -> open Step 5b (cross-encoder re-ranker).

Workflow
--------
1. Resolve the fine-tuned checkpoint via ``--run-name`` or
   ``models/skill_matcher/latest.txt``.
2. Build (or load from cache) the ESCO index for both the zero-shot
   base model and the fine-tuned checkpoint. The Step 4 cache key
   includes a ``model_sha12`` derived from
   ``sha256(model_name + finetuned_model_path)``, so the fine-tuned
   path gets its own cache filename automatically -- no manual flush.
3. Run :func:`baseline.run_baseline` for each encoder over the same
   eval corpus. Reuses the Step 4 implementation verbatim (D8).
4. Render the comparison report with headline / per-CV-delta /
   threshold-ablation / qualitative-wins-and-regressions sections.

CLI
---
Run from ``nlp-service/``::

    python scripts/run_finetuned_baseline.py \
      [--run-name mnrl_v1_20260516_1610] \
      --eval-corpus-dir tests/fixtures/eval_corpus \
      --out-report reports/skill_matcher_finetuned_<YYYYMMDD>.md

Idempotency: cached indices at
``nlp-service/.cache/embeddings/esco_<model_sha>_<esco_sha>_bounded-a.npz``
are reused. Pass ``--rebuild-index`` to force a fresh cold build (~12-15
min on CPU per encoder).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
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

import structlog  # noqa: E402

from skill_matcher import __version__ as SKILL_MATCHER_VERSION  # noqa: E402
from skill_matcher.baseline import (  # noqa: E402
    BaselineMetrics,
    PRF,
    ViewMetrics,
    run_baseline,
    threshold_sweep,
)
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
    compute_esco_file_sha,
    load_esco_concepts,
)
from skill_matcher.eval_corpus import (  # noqa: E402
    DEFAULT_EVAL_CORPUS_ROOT,
    load_eval_corpus,
)

logger = structlog.get_logger("run_finetuned_baseline")


_BASE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_MODELS_DIR = _REPO_ROOT / "models" / "skill_matcher"
_LATEST_FILE = _MODELS_DIR / "latest.txt"
_DEFAULT_FORMAT = "bounded-a"

_THRESHOLD_ABLATION = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75)
_REGRESSION_THRESHOLD = 0.05
"""Per-CV F1 delta below ``-_REGRESSION_THRESHOLD`` counts as a regression."""

_QUALITATIVE_WIN_THRESHOLD = 0.10
"""Per-CV F1 delta above ``+_QUALITATIVE_WIN_THRESHOLD`` counts as a win."""

_GO_FOR_STEP_6_MACRO_F1 = 0.55
"""DECISIONS.md D7: macro F1 >= 0.55 -> Step 6; else Step 5b."""


# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Step 4 baseline with the fine-tuned encoder."
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default=None,
        help=(
            "Fine-tuned run name (defaults to contents of "
            "models/skill_matcher/latest.txt)."
        ),
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
            "reports/skill_matcher_finetuned_<YYYYMMDD>.md."
        ),
    )
    parser.add_argument(
        "--semantic-threshold",
        type=float,
        default=0.55,
        help=(
            "Cosine threshold for the headline metric (default: 0.55, "
            "locked at Step 4 sign-off)."
        ),
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Top-k retrievals per sliding window (default: 5).",
    )
    parser.add_argument(
        "--window-stride-tokens",
        type=int,
        default=15,
        help="Sliding-window stride in tokens (default: 15, Step 4 winner).",
    )
    parser.add_argument(
        "--window-size-tokens",
        type=int,
        default=30,
        help="Sliding-window width in tokens (default: 30).",
    )
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "auto"],
        default="cpu",
        help="Encoder device (default: cpu).",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Force a fresh cold build of both ESCO indexes.",
    )
    parser.add_argument(
        "--skip-zero-shot",
        action="store_true",
        help=(
            "Skip the zero-shot baseline re-run (use this only if you "
            "already have its results cached and just want the fine-tuned "
            "numbers in the report)."
        ),
    )
    return parser.parse_args(argv)


def _default_report_path() -> Path:
    today = datetime.now(tz=UTC).strftime("%Y%m%d")
    return _REPO_ROOT / "reports" / f"skill_matcher_finetuned_{today}.md"


# ---------------------------------------------------------------------------
# Run-name resolution
# ---------------------------------------------------------------------------


def resolve_run_name(cli_run_name: str | None) -> str:
    """Return the run name, either from CLI or ``latest.txt``."""
    if cli_run_name:
        return cli_run_name
    if not _LATEST_FILE.exists():
        raise SystemExit(
            f"No --run-name given and {_LATEST_FILE} does not exist. "
            "Import a checkpoint first with scripts/import_finetuned_model.py."
        )
    name = _LATEST_FILE.read_text(encoding="utf-8").strip()
    if not name:
        raise SystemExit(f"{_LATEST_FILE} is empty.")
    return name


def resolve_checkpoint_path(run_name: str) -> Path:
    """Validate that ``models/skill_matcher/<run_name>/`` exists."""
    path = _MODELS_DIR / run_name
    if not path.is_dir():
        raise SystemExit(
            f"Checkpoint directory not found: {path}. "
            "Did you run scripts/import_finetuned_model.py?"
        )
    return path


# ---------------------------------------------------------------------------
# Index get-or-build (mirrors run_zero_shot_baseline.get_or_build_index)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _IndexResult:
    index: EscoIndex
    elapsed_seconds: float
    was_cold_build: bool
    cache_path: Path


def _get_or_build_index(
    *,
    encoder: SentenceTransformerEncoder,
    finetuned_path: Path | None,
    concepts: list[EscoConcept],
    cache_dir: Path,
    esco_sha: str,
    rebuild: bool,
) -> _IndexResult:
    """Build (or load) the ESCO index for ``encoder``.

    The cache filename derives from ``compute_model_sha(model_name,
    finetuned_path)`` so the zero-shot and fine-tuned indexes get
    different filenames automatically -- no manual flush required.
    """
    model_sha = compute_model_sha(
        model_name=encoder.model_name,
        finetuned_model_path=finetuned_path,
    )
    cache_path = cache_dir / cache_filename(
        model_sha=model_sha, esco_sha=esco_sha, fmt=_DEFAULT_FORMAT
    )
    index = EscoIndex(encoder=encoder, cache_dir=cache_dir)

    if not rebuild and cache_path.exists():
        try:
            t0 = time.monotonic()
            index.load(
                cache_path,
                expected_esco_sha=esco_sha,
                expected_format=_DEFAULT_FORMAT,
            )
            elapsed = time.monotonic() - t0
            logger.info(
                "index.warm_load",
                path=str(cache_path),
                elapsed_seconds=round(elapsed, 3),
            )
            return _IndexResult(
                index=index,
                elapsed_seconds=elapsed,
                was_cold_build=False,
                cache_path=cache_path,
            )
        except EscoIndexCacheError as exc:
            logger.warning(
                "index.cache_invalid",
                path=str(cache_path),
                error=str(exc),
            )

    t0 = time.monotonic()
    index.build(concepts, fmt=_DEFAULT_FORMAT, batch_size=64)
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
    return _IndexResult(
        index=index,
        elapsed_seconds=elapsed,
        was_cold_build=True,
        cache_path=cache_path,
    )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _fmt_prf(prf: PRF) -> str:
    """Render a PRF as ``P=.xxx  R=.xxx  F1=.xxx``."""
    return f"P={prf.precision:.3f}  R={prf.recall:.3f}  F1={prf.f1:.3f}"


def _fmt_delta(zs: float, ft: float) -> str:
    """Render a signed delta with three decimals + colour-coded marker."""
    delta = ft - zs
    marker = "+" if delta >= 0 else ""
    return f"{marker}{delta:.3f}"


def _section_headline_table(
    zs: ViewMetrics | None,
    ft: ViewMetrics,
    view_name: str,
) -> str:
    """Render the macro/micro comparison table for a single view."""
    rows = []
    rows.append(f"### {view_name} view\n")
    rows.append(
        "| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Macro F1 delta |"
    )
    rows.append("|---|---|---|---|")
    for label, ft_macro, zs_macro in (
        ("Lexical (Module 2)",
         ft.lexical_macro,
         zs.lexical_macro if zs else None),
        ("Semantic",
         ft.semantic_macro,
         zs.semantic_macro if zs else None),
        ("Ensemble (lex ∪ sem)",
         ft.ensemble_macro,
         zs.ensemble_macro if zs else None),
    ):
        zs_str = _fmt_prf(zs_macro) if zs_macro is not None else "n/a"
        ft_str = _fmt_prf(ft_macro)
        delta_str = (
            _fmt_delta(zs_macro.f1, ft_macro.f1)
            if zs_macro is not None
            else "n/a"
        )
        rows.append(f"| {label} | {zs_str} | {ft_str} | {delta_str} |")
    rows.append("")
    rows.append("Micro:")
    rows.append("")
    rows.append(
        "| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Micro F1 delta |"
    )
    rows.append("|---|---|---|---|")
    for label, ft_micro, zs_micro in (
        ("Lexical",
         ft.lexical_micro,
         zs.lexical_micro if zs else None),
        ("Semantic",
         ft.semantic_micro,
         zs.semantic_micro if zs else None),
        ("Ensemble",
         ft.ensemble_micro,
         zs.ensemble_micro if zs else None),
    ):
        zs_str = _fmt_prf(zs_micro) if zs_micro is not None else "n/a"
        ft_str = _fmt_prf(ft_micro)
        delta_str = (
            _fmt_delta(zs_micro.f1, ft_micro.f1)
            if zs_micro is not None
            else "n/a"
        )
        rows.append(f"| {label} | {zs_str} | {ft_str} | {delta_str} |")
    return "\n".join(rows) + "\n"


def _section_per_cv_delta(
    zs_view: ViewMetrics | None, ft_view: ViewMetrics
) -> str:
    """Per-CV semantic F1 with delta (sorted by delta descending)."""
    rows = ["### Per-CV semantic F1\n"]
    rows.append("| CV | Zero-shot F1 | Fine-tuned F1 | Delta |")
    rows.append("|---|---|---|---|")

    cv_ids = sorted(ft_view.per_cv_semantic.keys())
    entries = []
    for cv_id in cv_ids:
        ft_prf = ft_view.per_cv_semantic[cv_id]
        zs_prf = (
            zs_view.per_cv_semantic.get(cv_id) if zs_view is not None else None
        )
        zs_f1 = zs_prf.f1 if zs_prf is not None else 0.0
        delta = ft_prf.f1 - zs_f1
        entries.append((delta, cv_id, zs_f1, ft_prf.f1))

    # Sort by delta descending so wins surface at top.
    entries.sort(key=lambda e: -e[0])
    for delta, cv_id, zs_f1, ft_f1 in entries:
        zs_str = f"{zs_f1:.3f}" if zs_view is not None else "n/a"
        marker = "+" if delta >= 0 else ""
        rows.append(
            f"| {cv_id} | {zs_str} | {ft_f1:.3f} | {marker}{delta:.3f} |"
        )
    return "\n".join(rows) + "\n"


def _section_threshold_ablation(
    zs_metrics: BaselineMetrics | None, ft_metrics: BaselineMetrics
) -> str:
    """Macro F1 (semantic only) at each threshold, side by side."""
    rows = ["### Threshold ablation (semantic macro F1, high+medium view)\n"]
    rows.append("| Threshold | Zero-shot | Fine-tuned | Delta |")
    rows.append("|---|---|---|---|")
    ft_sweep = threshold_sweep(ft_metrics, _THRESHOLD_ABLATION)
    zs_sweep = (
        threshold_sweep(zs_metrics, _THRESHOLD_ABLATION)
        if zs_metrics is not None
        else {}
    )
    for t in _THRESHOLD_ABLATION:
        ft_f1 = ft_sweep[t].f1
        zs_f1 = zs_sweep.get(t, PRF(0.0, 0.0, 0.0)).f1 if zs_sweep else 0.0
        zs_str = f"{zs_f1:.3f}" if zs_sweep else "n/a"
        delta = ft_f1 - zs_f1 if zs_sweep else 0.0
        marker = "+" if delta >= 0 else ""
        delta_str = f"{marker}{delta:.3f}" if zs_sweep else "n/a"
        rows.append(f"| {t:.2f} | {zs_str} | {ft_f1:.3f} | {delta_str} |")
    return "\n".join(rows) + "\n"


def _section_wins_and_regressions(
    zs_view: ViewMetrics | None, ft_view: ViewMetrics
) -> tuple[str, list[str], list[str]]:
    """Qualitative section + win/regression lists for the conclusion."""
    wins: list[str] = []
    regressions: list[str] = []
    rows = ["### Qualitative wins (F1 lift >= 0.10)\n"]
    for cv_id, ft_prf in sorted(ft_view.per_cv_semantic.items()):
        zs_prf = (
            zs_view.per_cv_semantic.get(cv_id) if zs_view is not None else None
        )
        zs_f1 = zs_prf.f1 if zs_prf is not None else 0.0
        delta = ft_prf.f1 - zs_f1
        if delta >= _QUALITATIVE_WIN_THRESHOLD:
            wins.append(
                f"* **{cv_id}**: F1 {zs_f1:.3f} -> {ft_prf.f1:.3f} "
                f"(+{delta:.3f})"
            )
    if wins:
        rows.extend(wins)
    else:
        rows.append("*None.*")
    rows.append("")
    rows.append("### Qualitative regressions (F1 drop > 0.05)\n")
    for cv_id, ft_prf in sorted(ft_view.per_cv_semantic.items()):
        zs_prf = (
            zs_view.per_cv_semantic.get(cv_id) if zs_view is not None else None
        )
        zs_f1 = zs_prf.f1 if zs_prf is not None else 0.0
        delta = ft_prf.f1 - zs_f1
        if delta < -_REGRESSION_THRESHOLD:
            regressions.append(
                f"* **{cv_id}**: F1 {zs_f1:.3f} -> {ft_prf.f1:.3f} "
                f"({delta:+.3f}) — investigate whether overfitting to "
                f"training distribution caused this"
            )
    if regressions:
        rows.extend(regressions)
    else:
        rows.append("*None — fine-tune is monotone non-regressive across all CVs.*")
    return "\n".join(rows) + "\n", wins, regressions


def _decision_section(ft_view: ViewMetrics, lexical_floor_f1: float) -> str:
    """Step 6 / Step 5b go/no-go logic per DECISIONS.md D7."""
    ft_f1 = ft_view.semantic_macro.f1
    ensemble_f1 = ft_view.ensemble_macro.f1

    bullets = []
    bullets.append(
        f"* **Fine-tuned semantic macro F1**: {ft_f1:.3f} "
        f"(gate: ≥ {_GO_FOR_STEP_6_MACRO_F1:.2f})."
    )
    bullets.append(
        f"* **Fine-tuned ensemble macro F1**: {ensemble_f1:.3f} "
        f"(must beat lexical floor {lexical_floor_f1:.3f})."
    )

    if ft_f1 >= _GO_FOR_STEP_6_MACRO_F1 and ensemble_f1 > lexical_floor_f1:
        decision = "**Go for Step 6 (Linker).**"
        rationale = (
            "Fine-tuned semantic F1 is at or above the locked 0.55 threshold "
            "(DECISIONS.md D7), and the ensemble beats lexical alone — the "
            "precision/recall sandwich works."
        )
    elif ft_f1 >= 0.45 and ft_f1 < _GO_FOR_STEP_6_MACRO_F1:
        decision = "**Borderline — propose one re-train with adjusted hyperparams.**"
        rationale = (
            "Fine-tuned F1 in [0.45, 0.55) zone per Step 5 Pre-Flight risk "
            "register. Recommended next: re-run with lr=1e-5 and EPOCHS=4 "
            "before falling back to Step 5b."
        )
    else:
        decision = "**Step 5b — cross-encoder re-ranker.**"
        rationale = (
            "Fine-tuned F1 is below 0.45 / 0.55 thresholds. The bi-encoder "
            "gap is too wide to close by hyperparameter sweep alone; "
            "open a Step 5b Pre-Flight for the cross-encoder design."
        )

    return (
        "## Decision\n\n"
        + "\n".join(bullets)
        + "\n\n"
        + decision
        + "\n\n"
        + rationale
        + "\n"
    )


def render_report(
    *,
    zs_metrics: BaselineMetrics | None,
    ft_metrics: BaselineMetrics,
    run_name: str,
    checkpoint_path: Path,
    zs_index_path: Path | None,
    ft_index_path: Path,
    zs_index_seconds: float,
    ft_index_seconds: float,
    zs_was_cold: bool | None,
    ft_was_cold: bool,
    n_concepts: int,
    args: argparse.Namespace,
) -> str:
    """Render the full comparison report as markdown."""
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    parts: list[str] = []

    parts.append("# Module 3 — Step 5 fine-tuned baseline\n")
    parts.append(f"Generated {today}\n")
    parts.append(f"Run name: **{run_name}**\n")
    parts.append("")

    # 1. Executive summary
    ft_headline = ft_metrics.headline
    ft_f1 = ft_headline.semantic_macro.f1
    ensemble_f1 = ft_headline.ensemble_macro.f1
    lexical_floor = ft_headline.lexical_macro.f1
    zs_f1 = (
        zs_metrics.headline.semantic_macro.f1 if zs_metrics is not None else 0.0
    )

    parts.append("## 1. Executive summary\n")
    parts.append(
        f"* Zero-shot semantic macro F1 (high+medium view): "
        f"**{zs_f1:.3f}**" if zs_metrics is not None else
        "* Zero-shot semantic macro F1: *not re-computed in this run.*"
    )
    parts.append(f"* Fine-tuned semantic macro F1: **{ft_f1:.3f}**")
    if zs_metrics is not None:
        delta = ft_f1 - zs_f1
        lift_x = ft_f1 / zs_f1 if zs_f1 > 0 else float("inf")
        parts.append(
            f"* Delta: **{delta:+.3f}** (lift: {lift_x:.2f}×)"
        )
    parts.append(f"* Lexical floor (Module 2): {lexical_floor:.3f}")
    parts.append(
        f"* Ensemble (lex ∪ sem) macro F1: **{ensemble_f1:.3f}** "
        f"({'beats' if ensemble_f1 > lexical_floor else 'BELOW'} "
        f"lexical floor)"
    )
    gate_status = (
        "PASS" if ft_f1 >= _GO_FOR_STEP_6_MACRO_F1 else "FAIL"
    )
    parts.append(
        f"* Step 6 gate (macro F1 ≥ {_GO_FOR_STEP_6_MACRO_F1:.2f}): "
        f"**{gate_status}**"
    )
    parts.append("")

    # 2. Environment
    parts.append("## 2. Environment\n")
    parts.append(f"* Base model: `{_BASE_MODEL}`")
    parts.append(f"* Fine-tuned checkpoint: `{checkpoint_path}`")
    parts.append(f"* skill_matcher version: {SKILL_MATCHER_VERSION}")
    parts.append(f"* Semantic threshold (headline): {args.semantic_threshold}")
    parts.append(f"* Top-k per window: {args.top_k}")
    parts.append(
        f"* Sliding window: size={args.window_size_tokens} tokens, "
        f"stride={args.window_stride_tokens} tokens"
    )
    parts.append(f"* Concept-text format: {_DEFAULT_FORMAT}")
    parts.append(f"* ESCO concepts indexed: {n_concepts}")
    parts.append(f"* Encoder device: {args.device}")
    parts.append("")

    # 3. Index timing
    parts.append("## 3. Index build timing\n")
    if zs_metrics is not None:
        parts.append(
            f"* Zero-shot index: "
            f"{'cold build' if zs_was_cold else 'warm load'} in "
            f"{zs_index_seconds:.1f}s (`{zs_index_path}`)"
        )
    parts.append(
        f"* Fine-tuned index: "
        f"{'cold build' if ft_was_cold else 'warm load'} in "
        f"{ft_index_seconds:.1f}s (`{ft_index_path}`)"
    )
    parts.append("")

    # 4. Per-CV breakdown
    parts.append("## 4. Per-CV breakdown\n")
    parts.append(
        _section_per_cv_delta(
            zs_metrics.headline if zs_metrics is not None else None,
            ft_headline,
        )
    )

    # 5. Aggregate metrics
    parts.append("## 5. Aggregate metrics\n")
    parts.append(
        _section_headline_table(
            zs_metrics.headline if zs_metrics is not None else None,
            ft_headline,
            view_name="high+medium (headline)",
        )
    )
    parts.append(
        _section_headline_table(
            zs_metrics.by_view["high"] if zs_metrics is not None else None,
            ft_metrics.by_view["high"],
            view_name="high (strict)",
        )
    )

    # 6. Threshold ablation
    parts.append("## 6. Threshold ablation\n")
    parts.append(_section_threshold_ablation(zs_metrics, ft_metrics))

    # 7. Qualitative wins + regressions
    qual_section, wins, regressions = _section_wins_and_regressions(
        zs_metrics.headline if zs_metrics is not None else None,
        ft_headline,
    )
    parts.append("## 7. Qualitative analysis\n")
    parts.append(qual_section)

    # 8. Decision
    parts.append(_decision_section(ft_headline, lexical_floor))

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    run_name = resolve_run_name(args.run_name)
    checkpoint_path = resolve_checkpoint_path(run_name)
    out_report = args.out_report or _default_report_path()
    out_report.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "run_finetuned_baseline.start",
        run_name=run_name,
        checkpoint=str(checkpoint_path),
        out_report=str(out_report),
        threshold=args.semantic_threshold,
        skip_zero_shot=args.skip_zero_shot,
    )

    # Load concepts once, hand the same list to both indexes.
    concepts = load_esco_concepts()
    esco_sha = compute_esco_file_sha()
    cfg = SkillMatcherConfig()
    cache_dir = cfg.embedding_cache_dir

    # ----- Fine-tuned -----
    ft_encoder = SentenceTransformerEncoder(
        model_name=str(checkpoint_path), device=args.device
    )
    ft_index_result = _get_or_build_index(
        encoder=ft_encoder,
        finetuned_path=checkpoint_path,
        concepts=concepts,
        cache_dir=cache_dir,
        esco_sha=esco_sha,
        rebuild=args.rebuild_index,
    )
    t0 = time.monotonic()
    ft_metrics = run_baseline(
        eval_corpus_dir=args.eval_corpus_dir,
        encoder=ft_encoder,
        index=ft_index_result.index,
        window_size_tokens=args.window_size_tokens,
        window_stride_tokens=args.window_stride_tokens,
        semantic_threshold=args.semantic_threshold,
        top_k_per_window=args.top_k,
    )
    ft_eval_seconds = time.monotonic() - t0
    logger.info(
        "run_finetuned_baseline.ft_done",
        elapsed_seconds=round(ft_eval_seconds, 1),
        macro_f1_headline=round(ft_metrics.headline.semantic_macro.f1, 4),
    )

    # ----- Zero-shot -----
    zs_metrics: BaselineMetrics | None = None
    zs_index_result: _IndexResult | None = None
    zs_eval_seconds = 0.0
    if not args.skip_zero_shot:
        zs_encoder = SentenceTransformerEncoder(
            model_name=_BASE_MODEL, device=args.device
        )
        zs_index_result = _get_or_build_index(
            encoder=zs_encoder,
            finetuned_path=None,
            concepts=concepts,
            cache_dir=cache_dir,
            esco_sha=esco_sha,
            rebuild=args.rebuild_index,
        )
        t0 = time.monotonic()
        zs_metrics = run_baseline(
            eval_corpus_dir=args.eval_corpus_dir,
            encoder=zs_encoder,
            index=zs_index_result.index,
            window_size_tokens=args.window_size_tokens,
            window_stride_tokens=args.window_stride_tokens,
            semantic_threshold=args.semantic_threshold,
            top_k_per_window=args.top_k,
        )
        zs_eval_seconds = time.monotonic() - t0
        logger.info(
            "run_finetuned_baseline.zs_done",
            elapsed_seconds=round(zs_eval_seconds, 1),
            macro_f1_headline=round(zs_metrics.headline.semantic_macro.f1, 4),
        )

    # ----- Report -----
    report_md = render_report(
        zs_metrics=zs_metrics,
        ft_metrics=ft_metrics,
        run_name=run_name,
        checkpoint_path=checkpoint_path,
        zs_index_path=zs_index_result.cache_path if zs_index_result else None,
        ft_index_path=ft_index_result.cache_path,
        zs_index_seconds=zs_index_result.elapsed_seconds if zs_index_result else 0.0,
        ft_index_seconds=ft_index_result.elapsed_seconds,
        zs_was_cold=zs_index_result.was_cold_build if zs_index_result else None,
        ft_was_cold=ft_index_result.was_cold_build,
        n_concepts=ft_index_result.index.n_concepts,
        args=args,
    )
    out_report.write_text(report_md, encoding="utf-8")

    # Mirror the JSON sidecar pattern from run_zero_shot_baseline.
    json_path = out_report.with_suffix(".json")
    json_payload: dict[str, Any] = {
        "run_name": run_name,
        "checkpoint_path": str(checkpoint_path),
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "config": {
            "semantic_threshold": args.semantic_threshold,
            "top_k": args.top_k,
            "window_size_tokens": args.window_size_tokens,
            "window_stride_tokens": args.window_stride_tokens,
            "concept_text_format": _DEFAULT_FORMAT,
            "device": args.device,
        },
        "n_concepts": ft_index_result.index.n_concepts,
        "fine_tuned": {
            "macro_f1_high_plus_medium": ft_metrics.headline.semantic_macro.f1,
            "macro_p_high_plus_medium": ft_metrics.headline.semantic_macro.precision,
            "macro_r_high_plus_medium": ft_metrics.headline.semantic_macro.recall,
            "ensemble_macro_f1": ft_metrics.headline.ensemble_macro.f1,
            "lexical_macro_f1": ft_metrics.headline.lexical_macro.f1,
            "eval_seconds": ft_eval_seconds,
            "index_seconds": ft_index_result.elapsed_seconds,
            "index_was_cold": ft_index_result.was_cold_build,
        },
        "zero_shot": (
            {
                "macro_f1_high_plus_medium": zs_metrics.headline.semantic_macro.f1,
                "macro_p_high_plus_medium": zs_metrics.headline.semantic_macro.precision,
                "macro_r_high_plus_medium": zs_metrics.headline.semantic_macro.recall,
                "ensemble_macro_f1": zs_metrics.headline.ensemble_macro.f1,
                "lexical_macro_f1": zs_metrics.headline.lexical_macro.f1,
                "eval_seconds": zs_eval_seconds,
                "index_seconds": zs_index_result.elapsed_seconds if zs_index_result else 0.0,
                "index_was_cold": zs_index_result.was_cold_build if zs_index_result else False,
            }
            if zs_metrics is not None
            else None
        ),
    }
    json_path.write_text(
        json.dumps(json_payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Report:  {out_report}")
    print(f"JSON:    {json_path}")
    print(
        f"Fine-tuned macro F1 (high+medium): "
        f"{ft_metrics.headline.semantic_macro.f1:.4f}"
    )
    if zs_metrics is not None:
        print(
            f"Zero-shot  macro F1 (high+medium): "
            f"{zs_metrics.headline.semantic_macro.f1:.4f}"
        )
        delta = (
            ft_metrics.headline.semantic_macro.f1
            - zs_metrics.headline.semantic_macro.f1
        )
        print(f"Delta:                              {delta:+.4f}")
    gate = "PASS" if ft_metrics.headline.semantic_macro.f1 >= _GO_FOR_STEP_6_MACRO_F1 else "FAIL"
    print(f"Step 6 gate (F1 >= {_GO_FOR_STEP_6_MACRO_F1:.2f}): {gate}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
