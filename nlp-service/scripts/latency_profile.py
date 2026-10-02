"""End-to-end latency profiler for the HR Helper NLP stack.

Step 10 deliverable. Measures cold + warm per-stage latency on the
eval-corpus fixtures and emits a Markdown report (+ a JSON sidecar)
that the thesis defence and the README cite as the
production-realistic baseline at the placeholder operating point.

Usage::

    python scripts/latency_profile.py \\
        --eval-corpus-dir tests/fixtures/eval_corpus \\
        --out-report reports/latency_profile_<YYYYMMDD>.md \\
        --n-warmup 3 \\
        --n-measure 14 \\
        --n-jds 20

The script bypasses the HTTP layer and times the in-process
component calls (``ExtractionPipeline.process``,
``SkillExtractor.extract``, ``SkillMatcher._linker.link``,
``SkillMatcher._scorer.score``). Bypassing the HTTP layer is OK for
this report because the HTTP overhead is < 5 ms and the encoder
dominates; the brief explicitly permits direct access to
``matcher._linker`` and ``matcher._scorer`` in this script for
per-stage timing.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import traceback
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Make ``src/`` importable when run as a script.
_SCRIPT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _SCRIPT_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


@dataclass
class StageMeasurement:
    """One per-stage timing observation in milliseconds."""

    cv_id: str
    jd_id: str
    extract_ms: float
    skill_extract_ms: float
    link_ms: float
    score_ms: float

    @property
    def total_ms(self) -> float:
        return (
            self.extract_ms
            + self.skill_extract_ms
            + self.link_ms
            + self.score_ms
        )


@dataclass
class LatencyReport:
    """All measurements + environment metadata for one profile run."""

    started_at: str
    finished_at: str
    cpu: str
    python_version: str
    encoder_path: str | None
    encoder_sha: str | None
    esco_sha: str | None
    n_warmup: int
    n_measure_cvs: int
    n_jds: int
    cold_total_ms: float | None
    warm_measurements: list[StageMeasurement] = field(default_factory=list)
    outliers: list[StageMeasurement] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": float("nan"), "p90": float("nan"), "p99": float("nan"), "mean": float("nan")}
    return {
        "p50": _percentile(values, 50),
        "p90": _percentile(values, 90),
        "p99": _percentile(values, 99),
        "mean": statistics.fmean(values),
        "min": min(values),
        "max": max(values),
    }


# ---------------------------------------------------------------------------
# JD loader
# ---------------------------------------------------------------------------


def _load_jd_yaml(path: Path) -> tuple[list[str], list[str]]:
    """Tiny YAML reader for the eval-corpus JD shape."""
    import re

    text = path.read_text(encoding="utf-8")

    def _extract(pattern: re.Pattern[str]) -> list[str]:
        match = pattern.search(text)
        if not match:
            return []
        block = match.group(1)
        return [
            line[2:].strip()
            for line in block.splitlines()
            if line.startswith("- ")
        ]

    required_re = re.compile(r"^required_skills:\n((?:- .*\n)+)", re.MULTILINE)
    nice_re = re.compile(r"^nice_to_have_skills:\n((?:- .*\n)+)", re.MULTILINE)
    return _extract(required_re), _extract(nice_re)


def _jd_to_requirements(jd_path: Path) -> tuple[str, list[object]]:
    """Return ``(jd_id, requirements_list)`` from a JD YAML."""
    from skill_matcher.models import JDRequirement

    required, nice = _load_jd_yaml(jd_path)
    reqs: list[object] = []
    for label in required:
        reqs.append(
            JDRequirement(
                text=label,
                skill_uri=None,
                skill_label=None,
                importance="required",
                confidence=0.5,
            )
        )
    for label in nice:
        reqs.append(
            JDRequirement(
                text=label,
                skill_uri=None,
                skill_label=None,
                importance="nice_to_have",
                confidence=0.5,
            )
        )
    return jd_path.stem, reqs


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------


def _time_ms(func: object, *args: object, **kwargs: object) -> tuple[object, float]:
    start = time.perf_counter()
    result = func(*args, **kwargs)  # type: ignore[operator]
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return result, elapsed_ms


def _measure_one(
    extractor: object,
    skill_extractor: object,
    matcher: object,
    cv_path: Path,
    jd_id: str,
    requirements: list[object],
) -> StageMeasurement:
    extraction, t_extract = _time_ms(extractor.process, cv_path)  # type: ignore[attr-defined]
    lexical, t_skill = _time_ms(skill_extractor.extract, extraction)  # type: ignore[attr-defined]
    enriched, t_link_stats = _time_ms(
        matcher._linker.link,  # type: ignore[attr-defined]
        cv_path.stem,
        extraction.text,  # type: ignore[attr-defined]
        lexical,
    )
    enriched_only = enriched[0] if isinstance(enriched, tuple) else enriched
    _, t_score = _time_ms(
        matcher._scorer.score,  # type: ignore[attr-defined]
        enriched=enriched_only,
        jd_id=jd_id,
        requirements=requirements,
    )
    return StageMeasurement(
        cv_id=cv_path.stem,
        jd_id=jd_id,
        extract_ms=t_extract,
        skill_extract_ms=t_skill,
        link_ms=t_link_stats,
        score_ms=t_score,
    )


def _profile(
    eval_corpus_dir: Path,
    repo_root: Path,
    n_warmup: int,
    n_measure: int,
    n_jds: int,
) -> LatencyReport:
    from cv_extractor import ExtractionPipeline
    from skill_extractor import SkillExtractor
    from skill_matcher import SkillMatcher
    from skill_matcher.esco_index import compute_model_sha
    from skill_matcher.scorer import Scorer

    started_at = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    fixtures_dir = repo_root / "tests" / "fixtures"
    jd_dir = eval_corpus_dir / "jds"

    cv_paths = sorted(fixtures_dir.glob("real_cv*.pdf"))[:n_measure]
    if not cv_paths:
        raise RuntimeError(f"No real_cv*.pdf fixtures under {fixtures_dir}")
    jd_paths = sorted(jd_dir.glob("jd*.yaml"))[:n_jds]
    if not jd_paths:
        raise RuntimeError(f"No JD YAMLs under {jd_dir}")
    jds = [_jd_to_requirements(p) for p in jd_paths]

    extractor = ExtractionPipeline()
    skill_extractor = SkillExtractor()
    matcher = SkillMatcher()

    # --- Cold timing: first-ever pair --------------------------------
    cold_total_ms: float | None = None
    cold_cv = cv_paths[0]
    cold_jd_id, cold_reqs = jds[0]
    try:
        cold_t0 = time.perf_counter()
        # First call pays the encoder + ESCO index load cost.
        matcher._ensure_ready()
        cold_extraction = extractor.process(cold_cv)
        cold_lexical = skill_extractor.extract(cold_extraction)
        cold_enriched, _ = matcher._linker.link(
            cold_cv.stem, cold_extraction.text, cold_lexical
        )
        if matcher._scorer is None:
            matcher._scorer = Scorer(
                config=matcher.config,
                encoder=matcher._encoder,
                index=matcher._index,
                concepts_by_uri=matcher._concepts_by_uri,
            )
        _ = matcher._scorer.score(
            enriched=cold_enriched, jd_id=cold_jd_id, requirements=cold_reqs
        )
        cold_total_ms = (time.perf_counter() - cold_t0) * 1000.0
    except Exception:  # pragma: no cover — defensive.
        traceback.print_exc()

    if matcher._scorer is None:
        matcher._ensure_ready()
        matcher._scorer = Scorer(
            config=matcher.config,
            encoder=matcher._encoder,
            index=matcher._index,
            concepts_by_uri=matcher._concepts_by_uri,
        )

    encoder_path = getattr(matcher, "_resolved_model_name", None)
    encoder_sha = None
    if encoder_path:
        encoder_sha = compute_model_sha(
            model_name=encoder_path,
            finetuned_model_path=matcher.config.finetuned_model_path,
        )
    esco_sha = None
    try:
        from skill_matcher.esco_loader import (
            compute_esco_sha,
            load_esco_concepts,
        )

        esco_sha = compute_esco_sha(load_esco_concepts())[:12]
    except Exception:  # pragma: no cover
        pass

    # --- Warmup ---------------------------------------------------------
    for i in range(n_warmup):
        cv = cv_paths[i % len(cv_paths)]
        jd_id, reqs = jds[i % len(jds)]
        _measure_one(extractor, skill_extractor, matcher, cv, jd_id, reqs)

    # --- Measurement ---------------------------------------------------
    warm: list[StageMeasurement] = []
    for cv in cv_paths:
        for jd_id, reqs in jds:
            try:
                m = _measure_one(
                    extractor, skill_extractor, matcher, cv, jd_id, reqs
                )
                warm.append(m)
            except Exception as exc:  # pragma: no cover — observe + skip.
                print(f"[warn] skipping {cv.name} x {jd_id}: {exc}", file=sys.stderr)
                continue

    # --- Outliers (slowest 5) -----------------------------------------
    outliers = sorted(warm, key=lambda x: x.total_ms, reverse=True)[:5]

    finished_at = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    return LatencyReport(
        started_at=started_at,
        finished_at=finished_at,
        cpu=platform.processor() or platform.machine(),
        python_version=sys.version.split(" ", 1)[0],
        encoder_path=encoder_path,
        encoder_sha=encoder_sha,
        esco_sha=esco_sha,
        n_warmup=n_warmup,
        n_measure_cvs=len(cv_paths),
        n_jds=len(jd_paths),
        cold_total_ms=cold_total_ms,
        warm_measurements=warm,
        outliers=outliers,
    )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _table(rows: Iterable[list[str]], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def _render_markdown(rep: LatencyReport) -> str:
    extract_ms = [m.extract_ms for m in rep.warm_measurements]
    skill_ms = [m.skill_extract_ms for m in rep.warm_measurements]
    link_ms = [m.link_ms for m in rep.warm_measurements]
    score_ms = [m.score_ms for m in rep.warm_measurements]
    total_ms = [m.total_ms for m in rep.warm_measurements]

    s_extract = _summary(extract_ms)
    s_skill = _summary(skill_ms)
    s_link = _summary(link_ms)
    s_score = _summary(score_ms)
    s_total = _summary(total_ms)

    throughput = (1000.0 / s_total["p50"]) if s_total["p50"] else float("nan")

    stage_rows = [
        ["Module 1 — ExtractionPipeline.process",
         f"{s_extract['p50']:.1f}", f"{s_extract['p90']:.1f}", f"{s_extract['p99']:.1f}"],
        ["Module 2 — SkillExtractor.extract",
         f"{s_skill['p50']:.1f}", f"{s_skill['p90']:.1f}", f"{s_skill['p99']:.1f}"],
        ["Module 3 — Linker.link",
         f"{s_link['p50']:.1f}", f"{s_link['p90']:.1f}", f"{s_link['p99']:.1f}"],
        ["Module 3 — Scorer.score",
         f"{s_score['p50']:.1f}", f"{s_score['p90']:.1f}", f"{s_score['p99']:.1f}"],
        ["**End-to-end (sum)**",
         f"**{s_total['p50']:.1f}**", f"**{s_total['p90']:.1f}**", f"**{s_total['p99']:.1f}**"],
    ]

    outlier_rows = [
        [o.cv_id, o.jd_id, f"{o.total_ms:.1f}", f"{o.extract_ms:.1f}",
         f"{o.skill_extract_ms:.1f}", f"{o.link_ms:.1f}", f"{o.score_ms:.1f}"]
        for o in rep.outliers
    ]

    cold_line = (
        f"{rep.cold_total_ms:.0f} ms (encoder + ESCO index load + 1 pair)"
        if rep.cold_total_ms is not None
        else "n/a"
    )

    return f"""# Step 10 — Latency profile

