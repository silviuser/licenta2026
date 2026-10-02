"""Configuration for the skill extraction pipeline.

All paths default to the repository layout we have today
(``nlp-service/taxionomy/...`` for the ESCO data, ``nlp-service/.cache/``
for the on-disk PhraseMatcher cache). Anything path-related can be
overridden via environment variables prefixed with ``SKILL_EXTRACTOR_``,
which is :mod:`pydantic_settings` standard.

The numeric weights (``section_weights`` and ``match_quality_weights``)
are deliberately surfaced as configuration so that they can be tuned
without touching code, and so the values used in the validation report
are auditable.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from skill_extractor.models import MatchKind, SectionLabel

# Repository root resolution: this file lives at
# ``nlp-service/src/skill_extractor/config.py`` so going up three parents
# lands us at ``nlp-service/``.
_NLP_SERVICE_ROOT = Path(__file__).resolve().parents[2]

# The skill_extractor package ships small static overlays under
# ``src/skill_extractor/data/``. Resolving paths from this file means
# the overlays travel with the package whether it is run from the repo
# checkout or installed as a wheel.
_PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = _PACKAGE_ROOT / "data"

DEFAULT_ESCO_DIR = (
    _NLP_SERVICE_ROOT
    / "taxionomy"
    / "ESCO dataset - v1.2.1 - classification - en - csv"
)
# Romanian ESCO bundle. Same concept URIs as the English bundle, with
# Romanian preferredLabel / altLabels. Folded onto the English concepts
# by the multilingual overlay so the matcher recognises Romanian surface
# forms (see ``overlays/multilingual.py``).
DEFAULT_ESCO_RO_DIR = (
    _NLP_SERVICE_ROOT
    / "taxionomy"
    / "ESCO dataset - v1.2.1 - classification - ro - csv"
)
DEFAULT_CACHE_DIR = _NLP_SERVICE_ROOT / ".cache" / "skill_extractor"
DEFAULT_TECH_ALIASES_PATH = DEFAULT_DATA_DIR / "tech_aliases.yaml"
DEFAULT_SUPPRESSION_RULES_PATH = DEFAULT_DATA_DIR / "suppression_rules.yaml"
DEFAULT_CUSTOM_CONCEPTS_PATH = DEFAULT_DATA_DIR / "custom_concepts.json"

# String constant used by Module 1's QualityChecker. Module 2 detects
# this exact string in ``ExtractionResult.warnings`` to decide whether
# to refuse extraction. Keeping it as a constant means the contract is
# documented in code, not buried in a substring match.
NOT_A_CV_WARNING = "Document may not be a CV — few CV-specific keywords found."


class SkillExtractorConfig(BaseSettings):
    """Configuration for :class:`skill_extractor.pipeline.SkillExtractor`.

    Environment variable prefix: ``SKILL_EXTRACTOR_``. Example::

        SKILL_EXTRACTOR_ESCO_DIR=/path/to/esco
        SKILL_EXTRACTOR_CACHE_DIR=/tmp/skill_cache
    """

    model_config = SettingsConfigDict(
        env_prefix="SKILL_EXTRACTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Paths ------------------------------------------------------------
    esco_dir: Path = Field(
        default=DEFAULT_ESCO_DIR,
        description="Directory containing the ESCO v1.2.1 EN CSV bundle.",
    )
    esco_ro_dir: Path = Field(
        default=DEFAULT_ESCO_RO_DIR,
        description=(
            "Directory containing the ESCO v1.2.1 RO CSV bundle. Used by "
            "the multilingual overlay to add Romanian surface forms to the "
            "English concepts (see ``enable_ro_labels``)."
        ),
    )
    cache_dir: Path = Field(
        default=DEFAULT_CACHE_DIR,
        description="Directory used to persist the serialised PhraseMatcher.",
    )

    # --- spaCy model selection -------------------------------------------
    spacy_model_en: str = Field(
        default="en_core_web_lg",
        description="spaCy model name to load for English input.",
    )
    spacy_model_ro: str = Field(
        default="ro_core_news_lg",
        description="spaCy model name to load for Romanian input.",
    )
    phrase_attr: str = Field(
        default="LOWER",
        description=(
            "spaCy token attribute the PhraseMatcher keys on. Default "
            "changed from ``LEMMA`` to ``LOWER`` on 2026-05-17 because "
            "``LEMMA`` produces silent mismatches on single-token "
            "uppercase acronyms (OOP, API, CRUD seen as bare tokens) — "
            "spaCy's POS tagger classifies them inconsistently in the "
            "pattern-build path (parser+ner disabled) vs the full "
            "pipeline at match time, and ``attribute_ruler`` lowercases "
            "the pattern lemma but preserves case on the text lemma. "
            "See ``scripts/debug_oop_lemma.py`` for the empirical "
            "evidence. Trade-off: loses morphological normalisation "
            "(pattern ``designing databases`` no longer matches text "
            "``design databases``); ESCO alt_labels already enumerate "
            "the most common inflected variants, so the net empirical "
            "effect is recovering the CV-frequent acronym FN family."
        ),
    )

    # --- Confidence-scoring weights --------------------------------------
    # The choice of weights is documented in scoring/confidence.py and in
    # the module README. The values below are the published baseline
    # used in the thesis validation report.

    section_weights: dict[SectionLabel, float] = Field(
        default_factory=lambda: {  # type: ignore[arg-type]
            "skills": 1.0,
            "experience": 0.9,
            "languages": 0.9,
            "education": 0.7,
            "profile": 0.5,
            "other": 0.5,
        },
        description=(
            "Multiplier applied based on the CV section the match was "
            "found in. Skills section is canonical (1.0), experience "
            "is direct evidence (0.9), profile/summary is least canonical "
            "(0.5)."
        ),
    )
    match_quality_weights: dict[MatchKind, float] = Field(
        default_factory=lambda: {  # type: ignore[arg-type]
            "exact": 1.0,
            "alt": 0.85,
            "lemma": 0.7,
        },
        description=(
            "Multiplier applied based on how the surface form was matched. "
            "Exact preferred-label match is unambiguous (1.0), altLabel "
            "match is high-confidence (0.85), lemma-only match is the "
            "weakest tier (0.7)."
        ),
    )

    # --- Filter knobs -----------------------------------------------------
    negation_window_chars: int = Field(
        default=50,
        ge=10,
        le=200,
        description=(
            "How many characters of context preceding a match the "
            "negation filter inspects."
        ),
    )
    min_token_length: int = Field(
        default=2,
        ge=1,
        description=(
            "ESCO surface forms shorter than this are dropped before "
            "matching to avoid false positives on stop-words and "
            "single-letter tokens."
        ),
    )

    # --- Cache invalidation ----------------------------------------------
    matcher_cache_filename_template: str = Field(
        default="phrasematcher_{lang}_{esco_hash}.pkl",
        description=(
            "Filename template for the cached PhraseMatcher. ``{lang}`` "
            "is the spaCy language code; ``{esco_hash}`` is a SHA-256 "
            "hex prefix of the source skills CSV file."
        ),
    )

    # --- Patch-round overlays (May 2026) ---------------------------------
    # All four overlays default to enabled so the published pipeline runs
    # with the same configuration as the validation report. Each one can
    # be disabled for ablation studies without touching code.

    enable_tech_aliases: bool = Field(
        default=True,
        description=(
            "Augment the ESCO matcher with surface→URI aliases from "
            ":attr:`tech_aliases_path`. Adds extra ``altLabel`` patterns "
            "to existing ESCO concepts."
        ),
    )
    enable_suppression: bool = Field(
        default=True,
        description=(
            "Drop matches that hit a (surface, target URI) pair listed "
            "in :attr:`suppression_rules_path`. Runs after candidate "
            "generation, before scoring."
        ),
    )
    enable_custom_overlay: bool = Field(
        default=True,
        description=(
            "Load custom (non-ESCO) concepts from "
            ":attr:`custom_concepts_path` as a secondary skill source. "
            "Custom concepts use ``CUST:`` URIs and are marked "
            "``is_custom=True`` on the output ``SkillMatch``."
        ),
    )
    enable_language_section: bool = Field(
        default=True,
        description=(
            "Run the dedicated languages-section regex parser over the "
            "``languages`` section detected by ``SectionDetector``. "
            "Produces ``SkillMatch`` instances with "
            "``skill_type='language'`` carrying parsed CEFR levels."
        ),
    )
    enable_slash_segmentation: bool = Field(
        default=True,
        description=(
            "Pre-process the text to insert a separator inside slash-"
            "joined tokens whose left and right sides are both known "
            "skills (e.g. ``C/C++`` → ``C / C++``). Fixes the canonical "
            "Romanian-style ``C/C++`` enumeration that was previously "
            "swallowed by the PhraseMatcher."
        ),
    )
    enable_ro_labels: bool = Field(
        default=True,
        description=(
            "Fold Romanian ESCO labels (preferredLabel + altLabels from "
            ":attr:`esco_ro_dir`/skills_ro.csv) onto the English concepts "
            "as extra ``altLabel`` surface forms, keyed by the shared "
            "concept URI. Lets Module 2 match Romanian-language skills "
            "(e.g. ``baze de date`` → the ``database`` URI) without "
            "changing anything downstream. Disable for an English-only "
            "ablation. Note: the first build after enabling triggers a "
            "cold PhraseMatcher rebuild (the pattern set roughly doubles)."
        ),
    )

    tech_aliases_path: Path = Field(
        default=DEFAULT_TECH_ALIASES_PATH,
        description="YAML file mapping surface forms to existing ESCO URIs.",
    )
    suppression_rules_path: Path = Field(
        default=DEFAULT_SUPPRESSION_RULES_PATH,
        description="YAML file listing (surface, target URI) suppression rules.",
    )
    custom_concepts_path: Path = Field(
        default=DEFAULT_CUSTOM_CONCEPTS_PATH,
        description="JSON file with custom (non-ESCO) concept definitions.",
    )
