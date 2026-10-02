"""Evaluation corpus loader for Module 3.

Internal helper module — **not** exported through
:mod:`skill_matcher.__init__`. Used by validation scripts and tests,
not by the runtime pipeline.

The corpus lives under ``nlp-service/tests/fixtures/eval_corpus/`` and
has four kinds of artefact:

* ``jds/jd*.yaml`` — :class:`JDFixture` per Job Description (raw
  LinkedIn scrape + gold required / nice-to-have skill lists).
* ``cv_labels/real_cv*.yaml`` — :class:`CVLabels` per CV (gold ESCO
  skill labels we expect Module 3 to find).
* ``fit_matrix.csv`` — recruiter-style ``strong`` / ``possible`` /
  ``no`` judgment for each ``(cv_id, jd_id)`` pair.

The CV PDFs themselves live under ``nlp-service/tests/fixtures/`` and
are shared with the Module 2 validation suite. The loader only
registers their paths; downstream callers feed them to Module 1's
:class:`cv_extractor.ExtractionPipeline`.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

# Repository layout: this file is at
# ``nlp-service/src/skill_matcher/eval_corpus.py``, so going up three
# parents lands at ``nlp-service/``. Same idiom as Module 2's config.
_NLP_SERVICE_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_EVAL_CORPUS_ROOT = (
    _NLP_SERVICE_ROOT / "tests" / "fixtures" / "eval_corpus"
)
DEFAULT_CV_FIXTURES_ROOT = _NLP_SERVICE_ROOT / "tests" / "fixtures"


JDCategory = Literal[
    "swe", "data", "devops", "qa", "frontend", "backend", "non_tech"
]
"""Coarse role classification used for stratified evaluation. ``non_tech``
is reserved for negative-control JDs (Marketing, HR, …) — we expect
Module 3 to rate ``non_tech`` vs dev-CV pairs as low fit."""

Seniority = Literal["junior", "mid", "senior", "unspecified"]
"""Seniority bucket. ``unspecified`` covers JDs that don't disclose one."""

FitJudgment = Literal["strong", "possible", "no"]
"""Recruiter-style fit judgment for a single (CV, JD) pair."""

EvalLanguage = Literal["en", "ro"]
"""Eval corpus languages — must match Module 2's ``Language`` alias."""


# ---------------------------------------------------------------------------
# Fixture types
# ---------------------------------------------------------------------------


class JDFixture(BaseModel):
    """A single Job Description fixture as stored on disk.

    Produced by ``scripts/convert_jds.py`` from the raw ``.txt`` LinkedIn
    scrapes under ``eval_corpus/jds_raw/``. ``required_skills`` and
    ``nice_to_have_skills`` are GOLD labels — the human's view of what
    the JD demands — and serve as ground truth for the JD parser
    introduced in Step 6 / 7.
    """

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    language: EvalLanguage
    location: str = ""
    category: JDCategory
    seniority: Seniority
    source_anonymized: str = ""
    raw_text: str = Field(min_length=1)
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    notes: str = ""


class GoldSkill(BaseModel):
    """One gold-label skill expected to be found in a CV."""

    skill_uri: str = Field(min_length=1)
    label: str = Field(min_length=1)
    confidence_expected: Literal["high", "medium"]
    """How confident the labeller is that Module 3 *must* find this
    skill. ``high`` = the skill is unambiguous and explicitly named;
    ``medium`` = the skill is implied or partially evidenced."""


class CVLabels(BaseModel):
    """Gold skill labels for a single CV.

    Ground truth for Module 3's Phase A (skill linking) metrics.
    """

    cv_id: str = Field(min_length=1)
    gold_skills: list[GoldSkill] = Field(default_factory=list)
    skills_definitely_not_in_cv: list[str] = Field(
        default_factory=list,
        description=(
            "Skill labels (free-form) that Module 2 sometimes "
            "false-positives on this CV. Listing them lets the Module 3 "
            "validator confirm they have been suppressed."
        ),
    )
    notes: str = ""


