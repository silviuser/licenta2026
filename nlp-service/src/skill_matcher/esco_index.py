"""ESCO embedding index for semantic skill retrieval.

The :class:`EscoIndex` holds L2-normalised embeddings for every
ESCO concept (plus the custom-concept overlay) keyed by URI. Cosine
similarity reduces to a dot product because the index and the query
are both unit-norm. Used by:

* Step 4's zero-shot baseline (sliding-window expansion over CV text).
* Step 6's :class:`Linker` for re-scoring + retrieval (TBD).
* Step 7's :class:`Scorer` for JD-side requirement matching (TBD).

Build → persist → reload contract
---------------------------------
``build(concepts)`` encodes every concept once. The text fed to the
encoder is one of three formats locked by the concept-text ablation
(see :class:`ConceptTextFormat`). The result is L2-normalised,
stored as :class:`numpy.ndarray` of dtype ``float32`` and shape
``(n_concepts, embedding_dim)``, with a parallel URI list ordered by
URI.

``save(path)`` persists the matrix + URIs to ``path`` as a single
``.npz`` archive and writes a JSON sidecar at ``path.with_suffix('.json')``
carrying provenance — model identifier, ESCO source hash, dimension,
build timestamp, concept-text format. ``load(path)`` validates the
sidecar against the current encoder identity so a stale cache cannot
silently produce wrong-shaped embeddings.

Cache key layout (locked at Step 4 Pre-Flight)
----------------------------------------------
Filenames live under :attr:`SkillMatcherConfig.embedding_cache_dir`::

    esco_{model_sha12}_{esco_sha12}_{format_tag}.npz
    esco_{model_sha12}_{esco_sha12}_{format_tag}.json   # sidecar

``model_sha12``  = first 12 hex chars of ``sha256(model_name + finetuned_model_path)``.
``esco_sha12``   = output of :func:`skill_matcher.esco_loader.compute_esco_file_sha`.
``format_tag``   = ``"bounded-a"`` / ``"b"`` / ``"c"`` per the ablation.

Any change to the model, fine-tuned checkpoint, ESCO source files, or
concept-text format produces a new filename and forces a cold rebuild.
The sidecar additionally records the same fields so a manually-renamed
or partially-corrupted cache fails loud rather than silent.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import structlog
from numpy.typing import NDArray

from skill_matcher.encoder import Encoder
from skill_matcher.esco_loader import EscoConcept

logger = structlog.get_logger(__name__)


ConceptTextFormat = Literal["bounded-a", "b", "c"]
"""Concept-text format selector for indexing.

* ``"bounded-a"`` — ``label. <up to 5 sorted altLabels>. description[:300]``.
  Default; locks deterministic altLabel ordering and bounds the
  contribution of long descriptions.
* ``"b"`` — ``label. description``. Drops altLabels entirely; tests
  whether altLabels are noise or signal.
* ``"c"`` — ``label. <up to 3 altLabels>. description[:300]``. Looser
  altLabel cap than bounded-(a); tests sensitivity to the altLabel
  budget.

