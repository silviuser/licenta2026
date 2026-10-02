"""Tests for :mod:`skill_matcher.esco_index`.

Fast tests use :class:`MockEncoder` + tiny synthetic concept sets so
the suite runs in milliseconds and never imports torch. The slow
test that builds the real ESCO index with the real SBERT model is
gated behind ``@pytest.mark.slow`` and is exercised by the baseline
runner during the headline cold run.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from skill_matcher.encoder import MockEncoder, SentenceTransformerEncoder
from skill_matcher.esco_index import (
    EscoIndex,
    EscoIndexCacheError,
    cache_filename,
    compute_model_sha,
    format_concept_text,
)
from skill_matcher.esco_loader import EscoConcept

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _synthetic_concepts() -> list[EscoConcept]:
    """A small concept set with one of each: knowledge, skill, language, custom."""
    return [
        EscoConcept(
            uri="uri:python",
            pref_label="Python (programming language)",
            alt_labels=("Python3", "py", "Python"),
            description="A high-level interpreted programming language.",
            skill_type="knowledge",
            is_custom=False,
        ),
        EscoConcept(
            uri="uri:sql",
            pref_label="SQL",
            alt_labels=(),
            description="Structured Query Language for relational databases.",
            skill_type="knowledge",
            is_custom=False,
        ),
        EscoConcept(
            uri="uri:write-en",
            pref_label="write English",
            alt_labels=("correspond in written English",),
            description="Compose written texts in English.",
            skill_type="language",
            is_custom=False,
        ),
        EscoConcept(
            uri="CUST:docker",
            pref_label="Docker",
            alt_labels=("Docker Engine", "containerd"),
            description="Container runtime and image format.",
            skill_type="knowledge",
            is_custom=True,
        ),
    ]


@pytest.fixture
def concepts() -> list[EscoConcept]:
    return _synthetic_concepts()


@pytest.fixture
def built_index(
    mock_encoder: MockEncoder,
    concepts: list[EscoConcept],
    tmp_cache_dir: Path,
) -> EscoIndex:
    """A freshly-built index ready for query / save tests."""
    index = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    index.build(concepts, fmt="bounded-a", batch_size=4)
    return index


# ---------------------------------------------------------------------------
# format_concept_text — concept-text format ablation contract
# ---------------------------------------------------------------------------


def test_format_concept_text_bounded_a_caps_alt_labels() -> None:
    """``bounded-a`` includes at most 5 sorted altLabels."""
    concept = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=tuple(f"alt{i}" for i in range(10)),
        description="d",
        skill_type="knowledge",
        is_custom=False,
    )
    text = format_concept_text(concept, "bounded-a")
    # 5 sorted altLabels means alt0..alt4 in this case.
    for i in range(5):
        assert f"alt{i}" in text
    for i in (5, 6, 7, 8, 9):
        assert f"alt{i}" not in text


def test_format_concept_text_bounded_a_sorts_alt_labels() -> None:
    """``bounded-a`` sorts altLabels for determinism — input order ignored."""
    a = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=("zeta", "alpha", "beta"),
        description="",
        skill_type="knowledge",
        is_custom=False,
    )
    b = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=("beta", "zeta", "alpha"),
        description="",
        skill_type="knowledge",
        is_custom=False,
    )
    assert format_concept_text(a, "bounded-a") == format_concept_text(b, "bounded-a")


def test_format_concept_text_b_drops_alt_labels() -> None:
    """Variant ``b`` is ``label. description`` only."""
    concept = EscoConcept(
        uri="x",
        pref_label="Python",
        alt_labels=("py", "Python3"),
        description="High-level language.",
        skill_type="knowledge",
        is_custom=False,
    )
    text = format_concept_text(concept, "b")
    assert "py" not in text
    assert "Python3" not in text
    assert "Python" in text
    assert "High-level language" in text


def test_format_concept_text_c_caps_alt_labels_to_three() -> None:
    """Variant ``c`` keeps up to 3 altLabels in insertion order."""
    concept = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=("alt0", "alt1", "alt2", "alt3", "alt4"),
        description="d",
        skill_type="knowledge",
        is_custom=False,
    )
    text = format_concept_text(concept, "c")
    for i in (0, 1, 2):
        assert f"alt{i}" in text
    for i in (3, 4):
        assert f"alt{i}" not in text


def test_format_concept_text_truncates_long_description_for_bounded() -> None:
    """Bounded variants cap description length; variant ``b`` does not."""
    long_desc = "x" * 500
    concept = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=(),
        description=long_desc,
        skill_type="knowledge",
        is_custom=False,
    )
    bounded = format_concept_text(concept, "bounded-a")
    plain = format_concept_text(concept, "b")
    assert "x" * 500 not in bounded
    assert "x" * 500 in plain


# ---------------------------------------------------------------------------
# compute_model_sha
# ---------------------------------------------------------------------------


def test_compute_model_sha_is_12_hex() -> None:
    sha = compute_model_sha(model_name="foo", finetuned_model_path=None)
    assert len(sha) == 12
    assert all(ch in "0123456789abcdef" for ch in sha)


def test_compute_model_sha_changes_with_finetuned_path(tmp_path: Path) -> None:
    """Adding / changing a fine-tuned path produces a different SHA.

    Critical for Step 5 — when the encoder swaps to a fine-tuned
    checkpoint the cache filename must change so the stale index is
    not silently reused.
    """
    a = compute_model_sha(model_name="foo", finetuned_model_path=None)
    b = compute_model_sha(model_name="foo", finetuned_model_path=tmp_path / "ckpt")
    c = compute_model_sha(model_name="foo", finetuned_model_path=tmp_path / "other")
    assert a != b
    assert b != c
    assert a != c


def test_cache_filename_format() -> None:
    """Filename pattern is the cache-key contract; lock it via test."""
    assert (
        cache_filename(
            model_sha="abcdef012345",
            esco_sha="0987654321ab",
            fmt="bounded-a",
        )
        == "esco_abcdef012345_0987654321ab_bounded-a.npz"
    )
    assert (
        cache_filename(
            model_sha="abcdef012345",
            esco_sha="0987654321ab",
            fmt="bounded-a",
            suffix=".json",
        )
        == "esco_abcdef012345_0987654321ab_bounded-a.json"
    )


# ---------------------------------------------------------------------------
# EscoIndex — build / properties / query
# ---------------------------------------------------------------------------


def test_index_construction_does_not_build(
    mock_encoder: MockEncoder, tmp_cache_dir: Path
) -> None:
    """A fresh index reports unbuilt state."""
    index = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    assert not index.is_built
    assert index.n_concepts == 0


def test_build_records_concept_text_format(built_index: EscoIndex) -> None:
    assert built_index.concept_text_format == "bounded-a"


def test_build_matrix_shape(
    built_index: EscoIndex, concepts: list[EscoConcept]
) -> None:
    """Matrix shape matches (n_concepts, encoder.embedding_dim)."""
    assert built_index.n_concepts == len(concepts)
    assert built_index.embedding_dim == built_index.encoder.embedding_dim


def test_build_uri_ordering_matches_input(
    built_index: EscoIndex, concepts: list[EscoConcept]
) -> None:
    """The URI list mirrors the input order — caller-provided sort wins."""
    assert built_index.uris == [c.uri for c in concepts]


def test_build_rejects_empty_concept_list(
    mock_encoder: MockEncoder, tmp_cache_dir: Path
) -> None:
    index = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    with pytest.raises(ValueError, match="empty"):
        index.build([])


def test_query_self_match_is_rank_1(
    built_index: EscoIndex, mock_encoder: MockEncoder, concepts: list[EscoConcept]
) -> None:
    """Querying with the embedding of a concept's own text retrieves
    the concept at rank 1 with similarity > 0.999."""
    target = concepts[0]  # Python
    target_text = format_concept_text(target, "bounded-a")
    query_emb = mock_encoder.encode([target_text])[0]
    results = built_index.query(query_emb, top_k=3)
    assert results[0][0] == target.uri
    assert results[0][1] > 0.999


def test_query_returns_top_k_sorted_descending(built_index: EscoIndex) -> None:
    """Results are sorted by similarity descending."""
    query = np.zeros(built_index.embedding_dim, dtype=np.float32)
    query[0] = 1.0
    results = built_index.query(query, top_k=3)
    sims = [s for _, s in results]
    assert sims == sorted(sims, reverse=True)


def test_query_clamps_top_k_to_index_size(built_index: EscoIndex) -> None:
    """Asking for more than n_concepts returns n_concepts results, not an error."""
    query = np.zeros(built_index.embedding_dim, dtype=np.float32)
    query[0] = 1.0
    results = built_index.query(query, top_k=999)
    assert len(results) == built_index.n_concepts


def test_query_rejects_wrong_dim(built_index: EscoIndex) -> None:
    """Dim mismatch raises rather than producing garbled results."""
    wrong = np.zeros(built_index.embedding_dim + 5, dtype=np.float32)
    with pytest.raises(ValueError, match="dim"):
        built_index.query(wrong)


def test_query_rejects_zero_top_k(built_index: EscoIndex) -> None:
    query = np.zeros(built_index.embedding_dim, dtype=np.float32)
    with pytest.raises(ValueError, match="top_k"):
        built_index.query(query, top_k=0)


def test_query_on_unbuilt_index_raises(
    mock_encoder: MockEncoder, tmp_cache_dir: Path
) -> None:
    index = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    with pytest.raises(RuntimeError, match="unbuilt"):
        index.query(np.zeros(mock_encoder.embedding_dim, dtype=np.float32))


# ---------------------------------------------------------------------------
# Batched query
# ---------------------------------------------------------------------------


def test_query_batch_returns_per_row_results(
    built_index: EscoIndex, mock_encoder: MockEncoder, concepts: list[EscoConcept]
) -> None:
    """Batched query produces the same top-k as the loop variant."""
    queries = mock_encoder.encode(
        [format_concept_text(concepts[0], "bounded-a"),
         format_concept_text(concepts[1], "bounded-a")]
    )
    batch = built_index.query_batch(queries, top_k=2)
    assert len(batch) == 2
    # Each row's top result is itself.
    assert batch[0][0][0] == concepts[0].uri
    assert batch[1][0][0] == concepts[1].uri


def test_query_batch_accepts_single_row_as_1d(built_index: EscoIndex) -> None:
    """``query_batch`` is forgiving about 1D vs (1, d) inputs."""
    query = np.zeros(built_index.embedding_dim, dtype=np.float32)
    query[0] = 1.0
    results = built_index.query_batch(query, top_k=2)
    assert len(results) == 1
    assert len(results[0]) == 2


# ---------------------------------------------------------------------------
# Save / load round-trip + sidecar validation
# ---------------------------------------------------------------------------


def test_save_and_load_round_trip(
    built_index: EscoIndex,
    mock_encoder: MockEncoder,
    tmp_cache_dir: Path,
    concepts: list[EscoConcept],
) -> None:
    """Saving then loading reproduces the matrix and URI ordering."""
    path = tmp_cache_dir / "test_index.npz"
    built_index.save(path, esco_sha="cafef00d1234", skill_matcher_version="0.2.0")

    reloaded = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    reloaded.load(path)
    assert reloaded.n_concepts == built_index.n_concepts
    assert reloaded.uris == built_index.uris
    # Query the same target on both indexes — should return identical (uri, sim).
    target_text = format_concept_text(concepts[0], "bounded-a")
    qemb = mock_encoder.encode([target_text])[0]
    assert built_index.query(qemb, top_k=2) == reloaded.query(qemb, top_k=2)


def test_load_missing_npz_raises(
    mock_encoder: MockEncoder, tmp_cache_dir: Path
) -> None:
    index = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    with pytest.raises(EscoIndexCacheError, match="not found"):
        index.load(tmp_cache_dir / "does_not_exist.npz")


def test_load_missing_sidecar_raises(
    built_index: EscoIndex, mock_encoder: MockEncoder, tmp_cache_dir: Path
) -> None:
    path = tmp_cache_dir / "no_sidecar.npz"
    built_index.save(path, esco_sha="abc123", skill_matcher_version="0.2.0")
    # Delete the sidecar to simulate partial cache corruption.
    path.with_suffix(".json").unlink()

    fresh = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    with pytest.raises(EscoIndexCacheError, match="Sidecar not found"):
        fresh.load(path)


def test_load_rejects_model_identity_mismatch(
    built_index: EscoIndex, tmp_cache_dir: Path
) -> None:
    """A different encoder identity must not be allowed to load the cache.

    Simulated here by saving with an explicit ``finetuned_model_path``
    on a stub encoder, then loading with a vanilla MockEncoder. In
    practice this catches the "Step 5 produced a checkpoint that
    overwrote the base-model cache" failure mode.
    """
    path = tmp_cache_dir / "model_mismatch.npz"
    built_index.save(path, esco_sha="abc123", skill_matcher_version="0.2.0")

    class _LyingEncoder:
        embedding_dim: int = built_index.embedding_dim
        model_name: str = "totally-different-model"

        def encode(
            self,
            texts: list[str],
            *,
            batch_size: int = 32,
        ) -> NDArray[np.float32]:
            _ = batch_size
            return np.zeros((len(texts), self.embedding_dim), dtype=np.float32)

    fresh = EscoIndex(encoder=_LyingEncoder(), cache_dir=tmp_cache_dir)
    with pytest.raises(EscoIndexCacheError, match="model_sha"):
        fresh.load(path)


def test_load_rejects_esco_sha_mismatch(
    built_index: EscoIndex, mock_encoder: MockEncoder, tmp_cache_dir: Path
) -> None:
    path = tmp_cache_dir / "sha_mismatch.npz"
    built_index.save(path, esco_sha="aaaaaa111111", skill_matcher_version="0.2.0")
    fresh = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    with pytest.raises(EscoIndexCacheError, match="esco_sha"):
        fresh.load(path, expected_esco_sha="bbbbbb222222")


def test_load_rejects_format_mismatch(
    built_index: EscoIndex, mock_encoder: MockEncoder, tmp_cache_dir: Path
) -> None:
    path = tmp_cache_dir / "fmt_mismatch.npz"
    built_index.save(path, esco_sha="abc123", skill_matcher_version="0.2.0")
    fresh = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    with pytest.raises(EscoIndexCacheError, match="concept_text_format"):
        fresh.load(path, expected_format="b")


def test_save_on_unbuilt_index_raises(
    mock_encoder: MockEncoder, tmp_cache_dir: Path
) -> None:
    index = EscoIndex(encoder=mock_encoder, cache_dir=tmp_cache_dir)
    with pytest.raises(RuntimeError, match="unbuilt"):
        index.save(
            tmp_cache_dir / "x.npz",
            esco_sha="abc",
            skill_matcher_version="0.2.0",
        )


# ---------------------------------------------------------------------------
# Slow tests — real SBERT against the real ESCO bundle
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_real_esco_index_build_and_sanity_query(tmp_cache_dir: Path) -> None:
    """End-to-end build with the real encoder + real ESCO loader.

    Asserts the index covers >10 000 concepts (ESCO v1.2.1 ships
    ~13.5k) and that a query for ``"Python"`` returns at least one
    Python-related concept in the top-5.
    """
    from skill_matcher.esco_loader import load_esco_concepts

    concepts = load_esco_concepts(include_custom_overlay=True)
    assert len(concepts) > 10_000

    enc = SentenceTransformerEncoder(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device="cpu",
    )
    index = EscoIndex(encoder=enc, cache_dir=tmp_cache_dir)
    index.build(concepts, fmt="bounded-a", batch_size=64)

    assert index.n_concepts == len(concepts)
    assert index.embedding_dim == 384

    qemb = enc.encode(["Python programming language"])[0]
    top = index.query(qemb, top_k=5)
    labels = [
        next(
            (c.pref_label for c in concepts if c.uri == uri),
            "<unknown>",
        )
        for uri, _ in top
    ]
    assert any("python" in label.lower() for label in labels), (
        f"Python query did not retrieve a Python-related concept: {labels}"
    )