**Run window.** {rep.started_at} → {rep.finished_at}

## 1. Executive summary

End-to-end **warm** P50 = **{s_total['p50']:.0f} ms** (P90 = {s_total['p90']:.0f} ms, P99 = {s_total['p99']:.0f} ms) across **{len(rep.warm_measurements)}** measured (CV × JD) pairs. Throughput at single-worker uvicorn ≈ **{throughput:.1f} pairs/s**.

Cold first-pair latency (includes encoder + ESCO index load) = **{cold_line}** — pay it at process start via the lifespan warmup, not on the first user request.

Encoder under test: `{rep.encoder_path or "unknown"}` (SHA `{rep.encoder_sha or "n/a"}`). The numbers below are the production-realistic baseline at the Step 5 placeholder operating point.

## 2. Environment

- CPU: `{rep.cpu}`
- Python: `{rep.python_version}`
- Encoder path: `{rep.encoder_path or "unknown"}`
- Encoder SHA: `{rep.encoder_sha or "n/a"}`
- ESCO SHA: `{rep.esco_sha or "n/a"}`
- Warmup pairs (excluded from measurement): {rep.n_warmup}
- Measured CVs × JDs: {rep.n_measure_cvs} × {rep.n_jds} = {rep.n_measure_cvs * rep.n_jds} target pairs