class EvalCorpus(BaseModel):
    """In-memory representation of the on-disk evaluation corpus.

    Constructed by :func:`load_eval_corpus`. Not serialised — this is a
    runtime DTO, not a wire format.
    """

    cvs: dict[str, Path] = Field(default_factory=dict)
    """``cv_id`` (e.g. ``"real_cv1"``) → absolute path to the PDF.
    The PDF itself is NOT loaded; downstream callers feed it to Module
    1's :class:`~cv_extractor.ExtractionPipeline`."""

    jds: dict[str, JDFixture] = Field(default_factory=dict)
    cv_labels: dict[str, CVLabels] = Field(default_factory=dict)

    fit_matrix: dict[str, dict[str, FitJudgment]] = Field(
        default_factory=dict,
        description=(
            "Two-level dict: ``fit_matrix[cv_id][jd_id]`` → judgment. "
            "Missing keys mean the cell was empty in the CSV; access "
            "via :meth:`fit` for a uniform ``None`` on unjudged pairs."
        ),
    )

    def cv_ids(self) -> list[str]:
        """Sorted list of CV IDs registered in the corpus."""
        return sorted(self.cvs.keys())

    def jd_ids(self) -> list[str]:
        """Sorted list of JD IDs loaded from ``jds/``."""
        return sorted(self.jds.keys())

    def fit(self, cv_id: str, jd_id: str) -> FitJudgment | None:
        """Return the fit judgment for a pair, or ``None`` if unjudged."""
        return self.fit_matrix.get(cv_id, {}).get(jd_id)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_eval_corpus(
    eval_root: Path | None = None,
    cv_fixtures_root: Path | None = None,
) -> EvalCorpus:
    """Load the held-out evaluation corpus from disk.

    Parameters
    ----------
    eval_root:
        Path to the ``eval_corpus/`` directory containing ``jds/``,
        ``cv_labels/`` and ``fit_matrix.csv``. Defaults to
        :data:`DEFAULT_EVAL_CORPUS_ROOT`.
    cv_fixtures_root:
        Directory containing the ``real_cv*.pdf`` files. Defaults to
        :data:`DEFAULT_CV_FIXTURES_ROOT`.

    Returns
    -------
    EvalCorpus
        Populated with whatever artefacts exist on disk. Missing
        directories produce empty maps rather than raising; the
        ``test_eval_corpus.py`` suite enforces presence invariants
        at the integration level rather than at the loader level.
    """
    resolved_eval_root = (
        eval_root if eval_root is not None else DEFAULT_EVAL_CORPUS_ROOT
    )
    resolved_cv_root = (
        cv_fixtures_root
        if cv_fixtures_root is not None
        else DEFAULT_CV_FIXTURES_ROOT
    )

    cvs: dict[str, Path] = {}
    if resolved_cv_root.exists():
        for pdf in sorted(resolved_cv_root.glob("real_cv*.pdf")):
            cvs[pdf.stem] = pdf

    jds: dict[str, JDFixture] = {}
    jds_dir = resolved_eval_root / "jds"
    if jds_dir.exists():
        for yaml_path in sorted(jds_dir.glob("jd*.yaml")):
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            jd = JDFixture.model_validate(data)
            jds[jd.id] = jd

    cv_labels: dict[str, CVLabels] = {}
    labels_dir = resolved_eval_root / "cv_labels"
    if labels_dir.exists():
        for yaml_path in sorted(labels_dir.glob("real_cv*.yaml")):
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            label = CVLabels.model_validate(data)
            cv_labels[label.cv_id] = label

    fit_matrix: dict[str, dict[str, FitJudgment]] = {}
    matrix_path = resolved_eval_root / "fit_matrix.csv"
    if matrix_path.exists():
        with matrix_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cv_id = (row.pop("cv_id", "") or "").strip()
                if not cv_id:
                    continue
                cv_matrix: dict[str, FitJudgment] = {}
                for jd_id, val in row.items():
                    if val is None:
                        continue
                    stripped = val.strip().lower()
                    match stripped:
                        case "strong" | "possible" | "no":
                            cv_matrix[jd_id] = stripped
                if cv_matrix:
                    fit_matrix[cv_id] = cv_matrix

    return EvalCorpus(
        cvs=cvs,
        jds=jds,
        cv_labels=cv_labels,
        fit_matrix=fit_matrix,
    )


__all__ = [
    "DEFAULT_CV_FIXTURES_ROOT",
    "DEFAULT_EVAL_CORPUS_ROOT",
    "CVLabels",
    "EvalCorpus",
    "EvalLanguage",
    "FitJudgment",
    "GoldSkill",
    "JDCategory",
    "JDFixture",
    "Seniority",
    "load_eval_corpus",
]
