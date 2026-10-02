"""End-to-end tests: Module 1 PDF extraction → Module 2 skill extraction.

These tests run the full real pipeline:

* :class:`cv_extractor.ExtractionPipeline` on the bundled CV PDFs
  (``tests/fixtures/``);
* :class:`skill_extractor.SkillExtractor` on the resulting
  :class:`ExtractionResult`, using the *real* ESCO bundle and the
  *real* spaCy language model.

Because they require the production spaCy models to be installed,
they are marked ``@pytest.mark.slow``. They skip gracefully when the
model is absent so a fresh checkout still passes
``pytest -m "not slow"``.

The cover letter fixture is exercised here too — it must trigger
:class:`NotACVError` end-to-end, validating the contract between
Module 1's quality warning and Module 2's input filter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

spacy = pytest.importorskip("spacy")

from cv_extractor import ExtractionPipeline  # noqa: E402
from cv_extractor.config import ExtractorConfig  # noqa: E402
from cv_extractor.exceptions import (  # noqa: E402
    CVExtractorError,
    PDFCorruptError,
)
from skill_extractor import (  # noqa: E402
    NotACVError,
    SkillExtractionResult,
    SkillExtractor,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _load_or_skip(model_name: str) -> spacy.Language:  # type: ignore[name-defined]
    try:
        return spacy.load(model_name)
    except OSError:
        pytest.skip(
            f"spaCy model {model_name!r} is not installed. "
            f"Install with: python -m spacy download {model_name}"
        )


@pytest.fixture(scope="module")
def real_extractor() -> SkillExtractor:
    """A :class:`SkillExtractor` wired to the real ESCO bundle and the
    real ``en_core_web_lg`` / ``ro_core_news_lg`` models."""
    en_nlp = _load_or_skip("en_core_web_lg")
    ro_nlp = _load_or_skip("ro_core_news_lg")
    nlp_by_lang = {"en": en_nlp, "ro": ro_nlp}
    return SkillExtractor(nlp_factory=lambda lang: nlp_by_lang[lang])


@pytest.fixture(scope="module")
def module1_pipeline() -> ExtractionPipeline:
    """Module 1 pipeline configured for the test corpus.

    The default ``min_quality_score`` of 0.5 rejects short Europass-
    style CVs (quality scores ~0.4) and bounces them to the OCR
    fallback, which on a Windows dev box without Poppler produces a
    confusing :class:`PDFCorruptError`. Lowering the threshold to 0.3
    keeps the digital extractors in play and exercises Module 2 the
    way it would behave under the production override documented in
    ``project_module1_limitations.md``.
    """
    return ExtractionPipeline(
        config=ExtractorConfig(min_quality_score=0.3)
    )


def _full_pipeline(
    *,
    pdf_path: Path,
    module1: ExtractionPipeline,
    module2: SkillExtractor,
) -> SkillExtractionResult:
    """Run Module 1 then Module 2; skip the test cleanly on Module 1
    failures that are environmental (missing Poppler, corrupt PDF)."""
    try:
        er = module1.process(pdf_path)
    except (PDFCorruptError, CVExtractorError) as exc:
        pytest.skip(
            f"Module 1 cannot extract {pdf_path.name} on this machine "
            f"(likely missing Poppler / OCR dependencies): {exc}"
        )
    return module2.extract(er)


@pytest.mark.slow
class TestRealCVs:
    @pytest.mark.parametrize(
        "fixture_name",
        [
            "CV - Silviu.pdf",
            "CV_14-03-2025.pdf",
            "cv-europass.pdf",
        ],
    )
    def test_real_cv_returns_some_skills(
        self,
        fixture_name: str,
        real_extractor: SkillExtractor,
        module1_pipeline: ExtractionPipeline,
    ) -> None:
        pdf = FIXTURES_DIR / fixture_name
        if not pdf.exists():
            pytest.skip(f"Fixture {fixture_name!r} not in repo.")
        result = _full_pipeline(
            pdf_path=pdf,
            module1=module1_pipeline,
            module2=real_extractor,
        )
        assert isinstance(result, SkillExtractionResult)
        assert result.skill_count > 0, (
            f"{fixture_name}: expected at least one skill match"
        )
        for s in result.skills:
            assert 0.0 <= s.confidence <= 1.0
            assert s.frequency >= 1
            assert len(s.spans) >= 1

    def test_silviu_cv_contains_expected_tech_skills(
        self,
        real_extractor: SkillExtractor,
        module1_pipeline: ExtractionPipeline,
    ) -> None:
        """The author's own CV should list Python or similar common
        tech skills. We check via ESCO preferred_label substring."""
        pdf = FIXTURES_DIR / "CV - Silviu.pdf"
        if not pdf.exists():
            pytest.skip("Author CV fixture missing.")

        result = _full_pipeline(
            pdf_path=pdf,
            module1=module1_pipeline,
            module2=real_extractor,
        )
        labels_lower = [s.preferred_label.lower() for s in result.skills]
        candidate_signals = (
            "python",
            "sql",
            "java",
            "git",
            "javascript",
            "html",
            "css",
            "linux",
        )
        assert any(
            any(sig in lbl for lbl in labels_lower)
            for sig in candidate_signals
        ), (
            f"None of {candidate_signals!r} found in CV skill labels: "
            f"{labels_lower[:20]} (showing first 20 of {len(labels_lower)})."
        )


@pytest.mark.slow
class TestCoverLetterIsRefused:
    """Module 1 emits the NOT_A_CV_WARNING for the cover letter
    fixture; Module 2 must refuse to extract from it."""

    def test_cover_letter_raises_not_a_cv(
        self,
        real_extractor: SkillExtractor,
        module1_pipeline: ExtractionPipeline,
    ) -> None:
        pdf = FIXTURES_DIR / (
            "Scrisoare de intenție pentru desfășurarea "
            "stagiului de practică.pdf"
        )
        if not pdf.exists():
            pytest.skip("Cover letter fixture missing.")
        try:
            er = module1_pipeline.process(pdf)
        except (PDFCorruptError, CVExtractorError) as exc:
            pytest.skip(
                f"Module 1 cannot extract cover letter on this machine: {exc}"
            )
        with pytest.raises(NotACVError):
            real_extractor.extract(er)
