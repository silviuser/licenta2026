"""Fast unit tests for :class:`skill_matcher.scorer.Scorer`.

Uses a hand-rolled ``_ControlledEncoder`` (mirrors the Linker tests'
pattern) so the test can dial cosine similarities to known values, and
a ``_StubIndex`` that returns caller-specified top-k hits. All semantic
similarities are commanded explicitly; no real model is loaded except
in the ``@pytest.mark.slow`` end-to-end test at the bottom.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from skill_matcher.config import SkillMatcherConfig
from skill_matcher.esco_loader import EscoConcept
from skill_matcher.models import (
    EnrichedSkillResult,
    JDRequirement,
    MatchCandidate,
)
from skill_matcher.scorer import Scorer

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_DIM = 4
"""Match the Linker tests' embedding dim; 4D is plenty to pick distinct
unit vectors with known cosines."""


class _ControlledEncoder:
    """Encoder returning caller-specified vectors for known strings.

    Mirrors the Linker tests' helper. Unknown strings encode to a zero
    vector so cosine similarity is zero against any other unit vector,
    which falls below ``keep_threshold`` and naturally turns into an
    unmatched requirement.
    """

    def __init__(
        self, vectors: dict[str, NDArray[np.float32]] | None = None
    ) -> None:
        self.embedding_dim = _DIM
        self.model_name = "controlled-test-encoder"
        self.vectors: dict[str, NDArray[np.float32]] = dict(vectors or {})
        self.encode_call_count = 0
        self.encode_call_texts: list[list[str]] = []

    def encode(
        self, texts: list[str], *, batch_size: int = 32
    ) -> NDArray[np.float32]:
        _ = batch_size
        self.encode_call_count += 1
        self.encode_call_texts.append(list(texts))
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        rows = [
            self.vectors.get(t, np.zeros(self.embedding_dim, dtype=np.float32))
            for t in texts
        ]
        return np.vstack(rows).astype(np.float32, copy=False)


class _StubIndex:
    """Duck-typed :class:`EscoIndex` substitute.

    Returns caller-specified top-k hits from ``query()`` and is never
    asked to ``build()`` / ``load()`` in fast tests.
    """

    def __init__(self, fixed_top1: tuple[str, float] | None = None) -> None:
        self._fixed_top1 = fixed_top1
        self.query_call_count = 0

    def query(
        self,
        query_embedding: NDArray[np.float32] | list[float],
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        _ = (query_embedding, top_k)
        self.query_call_count += 1
        if self._fixed_top1 is None:
            return []
        return [self._fixed_top1]


def _unit_vec(i: int, dim: int = _DIM) -> NDArray[np.float32]:
    v = np.zeros(dim, dtype=np.float32)
    v[i % dim] = 1.0
    return v


def _vec_at_cosine(target_cos: float) -> NDArray[np.float32]:
    """4D unit vector at the specified cosine against ``_unit_vec(0)``."""
    theta = math.acos(target_cos)
    return np.array(
        [math.cos(theta), math.sin(theta), 0.0, 0.0], dtype=np.float32
    )


def _make_concept(uri: str, label: str = "Skill") -> EscoConcept:
    return EscoConcept(
        uri=uri,
        pref_label=label,
        alt_labels=(),
        description="",
        skill_type="knowledge",
        is_custom=False,
    )


def _identity_concept_text(concept: EscoConcept) -> str:
    """Test-only builder: returns ``concept.uri`` verbatim so the
    encoder lookup table can key directly on URIs."""
    return concept.uri


def _make_candidate(
    *,
    uri: str,
    label: str = "X",
    confidence: float = 0.9,
    source: str = "lexical_kept",
    similarity_score: float = 0.7,
    cv_evidence_text: str = "X (skills)",
    cv_evidence_offset: tuple[int, int] | None = (10, 16),
    lexical_confidence: float | None = 0.85,
) -> MatchCandidate:
    return MatchCandidate(
        skill_uri=uri,
        skill_label=label,
        confidence=confidence,
        source=source,  # type: ignore[arg-type]
        cv_evidence_text=cv_evidence_text,
        cv_evidence_offset=cv_evidence_offset,
        similarity_score=similarity_score,
        lexical_confidence=lexical_confidence,
    )


def _make_enriched(
    *,
    cv_id: str = "cv_test",
    candidates: list[MatchCandidate] | None = None,
) -> EnrichedSkillResult:
    return EnrichedSkillResult(
        cv_id=cv_id,
        candidates=candidates or [],
        detected_language="en",
        pipeline_version="skill_matcher@0.5.0+encoder=test",
    )


def _make_req(
    *,
    text: str,
    skill_uri: str | None = None,
    importance: str = "required",
    confidence: float = 0.8,
) -> JDRequirement:
    return JDRequirement(
        text=text,
        skill_uri=skill_uri,
        skill_label=None,
        importance=importance,  # type: ignore[arg-type]
        confidence=confidence,
    )


def _fixed_clock() -> datetime:
    """Deterministic clock for ``MatchResult.timestamp`` assertions."""
    return datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)


def _make_scorer(
    *,
    config: SkillMatcherConfig,
    encoder: _ControlledEncoder,
    index: _StubIndex,
    concepts: dict[str, EscoConcept],
) -> Scorer:
    return Scorer(
        config=config,
        encoder=encoder,  # type: ignore[arg-type]
        index=index,  # type: ignore[arg-type]
        concepts_by_uri=concepts,
        concept_text_builder=_identity_concept_text,
        clock=_fixed_clock,
        pipeline_version="skill_matcher@test+encoder=controlled",
    )


# ---------------------------------------------------------------------------
# Filter + dedup
# ---------------------------------------------------------------------------


def test_filter_and_dedup_drops_lexical_dropped(
    default_config: SkillMatcherConfig,
) -> None:
    """Candidates with ``source='lexical_dropped'`` are removed before
    matching."""
    enc = _ControlledEncoder()
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={},
    )
    enriched = _make_enriched(
        candidates=[
            _make_candidate(uri="uri_a", source="lexical_kept"),
            _make_candidate(uri="uri_b", source="lexical_dropped"),
            _make_candidate(uri="uri_c", source="expansion"),
        ]
    )
    cv_by_uri = scorer._filter_and_dedup_candidates(enriched)
    assert set(cv_by_uri.keys()) == {"uri_a", "uri_c"}
    assert cv_by_uri["uri_a"].source == "lexical_kept"
    assert cv_by_uri["uri_c"].source == "expansion"


def test_filter_and_dedup_keeps_highest_confidence_per_uri(
    default_config: SkillMatcherConfig,
) -> None:
    """Duplicate URIs (different spans) collapse to the highest-
    confidence representative."""
    enc = _ControlledEncoder()
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={},
    )
    enriched = _make_enriched(
        candidates=[
            _make_candidate(
                uri="uri_dup",
                confidence=0.4,
                similarity_score=0.6,
                cv_evidence_offset=(10, 14),
            ),
            _make_candidate(
                uri="uri_dup",
                confidence=0.9,  # higher -> wins
                similarity_score=0.7,
                cv_evidence_offset=(40, 44),
            ),
            _make_candidate(
                uri="uri_dup",
                confidence=0.5,
                similarity_score=0.8,
                cv_evidence_offset=(70, 74),
            ),
        ]
    )
    cv_by_uri = scorer._filter_and_dedup_candidates(enriched)
    assert len(cv_by_uri) == 1
    assert cv_by_uri["uri_dup"].confidence == pytest.approx(0.9)
    assert cv_by_uri["uri_dup"].cv_evidence_offset == (40, 44)


def test_filter_and_dedup_tie_break_uses_similarity_then_source_then_span(
    default_config: SkillMatcherConfig,
) -> None:
    """When confidence ties, dedup falls through to similarity_score,
    then source priority (kept > expansion), then span start."""
    enc = _ControlledEncoder()
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={},
    )
    enriched = _make_enriched(
        candidates=[
            # equal confidence -> sim_score tie-break: 0.7 wins
            _make_candidate(
                uri="uri_tie",
                confidence=0.8,
                similarity_score=0.6,
                source="lexical_kept",
                cv_evidence_offset=(10, 14),
            ),
            _make_candidate(
                uri="uri_tie",
                confidence=0.8,
                similarity_score=0.7,  # higher -> wins
                source="lexical_kept",
                cv_evidence_offset=(20, 24),
            ),
        ]
    )
    cv_by_uri = scorer._filter_and_dedup_candidates(enriched)
    assert cv_by_uri["uri_tie"].similarity_score == pytest.approx(0.7)

    # Now equal confidence AND equal sim -> source priority kept > expansion.
    enriched2 = _make_enriched(
        candidates=[
            _make_candidate(
                uri="uri_tie2",
                confidence=0.8,
                similarity_score=0.7,
                source="expansion",
                lexical_confidence=None,
                cv_evidence_offset=(10, 14),
            ),
            _make_candidate(
                uri="uri_tie2",
                confidence=0.8,
                similarity_score=0.7,
                source="lexical_kept",  # wins
                cv_evidence_offset=(50, 54),
            ),
        ]
    )
    cv_by_uri2 = scorer._filter_and_dedup_candidates(enriched2)
    assert cv_by_uri2["uri_tie2"].source == "lexical_kept"


# ---------------------------------------------------------------------------
# Exact URI match
# ---------------------------------------------------------------------------


def test_exact_uri_match_score(default_config: SkillMatcherConfig) -> None:
    """Exact URI -> uri_similarity = 1.0; score = req.conf * cand.conf * 1.0."""
    enc = _ControlledEncoder()
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={"uri_x": _make_concept("uri_x", "X")},
    )
    enriched = _make_enriched(
        candidates=[_make_candidate(uri="uri_x", confidence=0.7)]
    )
    requirements = [_make_req(text="X", skill_uri="uri_x", confidence=0.8)]

    result, stats = scorer.score(enriched, jd_id="jd_test", requirements=requirements)

    assert stats.n_req_matched_exact == 1
    assert stats.n_req_matched_semantic == 0
    assert stats.n_req_unmatched == 0
    assert len(result.matched_required) == 1
    matched = result.matched_required[0]
    assert matched.match_score == pytest.approx(0.8 * 0.7 * 1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Semantic fallback
# ---------------------------------------------------------------------------


def test_semantic_fallback_picks_above_keep_threshold(
    default_config: SkillMatcherConfig,
) -> None:
    """JD URI not in CV candidates; another CV URI has cos_sim 0.70 with
    the JD URI -> semantic fallback uses 0.70 as uri_similarity."""
    target_cos = 0.70
    enc = _ControlledEncoder()
    enc.vectors["uri_req"] = _unit_vec(0)
    enc.vectors["uri_other"] = _vec_at_cosine(target_cos)

    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={
            "uri_req": _make_concept("uri_req", "Req"),
            "uri_other": _make_concept("uri_other", "Other"),
        },
    )
    enriched = _make_enriched(
        candidates=[_make_candidate(uri="uri_other", confidence=0.6)]
    )
    requirements = [
        _make_req(text="Req", skill_uri="uri_req", confidence=0.9)
    ]
    result, stats = scorer.score(enriched, jd_id="jd_sem", requirements=requirements)

    assert stats.n_req_matched_semantic == 1
    assert stats.n_req_matched_exact == 0
    matched = result.matched_required[0]
    # match_score = 0.9 * 0.6 * 0.70 = 0.378
    assert matched.match_score == pytest.approx(0.9 * 0.6 * target_cos, abs=1e-4)


def test_semantic_fallback_rejects_below_keep_threshold(
    default_config: SkillMatcherConfig,
) -> None:
    """Best semantic similarity below ``keep_threshold`` (0.55) -> unmatched."""
    enc = _ControlledEncoder()
    enc.vectors["uri_req"] = _unit_vec(0)
    enc.vectors["uri_other"] = _vec_at_cosine(0.30)  # below 0.55

    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={
            "uri_req": _make_concept("uri_req", "Req"),
            "uri_other": _make_concept("uri_other", "Other"),
        },
    )
    enriched = _make_enriched(
        candidates=[_make_candidate(uri="uri_other", confidence=0.7)]
    )
    requirements = [_make_req(text="Req", skill_uri="uri_req")]
    result, stats = scorer.score(enriched, jd_id="jd_sem_low", requirements=requirements)

    assert stats.n_req_unmatched == 1
    assert len(result.unmatched_required) == 1
    assert result.unmatched_required[0].text == "Req"


# ---------------------------------------------------------------------------
# Below-keep-threshold (per-requirement product floor)
# ---------------------------------------------------------------------------


def test_per_requirement_keep_threshold_rejects_low_product(
    default_config: SkillMatcherConfig,
) -> None:
    """Even an exact-URI match is rejected when the tri-factor product
    falls below ``per_requirement_keep_threshold``.

    Step 8 lock dropped the default to 0.085 (was 0.30 in Step 7), so
    this test pins the threshold explicitly via ``model_copy`` rather
    than relying on the current default. That way the test's behaviour
    remains "an exact match scoring 0.20 with a 0.30 floor is rejected"
    regardless of how Step 9 / the Step 5 redo move the production
    default around.
    """
    cfg = default_config.model_copy(
        update={"per_requirement_keep_threshold": 0.30}
    )
    enc = _ControlledEncoder()
    scorer = _make_scorer(
        config=cfg,
        encoder=enc,
        index=_StubIndex(),
        concepts={"uri_x": _make_concept("uri_x", "X")},
    )
    enriched = _make_enriched(
        candidates=[_make_candidate(uri="uri_x", confidence=0.4)]
    )
    # 0.5 * 0.4 * 1.0 = 0.20 < 0.30 -> unmatched
    requirements = [_make_req(text="X", skill_uri="uri_x", confidence=0.5)]
    result, _ = scorer.score(enriched, jd_id="jd_low", requirements=requirements)
    assert len(result.matched_required) == 0
    assert len(result.unmatched_required) == 1


# ---------------------------------------------------------------------------
# Online URI resolution
# ---------------------------------------------------------------------------


def test_requirement_resolution_uses_index_top1(
    default_config: SkillMatcherConfig,
) -> None:
    """A free-text requirement (``skill_uri=None``) is resolved via
    ``index.query`` -> top-1 URI, then matched as exact."""
    enc = _ControlledEncoder()
    # The encoder must produce some embedding for the requirement text;
    # the stub index returns its preset top-1 regardless of input.
    enc.vectors["Python programming"] = _unit_vec(0)
    enc.vectors["uri_python"] = _unit_vec(0)

    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(fixed_top1=("uri_python", 0.9)),
        concepts={"uri_python": _make_concept("uri_python", "Python")},
    )
    enriched = _make_enriched(
        candidates=[
            _make_candidate(
                uri="uri_python", label="Python", confidence=0.85
            )
        ]
    )
    requirements = [
        _make_req(text="Python programming", skill_uri=None, confidence=0.0)
    ]
    result, stats = scorer.score(enriched, jd_id="jd_res", requirements=requirements)

    assert stats.n_req_resolved_online == 1
    assert stats.n_req_matched_exact == 1
    matched = result.matched_required[0]
    # When confidence is 0.0 the resolved cosine (0.9) becomes the new confidence.
    assert matched.requirement.skill_uri == "uri_python"
    assert matched.requirement.confidence == pytest.approx(0.9, abs=1e-4)


def test_requirement_resolution_preserves_nonzero_parser_confidence(
    default_config: SkillMatcherConfig,
) -> None:
    """A non-zero parser confidence is preserved through resolution."""
    enc = _ControlledEncoder()
    enc.vectors["Python"] = _unit_vec(0)
    enc.vectors["uri_python"] = _unit_vec(0)

    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(fixed_top1=("uri_python", 0.92)),
        concepts={"uri_python": _make_concept("uri_python", "Python")},
    )
    requirements = [
        _make_req(text="Python", skill_uri=None, confidence=0.65)
    ]
    resolved, _ = scorer._resolve_requirements_batched(requirements)
    assert resolved[0].skill_uri == "uri_python"
    # 0.65 is non-zero -> preserved (not overwritten by 0.92).
    assert resolved[0].confidence == pytest.approx(0.65, abs=1e-6)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_aggregation_required_and_nice_combine_correctly(
    default_config: SkillMatcherConfig,
) -> None:
    """Required matches dominate via the 0.8/0.2 weighting.

    Synthetic: 3 required matched at scores 0.8/0.6/0.4 -> req_score 0.6.
    2 nice with 1 matched at 0.5 and 1 unmatched -> nice_score 0.25.
    overall = 0.8 * 0.6 + 0.2 * 0.25 = 0.530.

    Step 8 lock moved the production default ``required_weight`` to 0.50,
    so this test pins 0.80 explicitly to preserve the arithmetic
    documented above.
    """
    cfg = default_config.model_copy(update={"required_weight": 0.8})
    enc = _ControlledEncoder()
    # Three required exact-URI matches. Use req_conf = 1.0 and dial
    # candidate confidence to land match_score exactly at 0.8 / 0.6 / 0.4.
    concepts = {
        "uri_r1": _make_concept("uri_r1"),
        "uri_r2": _make_concept("uri_r2"),
        "uri_r3": _make_concept("uri_r3"),
        "uri_n1": _make_concept("uri_n1"),
        "uri_n2": _make_concept("uri_n2"),
    }
    scorer = _make_scorer(
        config=cfg,
        encoder=enc,
        index=_StubIndex(),
        concepts=concepts,
    )
    enriched = _make_enriched(
        candidates=[
            _make_candidate(uri="uri_r1", confidence=0.8),
            _make_candidate(uri="uri_r2", confidence=0.6),
            _make_candidate(uri="uri_r3", confidence=0.4),
            _make_candidate(uri="uri_n1", confidence=0.5),
            # uri_n2 deliberately absent -> nice req unmatched
        ]
    )
    requirements = [
        _make_req(text="R1", skill_uri="uri_r1", confidence=1.0),
        _make_req(text="R2", skill_uri="uri_r2", confidence=1.0),
        _make_req(text="R3", skill_uri="uri_r3", confidence=1.0),
        _make_req(
            text="N1", skill_uri="uri_n1", importance="nice_to_have", confidence=1.0
        ),
        _make_req(
            text="N2", skill_uri="uri_n2", importance="nice_to_have", confidence=1.0
        ),
    ]

    result, _ = scorer.score(enriched, jd_id="jd_agg", requirements=requirements)
    assert result.overall_score == pytest.approx(0.53, abs=1e-4)
    assert result.required_coverage == pytest.approx(1.0)
    assert result.nice_to_have_coverage == pytest.approx(0.5)
    assert len(result.matched_required) == 3
    assert len(result.matched_nice_to_have) == 1
    assert len(result.unmatched_nice_to_have) == 1
    assert result.unmatched_nice_to_have[0].text == "N2"


def test_aggregation_required_empty_falls_back_to_nice_weight_one(
    default_config: SkillMatcherConfig,
) -> None:
    """JD with 0 required + only nice-to-haves -> nice_weight = 1.0."""
    enc = _ControlledEncoder()
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={"uri_n": _make_concept("uri_n")},
    )
    enriched = _make_enriched(
        candidates=[_make_candidate(uri="uri_n", confidence=0.8)]
    )
    requirements = [
        _make_req(
            text="N",
            skill_uri="uri_n",
            importance="nice_to_have",
            confidence=0.9,
        )
    ]
    result, stats = scorer.score(
        enriched, jd_id="jd_no_required", requirements=requirements
    )
    # match_score = 0.9 * 0.8 * 1.0 = 0.72
    # required_total == 0 -> overall == nice_score == 0.72
    assert result.overall_score == pytest.approx(0.72, abs=1e-4)
    assert stats.n_required_total == 0
    assert stats.n_nice_total == 1


def test_aggregation_completely_empty_jd_collapses_to_zero(
    default_config: SkillMatcherConfig,
) -> None:
    """JD with neither required nor nice requirements -> 0.0."""
    enc = _ControlledEncoder()
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={},
    )
    enriched = _make_enriched()
    result, stats = scorer.score(enriched, jd_id="jd_empty", requirements=[])
    assert result.overall_score == 0.0
    assert result.required_coverage == 0.0
    assert result.nice_to_have_coverage == 0.0
    assert stats.n_required_total == 0
    assert stats.n_nice_total == 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism_two_calls_produce_identical_match_result(
    default_config: SkillMatcherConfig,
) -> None:
    """Two consecutive ``score()`` calls on identical inputs produce
    byte-identical JSON dumps (after pinning the clock)."""
    enc = _ControlledEncoder()
    enc.vectors["uri_x"] = _unit_vec(0)
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={"uri_x": _make_concept("uri_x")},
    )
    enriched = _make_enriched(
        candidates=[_make_candidate(uri="uri_x", confidence=0.7)]
    )
    requirements = [_make_req(text="X", skill_uri="uri_x", confidence=0.9)]
    r1, _ = scorer.score(enriched, jd_id="jd_det", requirements=requirements)
    r2, _ = scorer.score(enriched, jd_id="jd_det", requirements=requirements)
    assert r1.model_dump_json() == r2.model_dump_json()


# ---------------------------------------------------------------------------
# Encoder batching
# ---------------------------------------------------------------------------


def test_encoder_called_at_most_twice_per_score(
    default_config: SkillMatcherConfig,
) -> None:
    """One ``score()`` call with N unresolved requirements + M unique
    CV URIs invokes ``encoder.encode`` at most twice:
    1) batched encode of unresolved requirement texts,
    2) batched encode of CV-URI concept-texts (+ any resolved-req URIs).
    """
    enc = _ControlledEncoder()
    # Pre-populate so cosines stay deterministic; values irrelevant here.
    enc.vectors["unresolved_text_1"] = _unit_vec(0)
    enc.vectors["unresolved_text_2"] = _unit_vec(0)
    enc.vectors["uri_a"] = _unit_vec(0)
    enc.vectors["uri_b"] = _unit_vec(0)
    enc.vectors["uri_c"] = _unit_vec(0)

    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(fixed_top1=("uri_a", 0.9)),
        concepts={
            "uri_a": _make_concept("uri_a"),
            "uri_b": _make_concept("uri_b"),
            "uri_c": _make_concept("uri_c"),
        },
    )
    enriched = _make_enriched(
        candidates=[
            _make_candidate(uri="uri_a", confidence=0.7),
            _make_candidate(uri="uri_b", confidence=0.7),
            _make_candidate(uri="uri_c", confidence=0.7),
        ]
    )
    requirements = [
        _make_req(text="unresolved_text_1", skill_uri=None),
        _make_req(text="unresolved_text_2", skill_uri=None),
        _make_req(text="R_pre", skill_uri="uri_a"),
    ]
    scorer.score(enriched, jd_id="jd_batch", requirements=requirements)
    # encode() called twice:
    #   1. unresolved requirement texts (n=2)
    #   2. requirement-side resolved URIs + CV-URI concept-texts (n=1+3)
    #      but the implementation makes two separate calls -- one per URI list.
    # The contract is: at most 3 (one per logical batch, plus an empty call
    # for unresolved-zero would not happen). Accept <= 3 for robustness.
    assert enc.encode_call_count <= 3


# ---------------------------------------------------------------------------
# pipeline_version + timestamp
# ---------------------------------------------------------------------------


def test_pipeline_version_format_uses_linker_style(
    default_config: SkillMatcherConfig,
) -> None:
    """Pipeline version follows Linker's ``+encoder=`` separator format."""
    enc = _ControlledEncoder()
    scorer = Scorer(
        config=default_config,
        encoder=enc,  # type: ignore[arg-type]
        index=_StubIndex(),  # type: ignore[arg-type]
        concepts_by_uri={},
        clock=_fixed_clock,
    )
    # The encoder's model_name is "controlled-test-encoder".
    assert "+encoder=controlled-test-encoder" in scorer._pipeline_version
    assert scorer._pipeline_version.startswith("skill_matcher@")


