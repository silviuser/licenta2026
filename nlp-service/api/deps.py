"""Dependency-injected singletons for the FastAPI service.

The three module pipelines are lazy-loaded via ``functools.lru_cache``
so the encoder and ESCO index are constructed once per process and
reused across requests. Tests override the cached functions via
FastAPI's ``app.dependency_overrides`` to short-circuit the heavy
load — see ``tests/api/conftest.py``.

The cache key is implicit (the function has no arguments), so the
``maxsize=1`` is a defensive belt-and-braces — only one instance can
ever live.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Depends

if TYPE_CHECKING:
    from cv_extractor import ExtractionPipeline
    from skill_extractor import SkillExtractor
    from skill_matcher import SkillMatcher


# ---------------------------------------------------------------------------
# Per-module singletons
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_extraction_pipeline() -> ExtractionPipeline:
    """Return the process-singleton Module 1 extractor.

    Constructed lazily on first call. Subsequent calls are O(1).
    Tests substitute a mock via
    ``app.dependency_overrides[get_extraction_pipeline] = lambda: mock``.
    """
    # Local import — keeping ``cv_extractor`` off the module-level
    # import path means importing ``api.deps`` is cheap even on a
    # bare Python install without the [api,ml] extras installed.
    from cv_extractor import ExtractionPipeline

    return ExtractionPipeline()


@lru_cache(maxsize=1)
def get_skill_extractor() -> SkillExtractor:
    """Return the process-singleton Module 2 extractor."""
    from skill_extractor import SkillExtractor

    return SkillExtractor()


@lru_cache(maxsize=1)
def get_skill_matcher() -> SkillMatcher:
    """Return the process-singleton Module 3 matcher.

    First call triggers the encoder + ESCO index lazy-load (~5-10 s
    with cached ESCO index, ~30-60 s cold). Subsequent calls are
    O(1).
    """
    from skill_matcher import SkillMatcher

    return SkillMatcher()


# ---------------------------------------------------------------------------
# Composite dependency (the three-pipelines tuple)
# ---------------------------------------------------------------------------


def get_pipeline(
    extractor: ExtractionPipeline = Depends(get_extraction_pipeline),
    skills: SkillExtractor = Depends(get_skill_extractor),
    matcher: SkillMatcher = Depends(get_skill_matcher),
) -> tuple[ExtractionPipeline, SkillExtractor, SkillMatcher]:
    """Composite dependency: the three pipelines as a tuple.

    Convenience for ``POST /v1/extract`` and ``POST /v1/full`` which
    need all three. Routers that need only one (e.g.
    ``POST /v1/match`` needs only Module 3) inject the relevant
    per-module dependency directly.
    """
    return (extractor, skills, matcher)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def clear_dependency_caches() -> None:
    """Clear all three LRU caches.

    Used by the per-test conftest fixture so a real pipeline that
    survived from a previous test (e.g. the slow E2E test) does not
    leak into the next test's process state. Also clears the matcher
    so the slow warm-up cost is not paid more than once per test
    session.
    """
    get_extraction_pipeline.cache_clear()
    get_skill_extractor.cache_clear()
    get_skill_matcher.cache_clear()


__all__ = [
    "clear_dependency_caches",
    "get_extraction_pipeline",
    "get_pipeline",
    "get_skill_extractor",
    "get_skill_matcher",
]
