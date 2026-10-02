"""Tests for :mod:`skill_matcher.baseline`.

Fast tests exercise the metric computations on synthetic CVs and
verify the run loop against stub extraction / skill_extractor
objects. The slow test runs the real Module 1 + 2 + 3 stack on the
held-out eval corpus and asserts only that macro F1 > 0.10 (the
Sign-Off sanity floor — anything lower means the index is wired
wrong, not that zero-shot is weak).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from cv_extractor.models import (
    ExtractionMetadata,
    ExtractionMethod,
    ExtractionResult,
    PageInfo,
)
from skill_extractor.models import SkillExtractionResult, SkillMatch
from skill_matcher.baseline import (
    PRF,
    BaselineMetrics,
    CVBaselineResult,
    _aggregate_view,
    _select_gold,
    _semantic_uris,
    run_baseline,
    threshold_sweep,
)
from skill_matcher.encoder import MockEncoder
from skill_matcher.esco_index import EscoIndex, format_concept_text
from skill_matcher.esco_loader import EscoConcept
from skill_matcher.eval_corpus import CVLabels, EvalCorpus, GoldSkill

# ---------------------------------------------------------------------------
# PRF
# ---------------------------------------------------------------------------


def test_prf_perfect_match() -> None:
    """Identical predicted == gold → P=R=F1=1."""
    prf = PRF.from_sets({"a", "b"}, {"a", "b"})
    assert prf == PRF(1.0, 1.0, 1.0)


def test_prf_partial_overlap() -> None:
    """Two predicted, one in gold, two in gold → P=0.5, R=0.5, F1=0.5."""
    prf = PRF.from_sets({"a", "b"}, {"a", "c"})
    assert prf.precision == 0.5
    assert prf.recall == 0.5
    assert prf.f1 == 0.5


def test_prf_no_overlap() -> None:
    """Disjoint predicted and gold → P=R=F1=0."""
    prf = PRF.from_sets({"a"}, {"b"})
    assert prf == PRF(0.0, 0.0, 0.0)


def test_prf_empty_predicted_nonempty_gold() -> None:
    """Empty predicted means we caught nothing; R=0 by convention."""
    prf = PRF.from_sets(set(), {"a"})
    assert prf.recall == 0.0
    assert prf.f1 == 0.0


def test_prf_empty_gold_nonempty_predicted() -> None:
    """Empty gold means everything predicted is FP; P=0 by convention."""
    prf = PRF.from_sets({"a"}, set())
    assert prf.precision == 0.0
    assert prf.f1 == 0.0


def test_prf_both_empty_is_vacuously_perfect() -> None:
    """Empty + empty = vacuously correct; reviewers see this in the log."""
    prf = PRF.from_sets(set(), set())
    assert prf == PRF(1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_result(
    cv_id: str,
    *,
    lexical: set[str],
    semantic: dict[str, float],
    gold_high: set[str],
    gold_medium: set[str] | None = None,
) -> CVBaselineResult:
    """Construct a CVBaselineResult for metric-aggregation tests."""
    gold_high_plus_medium = gold_high | (gold_medium or set())
    return CVBaselineResult(
        cv_id=cv_id,
        text_length=100,
        n_windows=3,
        lexical_uris=lexical,
        gold_high=gold_high,
        gold_high_plus_medium=gold_high_plus_medium,
        forbidden_uris=set(),
        semantic_max_similarity=semantic,
        elapsed_seconds=0.1,
    )


def test_select_gold_returns_correct_view() -> None:
    r = _make_result(
        "cv1",
        lexical=set(),
        semantic={},
        gold_high={"a"},
        gold_medium={"b"},
    )
    assert _select_gold(r, "high") == {"a"}
    assert _select_gold(r, "high_plus_medium") == {"a", "b"}


def test_semantic_uris_respects_threshold() -> None:
    r = _make_result(
        "cv1",
        lexical=set(),
        semantic={"a": 0.7, "b": 0.6, "c": 0.5},
        gold_high=set(),
    )
    assert _semantic_uris(r, threshold=0.6) == {"a", "b"}
    assert _semantic_uris(r, threshold=0.65) == {"a"}
    assert _semantic_uris(r, threshold=0.95) == set()


# ---------------------------------------------------------------------------
# _aggregate_view — hand-computed metric correctness
# ---------------------------------------------------------------------------


def test_aggregate_view_macro_vs_micro_can_differ() -> None:
    """Macro is per-CV mean; micro is global pool. They diverge when
    CV sizes differ."""
    # CV1: 1 predicted, 1 gold, perfect.        Per-CV P=R=F1=1.
    # CV2: 10 predicted, 0 in gold, 1 gold.    Per-CV P=0, R=0, F1=0.
    r1 = _make_result(
        "cv1",
        lexical=set(),
        semantic={"a": 0.9},
        gold_high={"a"},
    )
    r2 = _make_result(
        "cv2",
        lexical=set(),
        semantic={f"x{i}": 0.9 for i in range(10)},
        gold_high={"target_not_predicted"},
    )
    agg = _aggregate_view(
        [r1, r2], view="high", threshold=0.5, top_k=5
    )
    # Macro: mean of (1.0, 0.0) = 0.5
    assert agg.semantic_macro.f1 == pytest.approx(0.5)
    # Micro: TP=1, FP=10, FN=1 → P=1/11, R=1/2, F1 = 2*P*R/(P+R)
    p = 1 / 11
    r = 1 / 2
    expected_micro = 2 * p * r / (p + r)
    assert agg.semantic_micro.f1 == pytest.approx(expected_micro)


def test_aggregate_view_threshold_filters_semantic() -> None:
    """A threshold above all semantic similarities yields empty set."""
    r = _make_result(
        "cv1",
        lexical=set(),
        semantic={"a": 0.5, "b": 0.6},
        gold_high={"a", "b"},
    )
    agg = _aggregate_view([r], view="high", threshold=0.9, top_k=5)
    # No predictions → recall 0.
    assert agg.semantic_macro.recall == 0.0


def test_aggregate_view_lexical_independent_of_threshold() -> None:
    """Lexical PRF does not move when the semantic threshold changes."""
    r = _make_result(
        "cv1",
        lexical={"a", "b"},
        semantic={"a": 0.9, "c": 0.8},
        gold_high={"a", "b"},
    )
    low = _aggregate_view([r], view="high", threshold=0.1, top_k=5)
    high = _aggregate_view([r], view="high", threshold=0.99, top_k=5)
    assert low.lexical_macro == high.lexical_macro


def test_aggregate_view_ensemble_is_union() -> None:
    """Ensemble == lexical union semantic."""
    r = _make_result(
        "cv1",
        lexical={"a"},
        semantic={"b": 0.9, "c": 0.95},  # both clear default threshold
        gold_high={"a", "b", "c"},
    )
    agg = _aggregate_view([r], view="high", threshold=0.5, top_k=5)
    # Ensemble recovers all 3 gold → perfect.
    assert agg.ensemble_macro.recall == 1.0
    assert agg.ensemble_macro.precision == 1.0
    # Semantic alone misses 'a'.
    assert agg.semantic_macro.recall == pytest.approx(2 / 3)


def test_threshold_sweep_uses_cached_similarities() -> None:
    """``threshold_sweep`` does not re-encode — it only re-aggregates."""
    r = _make_result(
        "cv1",
        lexical=set(),
        semantic={"a": 0.7, "b": 0.6, "c": 0.55},
        gold_high={"a", "b", "c"},
    )
    metrics = BaselineMetrics(
        config={"top_k_per_window": 5},
        per_cv=[r],
        headline=_aggregate_view([r], view="high", threshold=0.65, top_k=5),
        by_view={
            "high": _aggregate_view([r], view="high", threshold=0.65, top_k=5),
            "high_plus_medium": _aggregate_view(
                [r], view="high_plus_medium", threshold=0.65, top_k=5
            ),
        },
    )
    sweep = threshold_sweep(metrics, [0.5, 0.65, 0.8], view="high")
    # At 0.5 all three retrieved → perfect recall.
    assert sweep[0.5].recall == 1.0
    # At 0.65 only 'a' retrieved → recall 1/3.
    assert sweep[0.65].recall == pytest.approx(1 / 3)
    # At 0.8 nothing retrieved.
    assert sweep[0.8].recall == 0.0


# ---------------------------------------------------------------------------
# run_baseline with stub extraction + skill_extractor
# ---------------------------------------------------------------------------


@dataclass
class _StubExtractionPipeline:
    """Returns a canned :class:`ExtractionResult` regardless of input path."""

    text: str

    def process(self, pdf_path: Path) -> ExtractionResult:
        return ExtractionResult(
            text=self.text,
            metadata=ExtractionMetadata(
                method_used=ExtractionMethod.PDFPLUMBER,
                total_pages=1,
                processing_time_ms=1,
                detected_language="en",
                is_scanned=False,
                quality_score=1.0,
                pages=[
                    PageInfo(
                        page_number=1,
                        width=612.0,
                        height=792.0,
                        is_multi_column=False,
                        word_count=len(self.text.split()),
                    )
                ],
            ),
            warnings=[],
        )


@dataclass
class _StubSkillExtractor:
    """Returns a canned lexical result; ignores input."""

    skills: list[SkillMatch]

    def extract(self, _input: object) -> SkillExtractionResult:
        return SkillExtractionResult(
            language="en",
            skills=self.skills,
            skill_count=len(self.skills),
            processing_time_ms=1.0,
        )


def _build_tiny_index(
    encoder: MockEncoder,
    concepts: list[EscoConcept],
    tmp_path: Path,
) -> EscoIndex:
    index = EscoIndex(encoder=encoder, cache_dir=tmp_path)
    index.build(concepts, fmt="bounded-a", batch_size=4)
    return index


def test_run_baseline_with_stub_extractors_produces_metrics(
    mock_encoder: MockEncoder, tmp_path: Path
) -> None:
    """End-to-end run on a 1-CV synthetic corpus via stub Module 1/2.

    Concept descriptions are deliberately written WITHOUT a trailing
    period: the sliding-window tokeniser strips trailing punctuation
    from the last token's span, so a description ending in ``.`` would
    cause ``window.text != format_concept_text(...)`` and the
    MockEncoder hash would diverge.
    """
    concepts = [
        EscoConcept(
            uri="uri:python",
            pref_label="Python",
            alt_labels=("py",),
            description="A programming language",
            skill_type="knowledge",
            is_custom=False,
        ),
        EscoConcept(
            uri="uri:sql",
            pref_label="SQL",
            alt_labels=(),
            description="Structured Query Language",
            skill_type="knowledge",
            is_custom=False,
        ),
        EscoConcept(
            uri="uri:docker",
            pref_label="Docker",
            alt_labels=(),
            description="Container runtime",
            skill_type="knowledge",
            is_custom=False,
        ),
    ]
    index = _build_tiny_index(mock_encoder, concepts, tmp_path)

    # The "CV" text is one of the concept's bounded-a texts so that
    # MockEncoder retrieves the matching URI deterministically.
    python_text = format_concept_text(concepts[0], "bounded-a")

    # Fake eval corpus: one CV whose only gold label is uri:python.
    cv_id = "synthetic_cv1"
    fake_pdf = tmp_path / f"{cv_id}.pdf"
    fake_pdf.write_bytes(b"")  # path must exist but is never read by stub
    corpus = EvalCorpus(
        cvs={cv_id: fake_pdf},
        cv_labels={
            cv_id: CVLabels(
                cv_id=cv_id,
                gold_skills=[
                    GoldSkill(
                        skill_uri="uri:python",
                        label="Python",
                        confidence_expected="high",
                    ),
                ],
            )
        },
    )

    stub_extraction = _StubExtractionPipeline(text=python_text)
    stub_sx = _StubSkillExtractor(skills=[])

    metrics = run_baseline(
        eval_corpus=corpus,
        encoder=mock_encoder,
        index=index,
        skill_extractor=stub_sx,  # type: ignore[arg-type]
        extraction_pipeline=stub_extraction,  # type: ignore[arg-type]
        window_size_tokens=8,
        window_stride_tokens=4,
        semantic_threshold=0.5,
        top_k_per_window=2,
    )

    assert len(metrics.per_cv) == 1
    cv_result = metrics.per_cv[0]
    # The window's encoding == the concept's encoding → similarity ≈ 1.0,
    # so uri:python is retrieved.
    assert "uri:python" in cv_result.semantic_max_similarity
    assert cv_result.semantic_max_similarity["uri:python"] > 0.9

    # With the only gold label being uri:python and it being retrieved,
    # semantic precision/recall/F1 should all be 1.0 for this CV.
    high = metrics.by_view["high"].per_cv_semantic[cv_id]
    assert high.precision == 1.0
    assert high.recall == 1.0
    assert high.f1 == 1.0


def test_run_baseline_rejects_unbuilt_index(
    mock_encoder: MockEncoder, tmp_path: Path
) -> None:
    """An unbuilt index is a programming error, not a runtime fallback."""
    index = EscoIndex(encoder=mock_encoder, cache_dir=tmp_path)
    corpus = EvalCorpus(cvs={"x": tmp_path / "x.pdf"})
    with pytest.raises(RuntimeError, match="not built"):
        run_baseline(
            eval_corpus=corpus,
            encoder=mock_encoder,
            index=index,
        )


def test_run_baseline_rejects_empty_corpus(
    mock_encoder: MockEncoder, tmp_path: Path
) -> None:
    """An empty corpus is a configuration error, not silent zero-result."""
    concepts = [
        EscoConcept(
            uri="x",
            pref_label="X",
            alt_labels=(),
            description="",
            skill_type="knowledge",
            is_custom=False,
        )
    ]
    index = _build_tiny_index(mock_encoder, concepts, tmp_path)
    with pytest.raises(RuntimeError, match="No CV PDFs"):
        run_baseline(
            eval_corpus=EvalCorpus(),
            encoder=mock_encoder,
            index=index,
        )


def test_run_baseline_skips_unlabelled_cv(
    mock_encoder: MockEncoder, tmp_path: Path
) -> None:
    """An unlabelled CV is skipped with a structured log line — not a crash."""
    concepts = [
        EscoConcept(
            uri="x",
            pref_label="X",
            alt_labels=(),
            description="",
            skill_type="knowledge",
            is_custom=False,
        )
    ]
    index = _build_tiny_index(mock_encoder, concepts, tmp_path)
    fake_pdf = tmp_path / "unknown_cv.pdf"
    fake_pdf.write_bytes(b"")
    corpus = EvalCorpus(cvs={"unknown_cv": fake_pdf})  # no labels for it

    with pytest.raises(RuntimeError, match="zero per-CV results"):
        run_baseline(
            eval_corpus=corpus,
            encoder=mock_encoder,
            index=index,
            skill_extractor=_StubSkillExtractor(skills=[]),  # type: ignore[arg-type]
            extraction_pipeline=_StubExtractionPipeline(text="some text"),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Slow test — real stack against the eval corpus
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_real_baseline_wiring_produces_meaningful_metrics(tmp_path: Path) -> None:
    """End-to-end real run; guards *wiring*, not threshold quality.

    The empirically observed zero-shot F1 at the provisional 0.65
    threshold is ~0.07: precision is ~0.48 (semantic retrieval finds
    meaningful URIs) but recall is ~0.05 because the 0.65 cut filters
    out most candidates. The *headline* number is produced by the CLI
    ablation in ``scripts/run_zero_shot_baseline.py --ablation`` which
    sweeps a wider threshold range and locks the chosen threshold in
    ``DECISIONS.md``.

    What this test guards:

    * The pipeline runs end-to-end against the real SBERT model + real
      ESCO bundle + real eval-corpus CVs (modulo Poppler-skipped ones).
    * Semantic retrieval produces a non-trivial precision — anything
      near zero would indicate a wiring problem (wrong cache key,
      un-normalised embeddings, off-by-one in window aggregation).

    The 0.05 F1 floor is a wiring sanity check; the real performance
    discussion belongs in the report's threshold-ablation table.
    """
    from skill_matcher.encoder import SentenceTransformerEncoder
    from skill_matcher.esco_loader import load_esco_concepts

    enc = SentenceTransformerEncoder(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device="cpu",
    )
    concepts = load_esco_concepts(include_custom_overlay=True)
    index = EscoIndex(encoder=enc, cache_dir=tmp_path)
    index.build(concepts, fmt="bounded-a", batch_size=64)

    metrics = run_baseline(
        encoder=enc,
        index=index,
        window_size_tokens=30,
        window_stride_tokens=15,
        semantic_threshold=0.65,
        top_k_per_window=5,
    )
    headline = metrics.headline.semantic_macro
    assert headline.f1 > 0.05, (
        f"Wiring sanity floor breached: macro_f1 = {headline.f1:.4f}, "
        f"macro_p = {headline.precision:.4f}, macro_r = {headline.recall:.4f}. "
        "F1 below 0.05 indicates a pipeline-wiring bug rather than "
        "threshold mistuning."
    )
    # Precision floor: semantic retrieval at this threshold should be
    # discriminative, not random. Random retrieval against 14k concepts
    # would give precision near 0.
    assert headline.precision > 0.20, (
        f"Wiring sanity floor breached: macro_precision = "
        f"{headline.precision:.4f}. Semantic retrieval is producing "
        "near-random URIs — check the cache key and the L2-normalisation "
        "of both index and queries."
    )
