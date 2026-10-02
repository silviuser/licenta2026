"""skill_extractor — Module 2 of HR Helper NLP service.

This package implements the **Skill Extraction Service**: the symbolic,
interpretable baseline that maps free-text CV content to ESCO skill URIs.

It consumes the output of Module 1 (``cv_extractor.ExtractionResult``) and
produces a typed ``SkillExtractionResult`` containing each detected skill
with its ESCO URI, surface form, span(s) in the source text, the CV
section it was found in, and a confidence score in ``[0.0, 1.0]``.

Public API
----------
.. code-block:: python

    from cv_extractor import ExtractionPipeline
    from skill_extractor import SkillExtractor

    extraction = ExtractionPipeline().process(Path("cv.pdf"))
    skills = SkillExtractor().extract(extraction)
    for s in skills.skills:
        print(s.preferred_label, s.confidence)

Design rationale
----------------
* **ESCO** as taxonomy: official EU standard, multilingual, free for
  commercial use, updated yearly by the European Commission.
* **PhraseMatcher on LEMMA**: deterministic, fast (O(text length)) and
  **interpretable** — every match has a traceable surface form and a
  canonical URI. This is the property HR / GDPR / anti-bias arguments
  require for the thesis defence.
* **Module 2 is a baseline by design.** Recall on natural-language
  formulations (``"developed asynchronous distributed messaging systems"``
  → Kafka / RabbitMQ) is intentionally weak; that gap is the motivation
  for Module 3 (semantic matching with a fine-tuned sentence-transformer).

This package is **framework-agnostic**: it must NOT import FastAPI,
Flask, Spring or any web framework. A future microservice layer will
wrap it.
"""

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.exceptions import (
    EscoLoadError,
    MatcherCacheError,
    NotACVError,
    SkillExtractorError,
    UnsupportedLanguageError,
)
from skill_extractor.models import (
    CefrLevel,
    EscoSkill,
    SectionLabel,
    SkillExtractionResult,
    SkillMatch,
    SkillType,
)
from skill_extractor.pipeline import SkillExtractor

# Step 10 (2026-05-17): introduced so the FastAPI ``GET /v1/info``
# endpoint can surface Module 2's version alongside Module 1 and
# Module 3 versions. The literal MUST match the ``[project].version``
# in ``nlp-service/pyproject.toml`` (single project version applies
# to all three packages built from this repo); a drift-detection
# test in ``tests/skill_extractor/test_version.py`` asserts this.
__version__ = "0.2.0"

__all__ = [
    "CefrLevel",
    "EscoLoadError",
    "EscoSkill",
    "MatcherCacheError",
    "NotACVError",
    "SectionLabel",
    "SkillExtractionResult",
    "SkillExtractor",
    "SkillExtractorConfig",
    "SkillExtractorError",
    "SkillMatch",
    "SkillType",
    "UnsupportedLanguageError",
    "__version__",
]
