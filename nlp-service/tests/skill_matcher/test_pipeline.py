"""Fast unit tests for :class:`skill_matcher.pipeline.SkillMatcher`.

Focuses on the parts of the orchestrator that *can* be tested without
the real sentence-transformers stack:

* Model-path resolution (3-tier fallback).
* Lazy-load idempotency.
* Step 7's :meth:`SkillMatcher.match` still raises.

The end-to-end ``.link()`` happy path is covered by
``test_linker.test_linker_e2e_on_real_cv1`` (slow).

The pipeline's lazy-load path calls four hot spots (encoder, index,
ESCO loader, ESCO SHA). The stubs below replace each with an explicit
signature matching the actual call shape -- no ``*args, **kwargs: Any``
trickery, so the module stays mypy-strict and ruff-ANN clean.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from skill_matcher.config import SkillMatcherConfig
from skill_matcher.pipeline import SkillMatcher

# ---------------------------------------------------------------------------
# Model-path resolution
# ---------------------------------------------------------------------------


def test_resolve_model_path_with_explicit_finetuned(tmp_path: Path) -> None:
    """``config.finetuned_model_path`` wins outright when set and existing."""
    finetuned_dir = tmp_path / "my_run"
    finetuned_dir.mkdir()

    cfg = SkillMatcherConfig(
        finetuned_model_path=finetuned_dir,
        models_dir=tmp_path / "models",
    )
    matcher = SkillMatcher(config=cfg)
    assert matcher._resolve_model_path() == str(finetuned_dir)


def test_resolve_model_path_with_missing_finetuned_raises(tmp_path: Path) -> None:
    """A non-existent ``finetuned_model_path`` fails loud, not silently."""
    cfg = SkillMatcherConfig(
        finetuned_model_path=tmp_path / "nonexistent",
        models_dir=tmp_path,
    )
    matcher = SkillMatcher(config=cfg)
    with pytest.raises(RuntimeError, match="does not exist"):
        matcher._resolve_model_path()


def test_resolve_model_path_via_latest_pointer(tmp_path: Path) -> None:
    """No override + ``latest.txt`` pointer -> returns the resolved run dir."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    run_dir = models_dir / "mnrl_v9"
    run_dir.mkdir()
    (models_dir / "latest.txt").write_text("mnrl_v9", encoding="utf-8")

    cfg = SkillMatcherConfig(models_dir=models_dir)
    matcher = SkillMatcher(config=cfg)
    assert matcher._resolve_model_path() == str(run_dir)


def test_resolve_model_path_falls_back_to_base_model(tmp_path: Path) -> None:
    """No override + no ``latest.txt`` -> returns ``config.base_model``."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    cfg = SkillMatcherConfig(models_dir=models_dir)
    matcher = SkillMatcher(config=cfg)
    assert matcher._resolve_model_path() == cfg.base_model


def test_resolve_model_path_latest_pointer_to_missing_dir_falls_back(
    tmp_path: Path,
) -> None:
    """``latest.txt`` points at a missing dir -> warn + fall through to base."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "latest.txt").write_text("nonexistent_run", encoding="utf-8")

    cfg = SkillMatcherConfig(models_dir=models_dir)
    matcher = SkillMatcher(config=cfg)
    assert matcher._resolve_model_path() == cfg.base_model


def test_resolve_model_path_empty_latest_falls_back(tmp_path: Path) -> None:
    """Whitespace-only ``latest.txt`` is ignored."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "latest.txt").write_text("   \n", encoding="utf-8")

    cfg = SkillMatcherConfig(models_dir=models_dir)
    matcher = SkillMatcher(config=cfg)
    assert matcher._resolve_model_path() == cfg.base_model


# ---------------------------------------------------------------------------
# Lazy-load idempotency
# ---------------------------------------------------------------------------


class _StubEncoder:
    """Minimal Encoder Protocol implementation for lazy-load tests.

    The pipeline never calls ``encode()`` during lazy-load (only the
    index builder does), but we provide it anyway so the stub
    satisfies the Protocol shape end-to-end.
    """

    model_name: str = "stub"
    embedding_dim: int = 4

    def encode(
        self, texts: list[str], *, batch_size: int = 32
    ) -> NDArray[np.float32]:
        _ = batch_size
        return np.zeros((len(texts), 4), dtype=np.float32)


class _StubIndex:
    """Duck-typed EscoIndex stub.

    Carries ``n_concepts`` / ``embedding_dim`` as class attributes so the
    pipeline's structured-log lines don't ``AttributeError``. Methods
    have explicit signatures matching the actual calls from
    :meth:`SkillMatcher._get_or_build_index` -- no ``Any`` typing
    games.
    """

    n_concepts: int = 0
    embedding_dim: int = 4

    def __init__(self, encoder: object, cache_dir: Path) -> None:
        self.encoder = encoder
        self.cache_dir = cache_dir

    def load(
        self,
        path: Path,
        *,
        expected_esco_sha: str | None = None,
        expected_format: str | None = None,
    ) -> None:
        _ = (path, expected_esco_sha, expected_format)
        return None

    def build(
        self, concepts: list[object], *, fmt: str = "bounded-a", batch_size: int = 64
    ) -> None:
        _ = (concepts, fmt, batch_size)
        return None

    def save(
        self,
        path: Path,
        *,
        esco_sha: str,
        skill_matcher_version: str,
    ) -> None:
        _ = (path, esco_sha, skill_matcher_version)
        return None

    def query_batch(
        self,
        query_embeddings: NDArray[np.float32],
        top_k: int = 5,
    ) -> list[list[tuple[str, float]]]:
        _ = (query_embeddings, top_k)
        return []


def test_ensure_ready_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling _ensure_ready twice does not re-construct the heavy components."""
    call_count: dict[str, int] = {"encoder": 0, "index": 0, "concepts": 0}

    def _stub_encoder_ctor(
        model_name: str, device: str = "auto", *, seed: int = 42
    ) -> _StubEncoder:
        _ = (model_name, device, seed)
        call_count["encoder"] += 1
        return _StubEncoder()

    def _stub_index_ctor(*, encoder: object, cache_dir: Path) -> _StubIndex:
        call_count["index"] += 1
        return _StubIndex(encoder=encoder, cache_dir=cache_dir)

    def _stub_load_concepts() -> list[object]:
        call_count["concepts"] += 1
        return []

    def _stub_compute_esco_sha(concepts: list[object]) -> str:
        _ = concepts
        return "deadbeef"

    monkeypatch.setattr(
        "skill_matcher.pipeline.SentenceTransformerEncoder",
        _stub_encoder_ctor,
    )
    monkeypatch.setattr("skill_matcher.pipeline.EscoIndex", _stub_index_ctor)
    monkeypatch.setattr(
        "skill_matcher.pipeline.load_esco_concepts", _stub_load_concepts
    )
    monkeypatch.setattr(
        "skill_matcher.pipeline.compute_esco_sha", _stub_compute_esco_sha
    )

    matcher = SkillMatcher()
    matcher._ensure_ready()
    matcher._ensure_ready()
    matcher._ensure_ready()

    assert call_count["encoder"] == 1
    assert call_count["index"] == 1
    assert call_count["concepts"] == 1


