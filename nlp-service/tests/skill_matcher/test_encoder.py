"""Tests for :mod:`skill_matcher.encoder`.

Fast tests use :class:`MockEncoder` exclusively so the default
``pytest`` run never imports torch. The single slow test
(:func:`test_sentence_transformer_encoder_smoke`) loads the real
``paraphrase-multilingual-MiniLM-L12-v2`` checkpoint and is gated
behind ``@pytest.mark.slow``.
"""

from __future__ import annotations

import pickle

import numpy as np
import pytest

from skill_matcher.encoder import (
    DEFAULT_MOCK_DIM,
    MockEncoder,
    SentenceTransformerEncoder,
)

# ---------------------------------------------------------------------------
# Protocol conformance — structural only.
# ---------------------------------------------------------------------------
#
# ``Encoder`` is intentionally NOT ``@runtime_checkable`` because an
# ``isinstance(enc, Encoder)`` call against an unloaded
# ``SentenceTransformerEncoder`` would access ``embedding_dim`` and
# trigger the HuggingFace model download. Static type-checkers still
# enforce Protocol conformance; the tests here only verify the public
# attribute / method shape on the implementations.
# ---------------------------------------------------------------------------


def test_mock_encoder_exposes_encoder_surface(mock_encoder: MockEncoder) -> None:
    """``MockEncoder`` exposes the public ``Encoder`` Protocol surface."""
    assert isinstance(mock_encoder.embedding_dim, int)
    assert callable(mock_encoder.encode)


def test_sentence_transformer_encoder_exposes_encoder_surface() -> None:
    """``SentenceTransformerEncoder`` exposes the surface BEFORE any load.

    Critically, this test must NOT trigger lazy load — accessing
    ``encode`` as an attribute is fine, *calling* it would download.
    """
    enc = SentenceTransformerEncoder(model_name="stub", device="cpu")
    assert callable(enc.encode)
    assert enc._model is None  # still unloaded


# ---------------------------------------------------------------------------
# MockEncoder — shape, normalisation, determinism, ordering
# ---------------------------------------------------------------------------


def test_mock_encoder_output_shape(mock_encoder: MockEncoder) -> None:
    """Output shape is (len(texts), embedding_dim) for non-empty input."""
    out = mock_encoder.encode(["alpha", "beta", "gamma"])
    assert out.shape == (3, DEFAULT_MOCK_DIM)
    assert out.dtype == np.float32


def test_mock_encoder_empty_input_returns_zero_shape(mock_encoder: MockEncoder) -> None:
    """``encode([])`` must return shape ``(0, embedding_dim)``, not raise."""
    out = mock_encoder.encode([])
    assert out.shape == (0, DEFAULT_MOCK_DIM)
    assert out.dtype == np.float32


def test_mock_encoder_is_l2_normalised(mock_encoder: MockEncoder) -> None:
    """Every output row must have unit Euclidean norm."""
    out = mock_encoder.encode(["one", "two", "three", "four", "five"])
    norms = np.linalg.norm(out, axis=1)
    np.testing.assert_allclose(norms, np.ones(5), atol=1e-5)


def test_mock_encoder_is_deterministic(mock_encoder: MockEncoder) -> None:
    """Same input → identical output across two calls."""
    first = mock_encoder.encode(["hello", "world"])
    second = mock_encoder.encode(["hello", "world"])
    np.testing.assert_array_equal(first, second)


def test_mock_encoder_preserves_order(mock_encoder: MockEncoder) -> None:
    """Permuting the input permutes the output, row-wise."""
    out_ab = mock_encoder.encode(["a", "b"])
    out_ba = mock_encoder.encode(["b", "a"])
    np.testing.assert_array_equal(out_ab[0], out_ba[1])
    np.testing.assert_array_equal(out_ab[1], out_ba[0])


def test_mock_encoder_distinct_inputs_produce_distinct_outputs(
    mock_encoder: MockEncoder,
) -> None:
    """Different texts must not collide to identical embeddings.

    The mock encoder hashes inputs; collision risk on short strings
    is vanishingly small but the test pins the expectation.
    """
    out = mock_encoder.encode(["alpha", "beta", "gamma", "delta"])
    for i in range(out.shape[0]):
        for j in range(i + 1, out.shape[0]):
            assert not np.allclose(out[i], out[j], atol=1e-3), (
                f"rows {i} and {j} collided"
            )


