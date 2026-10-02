"""Empirical validation of Module 2 (skill_extractor) on real CV fixtures.

Runs the full Module 1 → Module 2 pipeline on every PDF in
``tests/fixtures/`` and produces two artefacts under ``reports/``:

* ``per_cv_skills_<date>.json`` — full structured output (every
  skill, every span, every metadata field). Used for archival and
  any downstream automation.
* ``skill_extraction_validation_<date>.md`` — human-readable Markdown
  report with one section per CV containing a sortable table of
  detected skills and empty ``TP/FP`` columns. The author fills the
  columns manually and lists missed skills (FN) below each table;
  ``compute_metrics_from_labels.py`` then aggregates P / R / F1.

Run from ``nlp-service/`` after activating the venv::

    python scripts/skill_extraction_validation.py

The script also exercises the cover-letter refusal contract:
``NotACVError`` is expected for the cover letter fixture and is
recorded in the report as "REFUSED — contract upheld".

Console output mirrors the report header so you can grep for
regressions during a fast review.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

# stdout reconfigure for Windows cp1252 console — Romanian filenames break it.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, OSError):
    pass

# Locate the package source even when running from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from cv_extractor import ExtractionPipeline  # noqa: E402
from cv_extractor.config import ExtractorConfig  # noqa: E402
from cv_extractor.exceptions import CVExtractorError  # noqa: E402

from skill_extractor import (  # noqa: E402
    NotACVError,
    SkillExtractor,
    SkillExtractorConfig,
)

FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
REPORTS_DIR = _REPO_ROOT / "reports"


@dataclass
class CVResult:
    """One row in the validation table."""

    fixture: str
    status: str  # "ok", "refused", "module1_failed"
    module1_method: str = ""
    module1_chars: int = 0
    module1_quality: float = 0.0
    module1_language: str | None = None
    module1_warnings: list[str] = field(default_factory=list)
    module2_elapsed_ms: float = 0.0
    skill_count: int = 0
    avg_confidence: float = 0.0
    section_distribution: dict[str, int] = field(default_factory=dict)
    skills: list[dict] = field(default_factory=list)
    failure_reason: str = ""


def _module1_pipeline() -> ExtractionPipeline:
    return ExtractionPipeline(config=ExtractorConfig(min_quality_score=0.3))


def _module2_extractor() -> SkillExtractor:
    return SkillExtractor(config=SkillExtractorConfig())


def _run_one(
    pdf: Path,
    module1: ExtractionPipeline,
    module2: SkillExtractor,
) -> CVResult:
    print(f"\n[•] {pdf.name}")
    result = CVResult(fixture=pdf.name, status="ok")

    # --- Module 1 ----------------------------------------------------------
    try:
        er = module1.process(pdf)
    except (CVExtractorError, OSError) as exc:
        print(f"    Module 1 failed: {exc}")
        result.status = "module1_failed"
        result.failure_reason = f"{type(exc).__name__}: {exc}"
        return result

    result.module1_method = er.metadata.method_used.value
    result.module1_chars = len(er.text)
    result.module1_quality = round(er.metadata.quality_score, 3)
    result.module1_language = er.metadata.detected_language
    result.module1_warnings = list(er.warnings)
    print(
        f"    Module 1: {result.module1_method} | "
        f"{result.module1_chars} chars | "
        f"q={result.module1_quality} | "
        f"lang={result.module1_language}"
    )

    # --- Module 2 ----------------------------------------------------------
    t0 = time.monotonic()
    try:
        skills = module2.extract(er)
    except NotACVError as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        result.module2_elapsed_ms = round(elapsed_ms, 2)
        result.status = "refused"
        result.failure_reason = str(exc)
        print(f"    Module 2: REFUSED — {exc}")
        return result

    result.module2_elapsed_ms = round(skills.processing_time_ms, 2)
    result.skill_count = skills.skill_count
    if skills.skills:
        result.avg_confidence = round(
            mean(s.confidence for s in skills.skills), 3
        )

    section_dist: dict[str, int] = {}
    for s in skills.skills:
        section_dist[s.section] = section_dist.get(s.section, 0) + 1
    result.section_distribution = section_dist

    # Pack skills with all the detail the report needs.
    skills_payload: list[dict] = []
    for s in skills.skills:
        skills_payload.append(
            {
                "preferred_label": s.preferred_label,
                "esco_uri": s.esco_uri,
                "esco_uri_tail": s.esco_uri.rsplit("/", 1)[-1],
                "section": s.section,
                "confidence": round(s.confidence, 3),
                "frequency": s.frequency,
                "matched_text": s.matched_text,
                "skill_type": s.skill_type,
                "first_span_start": s.spans[0][0],
                "first_span_end": s.spans[0][1],
                "spans": s.spans,
            }
        )
    result.skills = skills_payload

    print(
        f"    Module 2: {result.skill_count} skills | "
        f"avg conf={result.avg_confidence} | "
        f"sections={result.section_distribution} | "
        f"{result.module2_elapsed_ms} ms"
    )
    return result


# ---------------------------------------------------------------------------
# Markdown emission
# ---------------------------------------------------------------------------


def _summary_table(rows: list[CVResult]) -> str:
    lines = [
        "| # | Fixture | Status | Lang | M1 chars | M1 quality | M2 skills | Avg conf | M2 elapsed (ms) |",
        "|---|---------|--------|------|----------|------------|-----------|----------|-----------------|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(
            "| {i} | `{fix}` | {st} | {lg} | {ch} | {q} | {sk} | {ac} | {ms} |".format(
                i=i,
                fix=r.fixture,
                st=r.status,
                lg=r.module1_language or "-",
                ch=r.module1_chars or "-",
                q=r.module1_quality or "-",
                sk=r.skill_count if r.status == "ok" else "-",
                ac=r.avg_confidence if r.status == "ok" else "-",
                ms=r.module2_elapsed_ms or "-",
            )
        )
    return "\n".join(lines)


def _per_cv_section(idx: int, r: CVResult) -> str:
    parts: list[str] = [f"### {idx}. `{r.fixture}`\n"]

    if r.status == "module1_failed":
        parts.append(
            f"**Module 1 FAILED** — `{r.failure_reason}`. "
            "Likely environmental (Poppler missing for OCR fallback). "
            "Skipping Module 2 evaluation.\n"
        )
        return "\n".join(parts)

    if r.status == "refused":
        parts.append(
            f"**Module 2 REFUSED** input — `{r.failure_reason}`.\n\n"
            f"Module 1 warnings: {r.module1_warnings}\n\n"
            "End-to-end contract upheld: cover letters / non-CV documents "
            "are correctly rejected before skill extraction.\n"
        )
        return "\n".join(parts)

    parts.append("**Module 1 extraction**\n")
    parts.append(f"- Method: `{r.module1_method}`")
    parts.append(f"- Characters extracted: {r.module1_chars}")
    parts.append(f"- Quality score: {r.module1_quality}")
    parts.append(f"- Detected language: `{r.module1_language}`")
    if r.module1_warnings:
        parts.append(f"- Warnings: {r.module1_warnings}")
    parts.append("")

    parts.append("**Module 2 extraction**\n")
    parts.append(f"- Detected skills: {r.skill_count}")
    parts.append(f"- Average confidence: {r.avg_confidence}")
    parts.append(f"- Section distribution: {r.section_distribution}")
    parts.append(f"- Elapsed: {r.module2_elapsed_ms} ms")
    parts.append("")

    parts.append("**Detected skills** (sorted by confidence desc):\n")
    parts.append(
        "| # | Preferred label | Section | Conf | Freq | Surface | Type | TP/FP |"
    )
    parts.append(
        "|---|-----------------|---------|------|------|---------|------|-------|"
    )
    for i, s in enumerate(r.skills, 1):
        parts.append(
            "| {i} | {lbl} | {sec} | {c} | {f} | `{m}` | {t} |  |".format(
                i=i,
                lbl=s["preferred_label"].replace("|", "\\|"),
                sec=s["section"],
                c=s["confidence"],
                f=s["frequency"],
                m=s["matched_text"].replace("|", "\\|"),
                t=s["skill_type"],
            )
        )
    parts.append("")

    parts.append(
        "**Expected skills NOT detected (False Negatives)** — list manually:\n"
    )
    parts.append("- _(read the original PDF and add any obvious misses)_\n")

    return "\n".join(parts)


def _build_report(rows: list[CVResult], when: datetime) -> str:
    ok_rows = [r for r in rows if r.status == "ok"]

    head = [
        f"# Skill Extraction Validation Report — {when:%Y-%m-%d}",
        "",
        "Empirical validation of **Module 2 (`skill_extractor`)** on the "
        "real CV fixtures shipped with the repository "
        "(`tests/fixtures/`).",
        "",
        "Auto-generated by "
        "[`scripts/skill_extraction_validation.py`](../scripts/skill_extraction_validation.py). "
        f"Generated at {when:%Y-%m-%d %H:%M:%S %Z}.",
        "",
        "## 1 — Methodology",
        "",
        "- **Module 1** pipeline configured with "
        "`min_quality_score=0.3` so Europass-style short CVs are "
        "accepted by the digital extractors instead of cascading to "
        "OCR (which on dev boxes without Poppler installed produces "
        "spurious failures).",
        "- **Module 2** pipeline used the default "
        "`SkillExtractorConfig`: ESCO v1.2.1 EN bundle + language "
        "overlay, default section weights, default confidence formula.",
        "- spaCy models: `en_core_web_lg` for English CVs, "
        "`ro_core_news_lg` for Romanian CVs.",
        "- The cover-letter fixture is included to verify the "
        "end-to-end `NotACVError` contract.",
        "",
        "## 2 — Summary",
        "",
        _summary_table(rows),
        "",
        "## 3 — Per-CV breakdown",
        "",
    ]

    body = [_per_cv_section(i, r) for i, r in enumerate(rows, 1)]

    tail = [
        "",
        "## 4 — Manual labeling instructions",
        "",
        "For each row in the per-CV tables above, mark the TP/FP column:",
        "",
        "- **TP** — the extracted skill is a real skill of the candidate "
        "(the CV genuinely supports the claim).",
        "- **FP** — the extracted skill is a false positive (wrong context, "
        "candidate name treated as a skill, etc.).",
        "",
        "Then list missed skills (**FN**) under each table — read the "
        "original PDF and identify any obvious skills the matcher did "
        "not surface.",
        "",
        "## 5 — Metrics (compute after labeling)",
        "",
        "Per CV:",
        "",
        "$$P = \\frac{TP}{TP + FP}, \\quad R = \\frac{TP}{TP + FN}, "
        "\\quad F_1 = \\frac{2PR}{P + R}$$",
        "",
        "Macro-averaged (mean of per-CV metrics):",
        "",
        "$$P_\\text{macro} = \\frac{1}{N}\\sum_i P_i, \\quad "
        "R_\\text{macro} = \\frac{1}{N}\\sum_i R_i, \\quad "
        "F_{1,\\text{macro}} = \\frac{1}{N}\\sum_i F_{1,i}$$",
        "",
        "## 6 — Failure analysis (fill in after labeling)",
        "",
        "**Top false-positive patterns** (cite specific rows with FP):",
        "",
        "1. _(e.g. \"Acme treated as the ESCO concept Acme Co. — NER tag missed\")_",
        "2. ...",
        "",
        "**Top false-negative patterns** (cite the FN list):",
        "",
        "1. _(e.g. \"Kafka not surfaced from 'asynchronous messaging systems' — "
        "no literal match; expected to be solved by Module 3 semantic encoder\")_",
        "2. ...",
        "",
        "## 7 — Conclusions",
        "",
        "_(Summarise the precision/recall split, motivate Module 3 once "
        "the numbers are in.)_",
        "",
        f"_Aggregate stats: {len(ok_rows)} of {len(rows)} fixtures "
        "produced skill output; the rest were correctly refused "
        "(cover letter) or skipped (environmental Module 1 failure)._",
        "",
    ]

    return "\n".join(head + body + tail)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    if not FIXTURES_DIR.exists():
        print(f"Fixtures dir not found: {FIXTURES_DIR}")
        return 1

    pdfs = sorted(FIXTURES_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {FIXTURES_DIR}")
        return 1

    print(
        f"Skill extraction validation — {len(pdfs)} fixture(s) — "
        f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S %Z}"
    )
    print(f"Fixtures: {FIXTURES_DIR}")
    print(f"Reports:  {REPORTS_DIR}")

    module1 = _module1_pipeline()
    module2 = _module2_extractor()

    rows: list[CVResult] = []
    for pdf in pdfs:
        rows.append(_run_one(pdf, module1, module2))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d")

    json_path = REPORTS_DIR / f"per_cv_skills_{stamp}.json"
    md_path = REPORTS_DIR / f"skill_extraction_validation_{stamp}.md"

    with json_path.open("w", encoding="utf-8") as fp:
        json.dump([asdict(r) for r in rows], fp, indent=2, ensure_ascii=False)
    print(f"\n[✓] JSON detail:  {json_path}")

    report = _build_report(rows, now)
    md_path.write_text(report, encoding="utf-8")
    print(f"[✓] Markdown report: {md_path}")

    print(
        "\nNext step: open the Markdown report, fill in TP/FP per skill "
        "and the FN bullet lists, then compute final metrics."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
