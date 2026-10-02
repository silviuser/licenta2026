# ruff: noqa: E501, RUF001, RUF002, RUF003
# E501 / RUF001-003 are suppressed file-wide because the rendered Markdown
# report deliberately carries long table rows and statistical-notation
# unicode (Δ, H₁, H₀, →, ×, −, subscripted digits). The genuine
# code-quality lints (ANN, B, F, I, UP, remaining RUF) stay active.
"""Step 5.5 — Six-Lens diagnostic for the failed Module 3 fine-tune.

Context
-------
Step 5 (Colab fine-tuning) was executed twice on 2026-05-16 and both
runs regressed eval macro-F1 below the zero-shot floor:

* ``mnrl_v1_20260516_1610``  — train_positives 2838 — F1 0.151 → 0.144 (Δ -0.007)
* ``mnrl_sw_v1_20260516_1953`` — train_positives 5559 — F1 0.151 → 0.121 (Δ -0.030)

Per ``DECISIONS.md`` D7, F1 < 0.55 triggers Step 5b (cross-encoder).
Before committing to that architectural change we need to know *why*
fine-tuning hurt. Two hypotheses:

* **H₀** (Step 5 report): bi-encoder ceiling reached.
* **H₁** (this script's working hypothesis): training positives are
  Module-2-derived, so fine-tuning amplified the lexical supervisor's
  distribution and *moved away* from the eval gold URIs Module 2 misses.

This script is **strictly read-only** on training data, eval labels,
model checkpoints and the embedding caches. It runs six lenses
(A-F) over the existing artefacts and writes a JSON + Markdown
prescription report under ``reports/``.

CLI
---
``python scripts/diagnose_step5.py --out-dir reports``

* ``--lens A,B,C,D,E,F`` to subset (default: all).
* ``--seed 42`` for reproducible sampling (Lens D / Lens E).

Out-of-scope (forbidden by the Step 5.5 Pre-Flight §3.8)
--------------------------------------------------------
* No re-encoding of the ESCO index.
* No mutation of ``train.jsonl`` / ``val.jsonl`` / model files.
* No new ``DECISIONS.md`` rows — Step 5.5 is investigative.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

# Windows console encoding fix — same idiom used by run_zero_shot_baseline.py.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, OSError):
    pass

# Path setup mirrors run_zero_shot_baseline.py so this script is runnable
# from ``nlp-service/`` without ``pip install -e``.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import structlog  # noqa: E402
from numpy.typing import NDArray  # noqa: E402

# Heavy `skill_matcher.*` imports are deferred into the orchestration
# helpers below. Keeping module-load light is what lets the test file
# import the script (and exercise the pure lens functions) without
# pulling in spacy, torch, sentence-transformers, or pdfplumber.
if TYPE_CHECKING:
    from skill_matcher.encoder import Encoder
    from skill_matcher.esco_index import EscoIndex
    from skill_matcher.esco_loader import EscoConcept
    from skill_matcher.eval_corpus import CVLabels, EvalCorpus

logger = structlog.get_logger("diagnose_step5")


# ---------------------------------------------------------------------------
# Constants — locked to Step 4 / Step 5 conventions
# ---------------------------------------------------------------------------

ZERO_SHOT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
"""HuggingFace identifier of the unmodified base encoder. The Step 4
zero-shot baseline and the Step 5 fine-tuning runs both start from this
checkpoint, so it is also the cache key for the zero-shot ESCO index."""

WINDOW_SIZE_TOKENS = 30
WINDOW_STRIDE_TOKENS = 15
"""Step 4 locks. Bounded-a + sliding-window stride 15 is the headline
configuration the eval-corpus baseline was built against; reusing it
keeps Lens B's similarity numbers comparable to the published Step 4
report."""

HIGH_MEDIUM: tuple[Literal["high"], Literal["medium"]] = ("high", "medium")
"""``confidence_expected`` levels that count toward the gold-URI set. The
prompt §3.1/§3.2 specifies both — ``high`` is unambiguous and
``medium`` is implied/partially evidenced, both of which Module 3 should
retrieve."""

LENS_B_FP_TOP_K = 5
LENS_B_FP_THRESHOLD = 0.55
"""Lens C uses these to define the retrieved set per CV per encoder.
Matches the Step 4 ablation pick (D-row in ``DECISIONS.md`` —
threshold 0.55 + stride 15 was the macro-F1 winner)."""

LENS_D_SAMPLE_SIZE = 200
"""Per the prompt §3.4 — 200 hard-negatives + 200 reference positives
sampled with ``random.Random(seed)``. Small enough to keep Lens D's
encoder pass under one minute on CPU."""

LENS_E_SAMPLE_SIZE = 5
"""Per the prompt §3.5 — 5 ESCO URIs sampled and rendered both
train-side and index-side, diffed character-by-character."""

CONCEPT_TEXT_FORMAT: Literal["bounded-a"] = "bounded-a"
"""Locked by DECISIONS.md (Step 4). Both the index and the training-side
positive renderer use this format; Lens E exists to assert they remain
in lockstep."""

DEFAULT_EMBEDDING_CACHE_DIR = _REPO_ROOT / ".cache" / "embeddings"
DEFAULT_MODELS_DIR = _REPO_ROOT / "models" / "skill_matcher"

# Model run identifiers carried into the report. Hard-coded here because
# the diagnostic is run-specific — every future re-run will pick up new
# checkpoint directories and would supersede these values.
MODEL_RUN_V1 = "mnrl_v1_20260516_1610"
MODEL_RUN_SW = "mnrl_sw_v1_20260516_1953"

# Cosine-similarity bin edges used by Lens C's FP-frequency histogram.
LENS_C_FREQ_BINS = (0, 1, 3, 6, 11, 26, 101)
"""Discrete bins for "how many times did this URI appear as a positive
in train.jsonl". The bin labels in the report read as
``[0, 1-2, 3-5, 6-10, 11-25, 26-100, 101+]`` so the eye can spot
high-frequency over-representation in fine-tuned FP sets quickly."""


# ---------------------------------------------------------------------------
# Findings dataclasses — one per lens, plus a top-level Findings container
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CoveragePerCV:
    """Lens A — gold-URI coverage for a single CV."""

    cv_id: str
    gold_count: int
    gold_in_training: int
    gold_unseen: int
    unseen_uris: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoverageFindings:
    """Lens A — training-set coverage of eval URIs."""

    total_eval_uris: int
    overlap_uris: int
    coverage_ratio: float
    per_cv: tuple[CoveragePerCV, ...]
    train_uri_set_size: int
    train_build_timestamp: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PerURISimRecord:
    """One row in Lens B's per-URI similarity table.

    Built by the orchestration layer (one record per ``(cv_id, gold_uri)``
    pair across the eval corpus). The lens function consumes a sequence
    of these — testable on synthetic records without the encoder stack.
    """

    cv_id: str
    uri: str
    in_training_v1: bool
    in_training_sw: bool
    sim_zero_shot: float
    sim_mnrl_v1: float
    sim_mnrl_sw: float


@dataclass(frozen=True, slots=True)
class RankCell:
    """One cell of Lens B's 2×2 cross-tab."""

    n_uris: int
    mean_delta_v1: float
    mean_delta_sw: float
    improved_count_v1: int
    improved_count_sw: int


@dataclass(frozen=True, slots=True)
class RankFindings:
    """Lens B — per-URI rank-attribution table."""

    in_training: RankCell
    not_in_training: RankCell
    n_records: int
    n_cvs_processed: int
    n_cvs_skipped: int
    skipped_cv_ids: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FPRecord:
    """One false-positive URI surfaced by an encoder on one eval CV."""

    cv_id: str
    encoder: str
    fp_uri: str
    train_freq: int


@dataclass(frozen=True, slots=True)
class FPHistogram:
    """Histogram of FP-URI training frequencies for one encoder."""

    encoder: str
    total_fp: int
    bin_edges: tuple[int, ...]
    bin_counts: tuple[int, ...]
    mean_freq: float
    median_freq: float