The headline baseline uses the format with the highest macro-F1 from
the Step 4 concept-text ablation. The chosen format is recorded as a
``DECISIONS.md`` amendment-log row.
"""


# Maximum description length carried into the concept text for the
# "bounded" formats. Empirically chosen to keep mean concept-text length
# inside the sentence-transformer's 256-token window for the
# multilingual MiniLM checkpoint, with margin.
_DESCRIPTION_TRUNCATION_CHARS = 300


class EscoIndexCacheError(RuntimeError):
    """Raised when a cached index cannot be safely loaded.

    Covers all integrity failures: missing ``.npz``, missing sidecar,
    sidecar/encoder identity mismatch, sidecar/format mismatch, shape
    inconsistency between matrix and URI list. Always log + raise —
    silent fallbacks are forbidden because they could ship wrong
    embeddings into the rest of the pipeline.
    """


# ---------------------------------------------------------------------------
# Concept-text formatting
# ---------------------------------------------------------------------------


def format_concept_text(concept: EscoConcept, fmt: ConceptTextFormat) -> str:
    """Render a concept as the text string fed to the encoder.

    The choice of format is the single biggest lever on baseline
    quality (Q3 in the Step 4 Pre-Flight). Locked formats:
    ``"bounded-a"`` (default), ``"b"``, ``"c"``.
    """
    label = concept.pref_label.strip()
    description = (concept.description or "").strip()
    alts = list(concept.alt_labels)

    if fmt == "bounded-a":
        # Sorted lexically for determinism; first 5 only.
        chosen = sorted(alts)[:5]
        return _join_concept_parts(label, chosen, description[:_DESCRIPTION_TRUNCATION_CHARS])
    if fmt == "b":
        return _join_concept_parts(label, [], description)
    if fmt == "c":
        chosen = list(alts)[:3]
        return _join_concept_parts(label, chosen, description[:_DESCRIPTION_TRUNCATION_CHARS])

    # Defensive — Literal narrowing should catch this at type-check time.
    raise ValueError(f"Unknown concept-text format {fmt!r}")  # pragma: no cover


def _join_concept_parts(
    label: str, alt_labels: list[str], description: str
) -> str:
    """Stitch label + alt-labels + description into a single sentence-ish string."""
    parts = [label]
    if alt_labels:
        parts.append(". ".join(alt_labels))
    if description:
        parts.append(description)
    return ". ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Cache key helpers
# ---------------------------------------------------------------------------


def compute_model_sha(
    *, model_name: str, finetuned_model_path: Path | None
) -> str:
    """First 12 hex chars of ``sha256(model_name + finetuned_path)``.

    Mirrors the SHA-12 prefix convention used by Module 2's
    :func:`skill_extractor.esco.cache.compute_esco_hash`. Combined with
    the ESCO file SHA into the cache filename so the cache is
    invalidated automatically when the model swaps to a Step 5 fine-
    tuned checkpoint.
    """
    payload = model_name.encode("utf-8")
    if finetuned_model_path is not None:
        payload += b"\x1f" + str(finetuned_model_path).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def cache_filename(
    *,
    model_sha: str,
    esco_sha: str,
    fmt: ConceptTextFormat,
    suffix: str = ".npz",
) -> str:
    """Deterministic cache filename. ``suffix`` toggles ``.npz`` vs ``.json``."""
    return f"esco_{model_sha}_{esco_sha}_{fmt}{suffix}"


# ---------------------------------------------------------------------------
# EscoIndex
# ---------------------------------------------------------------------------


@dataclass
class _SidecarMetadata:
    """The provenance record persisted alongside the .npz embedding matrix."""

    model_name: str
    finetuned_model_path: str | None
    model_sha: str
    esco_sha: str
    embedding_dim: int
    n_concepts: int
    concept_text_format: ConceptTextFormat
    build_timestamp_utc: str
    skill_matcher_version: str

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> _SidecarMetadata:
        return cls(**json.loads(text))


class EscoIndex:
    """Embedding index over ESCO + custom concepts.

    Construction is cheap — no encoding happens until
    :meth:`build` or :meth:`load` is called. The index is therefore
    safe to instantiate at process start without paying the cost of
    loading the encoder.
    """

    def __init__(
        self,
        encoder: Encoder,
        cache_dir: Path,
    ) -> None:
        self.encoder = encoder
        self.cache_dir = cache_dir
        self._matrix: NDArray[np.float32] | None = None
        self._uris: list[str] = []
        self._concept_text_format: ConceptTextFormat | None = None
        self._embedding_dim: int | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def n_concepts(self) -> int:
        """Number of concepts indexed. Zero before :meth:`build`/:meth:`load`."""
        if self._matrix is None:
            return 0
        return int(self._matrix.shape[0])

    @property
    def embedding_dim(self) -> int:
        """Output dimensionality of the underlying encoder."""
        if self._embedding_dim is None:
            self._embedding_dim = self.encoder.embedding_dim
        return self._embedding_dim

    @property
    def is_built(self) -> bool:
        """``True`` iff :meth:`build` or :meth:`load` has populated the index."""
        return self._matrix is not None

    @property
    def concept_text_format(self) -> ConceptTextFormat | None:
        """The text-format flag this index was built with (or ``None``)."""
        return self._concept_text_format

    @property
    def uris(self) -> list[str]:
        """The ordered URI list backing the matrix rows.

        Returned as a shallow copy so callers cannot accidentally
        mutate the index's invariants.
        """
        return list(self._uris)

    # ------------------------------------------------------------------
    # Build / save / load
    # ------------------------------------------------------------------

    def build(
        self,
        concepts: list[EscoConcept],
        *,
        fmt: ConceptTextFormat = "bounded-a",
        batch_size: int = 64,
    ) -> None:
        """Encode ``concepts`` and replace any previously built matrix.

        Concept ordering inside the matrix follows the input order —
        :func:`skill_matcher.esco_loader.load_esco_concepts` already
        sorts by URI for determinism, so callers normally do not need
        to sort again.

        ``fmt`` selects the concept-text format; the default
        ``"bounded-a"`` is the Step 4 baseline before the ablation
        picks a winner.
        """
        if not concepts:
            raise ValueError("Cannot build an index from an empty concept list.")

        texts = [format_concept_text(c, fmt) for c in concepts]
        logger.info(
            "esco_index.build.start",
            n_concepts=len(concepts),
            concept_text_format=fmt,
            batch_size=batch_size,
        )
        matrix = self.encoder.encode(texts, batch_size=batch_size)

        if matrix.shape[0] != len(concepts):
            raise RuntimeError(
                f"Encoder returned {matrix.shape[0]} rows for "
                f"{len(concepts)} concepts."
            )

        # The encoder Protocol guarantees L2-normalised output, but
        # assert defensively — a silently un-normalised matrix would
        # turn cosine similarity into raw dot product and tank metrics.
        norms = np.linalg.norm(matrix, axis=1)
        if not np.allclose(norms, 1.0, atol=1e-4):
            max_dev = float(np.max(np.abs(norms - 1.0)))
            raise RuntimeError(
                "Encoder violated the L2-normalisation contract; max "
                f"row-norm deviation from 1.0 = {max_dev:.6f}."
            )

        self._matrix = matrix.astype(np.float32, copy=False)
        self._uris = [c.uri for c in concepts]
        self._concept_text_format = fmt
        self._embedding_dim = int(matrix.shape[1])

        logger.info(
            "esco_index.build.complete",
            n_concepts=self.n_concepts,
            embedding_dim=self.embedding_dim,
            concept_text_format=fmt,
        )

    def save(
        self,
        path: Path,
        *,
        esco_sha: str,
        skill_matcher_version: str,
    ) -> None:
        """Persist the index to ``path`` (a ``.npz``) + a JSON sidecar.

        The sidecar is written *after* the ``.npz`` succeeds, so a
        partial write cannot leave behind metadata that points at a
        broken matrix.
        """
        if self._matrix is None or self._concept_text_format is None:
            raise RuntimeError(
                "Cannot save an unbuilt index; call build() first."
            )

        path = path.with_suffix(".npz")
        sidecar_path = path.with_suffix(".json")
        path.parent.mkdir(parents=True, exist_ok=True)

        # Persist matrix + URI list. ``np.savez_compressed`` shrinks
        # the float32 matrix by ~30% which matters when 13.5k concepts
        # x 384 dims is ~21 MB raw.
        np.savez_compressed(
            path,
            matrix=self._matrix,
            uris=np.array(self._uris, dtype=object),
        )

        sidecar = _SidecarMetadata(
            model_name=self._resolve_model_name(),
            finetuned_model_path=self._resolve_finetuned_path(),
            model_sha=compute_model_sha(
                model_name=self._resolve_model_name(),
                finetuned_model_path=(
                    Path(p) if (p := self._resolve_finetuned_path()) else None
                ),
            ),
            esco_sha=esco_sha,
            embedding_dim=self.embedding_dim,
            n_concepts=self.n_concepts,
            concept_text_format=self._concept_text_format,
            build_timestamp_utc=dt.datetime.now(tz=dt.UTC).isoformat(),
            skill_matcher_version=skill_matcher_version,
        )
        sidecar_path.write_text(sidecar.to_json(), encoding="utf-8")

        logger.info(
            "esco_index.saved",
            npz_path=str(path),
            sidecar_path=str(sidecar_path),
            n_concepts=self.n_concepts,
            bytes=path.stat().st_size,
        )

    def load(
        self,
        path: Path,
        *,
        expected_esco_sha: str | None = None,
        expected_format: ConceptTextFormat | None = None,
    ) -> None:
        """Load matrix + URIs from ``path``. Validates the sidecar.

        Raises :class:`EscoIndexCacheError` on any integrity issue so
        callers cannot accidentally use a stale index.

        Parameters
        ----------
        path
            ``.npz`` path. The sidecar is read from
            ``path.with_suffix('.json')``.
        expected_esco_sha
            If set, the sidecar's ``esco_sha`` must match. Mismatch
            means the ESCO source files have changed since the cache
            was built; rebuild.
        expected_format
            If set, the sidecar's ``concept_text_format`` must match.
            Mismatch means the caller asked for a different
            concept-text format; rebuild.
        """
        path = path.with_suffix(".npz")
        sidecar_path = path.with_suffix(".json")
        if not path.exists():
            raise EscoIndexCacheError(f"Index file not found: {path}")
        if not sidecar_path.exists():
            raise EscoIndexCacheError(
                f"Sidecar not found: {sidecar_path}. Cache integrity "
                "cannot be validated; rebuild."
            )

        sidecar = _SidecarMetadata.from_json(
            sidecar_path.read_text(encoding="utf-8")
        )

        # Validate encoder identity. The encoder's model name decides
        # the matrix's semantics; loading with a different encoder
        # would silently produce wrong-shaped similarities.
        expected_model_sha = compute_model_sha(
            model_name=self._resolve_model_name(),
            finetuned_model_path=(
                Path(p) if (p := self._resolve_finetuned_path()) else None
            ),
        )
        if sidecar.model_sha != expected_model_sha:
            raise EscoIndexCacheError(
                f"Sidecar model_sha {sidecar.model_sha!r} does not "
                f"match encoder model_sha {expected_model_sha!r}. "
                "The cache was built with a different model — rebuild."
            )

        if expected_esco_sha is not None and sidecar.esco_sha != expected_esco_sha:
            raise EscoIndexCacheError(
                f"Sidecar esco_sha {sidecar.esco_sha!r} does not match "
                f"expected {expected_esco_sha!r}. Source ESCO has "
                "changed — rebuild."
            )

        if (
            expected_format is not None
            and sidecar.concept_text_format != expected_format
        ):
            raise EscoIndexCacheError(
                f"Sidecar concept_text_format {sidecar.concept_text_format!r} "
                f"does not match expected {expected_format!r} — rebuild."
            )

        with np.load(path, allow_pickle=True) as data:
            matrix = data["matrix"].astype(np.float32, copy=False)
            uri_arr = data["uris"]

        if matrix.shape[0] != uri_arr.shape[0]:
            raise EscoIndexCacheError(
                f"Cache integrity error: matrix has {matrix.shape[0]} "
                f"rows but uris has {uri_arr.shape[0]}."
            )
        if int(matrix.shape[1]) != sidecar.embedding_dim:
            raise EscoIndexCacheError(
                f"Cache integrity error: matrix dim {matrix.shape[1]} "
                f"does not match sidecar dim {sidecar.embedding_dim}."
            )

        self._matrix = matrix
        self._uris = [str(u) for u in uri_arr.tolist()]
        self._concept_text_format = sidecar.concept_text_format
        self._embedding_dim = int(sidecar.embedding_dim)

        logger.info(
            "esco_index.loaded",
            npz_path=str(path),
            n_concepts=self.n_concepts,
            concept_text_format=self._concept_text_format,
        )

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(
        self,
        query_embedding: NDArray[np.float32] | list[float],
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        """Return the ``top_k`` ``(uri, cosine_similarity)`` pairs.

        Both the index matrix and the query embedding are
        L2-normalised, so cosine similarity is exactly a dot product.
        Results are sorted descending by similarity. ``top_k`` is
        clamped to :attr:`n_concepts` so callers do not need to know
        the index size.
        """
        if self._matrix is None:
            raise RuntimeError(
                "Cannot query an unbuilt index; call build() or load() first."
            )
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")

        query_arr = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
        if query_arr.shape[0] != self.embedding_dim:
            raise ValueError(
                f"Query has dim {query_arr.shape[0]}, expected "
                f"{self.embedding_dim}."
            )

        sims = self._matrix @ query_arr
        k = min(top_k, self.n_concepts)
        # ``argpartition`` is O(N), then we sort only the top-k subset.
        top_idx = np.argpartition(-sims, k - 1)[:k]
        top_idx_sorted = top_idx[np.argsort(-sims[top_idx])]
        return [
            (self._uris[int(i)], float(sims[int(i)])) for i in top_idx_sorted
        ]

    def query_batch(
        self,
        query_embeddings: NDArray[np.float32],
        top_k: int = 5,
    ) -> list[list[tuple[str, float]]]:
        """Batched version of :meth:`query` for sliding-window expansion.

        Computes the full ``(M, N)`` similarity matrix in one BLAS
        call -- vectorised, but ``M * N`` memory. For the eval corpus
        (~50 windows per CV * 13.5k concepts = 675k cells * 4 bytes
        ~= 2.7 MB per CV) this is well within budget.
        """
        if self._matrix is None:
            raise RuntimeError(
                "Cannot query an unbuilt index; call build() or load() first."
            )
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")

        queries = np.asarray(query_embeddings, dtype=np.float32)
        if queries.ndim == 1:
            queries = queries.reshape(1, -1)
        if queries.shape[1] != self.embedding_dim:
            raise ValueError(
                f"Query matrix has dim {queries.shape[1]}, expected "
                f"{self.embedding_dim}."
            )

        sim_matrix = queries @ self._matrix.T  # shape (M, N)
        k = min(top_k, self.n_concepts)

        results: list[list[tuple[str, float]]] = []
        for row in sim_matrix:
            top_idx = np.argpartition(-row, k - 1)[:k]
            top_idx_sorted = top_idx[np.argsort(-row[top_idx])]
            results.append(
                [(self._uris[int(i)], float(row[int(i)])) for i in top_idx_sorted]
            )
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_model_name(self) -> str:
        """Pull the model name off the encoder for sidecar / cache-key use."""
        # ``SentenceTransformerEncoder`` has a public ``model_name``.
        # ``MockEncoder`` and other Protocol implementers should expose
        # a usable identity; if they don't, fall back to the class name
        # (mock tests don't care about cross-process cache invariants).
        name = getattr(self.encoder, "model_name", None)
        if isinstance(name, str) and name:
            return name
        return type(self.encoder).__name__

    def _resolve_finetuned_path(self) -> str | None:
        """Pull the optional fine-tuned-checkpoint path off the encoder."""
        # ``SentenceTransformerEncoder`` does not currently track a
        # finetuned path on the instance — it is set via the
        # ``model_name`` argument. Future Step 5 work may add one;
        # the field exists in :class:`SkillMatcherConfig` already.
        path = getattr(self.encoder, "finetuned_model_path", None)
        return str(path) if path else None


# Re-export for convenience: callers building an index from production
# config can construct the encoder + index in one line.
def build_index_for_config(
    *,
    encoder: Encoder,
    cache_dir: Path,
    concepts: list[EscoConcept],
    fmt: ConceptTextFormat = "bounded-a",
    batch_size: int = 64,
) -> EscoIndex:
    """Convenience constructor: build a fresh in-memory index."""
    index = EscoIndex(encoder=encoder, cache_dir=cache_dir)
    index.build(concepts, fmt=fmt, batch_size=batch_size)
    return index


__all__ = [
    "ConceptTextFormat",
    "EscoIndex",
    "EscoIndexCacheError",
    "build_index_for_config",
    "cache_filename",
    "compute_model_sha",
    "format_concept_text",
]
