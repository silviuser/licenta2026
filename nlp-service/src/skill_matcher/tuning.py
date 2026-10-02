"""Phase C -- threshold tuning machinery (Step 8 deliverable).

This module is the **pure-Python** core of the Step 8 grid search. It
operates on per-cell intermediates produced by
:meth:`skill_matcher.scorer.Scorer.score_to_intermediates` and re-
aggregates / re-projects them across the three-tier knob space:

* **Tier 0** -- ``(t1, t2)`` 3-class projection. Trivial cost.
* **Tier 1** -- ``(per_requirement_keep_threshold, required_weight)``
  aggregation. Pure arithmetic over saved intermediates; cheap.
* **Tier 2** -- ``(drop_threshold, keep_threshold, expansion_threshold)``
  Linker thresholds. Expensive: requires a fresh Linker + Scorer pass
  (handled by ``scripts/tune_thresholds.py``, NOT by this module).

The module is **encoder-agnostic and I/O-free**: it never imports an
encoder, never reads or writes a file, never invokes the Linker or the
Scorer. All it does is consume a flat list of ``CellIntermediate``
objects and produce ``TuningMetric`` rows. This keeps the unit tests
fast (synthetic intermediates) and decouples grid-search semantics from
pipeline plumbing.

Three-tier cost asymmetry (Step 8 Pre-Flight ASCII diagram)
-----------------------------------------------------------
::

    Tier 2 (drop, keep_link, expansion)        expensive
            |  -> re-run Linker (handled by tune_thresholds.py)
            v
    Tier 1 (per_req_keep, required_weight)     cheap
            |  -> aggregate_from_intermediates(...)
            v
    Tier 0 (T1, T2)                            trivial
            |  -> project_to_three_class(...)
            v
    compute_metric(...) -> TuningMetric

``uri_similarity`` is invariant under Tier 0 and Tier 1 -- it depends
only on the encoder and the Linker's filtered candidate set. Tier 1 +
Tier 0 reuse the SAME intermediates within one Tier 2 iteration.

Determinism (DECISIONS.md D10)
------------------------------
Grid generators emit values in deterministic ``itertools.product`` order
over sorted knob lists. The ``best_combo`` tie-break is lexicographic
on the ``TuningCombo`` tuple (after objective score). Two consecutive
``run_tier1_tier0_only`` calls on the same intermediates and gold map
produce byte-identical ``TuningRunResult`` (modulo ``elapsed_seconds``,
which is excluded from any equality comparison).
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Public types -- intermediates produced by Scorer.score_to_intermediates
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReqIntermediate:
    """One requirement's pre-gate scoring inputs.

    Carries the three multiplicative factors that determine
    ``match_score = req_confidence * candidate_confidence * uri_similarity``
    plus the per-requirement importance flag, with the
    ``per_requirement_keep_threshold`` gate intentionally NOT applied.
    Tier 1 sweeps re-apply the gate at any candidate threshold without
    re-encoding.

    Fields
    ------
    req_text
        Original requirement phrase (verbatim from the JD). Carried for
        provenance / debugging only -- the grid search itself does not
        read it.
    importance
        ``"required"`` or ``"nice_to_have"``. Drives the Tier 1
        aggregation weighting.
    req_confidence
        ``JDRequirement.confidence`` after Scorer's online URI
        resolution. Always in ``[0.0, 1.0]``.
    candidate_confidence
        ``MatchCandidate.confidence`` of the best CV candidate matched
        to this requirement. ``0.0`` iff no candidate cleared the
        Scorer's ``keep_threshold`` semantic-fallback gate (the gate
        IS applied because lowering it requires a re-encode -- that's
        a Tier 2 concern, not Tier 1).
    uri_similarity
        ``1.0`` for exact URI match; the raw cosine similarity in
        ``[keep_threshold, 1.0]`` for a semantic fallback; ``0.0`` for
        an unmatched requirement.
    """

    req_text: str
    importance: Literal["required", "nice_to_have"]
    req_confidence: float
    candidate_confidence: float
    uri_similarity: float


@dataclass(frozen=True, slots=True)
class CellIntermediate:
    """Pre-aggregation intermediate state for one ``(cv_id, jd_id)`` cell.

    Produced by :meth:`Scorer.score_to_intermediates`. Holds the list of
    :class:`ReqIntermediate` tuples plus the Linker thresholds in force
    when the intermediates were computed (provenance -- prevents Tier 1
    from accidentally re-using intermediates that came from a different
    Tier 2 combo).
    """

    cv_id: str
    jd_id: str
    requirements: tuple[ReqIntermediate, ...]
    linker_thresholds: tuple[float, float, float]
    """``(drop, keep, expansion)`` -- the Linker config in force when
    these intermediates were produced. Tier 1 / Tier 0 ignore this
    field; the CLI driver uses it to assert provenance and to log per-
    Tier-2-combo elapsed time."""


# ---------------------------------------------------------------------------
# Public types -- the 7-dim grid point and its evaluation outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, order=True)
class TuningCombo:
    """One point in the 7-dimensional knob space.

    Field order matches the lexicographic tie-break used by
    :func:`run_tier1_tier0_only` when two combos hit the same objective
    score (``order=True`` enables that automatically).
    """

    drop_threshold: float
    keep_threshold: float
    expansion_threshold: float
    per_requirement_keep_threshold: float
    required_weight: float
    """Tier 1 weight on the ``required_score`` component; the
    nice-to-have weight is implicitly ``1.0 - required_weight``."""
    t1: float
    """3-class projection: ``score >= t1`` -> ``"strong"``."""
    t2: float
    """3-class projection: ``t2 <= score < t1`` -> ``"possible"``;
    ``score < t2`` -> ``"no"``. Invariant: ``t2 < t1``."""


@dataclass(frozen=True, slots=True)
class TuningMetric:
    """Outcome of evaluating one :class:`TuningCombo` against the gold map.

    Carries the per-class confusion matrix, the per-class P/R/F1, the
    headline macro F1, and the guard outcome. ``elapsed_seconds`` is
    intentionally absent -- per-combo timing is too noisy to be useful
    at this scale; only the whole-run timing is reported.
    """

    combo: TuningCombo
    macro_f1: float
    weighted_f1: float
    plain_accuracy: float
    weighted_accuracy: float
    f1_strong: float
    f1_possible: float
    f1_no: float
    precision_strong: float
    precision_possible: float
    precision_no: float
    recall_strong: float
    recall_possible: float
    recall_no: float
    n_predicted: dict[str, int]
    """``{"strong": ..., "possible": ..., "no": ...}`` count of cells
    the projection assigned to each class. Always sums to ``n_cells``."""
    confusion: dict[tuple[str, str], int]
    """``{(gold_class, pred_class) -> count}`` for every class pair.
    Equivalent to a 3x3 matrix; this shape is JSON-friendly."""
    guards_passed: bool
    """``True`` iff every guard in the active guard set passed."""
    guards_failed: tuple[str, ...]
    """Names of guards that failed. Empty when ``guards_passed`` is
    ``True``. Reported verbatim in the markdown so reviewers know
    exactly which safety check vetoed a combo."""


@dataclass(slots=True)
class TuningRunResult:
    """Whole-sweep outcome.

    Reports the best combo (strict guards), plus two fallback rows so
    the report can be transparent when even the relaxed guards fail.

    Determinism note: ``elapsed_seconds`` is excluded from any equality
    comparison; the rest of the fields are byte-stable across runs.
    """

    best_combo: TuningCombo | None
    """``None`` iff no combo passed the strict guard set."""
    best_metric: TuningMetric | None
    """``None`` iff ``best_combo`` is ``None``."""
    fallback_unguarded: TuningMetric | None
    """Best combo under macro F1 alone (no guards). Always populated
    when ``all_metrics`` is non-empty -- this is the "degenerate
    optimum" the report flags when calibration is impossible."""
    fallback_relaxed: TuningMetric | None
    """Best combo under the relaxed guard set (precision/recall floors
    dropped to 0.02, distribution-non-empty guard removed). Populated
    independently of the strict best so the report can show "you could
    lock these defaults but at relaxed safety"."""
    all_metrics: list[TuningMetric] = field(default_factory=list)
    """Every evaluated combo with its outcome. Sorted by macro F1
    descending; ties broken by lexicographic ``TuningCombo`` order
    (deterministic)."""
    config_used: dict[str, Any] = field(default_factory=dict)
    """Free-form record of the grid sizes, objective, locked Linker
    triple (fast mode), seed, etc. Round-trips through JSON unchanged."""
    elapsed_seconds: float = 0.0
    """Wall-clock spent in Tier 1 + Tier 0 sweeping. Excluded from
    equality / determinism comparisons."""


