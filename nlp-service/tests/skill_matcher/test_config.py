"""Tests for :mod:`skill_matcher.config`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from skill_matcher.config import SkillMatcherConfig


def test_default_config_loads() -> None:
    """All default values produce a valid config object."""
    cfg = SkillMatcherConfig()
    assert cfg.base_model.startswith("sentence-transformers/")
    assert (
        0.0
        <= cfg.drop_threshold
        <= cfg.keep_threshold
        <= cfg.expansion_threshold
        <= 1.0
    )
    assert cfg.seed == 42
    assert cfg.device == "auto"
    assert cfg.enable_expansion is True


def test_env_prefix_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``SKILL_MATCHER_*`` environment variables override defaults."""
    monkeypatch.setenv(
        "SKILL_MATCHER_BASE_MODEL",
        "sentence-transformers/all-mpnet-base-v2",
    )
    monkeypatch.setenv("SKILL_MATCHER_DEVICE", "cpu")
    monkeypatch.setenv("SKILL_MATCHER_SEED", "1337")
    monkeypatch.setenv("SKILL_MATCHER_KEEP_THRESHOLD", "0.7")

    cfg = SkillMatcherConfig()

    assert cfg.base_model == "sentence-transformers/all-mpnet-base-v2"
    assert cfg.device == "cpu"
    assert cfg.seed == 1337
    assert cfg.keep_threshold == 0.7


def test_threshold_out_of_range_raises() -> None:
    """Thresholds outside ``[0.0, 1.0]`` are rejected at construction time."""
    with pytest.raises(ValidationError):
        SkillMatcherConfig(keep_threshold=1.5)


def test_expansion_window_bounds() -> None:
    """``expansion_window_size`` is bounded to ``[5, 200]``."""
    with pytest.raises(ValidationError):
        SkillMatcherConfig(expansion_window_size=1)
    with pytest.raises(ValidationError):
        SkillMatcherConfig(expansion_window_size=500)


def test_expansion_window_stride_bounds() -> None:
    """``expansion_window_stride`` is bounded to ``[1, 200]``."""
    with pytest.raises(ValidationError):
        SkillMatcherConfig(expansion_window_stride=0)
    with pytest.raises(ValidationError):
        SkillMatcherConfig(expansion_window_stride=500)


def test_step4_threshold_locks_superseded_by_step8() -> None:
    """The Step 4 amendment-log locked drop/keep at (0.45, 0.55) and
    Step 7 locked per_req_keep at 0.30. **Step 8 (2026-05-17) tuner**
    superseded those with empirical values; this test now pins only
    the knobs Step 8 did NOT move (sliding-window geometry + the
    unchanged expansion_threshold).

    The seven-knob production lock lives in
    ``tests/skill_matcher/test_config_step8.py::test_step8_locked_defaults_for_seven_knobs``;
    do NOT duplicate the drop / keep / per_req assertions here.
    """
    cfg = SkillMatcherConfig()
    # Sliding-window geometry -- locked at Step 4, unchanged by Step 8.
    assert cfg.expansion_window_size == 30
    assert cfg.expansion_window_stride == 15
    # expansion_threshold: Step 4 = 0.75, Step 8 tuner picked the same value.
    assert cfg.expansion_threshold == 0.75


def test_step7_per_requirement_keep_threshold_superseded_by_step8() -> None:
    """Step 7's provisional ``per_requirement_keep_threshold = 0.30``
    was superseded by Step 8's tuner. The current locked default is
    0.085 (calibrated for the Step 5 placeholder encoder's compressed
    score range; expected to climb to ~0.20-0.30 after the Step 5 redo).
    See `test_config_step8.py` for the full seven-knob pin.
    """
    cfg = SkillMatcherConfig()
    assert cfg.per_requirement_keep_threshold == 0.085


def test_per_requirement_keep_threshold_out_of_range_raises() -> None:
    """The new threshold is bounded to ``[0.0, 1.0]`` like its siblings."""
    with pytest.raises(ValidationError):
        SkillMatcherConfig(per_requirement_keep_threshold=1.5)
    with pytest.raises(ValidationError):
        SkillMatcherConfig(per_requirement_keep_threshold=-0.1)
