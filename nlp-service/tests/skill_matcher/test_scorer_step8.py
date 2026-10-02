"""Step 8 additions to the Scorer test suite.

Behavioural-equivalence tests for :meth:`Scorer.score_to_intermediates`.
Held in a separate module from :mod:`test_scorer` so the Step 7 tests
remain untouched.

The contract being verified:

* ``score_to_intermediates`` makes the same number of encoder calls as
  ``score`` -- no extra encoding cost for the tuner.
* Aggregating the intermediates at the production defaults
  (``per_requirement_keep_threshold = 0.30``, ``required_weight = 0.8``)
  and projecting at production ``(T1=0.55, T2=0.25)`` produces the same
  ``overall_score`` and matched-requirement count as ``score`` would.
* The returned :class:`CellIntermediate` carries the Linker thresholds
  as provenance.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

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
from skill_matcher.tuning import (
    CellIntermediate,
    ReqIntermediate,
    aggregate_from_intermediates,
)

# ---------------------------------------------------------------------------
# Test helpers (light copies of test_scorer.py's ControlledEncoder/StubIndex)
# ---------------------------------------------------------------------------


_DIM = 4


class _ControlledEncoder:
    def __init__(
        self, vectors: dict[str, NDArray[np.float32]] | None = None
    ) -> None:
        self.embedding_dim = _DIM
        self.model_name = "controlled-test-encoder"
        self.vectors: dict[str, NDArray[np.float32]] = dict(vectors or {})
        self.encode_call_count = 0

    def encode(
        self, texts: list[str], *, batch_size: int = 32
    ) -> NDArray[np.float32]:
        _ = batch_size
        self.encode_call_count += 1
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        rows = [
            self.vectors.get(t, np.zeros(self.embedding_dim, dtype=np.float32))
            for t in texts
        ]
        return np.vstack(rows).astype(np.float32, copy=False)


class _StubIndex:
    def __init__(self, fixed_top1: tuple[str, float] | None = None) -> None:
        self._fixed_top1 = fixed_top1

    def query(
        self,
        query_embedding: NDArray[np.float32] | list[float],
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        _ = (query_embedding, top_k)
        if self._fixed_top1 is None:
            return []
        return [self._fixed_top1]


def _unit_vec(i: int) -> NDArray[np.float32]:
    v = np.zeros(_DIM, dtype=np.float32)
    v[i % _DIM] = 1.0
    return v


def _vec_at_cosine(target_cos: float) -> NDArray[np.float32]:
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
    return concept.uri


def _make_candidate(
    *,
    uri: str,
    confidence: float = 0.9,
    source: str = "lexical_kept",
) -> MatchCandidate:
    return MatchCandidate(
        skill_uri=uri,
        skill_label=uri,
        confidence=confidence,
        source=source,  # type: ignore[arg-type]
        cv_evidence_text=f"{uri} (skills)",
        cv_evidence_offset=(10, 16),
        similarity_score=0.7,
        lexical_confidence=0.85,
    )


def _make_enriched(
    candidates: list[MatchCandidate],
    *,
    cv_id: str = "cv_eq",
) -> EnrichedSkillResult:
    return EnrichedSkillResult(
        cv_id=cv_id,
        candidates=candidates,
        detected_language="en",
        pipeline_version="skill_matcher@0.6.0+encoder=test",
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


@pytest.fixture
def default_config() -> SkillMatcherConfig:
    return SkillMatcherConfig()


# ---------------------------------------------------------------------------
# Shape + provenance
# ---------------------------------------------------------------------------


def test_score_to_intermediates_returns_cell_intermediate(
    default_config: SkillMatcherConfig,
) -> None:
    enc = _ControlledEncoder()
    enc.vectors["uri_x"] = _unit_vec(0)
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={"uri_x": _make_concept("uri_x")},
    )
    enriched = _make_enriched([_make_candidate(uri="uri_x", confidence=0.7)])
    requirements = [_make_req(text="X", skill_uri="uri_x", confidence=0.9)]
    cell = scorer.score_to_intermediates(enriched, "jd_eq", requirements)

    assert isinstance(cell, CellIntermediate)
    assert cell.cv_id == "cv_eq"
    assert cell.jd_id == "jd_eq"
    assert len(cell.requirements) == 1
    assert isinstance(cell.requirements[0], ReqIntermediate)
    # Linker thresholds carried as provenance.
    assert cell.linker_thresholds == (
        default_config.drop_threshold,
        default_config.keep_threshold,
        default_config.expansion_threshold,
    )


def test_score_to_intermediates_records_exact_match_factors(
    default_config: SkillMatcherConfig,
) -> None:
    enc = _ControlledEncoder()
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={"uri_x": _make_concept("uri_x")},
    )
    enriched = _make_enriched([_make_candidate(uri="uri_x", confidence=0.7)])
    requirements = [_make_req(text="X", skill_uri="uri_x", confidence=0.9)]
    cell = scorer.score_to_intermediates(enriched, "jd_eq", requirements)

    r = cell.requirements[0]
    assert r.req_confidence == pytest.approx(0.9)
    assert r.candidate_confidence == pytest.approx(0.7)
    assert r.uri_similarity == pytest.approx(1.0)


def test_score_to_intermediates_records_unmatched_as_zeros(
    default_config: SkillMatcherConfig,
) -> None:
    """A requirement whose semantic fallback comes in below
    ``keep_threshold`` should be recorded as ``(cand_conf=0.0,
    uri_sim=0.0)`` -- the same way ``score()`` would treat it."""
    enc = _ControlledEncoder()
    enc.vectors["uri_req"] = _unit_vec(0)
    enc.vectors["uri_other"] = _vec_at_cosine(0.30)  # below 0.55 keep
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={
            "uri_req": _make_concept("uri_req"),
            "uri_other": _make_concept("uri_other"),
        },
    )
    enriched = _make_enriched([_make_candidate(uri="uri_other", confidence=0.7)])
    requirements = [_make_req(text="Req", skill_uri="uri_req", confidence=0.9)]
    cell = scorer.score_to_intermediates(enriched, "jd_eq", requirements)

    r = cell.requirements[0]
    assert r.candidate_confidence == 0.0
    assert r.uri_similarity == 0.0


# ---------------------------------------------------------------------------
# Behavioural equivalence with score()
# ---------------------------------------------------------------------------


def test_score_to_intermediates_matches_score_overall(
    default_config: SkillMatcherConfig,
) -> None:
    """Aggregating intermediates at production defaults reproduces
    ``score().overall_score`` for a non-trivial mixed-importance JD.
    """
    enc = _ControlledEncoder()
    concepts = {
        "uri_r1": _make_concept("uri_r1"),
        "uri_r2": _make_concept("uri_r2"),
        "uri_n1": _make_concept("uri_n1"),
    }
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts=concepts,
    )
    enriched = _make_enriched(
        [
            _make_candidate(uri="uri_r1", confidence=0.8),
            _make_candidate(uri="uri_r2", confidence=0.6),
            _make_candidate(uri="uri_n1", confidence=0.5),
        ]
    )
    requirements = [
        _make_req(text="R1", skill_uri="uri_r1", confidence=1.0),
        _make_req(text="R2", skill_uri="uri_r2", confidence=1.0),
        _make_req(
            text="N1",
            skill_uri="uri_n1",
            importance="nice_to_have",
            confidence=1.0,
        ),
    ]

    result, _ = scorer.score(enriched, jd_id="jd_eq", requirements=requirements)
    cell = scorer.score_to_intermediates(enriched, "jd_eq", requirements)
    rebuilt = aggregate_from_intermediates(
        [cell],
        per_requirement_keep_threshold=default_config.per_requirement_keep_threshold,
        # Step 8 wiring: ``Scorer._aggregate`` now reads
        # ``config.required_weight`` -- so behavioural equivalence requires
        # passing the SAME value to ``aggregate_from_intermediates``.
        required_weight=default_config.required_weight,
    )
    assert rebuilt[("cv_eq", "jd_eq")] == pytest.approx(
        result.overall_score, abs=1e-6
    )


def test_score_to_intermediates_does_not_exceed_score_encoder_calls(
    default_config: SkillMatcherConfig,
) -> None:
    """Encoder is called the same number of times by both methods on
    identical inputs -- no extra cost for the tuner."""
    enc_a = _ControlledEncoder()
    enc_a.vectors["unresolved_a"] = _unit_vec(0)
    enc_a.vectors["uri_x"] = _unit_vec(0)
    enc_a.vectors["uri_y"] = _unit_vec(1)

    enc_b = _ControlledEncoder()
    enc_b.vectors = dict(enc_a.vectors)

    scorer_a = _make_scorer(
        config=default_config,
        encoder=enc_a,
        index=_StubIndex(fixed_top1=("uri_x", 0.9)),
        concepts={
            "uri_x": _make_concept("uri_x"),
            "uri_y": _make_concept("uri_y"),
        },
    )
    scorer_b = _make_scorer(
        config=default_config,
        encoder=enc_b,
        index=_StubIndex(fixed_top1=("uri_x", 0.9)),
        concepts={
            "uri_x": _make_concept("uri_x"),
            "uri_y": _make_concept("uri_y"),
        },
    )

    enriched = _make_enriched(
        [
            _make_candidate(uri="uri_x", confidence=0.7),
            _make_candidate(uri="uri_y", confidence=0.7),
        ]
    )
    requirements = [
        _make_req(text="unresolved_a", skill_uri=None, confidence=0.0),
        _make_req(text="R_pre", skill_uri="uri_x", confidence=0.8),
    ]
    scorer_a.score(enriched, jd_id="jd_eq", requirements=requirements)
    scorer_b.score_to_intermediates(enriched, "jd_eq", requirements)

    assert enc_a.encode_call_count == enc_b.encode_call_count


def test_score_to_intermediates_preserves_order_of_requirements(
    default_config: SkillMatcherConfig,
) -> None:
    """The intermediates' order mirrors the input requirements list."""
    enc = _ControlledEncoder()
    scorer = _make_scorer(
        config=default_config,
        encoder=enc,
        index=_StubIndex(),
        concepts={
            "uri_a": _make_concept("uri_a"),
            "uri_b": _make_concept("uri_b"),
            "uri_c": _make_concept("uri_c"),
        },
    )
    enriched = _make_enriched(
        [
            _make_candidate(uri="uri_a", confidence=0.7),
            _make_candidate(uri="uri_b", confidence=0.7),
            _make_candidate(uri="uri_c", confidence=0.7),
        ]
    )
    requirements = [
        _make_req(text="A", skill_uri="uri_a"),
        _make_req(text="B", skill_uri="uri_b"),
        _make_req(text="C", skill_uri="uri_c"),
    ]
    cell = scorer.score_to_intermediates(enriched, "jd_order", requirements)
    assert [r.req_text for r in cell.requirements] == ["A", "B", "C"]