# ---------------------------------------------------------------------------
# Fit classes -- mirrors evaluate_matcher.py
# ---------------------------------------------------------------------------

FitClass = Literal["strong", "possible", "no"]
"""The three fit classes used end-to-end in Module 3. Mirrors
:data:`skill_matcher.eval_corpus.FitJudgment` -- re-declared here so
this module has no dependency on ``eval_corpus`` (the grid search
operates on intermediates + a gold map, nothing else)."""

_CLASSES: tuple[FitClass, ...] = ("strong", "possible", "no")


# ---------------------------------------------------------------------------
# Grid generators
# ---------------------------------------------------------------------------


# Tier 2 -- the Linker thresholds.
#
# The Linker constructor enforces
# ``0.0 <= drop <= keep <= expansion <= 1.0`` (linker.py:174-188), so
# ``grid_for_tier_2`` filters illegal triples out at generation time
# rather than relying on the Linker to raise.
_TIER2_DROP: tuple[float, ...] = (0.40, 0.45, 0.50)
_TIER2_KEEP: tuple[float, ...] = (0.50, 0.55, 0.60)
_TIER2_EXPANSION: tuple[float, ...] = (0.65, 0.75, 0.85)
_TIER2_FAST_LOCKED: tuple[float, float, float] = (0.45, 0.55, 0.75)
"""``--mode fast`` locks the Tier 2 triple at the Step 4 / Step 6
amendment defaults so the script only sweeps Tier 1 + Tier 0."""


