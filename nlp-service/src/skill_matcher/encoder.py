"""Sentence-transformer encoder wrappers for Module 3.

Step 4 deliverable. Replaces the Step 1 stub with three public
artefacts:

* :class:`Encoder` — a :mod:`typing.Protocol` satisfied by both real
  and mock encoders. Anything downstream (the ESCO index, the
  baseline runner, the future Linker) types its dependencies as
  ``Encoder`` so test fixtures can swap a deterministic mock in
  without touching production code.
* :class:`MockEncoder` — a deterministic, dependency-free encoder used
  by the fast test suite. Output vectors are derived from a stable
  cryptographic hash of each input string and L2-normalised so cosine
  similarity reduces to a dot product (matching the real encoder's
  contract). Same input → same output across runs and across
  processes; this lets the fast suite assert exact equality.
* :class:`SentenceTransformerEncoder` — production encoder wrapping
  :mod:`sentence_transformers`. The underlying model is **lazy
  loaded** on the first :meth:`encode` call so importing
  :mod:`skill_matcher` stays cheap (no torch import, no 500 MB
  download triggered) and so fast tests that use ``MockEncoder``
  never pay for sentence-transformers.

Both encoders guarantee:

1. **Order preservation** — ``output[i]`` corresponds to ``texts[i]``.
2. **L2-normalised float32** — every output row has unit Euclidean
   norm to within ``1e-5``. Cosine similarity == dot product
   downstream.
3. **Empty-input safety** — ``encode([])`` returns
   ``np.zeros((0, embedding_dim), dtype=np.float32)``.

Design rationale (defensible at the thesis defence)
---------------------------------------------------
The ``Encoder`` Protocol is the seam that lets Module 3 test the
expansion-stage logic without paying for SBERT inference in every CI
run. It also makes the cross-encoder re-ranker decision in Step 5b a
swap of one class — the rest of the pipeline does not change.

Lazy loading is not a premature optimisation. ``sentence_transformers``
imports ``torch`` at module-import time, which on a cold venv triggers
a ~3 s import cost plus ~200 MB of resident memory before any work is
done. Deferring the import means ``pytest -m "not slow"`` stays
import-cheap and that scripts which only build an empty pipeline
(``SkillMatcher()``) do not pay for it.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Protocol, cast

import numpy as np
import structlog
from numpy.typing import NDArray

if TYPE_CHECKING:
    # Imported only for type-checker visibility. The real import lives
    # inside ``SentenceTransformerEncoder._lazy_load`` so module import
    # remains cheap.
    from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(__name__)

# Default dimensionality for :class:`MockEncoder`. Small enough that
# 13k synthetic-concept indexes stay tiny in tests (13k * 32 * 4
# bytes ≈ 1.6 MB) yet large enough that hash collisions are vanishingly
# rare. The real model dimension is dictated by the underlying SBERT
# checkpoint (384 for ``paraphrase-multilingual-MiniLM-L12-v2``).
DEFAULT_MOCK_DIM = 32


class Encoder(Protocol):
    """Anything that maps a batch of texts to L2-normalised float32 vectors.

    Implementations must satisfy three contracts:

    1. ``output[i]`` corresponds to ``texts[i]`` (input order
       preserved).
    2. Each row has unit Euclidean norm so cosine similarity reduces
       to a dot product.
    3. ``encode([])`` returns ``ndarray`` of shape
       ``(0, embedding_dim)`` rather than raising.

    Not :func:`typing.runtime_checkable` because ``isinstance(enc,
    Encoder)`` against the production
    :class:`SentenceTransformerEncoder` (which lazy-loads its model
    on first ``embedding_dim`` access) would trigger a HuggingFace
    download just to satisfy a structural check. Static type-checkers
    still enforce Protocol conformance the right way.
    """

    embedding_dim: int

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int = 32,
    ) -> NDArray[np.float32]:
        """Encode ``texts`` into a unit-norm float32 matrix.

        Parameters
        ----------
        texts
            Input strings. May be empty.
        batch_size
            Hint for the underlying implementation. Mock encoders are
            free to ignore it; the production encoder forwards it to
            :meth:`sentence_transformers.SentenceTransformer.encode`.

        Returns
        -------
        ndarray
            Shape ``(len(texts), embedding_dim)``, dtype
            ``float32``, every row L2-normalised.
        """
        ...


def _l2_normalise(matrix: NDArray[np.float32]) -> NDArray[np.float32]:
    """Return ``matrix`` with every row L2-normalised to unit length.

    Rows that are exactly zero are left as zero (instead of producing
    NaN). Zero rows can only appear from the production encoder if a
    pathological input snuck through; we surface that as a structured
    log line rather than crashing the pipeline.
    """
    if matrix.size == 0:
        return matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    zero_rows = int(np.sum(norms == 0))
    if zero_rows:
        logger.warning(
            "encoder.zero_norm_rows",
            count=zero_rows,
            total=matrix.shape[0],
        )
    # Avoid divide-by-zero — replace zero norms with 1 so the zero
    # rows stay zero rather than turning into NaN.
    safe_norms = np.where(norms == 0, np.float32(1.0), norms)
    return (matrix / safe_norms).astype(np.float32, copy=False)


# ---------------------------------------------------------------------------
# MockEncoder
# ---------------------------------------------------------------------------


class MockEncoder:
    """Deterministic, dependency-free encoder for the fast test suite.

    Embeddings are derived from a BLAKE2b cryptographic hash of each
    input string. The hash output is interpreted as a sequence of
    big-endian 32-bit unsigned integers, mapped to ``[-1.0, 1.0]``,
    centred around zero (subtract the row mean), and L2-normalised.
    Two ``MockEncoder`` instances constructed with the same
    ``embedding_dim`` always produce identical output for the same
    input across runs and across Python processes.

    Picklable, thread-safe (no shared state), and zero heavy imports.

    Important — the mock encoder does **not** preserve semantic
    similarity. Two strings that mean the same thing will produce
    vectors with no particular relationship; the mock exists to test
    the *plumbing* (shape, ordering, normalisation, retrieval logic),
    not the *quality*. Tests that need semantic similarity must use
    :class:`SentenceTransformerEncoder` and are gated behind
    ``@pytest.mark.slow``.
    """

    def __init__(self, embedding_dim: int = DEFAULT_MOCK_DIM) -> None:
        if embedding_dim < 1:
            raise ValueError(
                f"embedding_dim must be >= 1, got {embedding_dim}"
            )
        self.embedding_dim = embedding_dim

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int = 32,
    ) -> NDArray[np.float32]:
        """Hash → centre → L2-normalise. Order-preserving.

        ``batch_size`` is accepted for Protocol compatibility but
        ignored — :class:`MockEncoder` does no batching.
        """
        _ = batch_size  # explicit "ignored" — keeps ruff happy without a noqa
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)

        rows = [self._hash_to_vector(t) for t in texts]
        matrix = np.vstack(rows).astype(np.float32, copy=False)
        return _l2_normalise(matrix)

    def _hash_to_vector(self, text: str) -> NDArray[np.float32]:
        """Map one string deterministically to a centred float32 vector."""
        # BLAKE2b output size is bounded; pull enough bytes for
        # ``embedding_dim`` 4-byte ints. ``digest_size`` upper bound is
        # 64 — for embedding_dim > 16 we extend by concatenating
        # successive hashes with a counter suffix.
        bytes_needed = self.embedding_dim * 4
        buf = bytearray()
        counter = 0
        while len(buf) < bytes_needed:
            h = hashlib.blake2b(
                text.encode("utf-8") + counter.to_bytes(4, "big"),
                digest_size=64,
            )
            buf.extend(h.digest())
            counter += 1
        # Interpret as big-endian uint32s, project to [-1, 1].
        ints = np.frombuffer(
            bytes(buf[:bytes_needed]), dtype=">u4"
        ).astype(np.float64)
        # Map [0, 2^32 - 1] → [-1, 1].
        scaled = (ints / (2**31)) - 1.0
        # Centre so the resulting embeddings have non-trivial mean
        # geometry; otherwise all-positive vectors would collapse to
        # near-parallel after normalisation.
        centred = scaled - scaled.mean()
        # ``.astype`` returns ``Any`` under numpy's current stubs; cast
        # so the function signature is honoured under mypy --strict.
        return cast("NDArray[np.float32]", centred.astype(np.float32))

    def __repr__(self) -> str:
        return f"MockEncoder(embedding_dim={self.embedding_dim})"


# ---------------------------------------------------------------------------
# SentenceTransformerEncoder
# ---------------------------------------------------------------------------


class SentenceTransformerEncoder:
    """Production encoder wrapping :mod:`sentence_transformers`.

    The wrapper is intentionally thin — its job is to:

    * Hide the lazy-loading dance so consumers can ``new`` an encoder
      cheaply and pay the model-load cost only when they actually need
      embeddings.
    * Resolve ``device="auto"`` at first encode (rather than at
      import time, which would break consumers that never actually
      encode).
    * Guarantee L2-normalised float32 output regardless of the
      underlying model's defaults.
    * Apply a consistent global seed so successive encode calls under
      the same Python process are reproducible.

    Parameters
    ----------
    model_name
        HuggingFace identifier (e.g.
        ``"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"``).
    device
        ``"cpu"``, ``"cuda"`` or ``"auto"``. ``"auto"`` resolves to
        ``"cuda"`` if :func:`torch.cuda.is_available` returns True at
        first encode, else ``"cpu"``. The dev box and CI run on CPU.
    seed
        Global seed applied to ``torch.manual_seed`` and
        ``transformers.set_seed`` at first encode. Default mirrors the
        package-wide convention (D10 in ``DECISIONS.md``).
    """

    def __init__(
        self,
        model_name: str,
        device: str = "auto",
        *,
        seed: int = 42,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.seed = seed
        self._model: SentenceTransformer | None = None
        self._resolved_device: str | None = None
        self._embedding_dim: int | None = None

    # ------------------------------------------------------------------
    # Public Protocol surface
    # ------------------------------------------------------------------

    @property
    def embedding_dim(self) -> int:
        """Dimensionality of the encoder's output vectors.

        Lazy-loads the model if it has not been loaded yet — there is
        no cheap way to know the dim of an SBERT checkpoint without
        instantiating the model.
        """
        if self._embedding_dim is None:
            self._lazy_load()
        # ``_lazy_load`` populates ``_embedding_dim`` unconditionally.
        assert self._embedding_dim is not None
        return self._embedding_dim

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int = 32,
    ) -> NDArray[np.float32]:
        """Encode ``texts`` and return a unit-norm float32 matrix."""
        if not texts:
            # Need the dim — triggers lazy load if not already done.
            return np.zeros((0, self.embedding_dim), dtype=np.float32)

        if self._model is None:
            self._lazy_load()
        assert self._model is not None  # for the type checker

        raw: Any = self._model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        matrix = np.asarray(raw, dtype=np.float32)
        if matrix.ndim != 2:
            raise RuntimeError(
                "SentenceTransformer.encode returned an array of "
                f"shape {matrix.shape}; expected 2D."
            )
        return _l2_normalise(matrix)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _lazy_load(self) -> None:
        """Load the SBERT model on demand. Idempotent."""
        if self._model is not None:
            return

        # Import inside the method so module-level imports of
        # :mod:`skill_matcher.encoder` do not pull torch.
        import torch
        from sentence_transformers import SentenceTransformer
        from transformers import set_seed as hf_set_seed

        resolved = self._resolve_device(self.device)
        logger.info(
            "encoder.loading",
            model_name=self.model_name,
            requested_device=self.device,
            resolved_device=resolved,
            seed=self.seed,
        )

        # Apply seeds before model construction so any internal random
        # initialisation (rare for pretrained checkpoints, but defensive)
        # is reproducible.
        torch.manual_seed(self.seed)
        hf_set_seed(self.seed)

        model = SentenceTransformer(self.model_name, device=resolved)
        # ``get_sentence_embedding_dimension`` returns ``Optional[int]``
        # per the SentenceTransformer stubs (None when the underlying
        # transformer module is non-standard). Every sentence-transformer
        # checkpoint we use returns an int; defend the None case anyway
        # so a future swap fails loud instead of producing ``int(None)``.
        raw_dim = model.get_sentence_embedding_dimension()
        if raw_dim is None:
            raise RuntimeError(
                f"SentenceTransformer({self.model_name!r}) reported no "
                "embedding dimension. The model wrapper is incompatible."
            )
        dim: int = int(raw_dim)

        self._model = model
        self._resolved_device = resolved
        self._embedding_dim = dim

        logger.info(
            "encoder.loaded",
            model_name=self.model_name,
            embedding_dim=dim,
            device=resolved,
        )

    @staticmethod
    def _resolve_device(requested: str) -> str:
        """Translate ``"auto"`` to ``"cuda"`` if available, else ``"cpu"``.

        ``"cpu"`` and ``"cuda"`` pass through unchanged. Any other
        value is rejected explicitly so a typo in configuration fails
        loud instead of silently CPU-falling.
        """
        if requested == "auto":
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        if requested in {"cpu", "cuda"}:
            return requested
        raise ValueError(
            f"Unknown device {requested!r}; expected 'cpu', 'cuda' or 'auto'."
        )

    def __repr__(self) -> str:
        loaded = self._model is not None
        return (
            f"SentenceTransformerEncoder(model_name={self.model_name!r}, "
            f"device={self.device!r}, loaded={loaded})"
        )


__all__ = [
    "DEFAULT_MOCK_DIM",
    "Encoder",
    "MockEncoder",
    "SentenceTransformerEncoder",
]