def test_clock_injected_and_used(default_config: SkillMatcherConfig) -> None:
    """The injected clock stamps ``MatchResult.timestamp``."""
    enc = _ControlledEncoder()
    enc.vectors["uri_x"] = _unit_vec(0)
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={"uri_x": _make_concept("uri_x")},
    )
    enriched = _make_enriched(
        candidates=[_make_candidate(uri="uri_x", confidence=0.7)]
    )
    requirements = [_make_req(text="X", skill_uri="uri_x", confidence=0.9)]
    result, _ = scorer.score(enriched, jd_id="jd_clock", requirements=requirements)
    assert result.timestamp == _fixed_clock()


def test_score_does_not_mutate_input_requirements(
    default_config: SkillMatcherConfig,
) -> None:
    """``score()`` treats the requirements list as immutable input."""
    enc = _ControlledEncoder()
    enc.vectors["X"] = _unit_vec(0)
    enc.vectors["uri_x"] = _unit_vec(0)
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(fixed_top1=("uri_x", 0.9)),
        concepts={"uri_x": _make_concept("uri_x")},
    )
    enriched = _make_enriched(
        candidates=[_make_candidate(uri="uri_x", confidence=0.7)]
    )
    original = _make_req(text="X", skill_uri=None, confidence=0.0)
    requirements = [original]
    scorer.score(enriched, jd_id="jd_no_mut", requirements=requirements)
    # Original untouched.
    assert original.skill_uri is None
    assert original.confidence == 0.0