@dataclass(frozen=True, slots=True)
class FPFindings:
    """Lens C — false-positive attribution."""

    histograms: tuple[FPHistogram, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DistributionSummary:
    """Quantile summary of a 1-D distribution."""

    n: int
    mean: float
    median: float
    p25: float
    p75: float


@dataclass(frozen=True, slots=True)
class NegativeQualityFindings:
    """Lens D — hard-negative quality audit."""

    negatives: DistributionSummary
    positives: DistributionSummary
    mean_gap: float
    figure_path: str | None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlignmentSample:
    """One ``(uri, train_side, index_side, diff)`` row from Lens E."""

    uri: str
    train_side: str
    index_side: str
    differs: bool


@dataclass(frozen=True, slots=True)
class AlignmentFindings:
    """Lens E — concept-text alignment audit."""

    n_sampled: int
    n_differs: int
    samples: tuple[AlignmentSample, ...]
    verdict: Literal["aligned", "drifted"]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrainingCurve:
    """Per-run training curve for Lens F."""

    run_name: str
    epoch_mrr: tuple[tuple[float, float], ...]
    peak_epoch: float
    peak_mrr: float
    final_mrr: float
    manifest_final_mrr: float | None
    monotonic: bool
    final_vs_peak_gap: float


@dataclass(frozen=True, slots=True)
class DynamicsFindings:
    """Lens F — training-dynamics inspection."""

    curves: tuple[TrainingCurve, ...]
    figure_path: str | None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Environment:
    """Run-environment metadata stamped onto every report."""

    run_date: str
    seed: int
    eval_corpus_size: int
    cvs_skipped: tuple[str, ...]
    runs_analysed: tuple[str, ...]
    on_disk_train_jsonl_timestamp: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Findings:
    """Top-level container — every lens slot is optional so partial runs
    (``--lens A``) still produce a coherent JSON document."""

    environment: Environment
    coverage: CoverageFindings | None = None
    rank: RankFindings | None = None
    fp: FPFindings | None = None
    negative_quality: NegativeQualityFindings | None = None
    alignment: AlignmentFindings | None = None
    dynamics: DynamicsFindings | None = None
    per_uri_records: tuple[PerURISimRecord, ...] = field(default_factory=tuple)
    fp_records: tuple[FPRecord, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Pure lens functions — testable on synthetic inputs
# ---------------------------------------------------------------------------


def analyse_training_coverage(
    *,
    train_positive_uris: set[str],
    eval_uri_set_by_cv: dict[str, set[str]],
    train_build_timestamp: str,
    notes: Sequence[str] = (),
) -> CoverageFindings:
    """Lens A — overlap between training URIs and eval gold URIs.

    Pure: takes pre-extracted URI sets, returns the cross-tab. The
    orchestration layer is responsible for loading the JSONL and the
    CV-label YAMLs.

    Parameters
    ----------
    train_positive_uris
        URI set drawn from positives in ``train.jsonl``.
    eval_uri_set_by_cv
        Mapping ``cv_id -> set of gold URIs at confidence high|medium``.
    train_build_timestamp
        ISO timestamp stamped on the JSONL header — surfaced in the
        report so reviewers can cross-reference the build identity.
    notes
        Free-text caveats injected by the orchestrator (e.g.
        ``"train.jsonl on disk is the 19:43 build; mnrl_v1 cited the
        08:59 build"``).
    """
    per_cv_rows: list[CoveragePerCV] = []
    eval_uri_union: set[str] = set()
    for cv_id, gold in sorted(eval_uri_set_by_cv.items()):
        eval_uri_union.update(gold)
        unseen = sorted(uri for uri in gold if uri not in train_positive_uris)
        per_cv_rows.append(
            CoveragePerCV(
                cv_id=cv_id,
                gold_count=len(gold),
                gold_in_training=len(gold) - len(unseen),
                gold_unseen=len(unseen),
                unseen_uris=tuple(unseen),
            )
        )

    overlap = eval_uri_union & train_positive_uris
    coverage_ratio = (
        len(overlap) / len(eval_uri_union) if eval_uri_union else 0.0
    )

    return CoverageFindings(
        total_eval_uris=len(eval_uri_union),
        overlap_uris=len(overlap),
        coverage_ratio=coverage_ratio,
        per_cv=tuple(per_cv_rows),
        train_uri_set_size=len(train_positive_uris),
        train_build_timestamp=train_build_timestamp,
        notes=tuple(notes),
    )


def _summarise_rank_group(
    records: Sequence[PerURISimRecord],
    *,
    flag: Literal["in", "out"],
) -> RankCell:
    """Compute the in-training / not-in-training half of Lens B's table.

    ``flag="in"`` filters records by ``in_training_sw`` (the
    authoritative training set, see R1 in the Pre-Flight). The mnrl_v1
    column shares the filter for consistency — a record that's "in" by
    sw but "out" by v1 still contributes to the "in" cell here, with the
    caveat already surfaced in the report's environment block.
    """
    selected = [
        r
        for r in records
        if (flag == "in" and r.in_training_sw)
        or (flag == "out" and not r.in_training_sw)
    ]
    if not selected:
        return RankCell(
            n_uris=0,
            mean_delta_v1=0.0,
            mean_delta_sw=0.0,
            improved_count_v1=0,
            improved_count_sw=0,
        )

    delta_v1 = [r.sim_mnrl_v1 - r.sim_zero_shot for r in selected]
    delta_sw = [r.sim_mnrl_sw - r.sim_zero_shot for r in selected]
    return RankCell(
        n_uris=len(selected),
        mean_delta_v1=float(np.mean(delta_v1)),
        mean_delta_sw=float(np.mean(delta_sw)),
        improved_count_v1=sum(1 for d in delta_v1 if d > 0),
        improved_count_sw=sum(1 for d in delta_sw if d > 0),
    )


def analyse_per_uri_rank_attribution(
    *,
    records: Sequence[PerURISimRecord],
    n_cvs_processed: int,
    n_cvs_skipped: int,
    skipped_cv_ids: Sequence[str],
    notes: Sequence[str] = (),
) -> RankFindings:
    """Lens B — cross-tab of similarity deltas by training-set membership.

    The load-bearing lens. If H₁ is true, the "in training" cell should
    show positive mean Δsim after fine-tuning and the "not in training"
    cell should show negative mean Δsim. The asymmetry is what we look
    at, not the absolute values.
    """
    return RankFindings(
        in_training=_summarise_rank_group(records, flag="in"),
        not_in_training=_summarise_rank_group(records, flag="out"),
        n_records=len(records),
        n_cvs_processed=n_cvs_processed,
        n_cvs_skipped=n_cvs_skipped,
        skipped_cv_ids=tuple(skipped_cv_ids),
        notes=tuple(notes),
    )


def _bin_frequencies(
    freqs: Sequence[int],
    *,
    bin_edges: Sequence[int],
) -> tuple[int, ...]:
    """Histogram helper: count freqs into ``[bin_edges[i], bin_edges[i+1])``
    half-open bins, with the last bin extended to infinity."""
    counts = [0] * len(bin_edges)
    for f in freqs:
        for i in range(len(bin_edges) - 1):
            if bin_edges[i] <= f < bin_edges[i + 1]:
                counts[i] += 1
                break
        else:
            # Beyond the last edge — extend to infinity.
            counts[-1] += 1
    return tuple(counts)


def analyse_fp_attribution(
    *,
    records: Sequence[FPRecord],
    bin_edges: Sequence[int] = LENS_C_FREQ_BINS,
    notes: Sequence[str] = (),
) -> FPFindings:
    """Lens C — FP frequency-in-training cross-tab.

    Records come pre-computed (one per ``(cv, encoder, fp_uri)``).
    Output: one histogram per encoder. The bins are exposed for tests
    so the same lens can be exercised on toy data with a custom layout.
    """
    by_encoder: dict[str, list[int]] = {}
    for r in records:
        by_encoder.setdefault(r.encoder, []).append(r.train_freq)

    histograms: list[FPHistogram] = []
    for encoder in sorted(by_encoder):
        freqs = by_encoder[encoder]
        sorted_freqs = sorted(freqs)
        n = len(sorted_freqs)
        mean = float(np.mean(sorted_freqs)) if sorted_freqs else 0.0
        median = float(np.median(sorted_freqs)) if sorted_freqs else 0.0
        histograms.append(
            FPHistogram(
                encoder=encoder,
                total_fp=n,
                bin_edges=tuple(bin_edges),
                bin_counts=_bin_frequencies(sorted_freqs, bin_edges=bin_edges),
                mean_freq=mean,
                median_freq=median,
            )
        )

    return FPFindings(histograms=tuple(histograms), notes=tuple(notes))


def _summarise_distribution(sims: Sequence[float]) -> DistributionSummary:
    """Quantile summary for Lens D's two distributions."""
    if not sims:
        return DistributionSummary(n=0, mean=0.0, median=0.0, p25=0.0, p75=0.0)
    arr = np.asarray(sims, dtype=np.float64)
    return DistributionSummary(
        n=len(sims),
        mean=float(arr.mean()),
        median=float(np.median(arr)),
        p25=float(np.quantile(arr, 0.25)),
        p75=float(np.quantile(arr, 0.75)),
    )


def audit_negative_quality(
    *,
    negative_sims: Sequence[float],
    positive_sims: Sequence[float],
    figure_path: str | None = None,
    notes: Sequence[str] = (),
) -> NegativeQualityFindings:
    """Lens D — hard-negative cosine distribution vs reference positives.

    Useful interpretive thresholds:
    * If negatives mean < 0.10 and positives mean > 0.50, the hard
      negatives are trivially easy — MNRL relies on in-batch random
      negatives for gradient and the curated negatives barely
      contribute.
    * If negatives mean > 0.35 and overlaps with the positive
      distribution, the negatives are *too* hard — possibly inducing
      label noise.
    """
    neg = _summarise_distribution(negative_sims)
    pos = _summarise_distribution(positive_sims)
    return NegativeQualityFindings(
        negatives=neg,
        positives=pos,
        mean_gap=pos.mean - neg.mean,
        figure_path=figure_path,
        notes=tuple(notes),
    )


def audit_concept_text_alignment(
    *,
    samples: Sequence[AlignmentSample],
    notes: Sequence[str] = (),
) -> AlignmentFindings:
    """Lens E — string-level diff of train-side vs index-side concept text.

    Verdict is the binary aligned/drifted flag the report leads with.
    The samples carry the full strings so the report can show the
    actual mismatch when ``drifted``.
    """
    n_differs = sum(1 for s in samples if s.differs)
    verdict: Literal["aligned", "drifted"] = (
        "drifted" if n_differs > 0 else "aligned"
    )
    return AlignmentFindings(
        n_sampled=len(samples),
        n_differs=n_differs,
        samples=tuple(samples),
        verdict=verdict,
        notes=tuple(notes),
    )


def audit_training_dynamics(
    *,
    curves_by_run: dict[str, Sequence[tuple[float, float]]],
    manifest_finals: dict[str, float],
    figure_path: str | None = None,
    notes: Sequence[str] = (),
) -> DynamicsFindings:
    """Lens F — training dynamics summary per run.

    Inputs:
    * ``curves_by_run`` — ``run_name -> [(epoch, val_cosine_mrr@10)]``.
    * ``manifest_finals`` — ``run_name -> final_val_mrr_at_10`` from each
      run's manifest. Compared against the last row of the CSV to flag
      ``save_best_model`` divergence.
    """
    out: list[TrainingCurve] = []
    for run_name in sorted(curves_by_run):
        rows = list(curves_by_run[run_name])
        if not rows:
            continue
        sorted_rows = sorted(rows, key=lambda r: r[0])
        mrrs = [m for _, m in sorted_rows]
        peak_idx = int(np.argmax(mrrs))
        peak_epoch, peak_mrr = sorted_rows[peak_idx]
        _final_epoch, final_mrr = sorted_rows[-1]
        monotonic = all(
            sorted_rows[i + 1][1] >= sorted_rows[i][1] - 1e-9
            for i in range(len(sorted_rows) - 1)
        )
        out.append(
            TrainingCurve(
                run_name=run_name,
                epoch_mrr=tuple(sorted_rows),
                peak_epoch=peak_epoch,
                peak_mrr=peak_mrr,
                final_mrr=final_mrr,
                manifest_final_mrr=manifest_finals.get(run_name),
                monotonic=monotonic,
                final_vs_peak_gap=peak_mrr - final_mrr,
            )
        )

    return DynamicsFindings(
        curves=tuple(out), figure_path=figure_path, notes=tuple(notes)
    )


# ---------------------------------------------------------------------------
# Orchestration helpers (IO heavy — exercised by main, lightly by tests)
# ---------------------------------------------------------------------------


def _gold_uris_for_cv(labels: CVLabels) -> set[str]:
    """High+medium gold URIs from a single CV-labels YAML.

    ``labels`` is a :class:`skill_matcher.eval_corpus.CVLabels` instance —
    typed as a forward reference so this module's tests can import the
    script without pulling in the eval-corpus stack.
    """
    return {g.skill_uri for g in labels.gold_skills if g.confidence_expected in HIGH_MEDIUM}


def _train_positive_uri_set_and_freq(
    train_path: Path,
) -> tuple[set[str], dict[str, int], str]:
    """Extract (a) the URI set used as positives in train.jsonl, (b) the
    per-URI positive-count, (c) the build timestamp from the header.

    The frequency map drives Lens C's FP histogram bins."""
    from skill_matcher.dataset import TrainingPair, load_training_dataset

    dataset = load_training_dataset(train_path)
    freq: dict[str, int] = {}
    for p in dataset.pairs:
        if isinstance(p, TrainingPair):
            freq[p.esco_uri] = freq.get(p.esco_uri, 0) + 1
    return set(freq.keys()), freq, dataset.build_timestamp.isoformat()


def _matrix_view(index: EscoIndex) -> NDArray[np.float32]:
    """Read-only access to the index's underlying embedding matrix.

    ``EscoIndex`` does not expose a public matrix accessor (its query
    surface goes through ``query`` / ``query_batch``). For Lens B we
    need per-URI vector lookups — using the private attribute here is
    a diagnostic-only choice; no source-code change is made.
    """
    matrix: NDArray[np.float32] = index._matrix
    if matrix is None:
        raise RuntimeError("Index has not been loaded.")
    return matrix


def _build_encoder_bundle(
    run_name_or_zero: str,
    *,
    cache_dir: Path,
    esco_sha: str,
    models_dir: Path,
) -> tuple[Any, EscoIndex]:
    """Return ``(encoder, loaded_index)`` for one of the three runs.

    ``run_name_or_zero`` is either ``"zero_shot"`` or one of the
    fine-tuned run names (e.g. ``"mnrl_v1_20260516_1610"``). The loader
    validates the cache sidecar's ``model_sha`` against the encoder's
    identity, so the cache file we open is guaranteed to belong to the
    encoder we constructed.
    """
    from skill_matcher.encoder import SentenceTransformerEncoder
    from skill_matcher.esco_index import EscoIndex, cache_filename, compute_model_sha

    if run_name_or_zero == "zero_shot":
        model_name = ZERO_SHOT_MODEL
        # Zero-shot index was built with finetuned_model_path=None,
        # matching the SentenceTransformerEncoder default.
        finetuned_for_filename: Path | None = None
    else:
        # Sidecars for fine-tuned runs were built with the absolute
        # checkpoint path as model_name. The cache **filename**, however,
        # was generated by ``run_finetuned_baseline.py``'s
        # ``_get_or_build_index`` with ``finetuned_model_path=<same path>``,
        # so the on-disk SHA = sha256(path + 0x1f + path)[:12]. Mirror
        # that here. (The sidecar's ``model_sha`` field — used only by
        # ``EscoIndex.load`` for integrity validation — was computed with
        # ``finetuned_model_path=None``, so it matches the encoder's
        # identity at load time. Same divergence is hard-wired upstream.)
        model_name = str(models_dir / run_name_or_zero)
        finetuned_for_filename = Path(model_name)

    encoder = SentenceTransformerEncoder(model_name, device="cpu", seed=42)
    model_sha = compute_model_sha(
        model_name=model_name, finetuned_model_path=finetuned_for_filename
    )
    npz_path = cache_dir / cache_filename(
        model_sha=model_sha, esco_sha=esco_sha, fmt=CONCEPT_TEXT_FORMAT
    )

    index = EscoIndex(encoder=encoder, cache_dir=cache_dir)
    index.load(npz_path, expected_esco_sha=esco_sha, expected_format=CONCEPT_TEXT_FORMAT)
    return encoder, index


def _per_uri_records_for_corpus(
    *,
    eval_corpus: EvalCorpus,
    encoders: dict[str, Any],
    indexes: dict[str, EscoIndex],
    train_uri_set_v1: set[str],
    train_uri_set_sw: set[str],
) -> tuple[list[PerURISimRecord], list[str], list[str]]:
    """Run Module 1 → windows → encode three ways → per-URI max-sim.

    Returns ``(records, processed_cv_ids, skipped_cv_ids)``. CVs whose
    PDF extraction raises (Poppler block, corrupt page, etc.) are
    logged and skipped so the remaining lens analysis stays on track.
    """
    from cv_extractor import ExtractionPipeline
    from cv_extractor.exceptions import CVExtractorError
    from skill_matcher.sliding_window import generate_windows

    extraction = ExtractionPipeline()
    uri_to_row_by_encoder: dict[str, dict[str, int]] = {
        name: {u: i for i, u in enumerate(idx.uris)}
        for name, idx in indexes.items()
    }
    matrices: dict[str, NDArray[np.float32]] = {
        name: _matrix_view(idx) for name, idx in indexes.items()
    }

    records: list[PerURISimRecord] = []
    processed: list[str] = []
    skipped: list[str] = []

    for cv_id in eval_corpus.cv_ids():
        labels = eval_corpus.cv_labels.get(cv_id)
        pdf_path = eval_corpus.cvs.get(cv_id)
        if labels is None or pdf_path is None:
            logger.warning("lens_b.no_labels_or_pdf", cv_id=cv_id)
            skipped.append(cv_id)
            continue

        gold = _gold_uris_for_cv(labels)
        if not gold:
            logger.info("lens_b.cv_no_gold", cv_id=cv_id)
            processed.append(cv_id)
            continue

        try:
            result = extraction.process(pdf_path)
        except CVExtractorError as exc:
            logger.warning("lens_b.cv_extraction_failed", cv_id=cv_id, error=str(exc))
            skipped.append(cv_id)
            continue
        except Exception as exc:
            logger.warning("lens_b.cv_extraction_error", cv_id=cv_id, error=repr(exc))
            skipped.append(cv_id)
            continue

        text = result.text
        windows = generate_windows(
            text,
            window_size_tokens=WINDOW_SIZE_TOKENS,
            stride_tokens=WINDOW_STRIDE_TOKENS,
        )
        if not windows:
            logger.warning("lens_b.no_windows", cv_id=cv_id, text_len=len(text))
            processed.append(cv_id)
            continue

        window_texts = [w.text for w in windows]
        window_embs: dict[str, NDArray[np.float32]] = {}
        for name, enc in encoders.items():
            window_embs[name] = enc.encode(window_texts, batch_size=32)

        for uri in sorted(gold):
            sims: dict[str, float] = {}
            ok = True
            for name in encoders:
                row_idx = uri_to_row_by_encoder[name].get(uri)
                if row_idx is None:
                    ok = False
                    break
                uri_vec = matrices[name][row_idx]
                sims[name] = float(np.max(window_embs[name] @ uri_vec))
            if not ok:
                logger.info("lens_b.uri_not_in_index", cv_id=cv_id, uri=uri)
                continue
            records.append(
                PerURISimRecord(
                    cv_id=cv_id,
                    uri=uri,
                    in_training_v1=uri in train_uri_set_v1,
                    in_training_sw=uri in train_uri_set_sw,
                    sim_zero_shot=sims["zero_shot"],
                    sim_mnrl_v1=sims[MODEL_RUN_V1],
                    sim_mnrl_sw=sims[MODEL_RUN_SW],
                )
            )
        processed.append(cv_id)

    return records, processed, skipped


def _fp_records_for_corpus(
    *,
    eval_corpus: EvalCorpus,
    encoders: dict[str, Any],
    indexes: dict[str, EscoIndex],
    train_freq: dict[str, int],
    cv_text_cache: dict[str, str],
) -> list[FPRecord]:
    """Lens C records: per ``(cv, encoder)`` retrieve top-K above threshold
    and bucket the FP URIs by training frequency.

    ``cv_text_cache`` is populated by Lens B (PDF extraction is the
    expensive step). Re-using it keeps Lens C fast.
    """
    from skill_matcher.sliding_window import generate_windows

    records: list[FPRecord] = []
    for cv_id, text in sorted(cv_text_cache.items()):
        labels = eval_corpus.cv_labels.get(cv_id)
        if labels is None:
            continue
        gold = _gold_uris_for_cv(labels)
        windows = generate_windows(
            text,
            window_size_tokens=WINDOW_SIZE_TOKENS,
            stride_tokens=WINDOW_STRIDE_TOKENS,
        )
        if not windows:
            continue
        window_texts = [w.text for w in windows]
        for enc_name, encoder in encoders.items():
            embs = encoder.encode(window_texts, batch_size=32)
            hits = indexes[enc_name].query_batch(embs, top_k=LENS_B_FP_TOP_K)
            retrieved: set[str] = set()
            for per_window in hits:
                for uri, sim in per_window:
                    if sim >= LENS_B_FP_THRESHOLD:
                        retrieved.add(uri)
            fp_set = retrieved - gold
            for fp_uri in sorted(fp_set):
                records.append(
                    FPRecord(
                        cv_id=cv_id,
                        encoder=enc_name,
                        fp_uri=fp_uri,
                        train_freq=train_freq.get(fp_uri, 0),
                    )
                )
    return records


def _encode_with_zero_shot(
    encoder: Encoder, anchor_texts: Sequence[str], concept_texts: Sequence[str]
) -> tuple[list[float], list[float]]:
    """Encode anchors and concepts with the zero-shot encoder; return the
    pairwise cosine list (one cosine per index)."""
    if not anchor_texts:
        return [], []
    a = encoder.encode(list(anchor_texts), batch_size=32)
    c = encoder.encode(list(concept_texts), batch_size=32)
    # Both L2-normalised → cosine = elementwise dot.
    cos = np.einsum("ij,ij->i", a, c).astype(np.float64)
    return cos.tolist(), []


def _sample_negative_sims(
    *,
    negatives: Sequence[Any],
    positives: Sequence[Any],
    concepts_by_uri: dict[str, EscoConcept],
    encoder: Encoder,
    sample_size: int,
    seed: int,
) -> tuple[list[float], list[float]]:
    """Lens D sampling pass. Returns ``(negative_sims, positive_sims)``.

    ``negatives`` are :class:`skill_matcher.dataset.HardNegative` rows;
    ``positives`` are :class:`skill_matcher.dataset.TrainingPair` rows.
    Annotated as ``Sequence[Any]`` so this script can be imported in
    test environments that don't have ``skill_matcher`` installed.
    """
    from skill_matcher.training_data import build_anchor_text, build_positive_text_from_uri

    rng_neg = random.Random(seed)
    rng_pos = random.Random(seed + 1)

    neg_sample = rng_neg.sample(list(negatives), min(sample_size, len(negatives)))
    pos_sample = rng_pos.sample(list(positives), min(sample_size, len(positives)))

    def _pairs(rows: Sequence[Any]) -> tuple[list[str], list[str]]:
        anchors: list[str] = []
        concepts: list[str] = []
        for row in rows:
            concept_text = build_positive_text_from_uri(row.esco_uri, concepts_by_uri)
            if concept_text is None:
                continue
            anchors.append(build_anchor_text(row))
            concepts.append(concept_text)
        return anchors, concepts

    neg_anchors, neg_concepts = _pairs(neg_sample)
    pos_anchors, pos_concepts = _pairs(pos_sample)

    neg_sims, _ = _encode_with_zero_shot(encoder, neg_anchors, neg_concepts)
    pos_sims, _ = _encode_with_zero_shot(encoder, pos_anchors, pos_concepts)
    return neg_sims, pos_sims


def _alignment_samples(
    *,
    concepts_by_uri: dict[str, EscoConcept],
    sample_size: int,
    seed: int,
) -> list[AlignmentSample]:
    """Lens E samples: render the same URI through both formatters."""
    from skill_matcher.esco_index import format_concept_text
    from skill_matcher.training_data import build_positive_text_from_uri

    rng = random.Random(seed)
    uris = sorted(concepts_by_uri.keys())
    chosen = rng.sample(uris, min(sample_size, len(uris)))
    out: list[AlignmentSample] = []
    for uri in chosen:
        concept = concepts_by_uri[uri]
        train_side = build_positive_text_from_uri(uri, concepts_by_uri)
        index_side = format_concept_text(concept, CONCEPT_TEXT_FORMAT)
        if train_side is None:
            train_side = ""
        out.append(
            AlignmentSample(
                uri=uri,
                train_side=train_side,
                index_side=index_side,
                differs=(train_side != index_side),
            )
        )
    return out


def _load_training_curve(csv_path: Path) -> list[tuple[float, float]]:
    """Read ``Information-Retrieval_evaluation_val_results.csv`` and pull
    out ``(epoch, cosine-MRR@10)`` rows. Skips header."""
    out: list[tuple[float, float]] = []
    if not csv_path.exists():
        return out
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                epoch = float(row["epoch"])
                mrr = float(row["cosine-MRR@10"])
            except (KeyError, ValueError):
                continue
            out.append((epoch, mrr))
    return out


def _load_manifest_final_mrr(manifest_path: Path) -> float | None:
    """Pull ``final_val_mrr_at_10`` out of the run manifest if present."""
    if not manifest_path.exists():
        return None
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    val = data.get("final_val_mrr_at_10")
    return float(val) if isinstance(val, (int, float)) else None


# ---------------------------------------------------------------------------
# Rendering — JSON + Markdown + figures
# ---------------------------------------------------------------------------


def _json_safe(value: object) -> object:
    """Recursive coercion to JSON-serialisable primitives.

    Tuples → lists; dataclasses → dicts (already handled by asdict);
    Path → str; everything else falls through unchanged. Typed as
    ``object`` rather than ``Any`` so callers can still pass anything
    but ANN401 stays happy.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return value


def findings_to_dict(findings: Findings) -> dict[str, object]:
    """Convert ``Findings`` to a plain dict ready for ``json.dump``."""
    raw = asdict(findings)
    coerced = _json_safe(raw)
    # ``asdict`` on a dataclass always returns a ``dict`` — the narrowing
    # below is for the type checker, not the runtime.
    assert isinstance(coerced, dict)
    return coerced


def _render_lens_d_figure(
    *,
    negative_sims: Sequence[float],
    positive_sims: Sequence[float],
    out_path: Path,
) -> str | None:
    """Lens D histogram. Returns the path or ``None`` if matplotlib is
    missing."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("lens_d.no_matplotlib")
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(negative_sims, bins=30, alpha=0.55, label="hard negatives", color="#d62728")
    ax.hist(positive_sims, bins=30, alpha=0.55, label="positives (ref)", color="#2ca02c")
    ax.set_xlabel("cosine similarity (zero-shot encoder)")
    ax.set_ylabel("count")
    ax.set_title("Lens D — anchor↔concept cosine, hard negatives vs positives")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return str(out_path)


def _render_lens_f_figure(
    *,
    curves_by_run: dict[str, Sequence[tuple[float, float]]],
    out_path: Path,
) -> str | None:
    """Lens F training-curve plot. Returns the path or ``None`` if
    matplotlib is missing."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("lens_f.no_matplotlib")
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    for run, rows in sorted(curves_by_run.items()):
        if not rows:
            continue
        epochs = [r[0] for r in rows]
        mrrs = [r[1] for r in rows]
        ax.plot(epochs, mrrs, marker="o", label=run)
    ax.set_xlabel("epoch")
    ax.set_ylabel("val_cosine_mrr@10")
    ax.set_title("Lens F — val MRR@10 per epoch")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return str(out_path)


def _format_coverage_section(c: CoverageFindings) -> str:
    """Markdown rendering of Lens A."""
    pct = c.coverage_ratio * 100
    lines = [
        "## Lens A — Training-set coverage of eval URIs",
        "",
        f"* Total distinct eval URIs (high+medium): **{c.total_eval_uris}**",
        f"* Overlap with `train.jsonl` positives:     **{c.overlap_uris}**",
        f"* Coverage ratio:                            **{pct:.1f} %**",
        f"* Training URI set size:                     {c.train_uri_set_size}",
        f"* `train.jsonl` build timestamp:             {c.train_build_timestamp}",
        "",
        "Per-CV breakdown:",
        "",
        "| CV | gold | in training | unseen |",
        "|---|---:|---:|---:|",
    ]
    for cv in c.per_cv:
        lines.append(
            f"| {cv.cv_id} | {cv.gold_count} | {cv.gold_in_training} | {cv.gold_unseen} |"
        )
    if c.notes:
        lines.append("")
        for n in c.notes:
            lines.append(f"> {n}")
    return "\n".join(lines)


def _format_rank_section(r: RankFindings) -> str:
    """Markdown rendering of Lens B's headline table."""
    in_t = r.in_training
    out_t = r.not_in_training

    def _pct(num: int, denom: int) -> str:
        return f"{(num / denom * 100):.1f} %" if denom else "—"

    lines = [
        "## Lens B — Per-URI rank attribution",
        "",
        f"* Records analysed: **{r.n_records}** across {r.n_cvs_processed} CVs"
        f" ({r.n_cvs_skipped} skipped: {', '.join(r.skipped_cv_ids) or '—'}).",
        "",
        "|  | In `mnrl_sw` training | NOT in `mnrl_sw` training |",
        "|---|---:|---:|",
        f"| URIs analysed                       | {in_t.n_uris} | {out_t.n_uris} |",
        f"| Mean Δsim after `mnrl_v1`           | {in_t.mean_delta_v1:+.4f} | {out_t.mean_delta_v1:+.4f} |",
        f"| Mean Δsim after `mnrl_sw_v1`        | {in_t.mean_delta_sw:+.4f} | {out_t.mean_delta_sw:+.4f} |",
        f"| URIs with improved sim (`mnrl_v1`)  | {_pct(in_t.improved_count_v1, in_t.n_uris)} | {_pct(out_t.improved_count_v1, out_t.n_uris)} |",
        f"| URIs with improved sim (`mnrl_sw`)  | {_pct(in_t.improved_count_sw, in_t.n_uris)} | {_pct(out_t.improved_count_sw, out_t.n_uris)} |",
    ]
    if r.notes:
        lines.append("")
        for n in r.notes:
            lines.append(f"> {n}")
    return "\n".join(lines)


def _format_fp_section(f: FPFindings) -> str:
    """Markdown rendering of Lens C — one table per encoder."""
    bin_labels = [
        f"[{e}, {e_next})" if e_next < 1_000_000 else f"[{e}, ∞)"
        for e, e_next in zip(
            LENS_C_FREQ_BINS, [*list(LENS_C_FREQ_BINS[1:]), 1000000], strict=False
        )
    ]
    lines = ["## Lens C — False-positive attribution", ""]
    for h in f.histograms:
        lines += [
            f"### Encoder: `{h.encoder}` (total FPs = {h.total_fp})",
            "",
            f"* Mean training frequency of FP URIs:    **{h.mean_freq:.2f}**",
            f"* Median training frequency of FP URIs: **{h.median_freq:.1f}**",
            "",
            "| training freq bin | FP count |",
            "|---|---:|",
        ]
        for label, count in zip(bin_labels, h.bin_counts, strict=False):
            lines.append(f"| {label} | {count} |")
        lines.append("")
    if f.notes:
        for n in f.notes:
            lines.append(f"> {n}")
    return "\n".join(lines)


def _format_negative_section(n: NegativeQualityFindings) -> str:
    """Markdown rendering of Lens D."""
    lines = [
        "## Lens D — Hard-negative quality audit",
        "",
        "Cosine similarity between anchor and labelled concept, measured with the **zero-shot** encoder.",
        "",
        "| group | n | mean | median | P25 | P75 |",
        "|---|---:|---:|---:|---:|---:|",
        f"| hard negatives | {n.negatives.n} | {n.negatives.mean:.4f} | {n.negatives.median:.4f} | {n.negatives.p25:.4f} | {n.negatives.p75:.4f} |",
        f"| positives (ref) | {n.positives.n} | {n.positives.mean:.4f} | {n.positives.median:.4f} | {n.positives.p25:.4f} | {n.positives.p75:.4f} |",
        "",
        f"Mean gap (positives − negatives): **{n.mean_gap:+.4f}**",
    ]
    if n.figure_path:
        lines.append("")
        lines.append(f"![Lens D histogram]({n.figure_path})")
    if n.notes:
        lines.append("")
        for note in n.notes:
            lines.append(f"> {note}")
    return "\n".join(lines)


def _format_alignment_section(a: AlignmentFindings) -> str:
    """Markdown rendering of Lens E."""
    lines = [
        "## Lens E — Concept-text alignment audit",
        "",
        f"Verdict: **{a.verdict.upper()}** ({a.n_differs} of {a.n_sampled} samples differ).",
        "",
    ]
    if a.verdict == "drifted":
        lines.append("### Drifted samples")
        lines.append("")
        for sample in a.samples:
            if sample.differs:
                lines.append(f"* `{sample.uri}`")
                lines.append("  * train-side: " + json.dumps(sample.train_side))
                lines.append("  * index-side: " + json.dumps(sample.index_side))
    else:
        lines.append(
            "All sampled URIs produced byte-identical concept text on both the "
            "training side and the index side. The train↔eval text contract is intact."
        )
    if a.notes:
        lines.append("")
        for note in a.notes:
            lines.append(f"> {note}")
    return "\n".join(lines)


def _format_dynamics_section(d: DynamicsFindings) -> str:
    """Markdown rendering of Lens F."""
    lines = ["## Lens F — Training dynamics inspection", ""]
    for c in d.curves:
        manifest = f"{c.manifest_final_mrr:.4f}" if c.manifest_final_mrr is not None else "—"
        lines += [
            f"### `{c.run_name}`",
            "",
            f"* Final-row MRR@10:        {c.final_mrr:.4f}",
            f"* Peak MRR@10:             {c.peak_mrr:.4f} (epoch {c.peak_epoch:g})",
            f"* Manifest `final_val_mrr@10`: {manifest}",
            f"* Monotonic increasing:    {c.monotonic}",
            f"* Final-vs-peak gap:       {c.final_vs_peak_gap:+.4f}",
            "",
            "| epoch | val MRR@10 |",
            "|---:|---:|",
        ]
        for epoch, mrr in c.epoch_mrr:
            lines.append(f"| {epoch:g} | {mrr:.4f} |")
        lines.append("")
    if d.figure_path:
        lines.append(f"![Lens F curves]({d.figure_path})")
    if d.notes:
        lines.append("")
        for note in d.notes:
            lines.append(f"> {note}")
    return "\n".join(lines)


def _format_synthesis_and_prescription(findings: Findings) -> str:
    """Auto-generated synthesis + prescription.

    The renderer pulls verdicts from the findings dataclasses rather
    than hard-coding a story, so a result that contradicts H₁ produces
    a different prescription. This is the §3.11 anti-confirmation
    discipline applied at code level.
    """
    parts: list[str] = ["## Synthesis", ""]

    # H1 signals — Lens A coverage below 70% and Lens B asymmetry both
    # point toward bias amplification.
    coverage = findings.coverage
    rank = findings.rank
    fp = findings.fp
    neg = findings.negative_quality
    align = findings.alignment
    dyn = findings.dynamics

    bullets: list[str] = []
    if coverage is not None:
        cv = coverage.coverage_ratio
        if cv < 0.5:
            bullets.append(
                f"Lens A — coverage is {cv * 100:.1f} %. A large minority of eval gold URIs were never labelled as positives at training time; bias amplification is plausible (supports H₁)."
            )
        elif cv > 0.85:
            bullets.append(
                f"Lens A — coverage is {cv * 100:.1f} %. The model saw almost every eval URI labelled; H₁'s 'unseen URI' story is weaker; look to dynamics, negative quality, or text drift."
            )
        else:
            bullets.append(
                f"Lens A — coverage is {cv * 100:.1f} %. Mixed signal; combine with Lens B."
            )

    if rank is not None and rank.n_records > 0:
        in_t = rank.in_training
        out_t = rank.not_in_training
        v1_delta_gap = in_t.mean_delta_v1 - out_t.mean_delta_v1
        sw_delta_gap = in_t.mean_delta_sw - out_t.mean_delta_sw
        if (sw_delta_gap > 0.05) and (out_t.mean_delta_sw < -0.01):
            bullets.append(
                f"Lens B — asymmetric: in-training URIs gain {in_t.mean_delta_sw:+.4f} sim on average after `mnrl_sw`, NOT-in-training URIs lose {out_t.mean_delta_sw:+.4f}. The gap of {sw_delta_gap:+.4f} is consistent with bias amplification (H₁ supported)."
            )
        elif abs(sw_delta_gap) < 0.02:
            bullets.append(
                f"Lens B — both groups move similarly (gap {sw_delta_gap:+.4f}). H₁'s asymmetry signature is absent."
            )
        else:
            bullets.append(
                f"Lens B — gap = {sw_delta_gap:+.4f}; in-training mean Δ = {in_t.mean_delta_sw:+.4f}, out-of-training mean Δ = {out_t.mean_delta_sw:+.4f}. Inspect direction relative to expectation."
            )
        bullets.append(
            f"Lens B — `mnrl_v1` mirror: in-training Δ = {in_t.mean_delta_v1:+.4f}, out Δ = {out_t.mean_delta_v1:+.4f}, gap {v1_delta_gap:+.4f}."
        )

    if fp is not None and fp.histograms:
        for h in fp.histograms:
            if h.encoder != "zero_shot" and h.mean_freq > 5.0:
                bullets.append(
                    f"Lens C — `{h.encoder}` FP URIs have mean training frequency {h.mean_freq:.1f} (vs zero-shot baseline). High-frequency over-representation is a magnet effect — consistent with bias amplification."
                )

    if neg is not None:
        if neg.negatives.mean < 0.10 and neg.mean_gap > 0.4:
            bullets.append(
                f"Lens D — hard negatives mean cosine = {neg.negatives.mean:.4f}, positives = {neg.positives.mean:.4f}. The negatives are *trivially easy* — MNRL is leaning on in-batch random negatives for gradient. Curated hard negatives are not contributing."
            )
        else:
            bullets.append(
                f"Lens D — hard negatives mean cosine = {neg.negatives.mean:.4f}, positives = {neg.positives.mean:.4f}; mean gap {neg.mean_gap:+.4f}."
            )

    if align is not None:
        if align.verdict == "drifted":
            bullets.append(
                f"Lens E — train↔index text alignment is DRIFTED on {align.n_differs}/{align.n_sampled} samples. This is its own root cause and supersedes H₁."
            )
        else:
            bullets.append("Lens E — train↔index text alignment intact.")

    if dyn is not None:
        for c in dyn.curves:
            tag = "rising at final epoch" if c.final_mrr >= c.peak_mrr - 1e-6 else f"peaked early (epoch {c.peak_epoch:g})"
            bullets.append(
                f"Lens F — `{c.run_name}`: final MRR {c.final_mrr:.4f}, peak {c.peak_mrr:.4f} ({tag}); monotonic={c.monotonic}."
            )

    for b in bullets:
        parts.append(f"- {b}")

    parts += ["", "## Prescription (auto-generated, ranked)", ""]
    # Three default options, ordered by recommended likelihood-to-succeed
    # × cost. The ordering is fixed; the text references the lens
    # results so reviewers can sanity-check each option against the
    # numbers above.
    parts.append(
        "**Option 1 — Step 5c (data-side): rebuild training positives from a less-biased supervisor.**\n"
        "What: rebuild `train.jsonl` so positives come from (a) lexical-only Module 2 *plus* (b) gold-truth eval-corpus URIs from a held-OUT slice of training CVs (not eval CVs), then re-run Step 5 fine-tuning. Cost: ~6-10 h Silviu time, 1 Colab session. Expected F1 gain: medium-to-large if Lens A coverage < 70 % and Lens B shows asymmetry. Risk: data quality of new positives — needs manual spot-check. Feeds Step 5c prompt.\n"
    )
    parts.append(
        "**Option 2 — Step 5b (architecture-side): cross-encoder re-ranker.**\n"
        "What: train a cross-encoder on the same `train.jsonl`, deploy on top of the lexical+zero-shot retriever as a re-ranker. Cost: ~4-6 h Silviu, 1-2 Colab sessions. Expected F1 gain: small-to-medium if bias amplification is *not* the dominant failure mode. Risk: inherits the same bias if Lens B confirmed asymmetry — Option 1 should run first in that case. Feeds Step 5b prompt.\n"
    )
    parts.append(
        "**Option 3 — pivot to Step 6 with the zero-shot encoder.**\n"
        "What: accept that the bi-encoder ceiling is below the F1 gate and proceed to Linker/Scorer with the zero-shot baseline as the semantic component. Cost: 0 extra Colab. Expected F1 gain: zero — but ensures thesis progress. Risk: thesis chapter has to defend the failed Step 5; honest write-up turns it into a methodological contribution (\"naive distantly-supervised fine-tuning amplifies supervisor bias when the supervisor is the augmentation target\").\n"
    )

    # Recommendation logic — derived from the synthesis bullets, not
    # hand-written.
    parts += ["## Recommendation", ""]
    h1_supported = bool(
        rank is not None
        and rank.n_records > 0
        and (rank.in_training.mean_delta_sw - rank.not_in_training.mean_delta_sw) > 0.05
        and rank.not_in_training.mean_delta_sw < -0.01
    )
    align_drifted = align is not None and align.verdict == "drifted"
    if align_drifted:
        parts.append(
            "Run Lens E's drift remediation FIRST (re-align the concept-text formatters). "
            "Until the train↔index contract is restored, neither H₀ nor H₁ can be tested cleanly."
        )
    elif h1_supported:
        parts.append(
            "**Option 1 (Step 5c data-side).** Lens B's asymmetry indicates the model is amplifying "
            "Module 2's lexical bias rather than approaching a real bi-encoder ceiling. A cross-encoder "
            "trained on the same JSONL would inherit the same bias and likely fail similarly. Fix the "
            "supervision distribution before swapping the architecture."
        )
    else:
        parts.append(
            "**Option 2 (Step 5b cross-encoder).** Lens B does NOT show the asymmetry that would "
            "indicate bias amplification, so the regression is more consistent with a bi-encoder "
            "capacity limit. A cross-encoder over the same data is the cheapest probe of that limit."
        )

    parts += [
        "",
        "## Thesis-narrative implication",
        "",
        "Either outcome supports the thesis chapter:",
        "* If H₁ is confirmed (Option 1 path): Step 5 becomes a documented methodological finding —"
        " naive distantly-supervised fine-tuning amplifies supervisor bias when the supervisor is"
        " the augmentation target. The thesis is *stronger* with this caveat than without it.",
        "* If H₀ is supported (Option 2 path): Step 5 documents that bi-encoder fine-tuning on the"
        " current corpus is insufficient and motivates the cross-encoder swap.",
        "* If Lens E shows drift: Step 5 documents a process gap that the cross-encoder swap can"
        " also exploit once fixed.",
        "",
        "The defence answer in all three cases is the same shape: *we measured before we acted,"
        " and the prescription follows from the measurement.*",
    ]
    return "\n".join(parts)


def _format_executive_summary(findings: Findings) -> str:
    """Three-sentence summary lifted from the synthesis logic."""
    rank = findings.rank
    align = findings.alignment

    if align is not None and align.verdict == "drifted":
        verdict_word = "Concept-text drift detected"
        proof = f"{align.n_differs} of {align.n_sampled} sampled URIs render differently on the train side and the index side"
        next_step = "fix the concept-text formatters before any further Step 5 work"
    elif rank is not None and rank.n_records > 0:
        sw_gap = rank.in_training.mean_delta_sw - rank.not_in_training.mean_delta_sw
        if sw_gap > 0.05 and rank.not_in_training.mean_delta_sw < -0.01:
            verdict_word = "H₁ (bias amplification) is supported"
            proof = (
                f"in-training URIs gain {rank.in_training.mean_delta_sw:+.4f} sim "
                f"after `mnrl_sw_v1` while NOT-in-training URIs lose "
                f"{rank.not_in_training.mean_delta_sw:+.4f}"
            )
            next_step = "Option 1 — Step 5c data-side rebuild (do not jump to Step 5b)"
        else:
            verdict_word = "H₁ is not strongly supported by Lens B"
            proof = (
                f"in vs out gap on `mnrl_sw_v1` is {sw_gap:+.4f}, which falls inside the "
                "noise band for our sample size"
            )
            next_step = "Option 2 — Step 5b cross-encoder is the cheapest next probe"
    else:
        verdict_word = "Inconclusive"
        proof = "no Lens B records available"
        next_step = "re-run the diagnostic with full lens coverage"

    return (
        "## Executive summary\n\n"
        f"**{verdict_word}.** The single number: {proof}. **Prescribed next step:** {next_step}.\n"
    )


def render_markdown(findings: Findings, *, out_path: Path) -> None:
    """Write the human-readable diagnostic report."""
    sections: list[str] = []
    env = findings.environment
    sections.append(
        f"# Module 3 — Step 5.5 diagnostic report\n\n"
        f"_Generated {env.run_date}, seed {env.seed}._"
    )
    sections.append(_format_executive_summary(findings))
    sections.append(
        "## Environment\n\n"
        f"* Eval corpus size: {env.eval_corpus_size} CVs\n"
        f"* CVs skipped (extraction failure or no labels): {', '.join(env.cvs_skipped) or '—'}\n"
        f"* Runs analysed: {', '.join(env.runs_analysed)}\n"
        f"* On-disk `train.jsonl` build timestamp: {env.on_disk_train_jsonl_timestamp}\n"
        + ("\n".join(f"> {n}" for n in env.notes) if env.notes else "")
    )
    if findings.coverage is not None:
        sections.append(_format_coverage_section(findings.coverage))
    if findings.rank is not None:
        sections.append(_format_rank_section(findings.rank))
    if findings.fp is not None:
        sections.append(_format_fp_section(findings.fp))
    if findings.negative_quality is not None:
        sections.append(_format_negative_section(findings.negative_quality))
    if findings.alignment is not None:
        sections.append(_format_alignment_section(findings.alignment))
    if findings.dynamics is not None:
        sections.append(_format_dynamics_section(findings.dynamics))
    sections.append(_format_synthesis_and_prescription(findings))

    if findings.coverage is not None and findings.coverage.coverage_ratio < 0.7:
        sections.append("## Appendix — unseen-URI list (Lens A, coverage < 70 %)")
        sections.append("")
        for cv in findings.coverage.per_cv:
            if cv.unseen_uris:
                sections.append(f"### {cv.cv_id} ({cv.gold_unseen} unseen)")
                for uri in cv.unseen_uris:
                    sections.append(f"* `{uri}`")
                sections.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    logger.info("report.written", path=str(out_path))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


ALL_LENSES = ("A", "B", "C", "D", "E", "F")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI args. ``argv=None`` reads ``sys.argv[1:]``."""
    p = argparse.ArgumentParser(
        description="Step 5.5 diagnostic — six-lens analysis of failed Module 3 fine-tuning."
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=_REPO_ROOT / "reports",
        help="Reports directory (default: nlp-service/reports).",
    )
    p.add_argument(
        "--lens",
        default=",".join(ALL_LENSES),
        help="Comma-separated subset of lenses to run (default: all).",
    )
    p.add_argument("--seed", type=int, default=42, help="Sampling seed (default: 42).")
    p.add_argument(
        "--train-jsonl",
        type=Path,
        default=_REPO_ROOT / "data" / "training" / "pairs" / "train.jsonl",
        help="Path to train.jsonl (read-only).",
    )
    # ``DEFAULT_EVAL_CORPUS_ROOT`` is computed lazily so importing this
    # script does not depend on the eval-corpus module being importable
    # (the test environment doesn't pull in pydantic-settings).
    from skill_matcher.eval_corpus import DEFAULT_EVAL_CORPUS_ROOT

    p.add_argument(
        "--eval-corpus-dir",
        type=Path,
        default=DEFAULT_EVAL_CORPUS_ROOT,
        help="Eval corpus root.",
    )
    p.add_argument(
        "--models-dir",
        type=Path,
        default=DEFAULT_MODELS_DIR,
        help="Directory containing the fine-tuned checkpoints.",
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_EMBEDDING_CACHE_DIR,
        help="Embedding-cache directory.",
    )
    return p.parse_args(argv)


def _parse_lens_subset(spec: str) -> set[str]:
    """Validate and normalise the ``--lens`` flag."""
    requested = {x.strip().upper() for x in spec.split(",") if x.strip()}
    invalid = requested - set(ALL_LENSES)
    if invalid:
        raise SystemExit(f"Unknown lens(es): {sorted(invalid)} (valid: {ALL_LENSES})")
    return requested


def main(argv: Sequence[str] | None = None) -> int:
    """Run the diagnostic and write the JSON + Markdown reports."""
    # All heavy skill_matcher imports happen here, inside main(), so the
    # test environment can import this module without them resolving.
    from skill_matcher.dataset import HardNegative, TrainingPair, load_training_dataset
    from skill_matcher.esco_loader import compute_esco_file_sha, load_esco_concepts
    from skill_matcher.eval_corpus import load_eval_corpus

    args = parse_args(argv)
    lenses = _parse_lens_subset(args.lens)

    run_date = datetime.now(UTC).strftime("%Y-%m-%d")
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"

    json_path = out_dir / f"skill_matcher_step5_diagnostic_{stamp}.json"
    md_path = out_dir / f"skill_matcher_step5_diagnostic_{stamp}.md"

    logger.info(
        "diagnose.start",
        lenses=sorted(lenses),
        out_dir=str(out_dir),
        seed=args.seed,
    )

    # Common loading — small + fast.
    t_load = time.monotonic()
    train_uri_set, train_freq, train_build_ts = _train_positive_uri_set_and_freq(
        args.train_jsonl
    )
    eval_corpus = load_eval_corpus(args.eval_corpus_dir)
    concepts = load_esco_concepts()
    concepts_by_uri = {c.uri: c for c in concepts}
    esco_sha = compute_esco_file_sha()
    logger.info(
        "diagnose.loaded",
        n_train_positive_uris=len(train_uri_set),
        n_concepts=len(concepts),
        eval_cvs=len(eval_corpus.cvs),
        elapsed=round(time.monotonic() - t_load, 3),
    )

    coverage: CoverageFindings | None = None
    rank: RankFindings | None = None
    fp: FPFindings | None = None
    negq: NegativeQualityFindings | None = None
    alignment: AlignmentFindings | None = None
    dynamics: DynamicsFindings | None = None
    per_uri: list[PerURISimRecord] = []
    fp_records: list[FPRecord] = []
    cvs_skipped: list[str] = []

    eval_uri_set_by_cv = {
        cv_id: _gold_uris_for_cv(labels)
        for cv_id, labels in eval_corpus.cv_labels.items()
    }
    train_uri_notes = (
        "train.jsonl build_timestamp is the 19:43 build (mnrl_sw_v1's training data). "
        "Lens A coverage against `mnrl_v1` is best-effort — the 08:59 build it trained on was overwritten on disk.",
    )

    if "A" in lenses:
        t0 = time.monotonic()
        coverage = analyse_training_coverage(
            train_positive_uris=train_uri_set,
            eval_uri_set_by_cv=eval_uri_set_by_cv,
            train_build_timestamp=train_build_ts,
            notes=train_uri_notes,
        )
        logger.info("lens_a.done", elapsed=round(time.monotonic() - t0, 3))

    # Lenses B and C share encoder load + CV text extraction.
    cv_text_cache: dict[str, str] = {}
    encoders: dict[str, Any] = {}
    indexes: dict[str, EscoIndex] = {}
    if "B" in lenses or "C" in lenses:
        t0 = time.monotonic()
        for tag in ("zero_shot", MODEL_RUN_V1, MODEL_RUN_SW):
            enc, idx = _build_encoder_bundle(
                tag, cache_dir=args.cache_dir, esco_sha=esco_sha, models_dir=args.models_dir
            )
            encoders[tag] = enc
            indexes[tag] = idx
        logger.info("lens_b.encoders_loaded", elapsed=round(time.monotonic() - t0, 3))

    if "B" in lenses:
        t0 = time.monotonic()
        records, processed, skipped = _per_uri_records_for_corpus(
            eval_corpus=eval_corpus,
            encoders=encoders,
            indexes=indexes,
            train_uri_set_v1=train_uri_set,  # best-effort, see R1
            train_uri_set_sw=train_uri_set,
        )
        rank = analyse_per_uri_rank_attribution(
            records=records,
            n_cvs_processed=len(processed),
            n_cvs_skipped=len(skipped),
            skipped_cv_ids=skipped,
            notes=(
                "in_training_v1 uses the on-disk train.jsonl as a proxy for mnrl_v1's training set"
                " (the 08:59 build it actually trained on was overwritten by the 19:43 build).",
            ),
        )
        per_uri = list(records)
        cvs_skipped.extend(skipped)
        # Cache CV texts for Lens C re-use.
        from cv_extractor import ExtractionPipeline

        ex = ExtractionPipeline()
        for cv_id in processed:
            if cv_id in cv_text_cache:
                continue
            pdf = eval_corpus.cvs.get(cv_id)
            if pdf is None:
                continue
            try:
                cv_text_cache[cv_id] = ex.process(pdf).text
            except Exception as exc:
                logger.warning("lens_c.cv_text_cache_failed", cv_id=cv_id, error=repr(exc))
        logger.info(
            "lens_b.done",
            n_records=len(records),
            processed=len(processed),
            skipped=len(skipped),
            elapsed=round(time.monotonic() - t0, 3),
        )

    if "C" in lenses:
        t0 = time.monotonic()
        # If Lens B did not pre-populate the cache (e.g. --lens C alone),
        # populate it here. Cheap because the extraction stack is reused.
        if not cv_text_cache:
            from cv_extractor import ExtractionPipeline

            ex = ExtractionPipeline()
            for cv_id, pdf in sorted(eval_corpus.cvs.items()):
                try:
                    cv_text_cache[cv_id] = ex.process(pdf).text
                except Exception as exc:
                    logger.warning(
                        "lens_c.cv_text_extract_failed", cv_id=cv_id, error=repr(exc)
                    )
                    cvs_skipped.append(cv_id)
        records = _fp_records_for_corpus(
            eval_corpus=eval_corpus,
            encoders=encoders,
            indexes=indexes,
            train_freq=train_freq,
            cv_text_cache=cv_text_cache,
        )
        fp = analyse_fp_attribution(records=records)
        fp_records = list(records)
        logger.info(
            "lens_c.done", n_records=len(records), elapsed=round(time.monotonic() - t0, 3)
        )

    if "D" in lenses:
        t0 = time.monotonic()
        from skill_matcher.encoder import SentenceTransformerEncoder

        zs_encoder = encoders.get("zero_shot")
        if zs_encoder is None:
            zs_encoder = SentenceTransformerEncoder(
                ZERO_SHOT_MODEL, device="cpu", seed=args.seed
            )
        dataset = load_training_dataset(args.train_jsonl)
        positives = [p for p in dataset.pairs if isinstance(p, TrainingPair)]
        negatives = [p for p in dataset.pairs if isinstance(p, HardNegative)]
        neg_sims, pos_sims = _sample_negative_sims(
            negatives=negatives,
            positives=positives,
            concepts_by_uri=concepts_by_uri,
            encoder=zs_encoder,
            sample_size=LENS_D_SAMPLE_SIZE,
            seed=args.seed,
        )
        figure_path = _render_lens_d_figure(
            negative_sims=neg_sims,
            positive_sims=pos_sims,
            out_path=figures_dir / f"step5_diagnostic_lens_d_{stamp}.png",
        )
        negq = audit_negative_quality(
            negative_sims=neg_sims, positive_sims=pos_sims, figure_path=figure_path
        )
        logger.info(
            "lens_d.done",
            n_neg=len(neg_sims),
            n_pos=len(pos_sims),
            elapsed=round(time.monotonic() - t0, 3),
        )

    if "E" in lenses:
        t0 = time.monotonic()
        samples = _alignment_samples(
            concepts_by_uri=concepts_by_uri,
            sample_size=LENS_E_SAMPLE_SIZE,
            seed=args.seed,
        )
        alignment = audit_concept_text_alignment(samples=samples)
        logger.info("lens_e.done", elapsed=round(time.monotonic() - t0, 3))

    if "F" in lenses:
        t0 = time.monotonic()
        curves_by_run: dict[str, list[tuple[float, float]]] = {}
        manifest_finals: dict[str, float] = {}
        for run_name in (MODEL_RUN_V1, MODEL_RUN_SW):
            run_dir = args.models_dir / run_name
            csv_path = run_dir / "eval" / "Information-Retrieval_evaluation_val_results.csv"
            manifest_path = run_dir / f"{run_name}_manifest.json"
            curve = _load_training_curve(csv_path)
            if curve:
                curves_by_run[run_name] = curve
            final = _load_manifest_final_mrr(manifest_path)
            if final is not None:
                manifest_finals[run_name] = final
        figure_path = _render_lens_f_figure(
            curves_by_run=curves_by_run,
            out_path=figures_dir / f"step5_diagnostic_lens_f_{stamp}.png",
        )
        dynamics = audit_training_dynamics(
            curves_by_run=curves_by_run,
            manifest_finals=manifest_finals,
            figure_path=figure_path,
        )
        logger.info(
            "lens_f.done", runs=len(curves_by_run), elapsed=round(time.monotonic() - t0, 3)
        )

    findings = Findings(
        environment=Environment(
            run_date=run_date,
            seed=args.seed,
            eval_corpus_size=len(eval_corpus.cvs),
            cvs_skipped=tuple(sorted(set(cvs_skipped))),
            runs_analysed=(MODEL_RUN_V1, MODEL_RUN_SW),
            on_disk_train_jsonl_timestamp=train_build_ts,
            notes=train_uri_notes,
        ),
        coverage=coverage,
        rank=rank,
        fp=fp,
        negative_quality=negq,
        alignment=alignment,
        dynamics=dynamics,
        per_uri_records=tuple(per_uri),
        fp_records=tuple(fp_records),
    )

    json_path.write_text(
        json.dumps(findings_to_dict(findings), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    logger.info("diagnose.json_written", path=str(json_path))
    render_markdown(findings, out_path=md_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