# Tier 1.
_TIER1_PER_REQ_KEEP: tuple[float, ...] = tuple(
    round(0.01 + 0.025 * i, 4) for i in range(20)
)
"""20 values: 0.01, 0.035, 0.06, ..., 0.485. Bounded inside
``[0.01, 0.50]`` per the Step 8 brief; resolution 0.025 is dense
enough to land on the score-distribution percentiles."""

_TIER1_REQUIRED_WEIGHT: tuple[float, ...] = (0.5, 0.7, 0.8, 0.9, 1.0)
"""Five candidates from the Step 8 brief. ``1.0`` is the
"ignore nice-to-haves" extreme; included for ablation."""


# Tier 0.
_TIER0_T1: tuple[float, ...] = tuple(
    round(0.02 + 0.04 * i, 4) for i in range(20)
)
"""40 values: 0.02, 0.04, 0.06, ..., 0.80. Resolution 0.02 sits below
the ~0.011 gap between distinct scores in the Step 7 baseline JSON."""

_TIER0_T2: tuple[float, ...] = tuple(
    round(0.005 + 0.02 * i, 4) for i in range(25)
)
"""50 values: 0.005, 0.015, 0.025, ..., 0.495. Step 8 Pre-Flight §5
showed the gold-no distribution sits almost entirely below 0.05, so
T2 below 0.05 is well-populated."""


def grid_for_tier_2(fast: bool) -> Iterator[tuple[float, float, float]]:
    """Generate ``(drop, keep, expansion)`` triples for the Tier 2 sweep.

    Parameters
    ----------
    fast
        When ``True``, yields a single locked triple (Step 4 / Step 6
        amendment defaults) -- the ``--mode fast`` sweep. When
        ``False``, yields every legal triple from the brief's grid.

    Yields
    ------
    tuple[float, float, float]
        ``(drop, keep, expansion)`` satisfying
        ``0 <= drop <= keep <= expansion <= 1``. Order is deterministic:
        sorted-tuple lexicographic.
    """
    if fast:
        yield _TIER2_FAST_LOCKED
        return
    for drop, keep, expansion in itertools.product(
        _TIER2_DROP, _TIER2_KEEP, _TIER2_EXPANSION
    ):
        if not (0.0 <= drop <= keep <= expansion <= 1.0):
            continue
        yield (drop, keep, expansion)


def grid_for_tier_1() -> Iterator[tuple[float, float]]:
    """Yield ``(per_requirement_keep_threshold, required_weight)`` pairs."""
    yield from itertools.product(
        _TIER1_PER_REQ_KEEP, _TIER1_REQUIRED_WEIGHT
    )


def grid_for_tier_0() -> Iterator[tuple[float, float]]:
    """Yield ``(t1, t2)`` pairs with the ``t2 < t1`` constraint enforced."""
    for t1, t2 in itertools.product(_TIER0_T1, _TIER0_T2):
        if t2 >= t1:
            continue
        yield (t1, t2)


def grid_size_tier_2(fast: bool) -> int:
    """How many Tier 2 combos the sweep will visit. O(1) -- enumerates."""
    return sum(1 for _ in grid_for_tier_2(fast))


def grid_size_tier_1() -> int:
    """How many Tier 1 combos the sweep will visit. O(1)."""
    return sum(1 for _ in grid_for_tier_1())


def grid_size_tier_0() -> int:
    """How many Tier 0 combos the sweep will visit. O(1)."""
    return sum(1 for _ in grid_for_tier_0())


# ---------------------------------------------------------------------------
# Tier 1 -- re-aggregate from saved intermediates
# ---------------------------------------------------------------------------