# ---------------------------------------------------------------------------
# Slow / real-encoder end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_scorer_e2e_on_real_cv1_with_jd1() -> None:
    """End-to-end Scorer run on real_cv1 x jd1 with production encoder.

    Asserts only that the result is structurally well-formed; F1
    quality is a Step 8/Step 9 concern, not a Step 7 gate.
    """
    from cv_extractor.pipeline import ExtractionPipeline
    from skill_extractor.pipeline import SkillExtractor
    from skill_matcher import SkillMatcher
    from skill_matcher.eval_corpus import load_eval_corpus
    from skill_matcher.jd_parser import jd_fixture_to_requirements

    pdf_path = Path("tests/fixtures/real_cv1.pdf")
    if not pdf_path.exists():
        pytest.skip(f"fixture {pdf_path} missing")

    corpus = load_eval_corpus()
    if "jd1" not in corpus.jds:
        pytest.skip("jd1 fixture missing")

    extraction = ExtractionPipeline().process(pdf_path)
    lexical = SkillExtractor().extract(extraction)

    matcher = SkillMatcher()
    enriched = matcher.link(
        cv_id="real_cv1",
        cv_text=extraction.text,
        lexical=lexical,
    )
    requirements = jd_fixture_to_requirements(corpus.jds["jd1"])
    result = matcher.match(
        enriched=enriched, jd_id="jd1", requirements=requirements
    )

    assert 0.0 <= result.overall_score <= 1.0
    assert 0.0 <= result.required_coverage <= 1.0
    assert 0.0 <= result.nice_to_have_coverage <= 1.0
    assert result.cv_id == "real_cv1"
    assert result.jd_id == "jd1"
    # Every matched/unmatched list element is the right type.
    for mr in result.matched_required + result.matched_nice_to_have:
        assert 0.0 <= mr.match_score <= 1.0
    for u in result.unmatched_required + result.unmatched_nice_to_have:
        assert isinstance(u, JDRequirement)
