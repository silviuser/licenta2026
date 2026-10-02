"""Skill-extraction pipeline orchestrator.

Architecture
------------
:class:`SkillExtractor` is the only public entry point of Module 2. It
wires together the components defined elsewhere in the package:

1. :class:`~skill_extractor.esco.loader.EscoLoader` — reads the
   ESCO CSV bundle once per process and applies the alias + custom
   overlays.
2. :class:`~skill_extractor.esco.matcher.EscoMatcherBuilder` — builds
   (or restores from disk cache) one
   :class:`~spacy.matcher.PhraseMatcher` per language.
3. :class:`~skill_extractor.tokenization.slash_segmenter.SlashSegmenter`
   — pre-processes the text so ``C/C++`` becomes ``C / C++`` (only when
   both sides are known skills).
4. :class:`~skill_extractor.sections.detector.SectionDetector` —
   partitions the CV into ``skills`` / ``experience`` / ... ranges.
5. :class:`~skill_extractor.filters.negation.NegationFilter` and
   :class:`~skill_extractor.filters.disambiguation.NerDisambiguationFilter`
   — drop matches that are negated or are NER-misclassified proper
   nouns.
6. :class:`~skill_extractor.overlays.suppression.SuppressionFilter`
   — drop matches that hit a known-bad (surface, target URI) pair
   from the patch-round catalogue.
7. :class:`~skill_extractor.sections.language_parser` — over the
   ``languages`` section, regex-parses ``Language (CEFR)`` lines and
   injects them as additional :class:`SkillMatch` entries.
8. :class:`~skill_extractor.scoring.confidence.ConfidenceScorer` —
   assigns the final ``[0, 1]`` confidence.

A :class:`SkillExtractor` instance is **stateful** in the sense that
the spaCy pipeline, the loaded ESCO skills and the per-language
:class:`~skill_extractor.esco.matcher.BuiltMatcher` are loaded lazily
on first use and then cached on the instance for the lifetime of the
process. Subsequent ``extract()`` calls reuse the cached artefacts and
take ~50-500 ms per CV.

Confidence formula and section/match-quality weights are documented
in :mod:`skill_extractor.scoring.confidence`.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

import structlog

from cv_extractor.models import ExtractionResult
from skill_extractor.config import NOT_A_CV_WARNING, SkillExtractorConfig
from skill_extractor.esco.cache import compute_esco_hash
from skill_extractor.esco.loader import EscoLoader
from skill_extractor.esco.matcher import (
    BuiltMatcher,
    EscoMatcherBuilder,
    compute_match_kind,
)
from skill_extractor.exceptions import (
    NotACVError,
    SkillExtractorError,
    UnsupportedLanguageError,
)
from skill_extractor.filters.disambiguation import (
    EntitySpan,
    NerDisambiguationFilter,
)
from skill_extractor.filters.negation import NegationFilter
from skill_extractor.models import (
    CefrLevel,
    EscoSkill,
    Language,
    MatchKind,
    SectionLabel,
    SkillExtractionResult,
    SkillMatch,
)
from skill_extractor.overlays.aliases import apply_aliases, load_alias_overlay
from skill_extractor.overlays.custom import (
    load_custom_overlay,
    merge_custom_concepts,
)
from skill_extractor.overlays.multilingual import (
    RO_SKILLS_FILENAME,
    apply_ro_labels,
    load_ro_label_surfaces,
)
from skill_extractor.overlays.suppression import (
    SuppressionFilter,
    load_suppression_rules,
)
from skill_extractor.scoring.confidence import ConfidenceScorer
from skill_extractor.sections.detector import Section, SectionDetector
from skill_extractor.sections.language_parser import (
    LanguageMatch,
    parse_languages,
)
from skill_extractor.tokenization.slash_segmenter import SlashSegmenter

if TYPE_CHECKING:  # pragma: no cover
    from spacy.language import Language as SpacyLanguage

logger = structlog.get_logger(__name__)

# Inputs accepted by ``SkillExtractor.extract``. The tuple form is for
# callers that have plain text but no full ``ExtractionResult`` (e.g.
# unit tests, REPL exploration).
ExtractInput = Union["ExtractionResult", tuple[str, Language]]

# Order in which match kinds dominate when collapsing duplicates: an
# exact match for the same URI beats an alt match beats a lemma-only
# match. Lower value = "better" for the purpose of selecting the
# representative kind for the scorer.
_MATCH_KIND_ORDER: dict[MatchKind, int] = {"exact": 0, "alt": 1, "lemma": 2}

# Stable, sentinel-shaped URI used by the language-section parser when
# it injects a ``LanguageMatch``. The URI prefix follows the same
# ``CUST:`` convention as the custom-concept overlay so downstream
# reports can filter "custom" matches uniformly.
LANGUAGE_URI_PREFIX = "CUST:lang:"


# ---------------------------------------------------------------------------
# Internal raw-hit DTO
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _RawHit:
    """A single PhraseMatcher hit, post-filter, pre-aggregation."""

    concept_uri: str
    preferred_label: str
    skill_type: str
    section: SectionLabel
    char_start: int
    char_end: int
    surface: str
    match_kind: MatchKind
    is_custom: bool = False
    cefr_level: CefrLevel | None = None


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


class SkillExtractor:
    """Orchestrates the full skill-extraction pipeline.

    Parameters
    ----------
    config
        Configuration. If omitted, defaults from
        :class:`SkillExtractorConfig` are used.
    nlp_factory
        Optional callable ``(language) -> spacy.Language``. Lets tests
        inject a blank pipeline (``spacy.blank("en")``) without having
        to download the production model. Defaults to
        ``spacy.load(self._config.spacy_model_<lang>)``.
    """

    def __init__(
        self,
        config: SkillExtractorConfig | None = None,
        *,
        nlp_factory: Callable[[Language], SpacyLanguage] | None = None,
    ) -> None:
        self._config = config or SkillExtractorConfig()
        self._loader = EscoLoader(self._config)
        self._matcher_builder = EscoMatcherBuilder(self._config)
        self._negation_filter = NegationFilter(self._config)
        self._disambiguation_filter = NerDisambiguationFilter()
        self._scorer = ConfidenceScorer(self._config)
        self._nlp_factory = nlp_factory or self._default_nlp_factory

        # Suppression filter — empty rule set if the overlay is disabled.
        if self._config.enable_suppression:
            self._suppression_filter = SuppressionFilter(
                load_suppression_rules(self._config.suppression_rules_path)
            )
        else:
            self._suppression_filter = SuppressionFilter()

        # Lazily-populated per-process caches.
        self._nlp_cache: dict[Language, SpacyLanguage] = {}
        self._matcher_cache: dict[Language, BuiltMatcher] = {}
        # Guards the (expensive) PhraseMatcher build/restore in
        # ``_ensure_matcher``. FastAPI runs sync endpoints in a thread pool, so
        # a bulk upload can fire several concurrent ``/v1/extract`` calls; without
        # this lock the first batch of CVs in a not-yet-cached language would each
        # trigger a full ~14k-pattern build in parallel (minutes of CPU + a memory
        # spike, all contending for the GIL). The lock serialises the build so only
        # one thread pays the cost and the rest reuse the populated cache.
        self._matcher_build_lock = threading.Lock()
        self._skills_cache: list[EscoSkill] | None = None
        self._esco_hash_cache: str | None = None
        self._slash_segmenter_cache: SlashSegmenter | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, input_data: ExtractInput) -> SkillExtractionResult:
        """Run the pipeline on a single CV.

        Parameters
        ----------
        input_data
            Either a :class:`cv_extractor.models.ExtractionResult` or
            a ``(text, language)`` tuple.

        Returns
        -------
        SkillExtractionResult
            Deduplicated, ranked list of detected skills. Sorted by
            descending confidence, ties broken by preferred label.

        Raises
        ------
        NotACVError
            If the input ``ExtractionResult`` carries the Module 1
            "not a CV" warning.
        UnsupportedLanguageError
            If the language is not in ``{"en", "ro"}``.
        SkillExtractorError
            If a required spaCy model is not installed.
        """
        text, language, source_warnings = self._parse_input(input_data)

        # Hard filter on Module 1's "not a CV" warning.
        if any(w == NOT_A_CV_WARNING for w in source_warnings):
            raise NotACVError()

        # Validate language. ``ExtractionMetadata.detected_language`` is
        # ``str | None`` so we may receive ``None`` here.
        if language not in ("en", "ro"):
            raise UnsupportedLanguageError(language)

        warnings: list[str] = []

        if not text or not text.strip():
            return SkillExtractionResult(
                language=language,
                skills=[],
                skill_count=0,
                processing_time_ms=0.0,
                warnings=warnings,
            )

        t0 = time.monotonic()

        nlp = self._ensure_nlp(language)
        built = self._ensure_matcher(language)

        # Slash segmentation MUST run before the spaCy pipeline so the
        # tokenizer sees ``C / C++`` instead of ``C/C++``. We split out
        # the rewriting step because it preserves character positions
        # for every retained character (the inserted whitespace just
        # shifts the right-side run by ``len(separator) - 1`` characters,
        # which only affects offsets internal to the run — which we
        # never report externally).
        if self._config.enable_slash_segmentation:
            segmented_text = self._ensure_slash_segmenter().segment(text)
        else:
            segmented_text = text

        # Tokenise with the full pipeline so we get NER for the
        # disambiguation filter. Blank pipelines (tests) just yield
        # an empty entity list, which is harmless.
        doc = nlp(segmented_text)

        entities: list[EntitySpan] = [
            EntitySpan(
                start_char=ent.start_char,
                end_char=ent.end_char,
                label=ent.label_,
            )
            for ent in doc.ents
        ]

        sections = SectionDetector.detect(segmented_text)

        raw_matches = built.matcher(doc)

        raw_hits: list[_RawHit] = []
        suppressed = 0
        for match_id, token_start, token_end in raw_matches:
            match_key = nlp.vocab.strings[match_id]
            meta = built.label_map.get(match_key)
            if meta is None:  # pragma: no cover — defensive
                continue

            span = doc[token_start:token_end]
            char_start = span.start_char
            char_end = span.end_char
            surface = span.text
            match_kind: MatchKind = compute_match_kind(  # type: ignore[assignment]
                surface=surface, meta=meta
            )
            section = SectionDetector.section_for(sections, char_start)

            # Filters — order matters for cost (negation is regex-only,
            # disambiguation walks an entity list).
            if self._negation_filter.is_negated(
                text=segmented_text, match_start=char_start, language=language
            ):
                continue
            if self._disambiguation_filter.is_misclassified_proper_noun(
                text=segmented_text,
                entities=entities,
                match_start=char_start,
                match_end=char_end,
                section=section,
            ):
                continue

            # Suppression rules — drop the documented false-positive
            # families before they reach scoring. The filter is a
            # no-op when ``enable_suppression`` is False (empty rule
            # set on the instance).
            sup_rule = self._suppression_filter.should_suppress(
                text=segmented_text,
                surface=surface,
                target_uri=meta.concept_uri,
                section=section,
                char_start=char_start,
                char_end=char_end,
            )
            if sup_rule is not None:
                suppressed += 1
                continue

            raw_hits.append(
                _RawHit(
                    concept_uri=meta.concept_uri,
                    preferred_label=meta.preferred_label,
                    skill_type=meta.skill_type,
                    section=section,
                    char_start=char_start,
                    char_end=char_end,
                    surface=surface,
                    match_kind=match_kind,
                    is_custom=meta.is_custom,
                )
            )

        # Language-section parser. Runs independently of the matcher and
        # emits one ``_RawHit`` per parsed ``Language (CEFR)`` entry.
        if self._config.enable_language_section:
            raw_hits.extend(
                self._language_section_hits(
                    text=segmented_text,
                    sections=sections,
                )
            )

        skill_matches = self._aggregate(raw_hits)

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        logger.info(
            "skill_extractor.extract",
            language=language,
            text_length=len(text),
            raw_hits=len(raw_hits),
            suppressed=suppressed,
            unique_skills=len(skill_matches),
            elapsed_ms=round(elapsed_ms, 2),
        )

        return SkillExtractionResult(
            language=language,
            skills=skill_matches,
            skill_count=len(skill_matches),
            processing_time_ms=elapsed_ms,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Internals: lazy resource loading
    # ------------------------------------------------------------------

    def _default_nlp_factory(self, language: Language) -> SpacyLanguage:
        """Load the configured spaCy model for ``language``."""
        import spacy

        model_name = (
            self._config.spacy_model_en
            if language == "en"
            else self._config.spacy_model_ro
        )
        try:
            return spacy.load(model_name)
        except OSError as exc:
            raise SkillExtractorError(
                f"spaCy model {model_name!r} is not installed. "
                f"Install it with: python -m spacy download {model_name}"
            ) from exc

    def _ensure_nlp(self, language: Language) -> SpacyLanguage:
        if language not in self._nlp_cache:
            self._nlp_cache[language] = self._nlp_factory(language)
        return self._nlp_cache[language]

    def _ensure_skills(self) -> tuple[list[EscoSkill], str]:
        """Load ESCO + apply the alias / custom overlays.

        The overlays are intentionally applied here rather than inside
        :class:`EscoLoader` so that ``loader.load()`` keeps its narrow
        contract of "parse the ESCO CSV bundle" — the pipeline is the
        one component that knows about the patch-round config flags.
        """
        if self._skills_cache is None:
            skills = self._loader.load()
            if self._config.enable_tech_aliases:
                overlay = load_alias_overlay(self._config.tech_aliases_path)
                skills = apply_aliases(skills, overlay)
            if self._config.enable_custom_overlay:
                custom_overlay = load_custom_overlay(
                    self._config.custom_concepts_path
                )
                skills = merge_custom_concepts(skills, custom_overlay)
            if self._config.enable_ro_labels:
                ro_surfaces = load_ro_label_surfaces(
                    self._config.esco_ro_dir / RO_SKILLS_FILENAME
                )
                skills = apply_ro_labels(skills, ro_surfaces)
            self._skills_cache = skills
            base_hash = compute_esco_hash(
                self._config.esco_dir / EscoLoader.SKILLS_FILE,
                self._config.esco_dir / EscoLoader.LANGUAGE_FILE,
            )
            self._esco_hash_cache = self._compose_cache_hash(base_hash)
        assert self._esco_hash_cache is not None
        return self._skills_cache, self._esco_hash_cache

    def _compose_cache_hash(self, base_hash: str) -> str:
        """Fold the overlay file contents into the matcher cache hash.

        The matcher cache is keyed on a short prefix of the SHA-256 of
        every input that materially affects what patterns end up in the
        PhraseMatcher. Without this, editing ``tech_aliases.yaml``,
        ``custom_concepts.json`` or the Romanian bundle ``skills_ro.csv``
        would silently load stale cached matchers built from the OLD
        overlays. We append a fixed-length digest of each overlay file
        (or an empty marker if the file is absent / the overlay is
        disabled) so the cache invalidates deterministically.
        """
        h = hashlib.sha256(base_hash.encode("utf-8"))
        for enabled, path in (
            (self._config.enable_tech_aliases, self._config.tech_aliases_path),
            (
                self._config.enable_custom_overlay,
                self._config.custom_concepts_path,
            ),
            (
                self._config.enable_ro_labels,
                self._config.esco_ro_dir / RO_SKILLS_FILENAME,
            ),
        ):
            if enabled and path.exists():
                h.update(path.read_bytes())
            else:
                h.update(b"\0")
        return h.hexdigest()[:12]

    def _ensure_matcher(self, language: Language) -> BuiltMatcher:
        # Fast path: already built/restored for this language — no lock needed
        # (dict reads are atomic under the GIL).
        cached = self._matcher_cache.get(language)
        if cached is not None:
            return cached
        # Slow path: serialise the build so concurrent first-requests for the same
        # (uncached) language don't each pay the full PhraseMatcher build. Re-check
        # inside the lock in case another thread finished while we waited.
        with self._matcher_build_lock:
            cached = self._matcher_cache.get(language)
            if cached is not None:
                return cached
            nlp = self._ensure_nlp(language)
            skills, esco_hash = self._ensure_skills()
            built = self._matcher_builder.load_or_build(
                skills=skills,
                nlp=nlp,
                esco_hash=esco_hash,
                phrase_attr=self._config.phrase_attr,
            )
            self._matcher_cache[language] = built
            return built

    # Single-character language tokens that we want to TREAT AS skills
    # for slash-segmentation purposes but that we DO NOT want as
    # matching patterns (a single letter ``C`` would otherwise match
    # every Dr. C. Initial in a CV). Listed here as a curated string
    # set so the slash segmenter has enough vocabulary to rewrite
    # ``C/C++`` / ``R/Python`` etc., independently of what the matcher
    # itself indexes.
    _SEGMENTATION_ONLY_SURFACES: frozenset[str] = frozenset(
        {"c", "r"}
    )

    def _ensure_slash_segmenter(self) -> SlashSegmenter:
        """Build the slash segmenter once per process from the loaded skills."""
        if self._slash_segmenter_cache is None:
            skills, _ = self._ensure_skills()
            surfaces: list[str] = []
            for s in skills:
                surfaces.append(s.preferred_label)
                surfaces.extend(s.alt_labels)
            self._slash_segmenter_cache = SlashSegmenter.from_surface_lists(
                surfaces,
                list(self._SEGMENTATION_ONLY_SURFACES),
            )
        return self._slash_segmenter_cache

    # ------------------------------------------------------------------
    # Internals: language section
    # ------------------------------------------------------------------

    def _language_section_hits(
        self,
        *,
        text: str,
        sections: list[Section],
    ) -> list[_RawHit]:
        """Run the regex language parser and turn its output into raw hits."""
        out: list[_RawHit] = []
        for sec in sections:
            if sec.label != "languages":
                continue
            for lang_match in parse_languages(
                text=text,
                section_start=sec.start,
                section_end=sec.end,
            ):
                out.append(self._language_match_to_raw_hit(lang_match))
        return out

    @staticmethod
    def _language_match_to_raw_hit(lang_match: LanguageMatch) -> _RawHit:
        """Convert a :class:`LanguageMatch` into the internal :class:`_RawHit`."""
        uri = f"{LANGUAGE_URI_PREFIX}{lang_match.language.lower()}"
        return _RawHit(
            concept_uri=uri,
            preferred_label=lang_match.language,
            skill_type="language",
            section="languages",
            char_start=lang_match.char_start,
            char_end=lang_match.char_end,
            surface=lang_match.surface,
            match_kind="exact",
            is_custom=True,
            cefr_level=lang_match.level,
        )

    # ------------------------------------------------------------------
    # Internals: input parsing & aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_input(
        input_data: ExtractInput,
    ) -> tuple[str, object, list[str]]:
        """Normalise the two accepted input forms to ``(text, lang,
        warnings)``."""
        if isinstance(input_data, ExtractionResult):
            language: object = input_data.metadata.detected_language
            return input_data.text, language, list(input_data.warnings)
        if (
            isinstance(input_data, tuple)
            and len(input_data) == 2
            and isinstance(input_data[0], str)
        ):
            return input_data[0], input_data[1], []
        raise TypeError(
            "extract() expects an ExtractionResult or a "
            "(text, language) tuple; got "
            f"{type(input_data).__name__}"
        )

    def _aggregate(self, raw_hits: list[_RawHit]) -> list[SkillMatch]:
        """Group hits by ESCO URI, dedupe span overlaps, score, sort."""
        # Group by concept_uri.
        by_uri: dict[str, list[_RawHit]] = defaultdict(list)
        for h in raw_hits:
            by_uri[h.concept_uri].append(h)

        section_weights = self._config.section_weights
        skill_matches: list[SkillMatch] = []

        for uri, hits in by_uri.items():
            # Within a URI, dedupe identical (start, end) spans that
            # arise when both preferred and alt patterns hit the same
            # surface form.
            unique_by_span: dict[tuple[int, int], _RawHit] = {}
            for h in hits:
                key = (h.char_start, h.char_end)
                existing = unique_by_span.get(key)
                if existing is None:
                    unique_by_span[key] = h
                elif (
                    _MATCH_KIND_ORDER[h.match_kind]
                    < _MATCH_KIND_ORDER[existing.match_kind]
                ):
                    # Prefer the better (lower-order) match kind.
                    unique_by_span[key] = h

            deduped = list(unique_by_span.values())

            # Pick the canonical section: highest section weight among
            # the surviving hits. Ties are broken by document order
            # (earliest occurrence wins) — the ``max`` is stable on
            # equal keys, but we make this explicit by including
            # ``-h.char_start`` as a tiebreaker.
            primary = max(
                deduped,
                key=lambda h: (section_weights[h.section], -h.char_start),
            )
            primary_section = primary.section

            # Pick the best (lowest-order) match kind across all hits
            # for this URI; this is the kind used by the scorer.
            best_kind = min(
                deduped, key=lambda h: _MATCH_KIND_ORDER[h.match_kind]
            ).match_kind

            # Representative surface form: use the hit in the primary
            # section if available, else the first one.
            rep = next(
                (h for h in deduped if h.section == primary_section),
                deduped[0],
            )

            spans = sorted(
                {(h.char_start, h.char_end) for h in deduped}
            )
            frequency = len(spans)

            confidence = self._scorer.compute(
                section=primary_section,
                match_kind=best_kind,
                frequency=frequency,
            )

            # CEFR level only meaningful for language matches. Take the
            # first non-None level encountered (parser already dedupes
            # per language so there will typically be one).
            cefr_level = next(
                (h.cefr_level for h in deduped if h.cefr_level is not None),
                None,
            )

            skill_matches.append(
                SkillMatch(
                    esco_uri=uri,
                    preferred_label=rep.preferred_label,
                    matched_text=rep.surface,
                    skill_type=rep.skill_type,  # type: ignore[arg-type]
                    spans=spans,
                    section=primary_section,
                    frequency=frequency,
                    confidence=confidence,
                    is_custom=rep.is_custom,
                    cefr_level=cefr_level,
                )
            )

        # Sort: highest confidence first, ties by label.
        skill_matches.sort(
            key=lambda m: (-m.confidence, m.preferred_label.lower())
        )
        return skill_matches
