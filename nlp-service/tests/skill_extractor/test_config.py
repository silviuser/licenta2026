"""Smoke tests for :mod:`skill_extractor.config`."""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_extractor.config import (
    DEFAULT_CACHE_DIR,
    DEFAULT_ESCO_DIR,
    NOT_A_CV_WARNING,
    SkillExtractorConfig,
)


def test_default_paths_resolve_to_repo() -> None:
    """Default paths are absolute and live under the repo root."""
    config = SkillExtractorConfig()
    assert config.esco_dir.is_absolute()
    assert config.cache_dir.is_absolute()
    assert config.esco_dir == DEFAULT_ESCO_DIR
    assert config.cache_dir == DEFAULT_CACHE_DIR


def test_default_esco_dir_exists_in_this_repo() -> None:
    """The repo ships with the ESCO bundle — sanity check the default path."""
    assert DEFAULT_ESCO_DIR.exists(), (
        f"ESCO data dir not found at {DEFAULT_ESCO_DIR}. "
        "If the dataset has moved, update DEFAULT_ESCO_DIR in config.py."
    )
    assert (DEFAULT_ESCO_DIR / "skills_en.csv").exists()


def test_section_weights_cover_all_labels() -> None:
    config = SkillExtractorConfig()
    expected = {
        "skills",
        "experience",
        "education",
        "profile",
        "languages",
        "other",
    }
    assert set(config.section_weights.keys()) == expected
    # Weights are positive and bounded.
    for w in config.section_weights.values():
        assert 0.0 < w <= 1.0


def test_match_quality_weights_ordered() -> None:
    """Exact > alt > lemma — assertion that anchors the documented ordering."""
    config = SkillExtractorConfig()
    assert (
        config.match_quality_weights["exact"]
        > config.match_quality_weights["alt"]
        > config.match_quality_weights["lemma"]
    )


def test_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Env vars with the right prefix override the defaults."""
    monkeypatch.setenv("SKILL_EXTRACTOR_CACHE_DIR", str(tmp_path))
    config = SkillExtractorConfig()
    assert config.cache_dir == tmp_path


def test_not_a_cv_warning_constant_matches_module1_string() -> None:
    """Hard-pinned string contract with Module 1's QualityChecker.

    If Module 1 ever changes the warning text, this test fails so that
    we can update the constant in lockstep.
    """
    assert (
        NOT_A_CV_WARNING
        == "Document may not be a CV — few CV-specific keywords found."
    )