def aggregate_from_intermediates(
    intermediates: Iterable[CellIntermediate],
    *,
    per_requirement_keep_threshold: float,
    required_weight: float,
) -> dict[tuple[str, str], float]:
    """Re-compute per-cell ``overall_score`` from saved intermediates.

    This is the cheap inner function the Tier 1 sweep calls 200x per
    Tier 2 iteration. Pure arithmetic; no encoder, no Linker.

    Parameters
    ----------
    intermediates
        Cells produced by :meth:`Scorer.score_to_intermediates` (with
        ``per_requirement_keep_threshold=0.0`` so the gate did NOT
        suppress any tuple).
    per_requirement_keep_threshold
        Tier 1 gate: a requirement contributes its match score iff
        ``req_conf * cand_conf * uri_sim >= per_requirement_keep_threshold``.
        Otherwise it counts as unmatched (zero numerator, one denominator).
    required_weight
        Tier 1 weight on the required-score component. Must satisfy
        ``0.0 <= required_weight <= 1.0``. The nice-to-have weight is
        derived as ``1.0 - required_weight``. When a JD has zero
        required requirements the function falls back to
        ``overall = nice_score`` (mirrors :meth:`Scorer._aggregate`).

    Returns
    -------
    dict[tuple[str, str], float]
        ``{(cv_id, jd_id) -> overall_score}``. Scores are clamped to
        ``[0.0, 1.0]`` defensively.
    """
    if not (0.0 <= required_weight <= 1.0):
        raise ValueError(
            f"required_weight must be in [0.0, 1.0]; got {required_weight}"
        )
    if not (0.0 <= per_requirement_keep_threshold <= 1.0):
        raise ValueError(
            "per_requirement_keep_threshold must be in [0.0, 1.0]; "
            f"got {per_requirement_keep_threshold}"
        )

    nice_weight = 1.0 - required_weight
    out: dict[tuple[str, str], float] = {}

    for cell in intermediates:
        req_sum = 0.0
        nice_sum = 0.0
        req_total = 0
        nice_total = 0

        for r in cell.requirements:
            match_score = (
                r.req_confidence * r.candidate_confidence * r.uri_similarity
            )
            matched = match_score >= per_requirement_keep_threshold
            if r.importance == "required":
                req_total += 1
                if matched:
                    req_sum += match_score
            else:
                nice_total += 1
                if matched:
                    nice_sum += match_score

        if req_total == 0 and nice_total == 0:
            out[(cell.cv_id, cell.jd_id)] = 0.0
            continue

        req_score = req_sum / req_total if req_total > 0 else 0.0
        nice_score = nice_sum / nice_total if nice_total > 0 else 0.0

        if req_total == 0:
            # Mirrors Scorer._aggregate: no required -> nice carries
            # the whole score (weight collapses to 1.0).
            overall = nice_score
        else:
            overall = required_weight * req_score + nice_weight * nice_score

        # Defensive clamp -- the inputs are bounded in [0, 1] so a
        # convex combination cannot exceed [0, 1], but float drift can.
        out[(cell.cv_id, cell.jd_id)] = max(0.0, min(1.0, overall))

    return out


# ---------------------------------------------------------------------------
# Tier 0 -- 3-class projection
# ---------------------------------------------------------------------------


def project_to_three_class(
    overall_scores: dict[tuple[str, str], float],
    *,
    t1: float,
    t2: float,
) -> dict[tuple[str, str], FitClass]:
    """Project ``overall_score`` -> ``{"strong", "possible", "no"}``.

    Boundary behaviour: ``score >= t1`` is ``"strong"``;
    ``score == t1 - epsilon`` is ``"possible"``. ``score == t2`` is
    ``"possible"`` (inclusive lower bound).

    Parameters
    ----------
    overall_scores
        Output of :func:`aggregate_from_intermediates`.
    t1, t2
        Strong / possible cut points. The constraint ``t2 < t1`` is
        enforced here so a caller bypassing :func:`grid_for_tier_0`
        cannot silently produce a degenerate projection.

    Returns
    -------
    dict[tuple[str, str], FitClass]
        Same keys as the input, with class labels.
    """
    if not (t2 < t1):
        raise ValueError(f"projection requires t2 < t1; got t1={t1}, t2={t2}")

    out: dict[tuple[str, str], FitClass] = {}
    for key, s in overall_scores.items():
        if s >= t1:
            out[key] = "strong"
        elif s >= t2:
            out[key] = "possible"
        else:
            out[key] = "no"
    return out


# ---------------------------------------------------------------------------
# Metric + guards
# ---------------------------------------------------------------------------


def _f1(precision: float, recall: float) -> float:
    """Harmonic mean of precision and recall. Returns 0.0 on a 0/0 case."""
    if precision + recall <= 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def _build_confusion(
    predictions: dict[tuple[str, str], FitClass],
    gold: dict[tuple[str, str], FitClass],
) -> dict[tuple[str, str], int]:
    """Build a confusion dict over ``{(gold_cls, pred_cls) -> count}``.

    Only keys present in BOTH dicts contribute; mismatched keys (gold
    available but no prediction, or vice versa) are dropped silently.
    The CLI driver guards against this upstream by intersecting the
    keys before calling.
    """
    confusion: dict[tuple[str, str], int] = {
        (g, p): 0 for g in _CLASSES for p in _CLASSES
    }
    for key, gold_cls in gold.items():
        if key not in predictions:
            continue
        pred_cls = predictions[key]
        confusion[(gold_cls, pred_cls)] += 1
    return confusion


def _per_class_metrics(
    confusion: dict[tuple[str, str], int],
) -> tuple[
    dict[FitClass, float], dict[FitClass, float], dict[FitClass, float]
]:
    """Per-class precision, recall, F1 from a confusion dict.

    Precision uses ``pred_total`` as the denominator (0/0 -> 0.0).
    Recall uses ``gold_total`` as the denominator (0/0 -> 0.0).
    """
    precision: dict[FitClass, float] = {}
    recall: dict[FitClass, float] = {}
    f1: dict[FitClass, float] = {}
    for cls in _CLASSES:
        tp = confusion[(cls, cls)]
        pred_total = sum(confusion[(g, cls)] for g in _CLASSES)
        gold_total = sum(confusion[(cls, p)] for p in _CLASSES)
        p = tp / pred_total if pred_total > 0 else 0.0
        r = tp / gold_total if gold_total > 0 else 0.0
        precision[cls] = p
        recall[cls] = r
        f1[cls] = _f1(p, r)
    return precision, recall, f1


