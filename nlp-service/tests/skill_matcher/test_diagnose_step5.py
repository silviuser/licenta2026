# ruff: noqa: E501, RUF003
"""Fast unit tests for ``scripts/diagnose_step5.py``.

Covers each pure lens function on synthetic inputs (no encoder loads,
no PDFs, no real ESCO) plus light CLI / rendering smoke tests. The
real diagnostic run lives in the Sign-Off gate (``pytest tests/``
green + ``python scripts/diagnose_step5.py``) so this suite is
intentionally lean.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# The diagnostic script lives outside ``src/`` and is not a package
# member, so ``import diagnose_step5`` does not resolve through
# pyproject's ``pythonpath = ["src"]``. Load it explicitly off the
# scripts dir.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "diagnose_step5.py"

_spec = importlib.util.spec_from_file_location("diagnose_step5", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
diagnose_step5 = importlib.util.module_from_spec(_spec)
sys.modules["diagnose_step5"] = diagnose_step5
_spec.loader.exec_module(diagnose_step5)


# ---------------------------------------------------------------------------
# Lens A — training coverage
# ---------------------------------------------------------------------------


def test_lens_a_basic_overlap() -> None:
    """Prompt §3.1 spec: 3 train URIs, 5 eval URIs, expected overlap = 2."""
    train_uris = {
        "http://esco/a",
        "http://esco/b",
        "http://esco/c",
    }
    eval_set = {
        "cv1": {"http://esco/a", "http://esco/b"},
        "cv2": {"http://esco/x", "http://esco/y", "http://esco/z"},
    }
    findings = diagnose_step5.analyse_training_coverage(
        train_positive_uris=train_uris,
        eval_uri_set_by_cv=eval_set,
        train_build_timestamp="2026-05-16T19:43:28+00:00",
    )
    assert findings.total_eval_uris == 5
    assert findings.overlap_uris == 2
    assert findings.coverage_ratio == pytest.approx(2 / 5)
    per_cv = {cv.cv_id: cv for cv in findings.per_cv}
    assert per_cv["cv1"].gold_count == 2
    assert per_cv["cv1"].gold_unseen == 0
    assert per_cv["cv2"].gold_count == 3
    assert per_cv["cv2"].gold_unseen == 3
    assert "http://esco/x" in per_cv["cv2"].unseen_uris


def test_lens_a_empty_eval_set() -> None:
    """Coverage ratio is 0.0 (not NaN) when there are no eval URIs."""
    findings = diagnose_step5.analyse_training_coverage(
        train_positive_uris={"http://esco/a"},
        eval_uri_set_by_cv={"cv1": set()},
        train_build_timestamp="2026-05-16T00:00:00+00:00",
    )
    assert findings.total_eval_uris == 0
    assert findings.coverage_ratio == 0.0
    assert findings.per_cv[0].gold_count == 0


# ---------------------------------------------------------------------------
# Lens B — per-URI rank attribution
# ---------------------------------------------------------------------------


def _make_rank_record(
    *,
    cv_id: str = "cv1",
    uri: str = "http://esco/u1",
    in_training_sw: bool = True,
    in_training_v1: bool | None = None,
    sim_zero_shot: float = 0.5,
    sim_mnrl_v1: float = 0.55,
    sim_mnrl_sw: float = 0.6,
) -> diagnose_step5.PerURISimRecord:
    return diagnose_step5.PerURISimRecord(
        cv_id=cv_id,
        uri=uri,
        in_training_v1=in_training_v1 if in_training_v1 is not None else in_training_sw,
        in_training_sw=in_training_sw,
        sim_zero_shot=sim_zero_shot,
        sim_mnrl_v1=sim_mnrl_v1,
        sim_mnrl_sw=sim_mnrl_sw,
    )


def test_lens_b_asymmetry_signature_h1() -> None:
    """When in-training URIs gain sim and out-of-training URIs lose sim,
    the summary surfaces both means with the expected signs."""
    records = [
        # In training: gain after fine-tune
        _make_rank_record(uri=f"in/{i}", in_training_sw=True, sim_zero_shot=0.40, sim_mnrl_v1=0.55, sim_mnrl_sw=0.60)
        for i in range(5)
    ] + [
        # Not in training: lose after fine-tune
        _make_rank_record(uri=f"out/{i}", in_training_sw=False, sim_zero_shot=0.50, sim_mnrl_v1=0.45, sim_mnrl_sw=0.42)
        for i in range(5)
    ]
    rank = diagnose_step5.analyse_per_uri_rank_attribution(
        records=records, n_cvs_processed=1, n_cvs_skipped=0, skipped_cv_ids=()
    )
    assert rank.in_training.n_uris == 5
    assert rank.not_in_training.n_uris == 5
    assert rank.in_training.mean_delta_sw == pytest.approx(0.20)
    assert rank.not_in_training.mean_delta_sw == pytest.approx(-0.08)
    assert rank.in_training.improved_count_sw == 5
    assert rank.not_in_training.improved_count_sw == 0


def test_lens_b_empty_records() -> None:
    rank = diagnose_step5.analyse_per_uri_rank_attribution(
        records=(), n_cvs_processed=0, n_cvs_skipped=2, skipped_cv_ids=("cvA", "cvB")
    )
    assert rank.n_records == 0
    assert rank.in_training.n_uris == 0
    assert rank.not_in_training.n_uris == 0
    assert rank.skipped_cv_ids == ("cvA", "cvB")


# ---------------------------------------------------------------------------
# Lens C — FP attribution
# ---------------------------------------------------------------------------


def test_lens_c_bins_and_summary_per_encoder() -> None:
    records = [
        diagnose_step5.FPRecord(cv_id="cv1", encoder="zero_shot", fp_uri="z1", train_freq=0),
        diagnose_step5.FPRecord(cv_id="cv1", encoder="zero_shot", fp_uri="z2", train_freq=2),
        diagnose_step5.FPRecord(cv_id="cv1", encoder="mnrl_sw", fp_uri="s1", train_freq=12),
        diagnose_step5.FPRecord(cv_id="cv1", encoder="mnrl_sw", fp_uri="s2", train_freq=50),
        diagnose_step5.FPRecord(cv_id="cv1", encoder="mnrl_sw", fp_uri="s3", train_freq=4),
    ]
    out = diagnose_step5.analyse_fp_attribution(records=records)
    by_enc = {h.encoder: h for h in out.histograms}
    assert set(by_enc) == {"zero_shot", "mnrl_sw"}
    assert by_enc["zero_shot"].total_fp == 2
    assert by_enc["mnrl_sw"].total_fp == 3
    assert by_enc["mnrl_sw"].mean_freq == pytest.approx((12 + 50 + 4) / 3)
    # Default bins (0, 1, 3, 6, 11, 26, 101): 12 → [11, 26), 50 → [26, 101), 4 → [3, 6)
    bins_sw = by_enc["mnrl_sw"].bin_counts
    assert sum(bins_sw) == 3
    assert bins_sw[diagnose_step5.LENS_C_FREQ_BINS.index(3)] == 1  # 4 lands in [3,6)
    assert bins_sw[diagnose_step5.LENS_C_FREQ_BINS.index(11)] == 1  # 12 lands in [11,26)
    assert bins_sw[diagnose_step5.LENS_C_FREQ_BINS.index(26)] == 1  # 50 lands in [26,101)


def test_lens_c_bin_helper_handles_zero_and_overflow() -> None:
    counts = diagnose_step5._bin_frequencies(
        [0, 0, 1, 2, 5, 25, 100, 999], bin_edges=diagnose_step5.LENS_C_FREQ_BINS
    )
    assert sum(counts) == 8
    # bin 0: [0, 1) → freq=0 only (×2). bin 1: [1, 3) → 1, 2. bin 2: [3, 6) → 5. ...
    assert counts[0] == 2
    assert counts[1] == 2
    # 999 should land in the final [101, ∞) bucket.
    assert counts[-1] >= 1


# ---------------------------------------------------------------------------
# Lens D — negative quality
# ---------------------------------------------------------------------------


def test_lens_d_easy_negatives_signature() -> None:
    """Trivially-easy negatives (very low sim) + tight positive
    distribution → large mean gap."""
    neg_sims = [0.02 + 0.001 * i for i in range(50)]
    pos_sims = [0.60 + 0.001 * i for i in range(50)]
    d = diagnose_step5.audit_negative_quality(
        negative_sims=neg_sims, positive_sims=pos_sims
    )
    assert d.negatives.mean < 0.1
    assert d.positives.mean > 0.5
    assert d.mean_gap > 0.5


def test_lens_d_empty_distribution() -> None:
    d = diagnose_step5.audit_negative_quality(negative_sims=(), positive_sims=())
    assert d.negatives.n == 0
    assert d.positives.n == 0
    assert d.mean_gap == 0.0


# ---------------------------------------------------------------------------
# Lens E — concept-text alignment
# ---------------------------------------------------------------------------


def test_lens_e_verdict_aligned() -> None:
    samples = [
        diagnose_step5.AlignmentSample(
            uri="http://esco/u1",
            train_side="Python. high-level. ...",
            index_side="Python. high-level. ...",
            differs=False,
        ),
        diagnose_step5.AlignmentSample(
            uri="http://esco/u2",
            train_side="Java. computer programming. ...",
            index_side="Java. computer programming. ...",
            differs=False,
        ),
    ]
    a = diagnose_step5.audit_concept_text_alignment(samples=samples)
    assert a.verdict == "aligned"
    assert a.n_differs == 0


def test_lens_e_verdict_drifted() -> None:
    samples = [
        diagnose_step5.AlignmentSample(
            uri="http://esco/u1",
            train_side="Python.",
            index_side="Python ",
            differs=True,
        ),
    ]
    a = diagnose_step5.audit_concept_text_alignment(samples=samples)
    assert a.verdict == "drifted"
    assert a.n_differs == 1


# ---------------------------------------------------------------------------
# Lens F — training dynamics
# ---------------------------------------------------------------------------


def test_lens_f_monotonic_rising_curve() -> None:
    curves = {
        "runA": [(1.0, 0.10), (2.0, 0.13), (3.0, 0.15)],
    }
    manifest = {"runA": 0.15}
    d = diagnose_step5.audit_training_dynamics(
        curves_by_run=curves, manifest_finals=manifest
    )
    c = d.curves[0]
    assert c.peak_epoch == 3.0
    assert c.peak_mrr == 0.15
    assert c.final_mrr == 0.15
    assert c.monotonic is True
    assert c.final_vs_peak_gap == pytest.approx(0.0)
    assert c.manifest_final_mrr == 0.15


def test_lens_f_peak_then_decay() -> None:
    curves = {
        "runB": [(1.0, 0.10), (2.0, 0.18), (3.0, 0.14)],
    }
    d = diagnose_step5.audit_training_dynamics(curves_by_run=curves, manifest_finals={})
    c = d.curves[0]
    assert c.peak_epoch == 2.0
    assert c.peak_mrr == 0.18
    assert c.final_mrr == 0.14
    assert c.monotonic is False
    assert c.final_vs_peak_gap == pytest.approx(0.04)
    assert c.manifest_final_mrr is None


# ---------------------------------------------------------------------------
# JSON serialisation + CLI lens-subset filter
# ---------------------------------------------------------------------------


def _minimal_env() -> diagnose_step5.Environment:
    return diagnose_step5.Environment(
        run_date="2026-05-16",
        seed=42,
        eval_corpus_size=15,
        cvs_skipped=(),
        runs_analysed=(diagnose_step5.MODEL_RUN_V1, diagnose_step5.MODEL_RUN_SW),
        on_disk_train_jsonl_timestamp="2026-05-16T19:43:28+00:00",
    )


def test_findings_to_dict_round_trips_json() -> None:
    """Findings → dict → json.dumps must not raise; tuples become lists."""
    f = diagnose_step5.Findings(
        environment=_minimal_env(),
        coverage=diagnose_step5.analyse_training_coverage(
            train_positive_uris={"http://esco/a"},
            eval_uri_set_by_cv={"cv1": {"http://esco/a", "http://esco/b"}},
            train_build_timestamp="2026-05-16T00:00:00+00:00",
        ),
    )
    blob = diagnose_step5.findings_to_dict(f)
    serialised = json.dumps(blob)
    decoded: dict[str, Any] = json.loads(serialised)
    assert decoded["environment"]["seed"] == 42
    assert decoded["coverage"]["total_eval_uris"] == 2
    assert decoded["coverage"]["per_cv"][0]["cv_id"] == "cv1"


def test_parse_lens_subset_rejects_unknown() -> None:
    with pytest.raises(SystemExit):
        diagnose_step5._parse_lens_subset("A,Z")


def test_parse_lens_subset_normalises_case_and_whitespace() -> None:
    out = diagnose_step5._parse_lens_subset(" a , B , c ")
    assert out == {"A", "B", "C"}


def test_render_markdown_smoke(tmp_path: Path) -> None:
    """Markdown renderer produces a file with the executive summary,
    environment block, and each populated lens section."""
    findings = diagnose_step5.Findings(
        environment=_minimal_env(),
        coverage=diagnose_step5.analyse_training_coverage(
            train_positive_uris={"http://esco/a"},
            eval_uri_set_by_cv={"cv1": {"http://esco/a", "http://esco/b"}},
            train_build_timestamp="2026-05-16T00:00:00+00:00",
        ),
        rank=diagnose_step5.analyse_per_uri_rank_attribution(
            records=(_make_rank_record(),),
            n_cvs_processed=1,
            n_cvs_skipped=0,
            skipped_cv_ids=(),
        ),
        alignment=diagnose_step5.audit_concept_text_alignment(
            samples=(
                diagnose_step5.AlignmentSample(
                    uri="http://esco/u1",
                    train_side="x",
                    index_side="x",
                    differs=False,
                ),
            )
        ),
        dynamics=diagnose_step5.audit_training_dynamics(
            curves_by_run={"runA": [(1.0, 0.1), (2.0, 0.12)]},
            manifest_finals={"runA": 0.12},
        ),
        negative_quality=diagnose_step5.audit_negative_quality(
            negative_sims=(0.05, 0.07, 0.09),
            positive_sims=(0.45, 0.55, 0.65),
        ),
    )
    out_path = tmp_path / "report.md"
    diagnose_step5.render_markdown(findings, out_path=out_path)
    text = out_path.read_text(encoding="utf-8")
    assert "Executive summary" in text
    assert "Lens A" in text
    assert "Lens B" in text
    assert "Lens D" in text
    assert "Lens E" in text
    assert "Lens F" in text
    assert "Prescription" in text


def test_render_markdown_appendix_only_when_coverage_low(tmp_path: Path) -> None:
    """Appendix is omitted when coverage is ≥ 70 %."""
    high_coverage = diagnose_step5.Findings(
        environment=_minimal_env(),
        coverage=diagnose_step5.analyse_training_coverage(
            train_positive_uris={"a", "b", "c", "d", "e"},
            eval_uri_set_by_cv={"cv1": {"a", "b", "c", "d", "e"}},
            train_build_timestamp="2026-05-16T00:00:00+00:00",
        ),
    )
    out_path = tmp_path / "report.md"
    diagnose_step5.render_markdown(high_coverage, out_path=out_path)
    assert "unseen-URI list" not in out_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Sanity: numpy import path used inside the script works
# ---------------------------------------------------------------------------


def test_summarise_distribution_consistent_with_numpy() -> None:
    """Distribution helper agrees with raw numpy on a known sample."""
    sims = [0.1, 0.2, 0.3, 0.4, 0.5]
    summary = diagnose_step5._summarise_distribution(sims)
    arr = np.asarray(sims)
    assert summary.mean == pytest.approx(float(arr.mean()))
    assert summary.median == pytest.approx(0.3)
    assert summary.p25 == pytest.approx(0.2)
    assert summary.p75 == pytest.approx(0.4)
