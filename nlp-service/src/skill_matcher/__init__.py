"""skill_matcher -- Module 3 of HR Helper NLP service.

This package implements the **Semantic Skill Matcher**: a fine-tuned
sentence-transformer that (a) re-scores Module 2 lexical candidates
using contextual semantics, (b) recovers skills Module 2 missed via
sliding-window retrieval against an ESCO embedding index, and (c)
produces the final CV <-> JD compatibility score consumed by the B2B
product surface.

Step status (as of v0.7.0 -- Step 9 final validation report delivered)
----------------------------------------------------------------------
* Steps 0-3: package skeleton, eval corpus, training dataset.
* Step 4: zero-shot baseline + ESCO embedding index.
* Step 5 Phase Alpha: training-data converter (placeholder encoder).
* Step 6: Linker -- semantic re-scoring + sliding-window expansion.
* Step 7: Scorer -- tri-factor per-requirement product + Step 8
  configurable required / nice weighting.
* Step 8: threshold-tuning machinery (the ``tuning`` submodule +
  ``scripts/tune_thresholds.py``).
* **Step 9 (this release)**: Module 3 declared READY at the
  placeholder operating point. Final validation report aggregator
  (``scripts/generate_final_validation_report.py``); no source-code
  changes inside ``src/skill_matcher/`` beyond this version bump and
  the corresponding ``DECISIONS.md`` amendment row.
* Step 10 (pending): API surface + Spring Boot integration hooks.
"""

from skill_matcher.config import Device, SkillMatcherConfig
from skill_matcher.encoder import (
    Encoder,
    MockEncoder,
    SentenceTransformerEncoder,
)
from skill_matcher.esco_index import (
    ConceptTextFormat,
    EscoIndex,
    EscoIndexCacheError,
)
from skill_matcher.esco_loader import (
    EscoConcept,
    compute_esco_file_sha,
    compute_esco_sha,
    load_esco_concepts,
)
from skill_matcher.jd_parser import jd_fixture_to_requirements
from skill_matcher.linker import Linker, LinkerStats
from skill_matcher.models import (
    CandidateSource,
    EnrichedSkillResult,
    JDRequirement,
    Language,
    MatchCandidate,
    MatchedRequirement,
    MatchResult,
    RequirementImportance,
)
from skill_matcher.pipeline import SkillMatcher
from skill_matcher.scorer import Scorer, ScorerStats
from skill_matcher.training_data import (
    ANCHOR_HARD_CAP_CHARS,
    SBERTExample,
    SBERTMode,
    build_anchor_text,
    build_positive_text_from_uri,
    prepare_sbert_examples,
)
from skill_matcher.tuning import (
    CellIntermediate,
    FitClass,
    LinkerIntermediatesBuilder,
    ObjectiveFn,
    ReqIntermediate,
    TuningCombo,
    TuningMetric,
    TuningRunResult,
    aggregate_from_intermediates,
    compute_metric,
    grid_for_tier_0,
    grid_for_tier_1,
    grid_for_tier_2,
    objective_macro_f1,
    objective_weighted_f1,
    project_to_three_class,
    run_full,
    run_tier1_tier0_only,
    score_distribution,
)

__version__ = "0.7.0"

__all__ = [
    "ANCHOR_HARD_CAP_CHARS",
    "CandidateSource",
    "CellIntermediate",
    "ConceptTextFormat",
    "Device",
    "Encoder",
    "EnrichedSkillResult",
    "EscoConcept",
    "EscoIndex",
    "EscoIndexCacheError",
    "FitClass",
    "JDRequirement",
    "Language",
    "Linker",
    "LinkerIntermediatesBuilder",
    "LinkerStats",
    "MatchCandidate",
    "MatchResult",
    "MatchedRequirement",
    "MockEncoder",
    "ObjectiveFn",
    "ReqIntermediate",
    "RequirementImportance",
    "SBERTExample",
    "SBERTMode",
    "Scorer",
    "ScorerStats",
    "SentenceTransformerEncoder",
    "SkillMatcher",
    "SkillMatcherConfig",
    "TuningCombo",
    "TuningMetric",
    "TuningRunResult",
    "__version__",
    "aggregate_from_intermediates",
    "build_anchor_text",
    "build_positive_text_from_uri",
    "compute_esco_file_sha",
    "compute_esco_sha",
    "compute_metric",
    "grid_for_tier_0",
    "grid_for_tier_1",
    "grid_for_tier_2",
    "jd_fixture_to_requirements",
    "load_esco_concepts",
    "objective_macro_f1",
    "objective_weighted_f1",
    "prepare_sbert_examples",
    "project_to_three_class",
    "run_full",
    "run_tier1_tier0_only",
    "score_distribution",
]
