"""Step 8 pin tests for :mod:`skill_matcher.config`.

Kept in a separate module from :mod:`test_config` so the existing Step
4 / Step 7 pin tests remain untouched. Pins the new fields added in
Step 8 (`required_weight`, `t1_strong_threshold`,
`t2_possible_threshold`) so an unintended config edit shows up as a
test failure rather than silently regressing the production defaults.

Provisional-default doctrine
----------------------------
The default values for the seven knobs ARE the Step 7 provisional
values:

* drop_threshold = 0.45      (Step 4 lock)
* keep_threshold = 0.55      (Step 4 lock)
* expansion_threshold = 0.75 (Step 4 lock)
* per_requirement_keep_threshold = 0.30  (Step 7 lock)
* required_weight = 0.8      (Step 7 implicit; Step 8 promoted to config field)
* t1_strong_threshold = 0.55 (Step 7 implicit; Step 8 promoted)
* t2_possible_threshold = 0.25 (Step 7 implicit; Step 8 promoted)

After ``scripts/tune_thresholds.py`` reports a strict-guard-passing
combo and the operator pastes the amendment row, this file MUST be
updated alongside ``config.py`` defaults so the schema and the pins
move in lockstep.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from skill_matcher.config import SkillMatcherConfig, nice_weight


def test_step8_locked_defaults_for_seven_knobs() -> None:
    """Step 8 lock (2026-05-17): the seven tunable knobs hold the values
    that strict-guard-passing tuner produced.

    Reproducible via `python scripts/tune_thresholds.py --mode full`
    against `tests/fixtures/eval_corpus` on the Step 5 placeholder
    encoder. Macro F1 lift vs Step 7 baseline: 0.225 -> 0.504 (+0.279).

    When the Step 5 redo lands, re-run the tuner and update these
    pinned values + the corresponding `config.py` defaults in one
    coordinated commit. Expected direction of change: t1, t2, and
    per_requirement_keep_threshold all climb upward as the score
    distribution widens toward `[0, 1]`.
    """
    cfg = SkillMatcherConfig()
    # Linker-tier knobs.
    assert cfg.drop_threshold == 0.40
    assert cfg.keep_threshold == 0.50
    assert cfg.expansion_threshold == 0.75
    # Scorer-tier knobs.
    assert cfg.per_requirement_keep_threshold == 0.085
    assert cfg.required_weight == 0.50
    # Projection-tier knobs.
    assert cfg.t1_strong_threshold == 0.060
    assert cfg.t2_possible_threshold == 0.005


def test_step8_nice_weight_derivation() -> None:
    """``nice_weight`` is the complement of ``required_weight``."""
    cfg = SkillMatcherConfig()
    assert nice_weight(cfg) == pytest.approx(1.0 - cfg.required_weight)
    # Sweep a few specific values.
    for rw in (0.0, 0.5, 0.7, 0.9, 1.0):
        cfg_alt = cfg.model_copy(update={"required_weight": rw})
        assert nice_weight(cfg_alt) == pytest.approx(1.0 - rw)


def test_step8_required_weight_out_of_range_raises() -> None:
    """``required_weight`` is bounded to ``[0.0, 1.0]``."""
    with pytest.raises(ValidationError):
        SkillMatcherConfig(required_weight=1.5)
    with pytest.raises(ValidationError):
        SkillMatcherConfig(required_weight=-0.1)


def test_step8_t1_t2_out_of_range_raises() -> None:
    """``t1_strong_threshold`` and ``t2_possible_threshold`` are bounded
    to ``[0.0, 1.0]``."""
    with pytest.raises(ValidationError):
        SkillMatcherConfig(t1_strong_threshold=1.5)
    with pytest.raises(ValidationError):
        SkillMatcherConfig(t2_possible_threshold=-0.1)


def test_step8_projection_ordering_enforced() -> None:
    """``t2_possible_threshold >= t1_strong_threshold`` is rejected.

    Without this guard the 3-class projection would collapse to two
    classes (everything below ``t1`` would fall to ``"no"``).
    """
    with pytest.raises(ValidationError, match="Projection ordering"):
        SkillMatcherConfig(
            t1_strong_threshold=0.5, t2_possible_threshold=0.5
        )
    with pytest.raises(ValidationError, match="Projection ordering"):
        SkillMatcherConfig(
            t1_strong_threshold=0.3, t2_possible_threshold=0.6
        )


def test_step8_projection_ordering_accepts_strict_inequality() -> None:
    """The validator allows ``t2 < t1`` with arbitrarily small margins."""
    cfg = SkillMatcherConfig(
        t1_strong_threshold=0.50001, t2_possible_threshold=0.5
    )
    assert cfg.t1_strong_threshold == pytest.approx(0.50001)
    assert cfg.t2_possible_threshold == 0.5


def test_step8_env_prefix_override_for_new_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SKILL_MATCHER_*`` env vars override the new Step 8 fields."""
    monkeypatch.setenv("SKILL_MATCHER_REQUIRED_WEIGHT", "0.9")
    monkeypatch.setenv("SKILL_MATCHER_T1_STRONG_THRESHOLD", "0.7")
    monkeypatch.setenv("SKILL_MATCHER_T2_POSSIBLE_THRESHOLD", "0.3")

    cfg = SkillMatcherConfig()
    assert cfg.required_weight == 0.9
    assert cfg.t1_strong_threshold == 0.7
    assert cfg.t2_possible_threshold == 0.3
    # Step 8 locked defaults still hold for everything else.
    assert cfg.drop_threshold == 0.40
    assert cfg.keep_threshold == 0.50


def test_step8_schema_export_lists_new_fields() -> None:
    """``SkillMatcherConfig.model_fields`` includes the three new fields."""
    fields = set(SkillMatcherConfig.model_fields.keys())
    assert "required_weight" in fields
    assert "t1_strong_threshold" in fields
    assert "t2_possible_threshold" in fields
