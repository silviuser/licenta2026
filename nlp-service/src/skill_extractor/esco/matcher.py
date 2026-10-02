"""Build a spaCy :class:`PhraseMatcher` over the ESCO skill set.

Given a list of :class:`~skill_extractor.models.EscoSkill` and a loaded
spaCy ``Language`` pipeline, :class:`EscoMatcherBuilder` produces a
ready-to-use :class:`BuiltMatcher` containing:

* the :class:`spacy.matcher.PhraseMatcher` itself;
* a ``label_map`` from match-key string to :class:`MatchMeta`,
  used at hit time to recover the ESCO URI / preferred label /
  whether the pattern was preferred or alt;
* the underlying :class:`Language` (kept on the bundle so callers don't
  have to thread it separately).

The builder integrates the on-disk :class:`MatcherDiskCache`: if a fresh
cache file exists for the current ``(language, esco-hash, attr)`` tuple,
patterns are restored from the serialised ``DocBin`` instead of being
re-tokenised.

Only the spaCy-touching code lives here; the cache module knows
nothing about spaCy and the loader module knows nothing about the
matcher. This separation is what allows fast unit tests for the
loader (no spaCy required) and the cache (no spaCy required either —
its tests pickle and unpickle dataclasses directly).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.esco.cache import (
    LabelKind,
    MatcherCachePayload,
    MatcherDiskCache,
    MatchMeta,
)
from skill_extractor.exceptions import SkillExtractorError
from skill_extractor.models import EscoSkill

if TYPE_CHECKING:  # pragma: no cover
    from spacy.language import Language
    from spacy.matcher import PhraseMatcher

logger = structlog.get_logger(__name__)

# Default attribute to match on.
#
# Historical note: this was ``"LEMMA"`` until 2026-05-17. The
# ``scripts/debug_oop_lemma.py`` diagnostic revealed that spaCy's POS
# tagger classifies standalone uppercase acronyms inconsistently when
# the matcher's pattern build path disables parser+ner (e.g. "OOP" is
# tagged as ADV with lemma "oop", while in CV context the same token
# is tagged as PROPN with lemma "OOP"). ``attribute_ruler`` then
# lower-cases the pattern lemma but preserves case on the text lemma,
# producing a silent ``LEMMA``-attr mismatch on every single-token
# uppercase acronym (OOP, API, CRUD seen as bare token, etc.).
#
# Switching to ``"LOWER"`` bypasses the lemmatiser entirely and matches
# on case-folded surface forms. Trade-off: loses morphological
# normalisation (e.g. pattern "designing databases" no longer matches
# text "design databases"); however, ESCO alt_labels already enumerate
# the most common inflected variants explicitly, and the validation
# corpus is dominated by canonical noun phrases. Net empirical gain:
# recovers the FN family of CV-frequent acronyms documented in
# reports/skill_extraction_validation_20260511.md (FN family #5).
DEFAULT_PHRASE_ATTR = "LOWER"


@dataclass(slots=True)
class BuiltMatcher:
    """Assembled artefacts ready to run against a CV ``Doc``.

    Attributes
    ----------
    matcher
        The :class:`spacy.matcher.PhraseMatcher` instance.
    label_map
        Match-key string → :class:`MatchMeta`. The match-key follows
        the convention ``"{concept_uri}|{label_kind}"``.
    nlp
        The :class:`spacy.language.Language` whose vocab the matcher is
        bound to. Stored so callers can tokenise CV text consistently.
    phrase_attr
        Which token attribute the matcher is keyed on
        (``"LEMMA"`` in production, ``"LOWER"`` in tests).
    """

    matcher: PhraseMatcher
    label_map: dict[str, MatchMeta]
    nlp: Language
    phrase_attr: str


class EscoMatcherBuilder:
    """Builds — or loads — a :class:`PhraseMatcher` over ESCO skills.

    A single builder instance is reusable across languages but is
    typically constructed once per :class:`~skill_extractor.pipeline.SkillExtractor`.

    Parameters
    ----------
    config
        Optional :class:`SkillExtractorConfig`. Used for the cache
        directory, filename template and (default) phrase attribute
        knobs only — the builder does not read paths from it directly.
    """

    def __init__(self, config: SkillExtractorConfig | None = None) -> None:
        self._config = config or SkillExtractorConfig()
        self._cache = MatcherDiskCache(
            cache_dir=self._config.cache_dir,
            filename_template=self._config.matcher_cache_filename_template,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_or_build(
        self,
        *,
        skills: list[EscoSkill],
        nlp: Language,
        esco_hash: str,
        phrase_attr: str = DEFAULT_PHRASE_ATTR,
        use_cache: bool = True,
    ) -> BuiltMatcher:
        """Return a built matcher, restoring from cache if possible.

        Parameters
        ----------
        skills
            Output of :class:`EscoLoader.load`.
        nlp
            A loaded spaCy :class:`Language`. Determines the language
            of the cache key.
        esco_hash
            SHA-256 prefix of the source ESCO files (use
            :func:`compute_esco_hash`). The matcher rebuilds whenever
            this changes.
        phrase_attr
            spaCy token attribute to match on. Production default is
            ``"LEMMA"``.
        use_cache
            Set to ``False`` to force a rebuild regardless of cache
            state — useful in tests and when investigating cache bugs.
        """
        # ``nlp.lang`` is typed as ``str | None`` upstream but always
        # carries a value at runtime; narrow it so the cache call type-
        # checks.
        if not nlp.lang:
            raise SkillExtractorError(
                "spaCy Language has no lang code; cannot key the cache."
            )
        lang: str = nlp.lang
        if use_cache:
            payload = self._cache.load(lang=lang, esco_hash=esco_hash)
            if (
                payload is not None
                and payload.spacy_model == nlp.meta.get("name", "")
                and payload.phrase_attr == phrase_attr
            ):
                return self._restore_from_cache(payload, nlp)
            elif payload is not None:
                logger.info(
                    "matcher_cache.invalidated_by_metadata",
                    cached_model=payload.spacy_model,
                    cached_attr=payload.phrase_attr,
                    requested_model=nlp.meta.get("name", ""),
                    requested_attr=phrase_attr,
                )

        built = self._build_fresh(skills=skills, nlp=nlp, phrase_attr=phrase_attr)

        if use_cache:
            try:
                payload = self._serialise(built, esco_hash=esco_hash)
                self._cache.save(payload)
            except Exception as exc:
                logger.warning(
                    "matcher_cache.save_failed", error=str(exc)
                )

        return built

    # ------------------------------------------------------------------
    # Build path
    # ------------------------------------------------------------------

    def _build_fresh(
        self,
        *,
        skills: list[EscoSkill],
        nlp: Language,
        phrase_attr: str,
    ) -> BuiltMatcher:
        """Tokenise every pattern and add it to a fresh PhraseMatcher."""
        from spacy.matcher import PhraseMatcher

        matcher = PhraseMatcher(nlp.vocab, attr=phrase_attr)
        label_map: dict[str, MatchMeta] = {}

        # Group patterns by match-key so we can `matcher.add()` in batches.
        # batches[key] = (MatchMeta, list[str])
        batches: dict[str, tuple[MatchMeta, list[str]]] = {}

        for skill in skills:
            preferred_key = self._make_key(skill.concept_uri, "preferred")
            alt_key = self._make_key(skill.concept_uri, "alt")

            preferred_meta = MatchMeta(
                concept_uri=skill.concept_uri,
                preferred_label=skill.preferred_label,
                label_kind="preferred",
                skill_type=skill.skill_type,
                surfaces={skill.preferred_label.lower()},
                is_custom=skill.is_custom,
            )
            label_map[preferred_key] = preferred_meta
            batches[preferred_key] = (preferred_meta, [skill.preferred_label])

            if skill.alt_labels:
                alt_meta = MatchMeta(
                    concept_uri=skill.concept_uri,
                    preferred_label=skill.preferred_label,
                    label_kind="alt",
                    skill_type=skill.skill_type,
                    surfaces={a.lower() for a in skill.alt_labels},
                    is_custom=skill.is_custom,
                )
                label_map[alt_key] = alt_meta
                batches[alt_key] = (alt_meta, list(skill.alt_labels))

        # Pattern tokenisation: we cannot use ``nlp.make_doc`` here
        # because it runs the *tokeniser only* and skips the
        # lemmatiser. ``attr="LEMMA"`` then refuses to add the
        # patterns ("E155: pipeline needs a lemmatizer"). We use
        # ``nlp.pipe`` and disable the components we don't need on
        # short pattern strings (parser + NER).
        #
        # Performance critical: make ONE batched ``nlp.pipe`` call
        # over a flat list of all ~30k patterns rather than calling
        # ``nlp.pipe`` per match-key. The per-call overhead of
        # ``select_pipes`` + pipeline setup dominates an
        # element-by-element loop and inflates build time from a few
        # seconds to several minutes on the Romanian model.
        flat_patterns: list[str] = []
        flat_keys: list[str] = []
        for key, (_meta, pattern_texts) in batches.items():
            for text in pattern_texts:
                flat_patterns.append(text)
                flat_keys.append(key)

        disabled_on_patterns = [
            name for name in nlp.pipe_names if name in ("parser", "ner")
        ]
        with nlp.select_pipes(disable=disabled_on_patterns):
            flat_docs = list(nlp.pipe(flat_patterns, batch_size=512))

        # Group the docs back per match-key and feed them in batches
        # to the matcher.
        grouped_docs: dict[str, list[Any]] = defaultdict(list)
        for doc, key in zip(flat_docs, flat_keys, strict=True):
            grouped_docs[key].append(doc)
        for key, docs in grouped_docs.items():
            matcher.add(key, docs)
        n_patterns = len(flat_docs)

        logger.info(
            "matcher.built",
            language=nlp.lang,
            phrase_attr=phrase_attr,
            skills=len(skills),
            patterns=n_patterns,
            keys=len(batches),
        )

        return BuiltMatcher(
            matcher=matcher,
            label_map=label_map,
            nlp=nlp,
            phrase_attr=phrase_attr,
        )

    # ------------------------------------------------------------------
    # Cache (de)serialisation
    # ------------------------------------------------------------------

    def _serialise(
        self,
        built: BuiltMatcher,
        *,
        esco_hash: str,
    ) -> MatcherCachePayload:
        """Convert a :class:`BuiltMatcher` into a picklable payload."""
        from spacy.tokens import DocBin

        # We re-tokenise here because the PhraseMatcher does not expose
        # the docs we already added to it. This is fine — _build_fresh
        # has already done the heavy lifting and these are warm tokens.
        docbin = DocBin(store_user_data=False)
        pattern_names: list[str] = []
        # Same reasoning as in ``_build_fresh``: we need the lemmatiser
        # to run so the cached docs carry LEMMA values when restored.
        # Same batching strategy — one big ``nlp.pipe`` over a flat
        # list of all patterns avoids the per-key overhead.
        flat_patterns: list[str] = []
        flat_keys: list[str] = []
        for key, meta in built.label_map.items():
            patterns = (
                [meta.preferred_label]
                if meta.label_kind == "preferred"
                else list(meta.surfaces)  # already lower-cased
            )
            for text in patterns:
                flat_patterns.append(text)
                flat_keys.append(key)
        disabled_on_patterns = [
            name
            for name in built.nlp.pipe_names
            if name in ("parser", "ner")
        ]
        with built.nlp.select_pipes(disable=disabled_on_patterns):
            for d in built.nlp.pipe(flat_patterns, batch_size=512):
                docbin.add(d)
        pattern_names = flat_keys

        # Narrow ``nlp.lang`` to ``str`` for the dataclass.
        lang: str = built.nlp.lang or ""
        return MatcherCachePayload(
            esco_hash=esco_hash,
            language=lang,
            spacy_model=built.nlp.meta.get("name", ""),
            phrase_attr=built.phrase_attr,
            docbin_bytes=docbin.to_bytes(),
            pattern_names=pattern_names,
            label_map=built.label_map,
        )

    @staticmethod
    def _restore_from_cache(
        payload: MatcherCachePayload,
        nlp: Language,
    ) -> BuiltMatcher:
        """Rebuild a matcher from cached docs without re-tokenising."""
        from spacy.matcher import PhraseMatcher
        from spacy.tokens import DocBin

        matcher = PhraseMatcher(nlp.vocab, attr=payload.phrase_attr)
        docbin = DocBin().from_bytes(payload.docbin_bytes)
        docs = list(docbin.get_docs(nlp.vocab))

        if len(docs) != len(payload.pattern_names):
            raise RuntimeError(
                "Matcher cache corrupted: "
                f"docbin has {len(docs)} docs but "
                f"{len(payload.pattern_names)} pattern names recorded."
            )

        # Group docs back by name so we can batch-add to the matcher.
        groups: dict[str, list[Any]] = defaultdict(list)
        for doc, name in zip(docs, payload.pattern_names, strict=True):
            groups[name].append(doc)
        for name, docs_list in groups.items():
            matcher.add(name, docs_list)

        logger.info(
            "matcher.restored_from_cache",
            language=nlp.lang,
            phrase_attr=payload.phrase_attr,
            patterns=len(docs),
            keys=len(groups),
        )
        return BuiltMatcher(
            matcher=matcher,
            label_map=payload.label_map,
            nlp=nlp,
            phrase_attr=payload.phrase_attr,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(concept_uri: str, label_kind: LabelKind) -> str:
        """Format a stable matcher key string."""
        return f"{concept_uri}|{label_kind}"


def compute_match_kind(
    *,
    surface: str,
    meta: MatchMeta,
) -> str:
    """Classify a hit as ``"exact"`` / ``"alt"`` / ``"lemma"``.

    Returns one of the values of
    :data:`skill_extractor.models.MatchKind`. Kept as a top-level
    helper because it's tested independently and called from the
    pipeline without needing access to the matcher itself.
    """
    if surface.lower() in meta.surfaces:
        return "exact" if meta.label_kind == "preferred" else "alt"
    return "lemma"
