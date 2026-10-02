"""Top-level orchestrator for Module 3.

The :class:`SkillMatcher` ties together the encoder, ESCO index,
:class:`~skill_matcher.linker.Linker` and (from Step 7) the Scorer.
End-to-end usage::

    from cv_extractor import ExtractionPipeline
    from skill_extractor import SkillExtractor
    from skill_matcher import SkillMatcher

    extraction = ExtractionPipeline().process(Path("cv.pdf"))
    lexical = SkillExtractor().extract(extraction)
    matcher = SkillMatcher()
    enriched = matcher.link(cv_id="alice", cv_text=extraction.text,
                            lexical=lexical)
    result = matcher.match(enriched=enriched, jd_id="role-42",
                           requirements=jd_requirements)  # Step 7

Lazy loading
------------
The encoder, ESCO index and concept lookup are constructed on the
first :meth:`link` call -- importing :class:`SkillMatcher` is cheap.
Subsequent calls reuse the already-loaded components. This pattern
mirrors :class:`~skill_matcher.encoder.SentenceTransformerEncoder`'s
own deferred model load and means scripts that only build a
:class:`SkillMatcher` (e.g. for config validation) do not pay for
torch + 500 MB of model weights.

Model-path resolution
---------------------
Three-tier fallback, in this order:

1. ``config.finetuned_model_path`` -- explicit override.
2. ``models/skill_matcher/latest.txt`` -- single-line pointer to the
   most recent imported fine-tuned run directory.
3. ``config.base_model`` -- zero-shot fallback.

The resolved path is logged via structlog at INFO level so the
evaluation report can tell which encoder produced the numbers.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog

from skill_matcher.config import SkillMatcherConfig
from skill_matcher.encoder import Encoder, SentenceTransformerEncoder
from skill_matcher.esco_index import (
    EscoIndex,
    EscoIndexCacheError,
    cache_filename,
    compute_model_sha,
)
from skill_matcher.esco_loader import (
    EscoConcept,
    compute_esco_sha,
    load_esco_concepts,
)
from skill_matcher.linker import Linker
from skill_matcher.scorer import Scorer

if TYPE_CHECKING:
    from skill_extractor.models import SkillExtractionResult
    from skill_matcher.models import (
        EnrichedSkillResult,
        JDRequirement,
        MatchResult,
    )

logger = structlog.get_logger(__name__)


_LATEST_POINTER_FILENAME = "latest.txt"


class SkillMatcher:
    """End-to-end Module 3 orchestrator.

    Constructed eagerly with a :class:`SkillMatcherConfig`; the heavy
    components (encoder, ESCO index, concept map, Linker) are
    constructed lazily on the first :meth:`link` call. Thread-safety
    is not provided -- callers that need it should serialise access or
    construct one ``SkillMatcher`` per worker.

    Step 6: ``link()`` is implemented. ``match()`` raises until Step 7.
    """

    def __init__(self, config: SkillMatcherConfig | None = None) -> None:
        self.config: SkillMatcherConfig = (
            config if config is not None else SkillMatcherConfig()
        )
        self._encoder: Encoder | None = None
        self._index: EscoIndex | None = None
        self._concepts_by_uri: dict[str, EscoConcept] | None = None
        self._linker: Linker | None = None
        self._scorer: Scorer | None = None
        self._resolved_model_name: str | None = None

    # ------------------------------------------------------------------
    # Phase A -- skill linking
    # ------------------------------------------------------------------

    def link(
        self,
        cv_id: str,
        cv_text: str,
        lexical: SkillExtractionResult,
    ) -> EnrichedSkillResult:
        """Run Phase A -- semantic re-scoring + expansion.

        Lazy-loads encoder / index / concepts on first call. Drops the
        :class:`~skill_matcher.linker.LinkerStats` from the return
        signature (the caller can pick it up via the structlog INFO
        line if needed); the public API surface stays one
        :class:`EnrichedSkillResult`.
        """
        self._ensure_ready()
        # `_ensure_ready` populates `_linker` unconditionally; assert
        # so mypy narrows the optional.
        assert self._linker is not None
        result, stats = self._linker.link(cv_id, cv_text, lexical)
        logger.info(
            "skill_matcher.link",
            cv_id=cv_id,
            encoder=self._resolved_model_name,
            **dataclasses.asdict(stats),
        )
        return result

    # ------------------------------------------------------------------
    # Phase B -- CV <-> JD scoring (Step 7)
    # ------------------------------------------------------------------

    def match(
        self,
        enriched: EnrichedSkillResult,
        jd_id: str,
        requirements: list[JDRequirement],
    ) -> MatchResult:
        """Run Phase B -- CV <-> JD scoring (Step 7 deliverable).

        Lazy-loads the heavy components on the first call (or piggy-
        backs on the Linker's load if :meth:`link` ran first); the
        :class:`~skill_matcher.scorer.Scorer` is constructed once and
        reused across subsequent ``match()`` calls.

        Parameters
        ----------
        enriched
            One CV's Linker output. Typically the return value of
            ``self.link(...)``.
        jd_id
            Stable identifier for the JD this requirement set describes.
        requirements
            JD requirements list. Treated as immutable; the Scorer
            produces resolved copies internally without mutating the
            caller's list.

        Returns
        -------
        MatchResult
            ``overall_score`` is the single number for the recruiter
            UI; the rest of the fields drive per-requirement views.
        """
        self._ensure_ready()
        # ``_ensure_ready`` populates the encoder / index / concept map
        # unconditionally; assert so mypy narrows the optionals.
        assert self._encoder is not None
        assert self._index is not None
        assert self._concepts_by_uri is not None

        if self._scorer is None:
            self._scorer = Scorer(
                config=self.config,
                encoder=self._encoder,
                index=self._index,
                concepts_by_uri=self._concepts_by_uri,
            )

        result, stats = self._scorer.score(
            enriched=enriched,
            jd_id=jd_id,
            requirements=requirements,
        )
        logger.info(
            "skill_matcher.match",
            cv_id=enriched.cv_id,
            jd_id=jd_id,
            encoder=self._resolved_model_name,
            overall_score=result.overall_score,
            **dataclasses.asdict(stats),
        )
        return result

    # ------------------------------------------------------------------
    # Lazy-load plumbing (private)
    # ------------------------------------------------------------------

    def _ensure_ready(self) -> None:
        """Build encoder + index + concepts + Linker on first call.

        Idempotent: subsequent calls are O(1). All four references go
        from ``None`` to populated atomically -- there is no partial
        state for the caller to observe.
        """
        if self._linker is not None:
            return

        # 1. Resolve model path and build the encoder.
        model_name = self._resolve_model_path()
        logger.info(
            "skill_matcher.ensure_ready.resolving",
            model_name=model_name,
        )
        encoder = SentenceTransformerEncoder(
            model_name=model_name,
            device=self.config.device,
            seed=self.config.seed,
        )

        # 2. Load ESCO concepts (Module 2's loader). Source of truth
        #    for the concept-text builder + the index keys.
        concepts = load_esco_concepts()
        concepts_by_uri: dict[str, EscoConcept] = {c.uri: c for c in concepts}
        esco_sha = compute_esco_sha(concepts)

        # 3. Get-or-build the ESCO embedding index.
        #    The cast bridges a tiny Protocol/property gap: the
        #    ``Encoder`` Protocol declares ``embedding_dim: int`` as a
        #    settable attribute, while ``SentenceTransformerEncoder``
        #    exposes it via ``@property``. Read access is identical so
        #    the cast is sound; the explicit form keeps mypy quiet.
        encoder_as_proto = cast("Encoder", encoder)
        index = self._get_or_build_index(encoder_as_proto, concepts, esco_sha)

        # 4. Construct the Linker.
        linker = Linker(
            config=self.config,
            encoder=encoder_as_proto,
            index=index,
            concepts_by_uri=concepts_by_uri,
        )

        # 5. Commit. Single assignment block keeps state consistent.
        self._encoder = encoder_as_proto
        self._index = index
        self._concepts_by_uri = concepts_by_uri
        self._linker = linker
        self._resolved_model_name = model_name

        logger.info(
            "skill_matcher.ready",
            encoder=model_name,
            n_concepts=len(concepts),
            esco_sha=esco_sha[:12],
            keep_threshold=self.config.keep_threshold,
            drop_threshold=self.config.drop_threshold,
            expansion_threshold=self.config.expansion_threshold,
            enable_expansion=self.config.enable_expansion,
        )

    def _resolve_model_path(self) -> str:
        """Three-tier model-path fallback. See module docstring.

        Returns the string passed to
        :class:`SentenceTransformerEncoder`. Local paths are returned
        as POSIX strings -- sentence-transformers accepts both
        HuggingFace IDs and local directories transparently.
        """
        cfg = self.config

        # Tier 1: explicit override.
        if cfg.finetuned_model_path is not None:
            path = Path(cfg.finetuned_model_path)
            if not path.exists():
                raise RuntimeError(
                    f"config.finetuned_model_path = {path!s} does not "
                    "exist. Either remove the override or import a "
                    "checkpoint via scripts/import_finetuned_model.py."
                )
            return str(path)

        # Tier 2: latest.txt pointer.
        pointer = cfg.models_dir / _LATEST_POINTER_FILENAME
        if pointer.exists():
            run_dir_name = pointer.read_text(encoding="utf-8").strip()
            if run_dir_name:
                run_dir = cfg.models_dir / run_dir_name
                if run_dir.is_dir():
                    return str(run_dir)
                logger.warning(
                    "skill_matcher.latest_pointer_invalid",
                    pointer=str(pointer),
                    target=str(run_dir),
                    reason="target directory missing",
                )

        # Tier 3: zero-shot base model.
        return cfg.base_model

    def _get_or_build_index(
        self,
        encoder: Encoder,
        concepts: list[EscoConcept],
        esco_sha: str,
    ) -> EscoIndex:
        """Load a cached ESCO index for this encoder, or build one cold.

        Cache key combines ``compute_model_sha`` (over the encoder's
        model name + finetuned path) and ``esco_sha`` so a stale
        cache cannot silently serve mismatched embeddings.
        """
        cfg = self.config
        cache_dir = cfg.embedding_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        model_name = getattr(encoder, "model_name", None) or type(
            encoder
        ).__name__
        finetuned_path = getattr(encoder, "finetuned_model_path", None)
        model_sha = compute_model_sha(
            model_name=str(model_name),
            finetuned_model_path=(
                Path(finetuned_path) if finetuned_path else None
            ),
        )
        cache_path = cache_dir / cache_filename(
            model_sha=model_sha,
            esco_sha=esco_sha,
            fmt="bounded-a",
        )

        index = EscoIndex(encoder=encoder, cache_dir=cache_dir)

        # Try cache first; rebuild on any integrity error.
        try:
            index.load(
                cache_path,
                expected_esco_sha=esco_sha,
                expected_format="bounded-a",
            )
            n_concepts = getattr(index, "n_concepts", None)
            logger.info(
                "skill_matcher.index.cache_hit",
                cache_path=str(cache_path),
                n_concepts=n_concepts,
            )
            return index
        except (FileNotFoundError, EscoIndexCacheError) as exc:
            logger.info(
                "skill_matcher.index.cold_build",
                cache_path=str(cache_path),
                reason=str(exc),
            )

        index.build(concepts, fmt="bounded-a", batch_size=64)
        from skill_matcher import __version__

        index.save(
            cache_path,
            esco_sha=esco_sha,
            skill_matcher_version=__version__,
        )
        return index


__all__ = ["SkillMatcher"]