def test_mock_encoder_is_picklable(mock_encoder: MockEncoder) -> None:
    """``MockEncoder`` must be picklable for use in fixtures."""
    blob = pickle.dumps(mock_encoder)
    restored = pickle.loads(blob)
    assert restored.embedding_dim == mock_encoder.embedding_dim
    np.testing.assert_array_equal(
        restored.encode(["x"]), mock_encoder.encode(["x"])
    )


def test_mock_encoder_supports_custom_dim() -> None:
    """Non-default embedding_dim is respected end-to-end."""
    enc = MockEncoder(embedding_dim=128)
    out = enc.encode(["x", "y"])
    assert out.shape == (2, 128)
    np.testing.assert_allclose(
        np.linalg.norm(out, axis=1), np.ones(2), atol=1e-5
    )


def test_mock_encoder_rejects_zero_dim() -> None:
    """A zero or negative embedding_dim is a programming error."""
    with pytest.raises(ValueError, match="embedding_dim"):
        MockEncoder(embedding_dim=0)


# ---------------------------------------------------------------------------
# SentenceTransformerEncoder — interactions that don't require the model
# ---------------------------------------------------------------------------


def test_st_encoder_does_not_load_at_construction() -> None:
    """Constructing the encoder must not import torch or download.

    We assert by checking the internal ``_model`` slot stays None;
    if construction loaded the model, ``_model`` would be populated.
    """
    enc = SentenceTransformerEncoder(model_name="never-downloaded", device="cpu")
    assert enc._model is None


def test_st_encoder_resolve_device_rejects_typo() -> None:
    """A typo like ``'GPU'`` raises rather than silently CPU-falling."""
    enc = SentenceTransformerEncoder(model_name="x", device="GPU")
    with pytest.raises(ValueError, match="Unknown device"):
        # Calling encode forces device resolution.
        enc.encode(["x"])


def test_st_encoder_resolve_device_static_cpu() -> None:
    """Static device resolution: ``cpu`` passes through."""
    assert SentenceTransformerEncoder._resolve_device("cpu") == "cpu"


def test_st_encoder_resolve_device_static_cuda() -> None:
    """Static device resolution: ``cuda`` passes through unchanged."""
    assert SentenceTransformerEncoder._resolve_device("cuda") == "cuda"


def test_st_encoder_repr_reports_unloaded_state() -> None:
    """``__repr__`` must communicate whether the model is loaded."""
    enc = SentenceTransformerEncoder(model_name="m", device="cpu")
    assert "loaded=False" in repr(enc)


# ---------------------------------------------------------------------------
# Slow tests — real sentence-transformers model
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_sentence_transformer_encoder_smoke() -> None:
    """End-to-end smoke test on the real MiniLM checkpoint.

    Asserts:

    1. The published embedding dim for ``paraphrase-multilingual-MiniLM-L12-v2``
       is 384.
    2. Output shape and dtype match the contract.
    3. Output rows are L2-normalised.
    4. Semantically related inputs produce higher dot products than
       unrelated ones — this is a sanity check that the model loaded
       correctly and that normalisation did not collapse the geometry.
    """
    enc = SentenceTransformerEncoder(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device="cpu",
    )
    related_a = "Python programming language"
    related_b = "developing software in Python"
    unrelated = "vanilla ice cream recipe"

    out = enc.encode([related_a, related_b, unrelated])
    assert out.shape == (3, 384)
    assert out.dtype == np.float32
    np.testing.assert_allclose(
        np.linalg.norm(out, axis=1), np.ones(3), atol=1e-5
    )

    sim_related = float(out[0] @ out[1])
    sim_unrelated = float(out[0] @ out[2])
    assert sim_related > sim_unrelated, (
        f"semantic ordering broken: related={sim_related:.3f} vs "
        f"unrelated={sim_unrelated:.3f}"
    )


@pytest.mark.slow
def test_sentence_transformer_encoder_handles_empty_input() -> None:
    """Real encoder must also honour the empty-input contract."""
    enc = SentenceTransformerEncoder(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device="cpu",
    )
    out = enc.encode([])
    assert out.shape == (0, 384)
    assert out.dtype == np.float32