# ---------------------------------------------------------------------------
# Step 7 surface -- ``match()`` end-to-end with stubs
# ---------------------------------------------------------------------------


def _wire_lazy_load_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Common monkeypatch wire-up for tests that need ``_ensure_ready``
    to succeed without loading the real model/index/concepts."""

    def _stub_encoder_ctor(
        model_name: str, device: str = "auto", *, seed: int = 42
    ) -> _StubEncoder:
        _ = (model_name, device, seed)
        return _StubEncoder()

    def _stub_index_ctor(*, encoder: object, cache_dir: Path) -> _StubIndex:
        return _StubIndex(encoder=encoder, cache_dir=cache_dir)

    def _stub_load_concepts() -> list[object]:
        return []

    def _stub_compute_esco_sha(concepts: list[object]) -> str:
        _ = concepts
        return "deadbeef"

    monkeypatch.setattr(
        "skill_matcher.pipeline.SentenceTransformerEncoder",
        _stub_encoder_ctor,
    )
    monkeypatch.setattr("skill_matcher.pipeline.EscoIndex", _stub_index_ctor)
    monkeypatch.setattr(
        "skill_matcher.pipeline.load_esco_concepts", _stub_load_concepts
    )
    monkeypatch.setattr(
        "skill_matcher.pipeline.compute_esco_sha", _stub_compute_esco_sha
    )


def test_skill_matcher_match_runs_with_empty_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty CV + empty requirements produces a well-formed
    :class:`MatchResult` with overall_score = 0.0 and no exceptions."""
    from skill_matcher.models import EnrichedSkillResult

    _wire_lazy_load_stubs(monkeypatch)

    matcher = SkillMatcher()
    enriched = EnrichedSkillResult(
        cv_id="x",
        candidates=[],
        detected_language="en",
        pipeline_version="skill_matcher@0.5.0",
    )
    result = matcher.match(enriched=enriched, jd_id="jd", requirements=[])
    assert result.cv_id == "x"
    assert result.jd_id == "jd"
    assert result.overall_score == 0.0


def test_skill_matcher_match_lazy_constructs_scorer_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two consecutive ``match()`` calls reuse the same Scorer instance.

    Verifies the lazy-construction guard in :meth:`SkillMatcher.match`
    so the heavy components are not re-created per call.
    """
    from skill_matcher.models import EnrichedSkillResult

    _wire_lazy_load_stubs(monkeypatch)

    matcher = SkillMatcher()
    enriched = EnrichedSkillResult(
        cv_id="x",
        candidates=[],
        detected_language="en",
        pipeline_version="skill_matcher@0.5.0",
    )
    matcher.match(enriched=enriched, jd_id="jd_a", requirements=[])
    scorer_after_first = matcher._scorer
    matcher.match(enriched=enriched, jd_id="jd_b", requirements=[])
    scorer_after_second = matcher._scorer
    assert scorer_after_first is not None
    assert scorer_after_first is scorer_after_second


def test_skill_matcher_link_and_match_share_loaded_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling :meth:`SkillMatcher.match` after :meth:`SkillMatcher.link`
    does not re-load encoder / index / concepts. The Scorer reuses the
    same instances the Linker already owns."""
    from skill_extractor.models import SkillExtractionResult
    from skill_matcher.models import EnrichedSkillResult

    _wire_lazy_load_stubs(monkeypatch)

    matcher = SkillMatcher()

    # Trigger lazy load via link() with an empty SkillExtractionResult.
    matcher.link(
        cv_id="x",
        cv_text="",
        lexical=SkillExtractionResult(
            language="en", skills=[], skill_count=0, processing_time_ms=0.0
        ),
    )
    encoder_before = matcher._encoder
    index_before = matcher._index
    concepts_before = matcher._concepts_by_uri

    enriched = EnrichedSkillResult(
        cv_id="x",
        candidates=[],
        detected_language="en",
        pipeline_version="skill_matcher@0.5.0",
    )
    matcher.match(enriched=enriched, jd_id="jd", requirements=[])

    assert matcher._encoder is encoder_before
    assert matcher._index is index_before
    assert matcher._concepts_by_uri is concepts_before