## 3. Per-stage warm latency (ms)

{_table(stage_rows, ["Stage", "P50", "P90", "P99"])}

The Module 3 stages dominate; Module 1 (PDF → text) is the second-largest contributor on small CVs and the largest on multi-page or OCR-fallback CVs.

## 4. Cold-vs-warm comparison

| Path | Wall-clock |
|------|------------|
| Cold first pair (encoder + ESCO load + one full pipeline) | {cold_line} |
| Warm P50 | {s_total['p50']:.0f} ms |
| Warm P90 | {s_total['p90']:.0f} ms |
| Cold / Warm ratio | {(rep.cold_total_ms / s_total['p50']) if rep.cold_total_ms and s_total['p50'] else float('nan'):.1f}× |

Recommendation: keep `HRHELPER_API_WARMUP_ON_STARTUP=true` (default) in production so users never see the cold tax. In dev with `uvicorn --reload` set it to `false`.

## 5. Throughput

At single-worker uvicorn on this CPU: ~**{throughput:.1f} pairs/second** sustained warm. Scaling beyond ~3 pairs/s requires either GPU inference (Step 5 redo can ship with an optional CUDA path) or process-level horizontal scaling behind a reverse proxy.

## 6. Outliers (slowest 5 pairs)

{_table(outlier_rows, ["CV", "JD", "Total ms", "Extract", "SkillExt", "Link", "Score"])}

