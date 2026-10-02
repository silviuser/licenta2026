"""Tests for :mod:`skill_matcher.eval_corpus`."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from skill_matcher.eval_corpus import (
    CVLabels,
    EvalCorpus,
    GoldSkill,
    JDFixture,
    load_eval_corpus,
)

# ---------------------------------------------------------------------------
# Synthetic-corpus fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def tiny_corpus(tmp_path: Path) -> tuple[Path, Path]:
    """Build a minimal valid eval corpus on disk; return ``(eval_root, cv_root)``."""
    eval_root = tmp_path / "eval_corpus"
    (eval_root / "jds").mkdir(parents=True)
    (eval_root / "cv_labels").mkdir(parents=True)

    cv_root = tmp_path / "fixtures"
    cv_root.mkdir()

    # Stub PDFs (loader only registers paths, never reads them).
    for i in (1, 2):
        (cv_root / f"real_cv{i}.pdf").write_bytes(b"%PDF-1.4 stub")

    # Two JDs — one EN, one RO.
    for i, lang in [(1, "en"), (2, "ro")]:
        jd_data = {
            "id": f"jd{i}",
            "title": f"Role {i}",
            "language": lang,
            "location": "Bucharest",
            "category": "swe",
            "seniority": "mid",
            "source_anonymized": f"Company {chr(64 + i)}",
            "raw_text": f"Job description body {i}",
            "required_skills": ["Python", "SQL"],
            "nice_to_have_skills": ["Docker"],
            "notes": "",
        }
        (eval_root / "jds" / f"jd{i}.yaml").write_text(
            yaml.safe_dump(jd_data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    # Two CV labels.
    for i in (1, 2):
        lbl_data = {
            "cv_id": f"real_cv{i}",
            "gold_skills": [
                {
                    "skill_uri": f"http://example.org/skill/{i}",
                    "label": f"Skill {i}",
                    "confidence_expected": "high",
                }
            ],
            "skills_definitely_not_in_cv": [],
            "notes": "",
        }
        (eval_root / "cv_labels" / f"real_cv{i}.yaml").write_text(
            yaml.safe_dump(lbl_data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    # Fit matrix.
    (eval_root / "fit_matrix.csv").write_text(
        "cv_id,jd1,jd2\n"
        "real_cv1,strong,no\n"
        "real_cv2,possible,strong\n",
        encoding="utf-8",
    )

    return eval_root, cv_root


# ---------------------------------------------------------------------------
# Loader behaviour
# ---------------------------------------------------------------------------


def test_load_tiny_corpus(tiny_corpus: tuple[Path, Path]) -> None:
    """End-to-end load of a synthetic 2x2 corpus."""
    eval_root, cv_root = tiny_corpus
    corpus = load_eval_corpus(eval_root=eval_root, cv_fixtures_root=cv_root)

    assert corpus.cv_ids() == ["real_cv1", "real_cv2"]
    assert corpus.jd_ids() == ["jd1", "jd2"]
    assert len(corpus.cv_labels) == 2

    # Fit matrix.
    assert corpus.fit("real_cv1", "jd1") == "strong"
    assert corpus.fit("real_cv1", "jd2") == "no"
    assert corpus.fit("real_cv2", "jd1") == "possible"
    assert corpus.fit("real_cv2", "jd2") == "strong"

    # Unknown pair returns None.
    assert corpus.fit("nonexistent", "jd1") is None
    assert corpus.fit("real_cv1", "nonexistent") is None

    # JD content roundtrip.
    jd1 = corpus.jds["jd1"]
    assert jd1.language == "en"
    assert "Python" in jd1.required_skills

    # CV label content.
    lbl1 = corpus.cv_labels["real_cv1"]
    assert lbl1.gold_skills[0].confidence_expected == "high"


def test_load_empty_corpus_works(tmp_path: Path) -> None:
    """Missing directories produce empty maps, not exceptions."""
    corpus = load_eval_corpus(
        eval_root=tmp_path / "missing_eval",
        cv_fixtures_root=tmp_path / "missing_fixtures",
    )
    assert corpus.cv_ids() == []
    assert corpus.jd_ids() == []
    assert corpus.cv_labels == {}
    assert corpus.fit_matrix == {}


def test_fit_matrix_skips_empty_cells(tmp_path: Path) -> None:
    """Empty cells in the CSV are treated as 'unjudged' rather than errors."""
    eval_root = tmp_path / "eval"
    eval_root.mkdir()
    (eval_root / "fit_matrix.csv").write_text(
        "cv_id,jd1,jd2\n"
        "real_cv1,strong,\n"
        "real_cv2,,no\n"
        "real_cv3,POSSIBLE,Strong\n",  # case-normalised on load
        encoding="utf-8",
    )
    corpus = load_eval_corpus(
        eval_root=eval_root,
        cv_fixtures_root=tmp_path / "no_cvs",
    )
    assert corpus.fit("real_cv1", "jd1") == "strong"
    assert corpus.fit("real_cv1", "jd2") is None
    assert corpus.fit("real_cv2", "jd1") is None
    assert corpus.fit("real_cv2", "jd2") == "no"
    assert corpus.fit("real_cv3", "jd1") == "possible"
    assert corpus.fit("real_cv3", "jd2") == "strong"


def test_fit_matrix_rejects_unknown_values(tmp_path: Path) -> None:
    """Unknown fit values are silently skipped — not stored, not errored."""
    eval_root = tmp_path / "eval"
    eval_root.mkdir()
    (eval_root / "fit_matrix.csv").write_text(
        "cv_id,jd1\nreal_cv1,maybe\n",
        encoding="utf-8",
    )
    corpus = load_eval_corpus(
        eval_root=eval_root,
        cv_fixtures_root=tmp_path / "no_cvs",
    )
    assert corpus.fit("real_cv1", "jd1") is None


def test_fit_matrix_skips_blank_cv_id_rows(tmp_path: Path) -> None:
    """A row whose ``cv_id`` is empty is silently skipped (Excel artefact)."""
    eval_root = tmp_path / "eval"
    eval_root.mkdir()
    (eval_root / "fit_matrix.csv").write_text(
        "cv_id,jd1\n"
        ",strong\n"  # blank cv_id
        "real_cv1,no\n",
        encoding="utf-8",
    )
    corpus = load_eval_corpus(
        eval_root=eval_root,
        cv_fixtures_root=tmp_path / "no_cvs",
    )
    assert list(corpus.fit_matrix.keys()) == ["real_cv1"]


# ---------------------------------------------------------------------------
# Type validation
# ---------------------------------------------------------------------------


def test_jd_fixture_rejects_invalid_category() -> None:
    with pytest.raises(ValidationError):
        JDFixture(
            id="jd1",
            title="x",
            language="en",
            category="not_a_real_category",  # type: ignore[arg-type]
            seniority="mid",
            raw_text="x",
        )


def test_jd_fixture_minimal_construction() -> None:
    """Optional fields default to empty values."""
    jd = JDFixture(
        id="jd1",
        title="t",
        language="en",
        category="swe",
        seniority="unspecified",
        raw_text="r",
    )
    assert jd.location == ""
    assert jd.required_skills == []
    assert jd.nice_to_have_skills == []
    assert jd.notes == ""


def test_cv_labels_allows_empty_gold_skills() -> None:
    """A CV that has not yet been labelled is still a valid record."""
    label = CVLabels(cv_id="real_cv13", gold_skills=[])
    assert label.gold_skills == []
    assert label.skills_definitely_not_in_cv == []


def test_gold_skill_confidence_validation() -> None:
    """`confidence_expected` must be 'high' or 'medium'."""
    with pytest.raises(ValidationError):
        GoldSkill(
            skill_uri="x",
            label="x",
            confidence_expected="low",  # type: ignore[arg-type]
        )


def test_eval_corpus_default_paths() -> None:
    """Default paths point at the canonical project locations."""
    from skill_matcher.eval_corpus import (
        DEFAULT_CV_FIXTURES_ROOT,
        DEFAULT_EVAL_CORPUS_ROOT,
    )
    assert DEFAULT_EVAL_CORPUS_ROOT.name == "eval_corpus"
    assert DEFAULT_EVAL_CORPUS_ROOT.parent.name == "fixtures"
    assert DEFAULT_CV_FIXTURES_ROOT.name == "fixtures"


def test_eval_corpus_helper_methods(tmp_path: Path) -> None:
    """Coverage for cv_ids / jd_ids / fit helpers on an empty corpus."""
    corpus = EvalCorpus()
    assert corpus.cv_ids() == []
    assert corpus.jd_ids() == []
    assert corpus.fit("a", "b") is None


# ---------------------------------------------------------------------------
# Integration: real on-disk corpus must load
# ---------------------------------------------------------------------------


def test_real_corpus_minimum_invariants() -> None:
    """Always-on baseline: the on-disk eval corpus has the expected scaffolding.

    Asserts only what is true RIGHT NOW after Step 2 code-side execution:

    * All 15 ``real_cv*.pdf`` fixtures are registered.
    * All 15 ``cv_labels/*.yaml`` stub files exist and parse.
    * The fit-matrix CSV template exists (rows may still be empty).

    The stricter ``test_real_corpus_complete`` (slow) runs the full
    data-side sign-off assertions; this test guards against schema
    regressions even before data is ingested.
    """
    corpus = load_eval_corpus()

    expected_cvs = {f"real_cv{i}" for i in range(1, 16)}
    actual_cvs = set(corpus.cv_ids())
    missing_cvs = expected_cvs - actual_cvs
    assert not missing_cvs, f"missing CV fixtures: {sorted(missing_cvs)}"

    missing_labels = expected_cvs - set(corpus.cv_labels.keys())
    assert not missing_labels, (
        f"missing cv_labels/*.yaml stubs: {sorted(missing_labels)}"
    )

    for cv_id in corpus.cv_ids():
        assert cv_id.startswith("real_cv")
        assert corpus.cvs[cv_id].suffix == ".pdf"


@pytest.mark.slow
def test_real_corpus_complete() -> None:
    """Strict invariants enforced once the user has finished data ingestion.

    This is the Step 2 SIGN-OFF GATE. Skips with a clear message until
    the data side is done. Once green, the eval corpus is locked.

    Required state for this test to pass:

    * 15 CVs registered (``real_cv1`` … ``real_cv15``).
    * At least 10 JDs YAML-ified under ``jds/``.
    * ``fit_matrix.csv`` populated for every (CV, JD) pair.
    * Every CV has a ``cv_labels/*.yaml`` with at least one ``gold_skill``.
    """
    corpus = load_eval_corpus()

    if not corpus.jd_ids():
        pytest.skip(
            "Eval corpus not yet populated. "
            "Run `python scripts/convert_jds.py` then review the "
            "generated jds/*.yaml, fill fit_matrix.csv and complete "
            "cv_labels/real_cv13.yaml … real_cv15.yaml before treating "
            "this test as the Step 2 sign-off gate."
        )

    expected_cvs = {f"real_cv{i}" for i in range(1, 16)}
    actual_cvs = set(corpus.cv_ids())
    missing_cvs = expected_cvs - actual_cvs
    assert not missing_cvs, f"missing CV fixtures: {sorted(missing_cvs)}"

    assert len(corpus.jd_ids()) >= 10, (
        f"expected >=10 JDs, found {len(corpus.jd_ids())}; "
        "run scripts/convert_jds.py and review the YAML output."
    )

    for cv_id in expected_cvs:
        assert cv_id in corpus.cv_labels, (
            f"missing cv_labels/{cv_id}.yaml"
        )
        gold = corpus.cv_labels[cv_id].gold_skills
        assert len(gold) > 0, (
            f"cv_labels/{cv_id}.yaml has empty gold_skills - fill it in."
        )

    for cv_id in expected_cvs:
        for jd_id in corpus.jd_ids():
            judgment = corpus.fit(cv_id, jd_id)
            assert judgment is not None, (
                f"fit_matrix.csv cell ({cv_id}, {jd_id}) is empty "
                "- fill it in."
            )