def _evaluate_guards(
    combo: TuningCombo,
    overall_scores: dict[tuple[str, str], float],
    confusion: dict[tuple[str, str], int],
    precision: dict[FitClass, float],
    recall: dict[FitClass, float],
    *,
    precision_floor: float,
    recall_floor: float,
    check_distribution_buckets: bool,
) -> list[str]:
    """Return the list of guard NAMES that FAILED. Empty list = all passed.

    The five guards from the Step 8 brief:

    1. ``all_three_classes_predicted`` -- every class is the prediction
       of at least one cell.
    2. ``precision_floor_<cls>`` -- per-class precision >= floor.
    3. ``recall_floor_<cls>`` -- per-class recall >= floor.
    4. ``t2_lt_t1`` -- enforced at the grid level; checked here too
       for defence-in-depth.
    5. ``score_buckets_non_empty`` -- ``overall_score`` distribution
       has at least one value below ``t2``, at least one in
       ``[t2, t1)``, and at least one ``>= t1``.

    The relaxed guard set drops #2/#3 floors to a tiny value and drops
    #5 entirely; the strict set uses the parameters as given.
    """
    failures: list[str] = []

    # Guard 4 (defensive) -- t2 < t1.
    if not (combo.t2 < combo.t1):
        failures.append("t2_lt_t1")

    # Guard 1 -- all three classes predicted at least once.
    predicted_classes: set[str] = set()
    for cls in _CLASSES:
        n_pred = sum(confusion[(g, cls)] for g in _CLASSES)
        if n_pred > 0:
            predicted_classes.add(cls)
    if len(predicted_classes) < 3:
        failures.append("all_three_classes_predicted")

    # Guard 2 + 3 -- per-class precision / recall floors.
    for cls in _CLASSES:
        if precision[cls] < precision_floor:
            failures.append(f"precision_floor_{cls}")
        if recall[cls] < recall_floor:
            failures.append(f"recall_floor_{cls}")

    # Guard 5 -- non-empty buckets in overall_score distribution.
    if check_distribution_buckets:
        below_t2 = sum(1 for s in overall_scores.values() if s < combo.t2)
        between = sum(
            1 for s in overall_scores.values() if combo.t2 <= s < combo.t1
        )
        above_t1 = sum(1 for s in overall_scores.values() if s >= combo.t1)
        if below_t2 == 0 or between == 0 or above_t1 == 0:
            failures.append("score_buckets_non_empty")

    return failures


def compute_metric(
    combo: TuningCombo,
    overall_scores: dict[tuple[str, str], float],
    predictions: dict[tuple[str, str], FitClass],
    gold: dict[tuple[str, str], FitClass],
    *,
    precision_floor: float = 0.05,
    recall_floor: float = 0.05,
    check_distribution_buckets: bool = True,
) -> TuningMetric:
    """Build the :class:`TuningMetric` for one combo.

    Parameters
    ----------
    combo
        The combo that produced ``overall_scores`` (Tier 1) and
        ``predictions`` (Tier 0). Reported back inside the metric.
    overall_scores
        ``{(cv_id, jd_id) -> overall_score}`` from
        :func:`aggregate_from_intermediates`. Used for guard #5.
    predictions
        ``{(cv_id, jd_id) -> class}`` from
        :func:`project_to_three_class`.
    gold
        ``{(cv_id, jd_id) -> class}`` from the fit matrix.
    precision_floor, recall_floor, check_distribution_buckets
        Guard parameters. Default values match the **strict** guard set;
        the CLI driver re-calls with relaxed values for the fallback
        chain.
    """
    confusion = _build_confusion(predictions, gold)
    precision, recall, f1 = _per_class_metrics(confusion)

    # Macro F1 over the 3 classes (equal weight).
    macro_f1 = sum(f1.values()) / len(_CLASSES)

    # Weighted F1 (support-weighted) -- reported as a secondary metric,
    # never the optimisation target unless --objective weighted_f1 is
    # set at the CLI.
    support = {
        cls: sum(confusion[(cls, p)] for p in _CLASSES) for cls in _CLASSES
    }
    total_support = sum(support.values())
    if total_support > 0:
        weighted_f1 = (
            sum(f1[c] * support[c] for c in _CLASSES) / total_support
        )
    else:
        weighted_f1 = 0.0

    # Plain accuracy.
    n_cells = sum(confusion.values())
    correct = sum(confusion[(c, c)] for c in _CLASSES)
    plain_accuracy = correct / n_cells if n_cells > 0 else 0.0

    # Weighted accuracy -- mean per-class recall over non-empty classes.
    nonempty = [c for c in _CLASSES if support[c] > 0]
    weighted_accuracy = (
        sum(recall[c] for c in nonempty) / len(nonempty) if nonempty else 0.0
    )

    n_predicted: dict[str, int] = {
        str(cls): sum(confusion[(g, cls)] for g in _CLASSES)
        for cls in _CLASSES
    }

    failures = _evaluate_guards(
        combo,
        overall_scores,
        confusion,
        precision,
        recall,
        precision_floor=precision_floor,
        recall_floor=recall_floor,
        check_distribution_buckets=check_distribution_buckets,
    )

    return TuningMetric(
        combo=combo,
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        plain_accuracy=plain_accuracy,
        weighted_accuracy=weighted_accuracy,
        f1_strong=f1["strong"],
        f1_possible=f1["possible"],
        f1_no=f1["no"],
        precision_strong=precision["strong"],
        precision_possible=precision["possible"],
        precision_no=precision["no"],
        recall_strong=recall["strong"],
        recall_possible=recall["possible"],
        recall_no=recall["no"],
        n_predicted=n_predicted,
        confusion=confusion,
        guards_passed=not failures,
        guards_failed=tuple(failures),
    )