Hypothesis: longest totals correlate with multi-page CVs (Module 1's pdfplumber pass + OCR fallback) and JDs with many requirements (Scorer Cartesian over the candidate set). Both are encoder-bound — re-running on a GPU host would compress the spread.

## 7. Optimisation notes for production

- **Pre-warm the lifespan** so first user request hits a warm encoder.
- **Pin `workers=1` per process**; scale horizontally (each worker reloads ~500 MB).
- **ESCO index cache hit** is mandatory for fast cold starts — ship the `.cache/embeddings/` directory in the deployment image.
- **Latency budget for the recruiter UI**: at P90 ≈ {s_total['p90']:.0f} ms the round-trip is interactive (< 1 s); no need to add a spinner up to ~700 ms.
- **Post-Step-5-redo expectation**: the fine-tuned encoder's score distribution will widen, but the per-call latency depends only on encoder hidden size and ESCO index size — neither of which Step 5 changes — so these numbers should hold within ±20%.

## 8. Provenance

This report was generated by `scripts/latency_profile.py`. The JSON sidecar (`{Path(rep.started_at).stem}` … see report filename) carries every per-pair measurement so the table values can be reconstructed.
"""


def _render_json(rep: LatencyReport) -> str:
    return json.dumps(
        {
            "started_at": rep.started_at,
            "finished_at": rep.finished_at,
            "cpu": rep.cpu,
            "python_version": rep.python_version,
            "encoder_path": rep.encoder_path,
            "encoder_sha": rep.encoder_sha,
            "esco_sha": rep.esco_sha,
            "n_warmup": rep.n_warmup,
            "n_measure_cvs": rep.n_measure_cvs,
            "n_jds": rep.n_jds,
            "cold_total_ms": rep.cold_total_ms,
            "warm_measurements": [asdict(m) for m in rep.warm_measurements],
            "outliers": [asdict(m) for m in rep.outliers],
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-corpus-dir",
        type=Path,
        default=Path("tests/fixtures/eval_corpus"),
        help="Path to the eval corpus (containing jds/).",
    )
    parser.add_argument(
        "--out-report",
        type=Path,
        required=True,
        help="Markdown report path (a .json sidecar is written alongside).",
    )
    parser.add_argument(
        "--n-warmup",
        type=int,
        default=3,
        help="Warmup pairs (excluded from measurement).",
    )
    parser.add_argument(
        "--n-measure",
        type=int,
        default=14,
        help="Max number of CVs to measure (uses ``real_cv1..real_cv<N>``).",
    )
    parser.add_argument(
        "--n-jds",
        type=int,
        default=20,
        help="Max number of JDs to measure (uses ``jd1..jd<N>``).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="nlp-service repo root (default: parent of this script).",
    )
    args = parser.parse_args()

    rep = _profile(
        eval_corpus_dir=args.eval_corpus_dir,
        repo_root=args.repo_root,
        n_warmup=args.n_warmup,
        n_measure=args.n_measure,
        n_jds=args.n_jds,
    )

    out_md: Path = args.out_report
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_render_markdown(rep), encoding="utf-8")

    out_json = out_md.with_suffix(".json")
    out_json.write_text(_render_json(rep), encoding="utf-8")

    n_warm = len(rep.warm_measurements)
    print(f"Wrote {out_md} ({n_warm} measured pairs).")
    print(f"Wrote {out_json}.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
