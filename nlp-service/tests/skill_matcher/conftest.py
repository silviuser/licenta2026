"""Shared fixtures for the skill_matcher test suite.

Most fixtures live here so individual test modules stay tight. The
fast suite is built on top of :class:`MockEncoder` — anything that
touches the real sentence-transformers model is gated behind
``@pytest.mark.slow`` and uses its own per-test setup.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_matcher.config import SkillMatcherConfig
from skill_matcher.encoder import DEFAULT_MOCK_DIM, MockEncoder


@pytest.fixture
def default_config() -> SkillMatcherConfig:
    """A vanilla :class:`SkillMatcherConfig` with all-default values.

    Tests that override individual fields should use
    ``default_config.model_copy(update={...})`` rather than constructing
    a new config — this keeps default values centralised.
    """
    return SkillMatcherConfig()


@pytest.fixture
def mock_encoder() -> MockEncoder:
    """A deterministic :class:`MockEncoder` of the default tiny dim.

    Used by every fast test that needs *some* encoder but not real
    semantics. Two test runs see identical embeddings, which lets the
    suite assert exact equality on retrieval order.
    """
    return MockEncoder(embedding_dim=DEFAULT_MOCK_DIM)


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """A scratch directory for embedding-cache I/O tests.

    Wrapping :func:`tmp_path` in a named fixture makes intent obvious
    at the call site (``tmp_cache_dir`` vs an anonymous ``tmp_path``)
    and lets us swap to a session-scoped cache later if hot tests
    start dominating wall-clock time.
    """
    cache = tmp_path / "embeddings"
    cache.mkdir(parents=True, exist_ok=True)
    return cache