# ---------------------------------------------------------------------------
# Tier 1 + Tier 0 sweep -- the inner loop of the whole grid search
# ---------------------------------------------------------------------------


# Type for the objective: maps a TuningMetric to a scalar to maximise.
ObjectiveFn = Callable[[TuningMetric], float]
"""``Callable[[TuningMetric], float]`` -- returns the scalar to
maximise. Two built-ins: ``objective_macro_f1`` (default) and
``objective_weighted_f1``."""


def objective_macro_f1(metric: TuningMetric) -> float:
    """Default objective: macro F1 across the 3 classes."""
    return metric.macro_f1


def objective_weighted_f1(metric: TuningMetric) -> float:
    """Alternative objective: support-weighted F1 (favours strong)."""
    return metric.weighted_f1


def run_tier1_tier0_only(
    intermediates: list[CellIntermediate],
    gold: dict[tuple[str, str], FitClass],
    *,
    locked_linker_thresholds: tuple[float, float, float],
    objective: ObjectiveFn = objective_macro_f1,
) -> TuningRunResult:
    """Tier 1 + Tier 0 grid search on a single set of intermediates.

    Used by ``--mode fast`` directly, and by ``--mode full`` once per
    Tier 2 combo (then the caller picks the best across all Tier 2
    iterations).

    Parameters
    ----------
    intermediates
        The Scorer's per-cell intermediates with
        ``per_requirement_keep_threshold=0.0`` (no Tier 1 gating
        applied during generation).
    gold
        Fit matrix as ``{(cv_id, jd_id) -> class}``. Only cells present
        in BOTH ``intermediates`` and ``gold`` contribute to metrics.
    locked_linker_thresholds
        ``(drop, keep, expansion)`` in force when the intermediates
        were produced. Used to populate the seven-knob ``TuningCombo``
        coordinates correctly.
    objective
        Scalar to maximise. Default is macro F1.

    Returns
    -------
    TuningRunResult
        ``best_combo`` is ``None`` iff no combo passed the strict
        guards. ``fallback_unguarded`` is always populated when
        ``all_metrics`` is non-empty.
    """
    t0 = time.monotonic()

    drop, keep, expansion = locked_linker_thresholds
    # Filter the intermediates' gold cells to those we actually have an
    # intermediate for -- prevents the metric loop from being fooled by
    # gold cells with no corresponding score.
    cells_with_intermediate: set[tuple[str, str]] = {
        (c.cv_id, c.jd_id) for c in intermediates
    }
    gold_filtered: dict[tuple[str, str], FitClass] = {
        k: v for k, v in gold.items() if k in cells_with_intermediate
    }

    all_metrics: list[TuningMetric] = []

    # Tier 1: re-aggregate.
    for per_req_keep, w in grid_for_tier_1():
        overall_scores = aggregate_from_intermediates(
            intermediates,
            per_requirement_keep_threshold=per_req_keep,
            required_weight=w,
        )

        # Tier 0: re-project.
        for t1, t2 in grid_for_tier_0():
            combo = TuningCombo(
                drop_threshold=drop,
                keep_threshold=keep,
                expansion_threshold=expansion,
                per_requirement_keep_threshold=per_req_keep,
                required_weight=w,
                t1=t1,
                t2=t2,
            )
            predictions = project_to_three_class(
                overall_scores, t1=t1, t2=t2
            )
            metric = compute_metric(
                combo, overall_scores, predictions, gold_filtered
            )
            all_metrics.append(metric)

    # Sort metrics: by objective desc; ties broken by lexicographic combo.
    all_metrics.sort(key=lambda m: (-objective(m), m.combo))

    # Strict best.
    best_metric = next((m for m in all_metrics if m.guards_passed), None)
    best_combo = best_metric.combo if best_metric is not None else None

    # Unguarded best (always the top of the sorted list when non-empty).
    fallback_unguarded = all_metrics[0] if all_metrics else None

    # Relaxed best. Re-evaluate with relaxed guards. The relaxed-guard
    # outcome is independent of the strict path, so we rebuild metrics
    # for every combo here -- the cost is O(grid_size) trivial work.
    fallback_relaxed = _best_under_relaxed_guards(
        all_metrics, intermediates, gold_filtered, objective
    )

    elapsed = time.monotonic() - t0
    config_used = {
        "mode": "tier1_tier0_only",
        "locked_linker_thresholds": list(locked_linker_thresholds),
        "n_intermediates": len(intermediates),
        "n_gold_cells": len(gold_filtered),
        "grid_size_tier_1": grid_size_tier_1(),
        "grid_size_tier_0": grid_size_tier_0(),
        "n_metrics_computed": len(all_metrics),
        "objective": objective.__name__,
    }

    return TuningRunResult(
        best_combo=best_combo,
        best_metric=best_metric,
        fallback_unguarded=fallback_unguarded,
        fallback_relaxed=fallback_relaxed,
        all_metrics=all_metrics,
        config_used=config_used,
        elapsed_seconds=elapsed,
    )


def _best_under_relaxed_guards(
    sorted_metrics: list[TuningMetric],
    intermediates: list[CellIntermediate],
    gold: dict[tuple[str, str], FitClass],
    objective: ObjectiveFn,
) -> TuningMetric | None:
    """Pick the best combo under the relaxed guard set.

    Relaxation (per Step 8 brief §3.2):
    * precision floor: 0.02 (was 0.05)
    * recall floor: 0.02 (was 0.05)
    * distribution-bucket guard: dropped
    * G1 (all 3 classes predicted) retained -- otherwise the report
      could lock a one-class collapse, which Step 8 §3.2 forbids.

    Re-evaluates every combo's guard status against the relaxed
    parameters; the per-class metrics themselves are unchanged so the
    objective ranking is the same as ``sorted_metrics``.
    """
    if not sorted_metrics:
        return None

    # Re-aggregate per Tier 1 combo only once per (per_req_keep, w)
    # tuple, keyed for cache hits across the Tier 0 fan-out.
    overall_cache: dict[tuple[float, float], dict[tuple[str, str], float]] = {}

    for metric in sorted_metrics:
        c = metric.combo
        key = (c.per_requirement_keep_threshold, c.required_weight)
        if key not in overall_cache:
            overall_cache[key] = aggregate_from_intermediates(
                intermediates,
                per_requirement_keep_threshold=c.per_requirement_keep_threshold,
                required_weight=c.required_weight,
            )
        overall_scores = overall_cache[key]
        predictions = project_to_three_class(
            overall_scores, t1=c.t1, t2=c.t2
        )
        relaxed_metric = compute_metric(
            c,
            overall_scores,
            predictions,
            gold,
            precision_floor=0.02,
            recall_floor=0.02,
            check_distribution_buckets=False,
        )
        if relaxed_metric.guards_passed:
            return relaxed_metric

    # We iterated in objective-sorted order; if we never hit a passing
    # row, the relaxed guards cannot be satisfied either.
    _ = objective  # parameter kept for API symmetry; sort order honours it
    return None


# ---------------------------------------------------------------------------
# Tier 2 sweep -- composes a builder callback with run_tier1_tier0_only
# ---------------------------------------------------------------------------


LinkerIntermediatesBuilder = Callable[
    [float, float, float], list[CellIntermediate]
]
"""Callback signature: ``(drop, keep, expansion) -> intermediates``.

The CLI driver wraps the Linker + Scorer in a closure with this
signature so the tuning module never imports the Linker. Each call is
expected to take 2-5 minutes (warm encoder, 14 CVs x 20 JDs)."""


def run_full(
    builder: LinkerIntermediatesBuilder,
    gold: dict[tuple[str, str], FitClass],
    *,
    mode: Literal["fast", "full"],
    objective: ObjectiveFn = objective_macro_f1,
    on_tier2_complete: Callable[[tuple[float, float, float], TuningRunResult], None]
    | None = None,
) -> TuningRunResult:
    """Full 3-tier grid search.

    Parameters
    ----------
    builder
        Closure returning Scorer intermediates for one Linker triple.
        Called once per Tier 2 combo. ``--mode fast`` produces one
        Tier 2 combo (the locked default); ``--mode full`` iterates.
    gold
        Fit matrix.
    mode
        ``"fast"`` -> single Tier 2 combo (Step 4 / Step 6 lock).
        ``"full"`` -> sweep Tier 2 too.
    objective
        Scalar to maximise. Default macro F1.
    on_tier2_complete
        Optional progress callback: invoked after each Tier 2 combo's
        Tier 1 + Tier 0 sweep finishes, with ``(triple, sub_result)``.
        The CLI driver uses it to log per-combo INFO lines.

    Returns
    -------
    TuningRunResult
        Global best across every Tier 2 iteration. ``config_used`` is
        promoted to the full-mode record (grid sizes, total combos,
        etc.).
    """
    t0 = time.monotonic()

    all_metrics: list[TuningMetric] = []
    best_strict: TuningMetric | None = None
    best_unguarded: TuningMetric | None = None
    best_relaxed: TuningMetric | None = None

    tier2_combos: list[tuple[float, float, float]] = list(
        grid_for_tier_2(fast=(mode == "fast"))
    )

    for triple in tier2_combos:
        intermediates = builder(*triple)
        sub_result = run_tier1_tier0_only(
            intermediates,
            gold,
            locked_linker_thresholds=triple,
            objective=objective,
        )
        all_metrics.extend(sub_result.all_metrics)

        if sub_result.best_metric is not None and (
            best_strict is None
            or objective(sub_result.best_metric) > objective(best_strict)
            or (
                objective(sub_result.best_metric) == objective(best_strict)
                and sub_result.best_metric.combo < best_strict.combo
            )
        ):
            best_strict = sub_result.best_metric
        if sub_result.fallback_unguarded is not None and (
            best_unguarded is None
            or objective(sub_result.fallback_unguarded)
            > objective(best_unguarded)
            or (
                objective(sub_result.fallback_unguarded)
                == objective(best_unguarded)
                and sub_result.fallback_unguarded.combo < best_unguarded.combo
            )
        ):
            best_unguarded = sub_result.fallback_unguarded
        if sub_result.fallback_relaxed is not None and (
            best_relaxed is None
            or objective(sub_result.fallback_relaxed) > objective(best_relaxed)
            or (
                objective(sub_result.fallback_relaxed) == objective(best_relaxed)
                and sub_result.fallback_relaxed.combo < best_relaxed.combo
            )
        ):
            best_relaxed = sub_result.fallback_relaxed

        if on_tier2_complete is not None:
            on_tier2_complete(triple, sub_result)

    # Re-sort the global all_metrics for the report's top-10 section.
    all_metrics.sort(key=lambda m: (-objective(m), m.combo))

    elapsed = time.monotonic() - t0
    config_used = {
        "mode": mode,
        "n_tier2_combos": len(tier2_combos),
        "tier2_combos": [list(t) for t in tier2_combos],
        "grid_size_tier_1": grid_size_tier_1(),
        "grid_size_tier_0": grid_size_tier_0(),
        "n_gold_cells": len(gold),
        "n_metrics_computed": len(all_metrics),
        "objective": objective.__name__,
    }

    return TuningRunResult(
        best_combo=best_strict.combo if best_strict is not None else None,
        best_metric=best_strict,
        fallback_unguarded=best_unguarded,
        fallback_relaxed=best_relaxed,
        all_metrics=all_metrics,
        config_used=config_used,
        elapsed_seconds=elapsed,
    )


# ---------------------------------------------------------------------------
# Score-distribution helper (Section 7 of the report; also used by tests)
# ---------------------------------------------------------------------------


def score_distribution(
    overall_scores: dict[tuple[str, str], float],
    gold: dict[tuple[str, str], FitClass],
    *,
    percentiles: tuple[int, ...] = (25, 50, 75, 90, 95, 99),
) -> dict[str, dict[str, float]]:
    """Compute per-class percentiles + min/max/mean for ``overall_score``.

    Used by the markdown report's Section 7 to show *why* the chosen
    T1/T2 land on real distribution percentiles rather than arbitrary
    constants. Also useful as a Pre-Flight sanity check.

    Returns
    -------
    dict[str, dict[str, float]]
        ``{"strong"|"possible"|"no"|"all" -> {"n": ..., "min": ...,
        "max": ..., "mean": ..., "P25": ..., ..., "P99": ...}}``.
        Empty strata yield ``{"n": 0}`` only.
    """
    by_class: dict[str, list[float]] = {c: [] for c in _CLASSES}
    by_class["all"] = []
    for key, s in overall_scores.items():
        by_class["all"].append(s)
        if key in gold:
            by_class[gold[key]].append(s)

    out: dict[str, dict[str, float]] = {}
    for cls, xs in by_class.items():
        if not xs:
            out[cls] = {"n": 0.0}
            continue
        xs_sorted = sorted(xs)
        n = len(xs_sorted)
        bucket: dict[str, float] = {
            "n": float(n),
            "min": xs_sorted[0],
            "max": xs_sorted[-1],
            "mean": sum(xs_sorted) / n,
        }
        for p in percentiles:
            k = (n - 1) * p / 100.0
            f = int(k)
            ck = min(f + 1, n - 1)
            bucket[f"P{p}"] = (
                xs_sorted[f]
                if f == ck
                else xs_sorted[f] + (xs_sorted[ck] - xs_sorted[f]) * (k - f)
            )
        out[cls] = bucket
    return out


__all__ = [
    "CellIntermediate",
    "FitClass",
    "LinkerIntermediatesBuilder",
    "ObjectiveFn",
    "ReqIntermediate",
    "TuningCombo",
    "TuningMetric",
    "TuningRunResult",
    "aggregate_from_intermediates",
    "compute_metric",
    "grid_for_tier_0",
    "grid_for_tier_1",
    "grid_for_tier_2",
    "grid_size_tier_0",
    "grid_size_tier_1",
    "grid_size_tier_2",
    "objective_macro_f1",
    "objective_weighted_f1",
    "project_to_three_class",
    "run_full",
    "run_tier1_tier0_only",
    "score_distribution",
]
