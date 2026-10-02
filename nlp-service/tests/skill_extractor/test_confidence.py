"""Unit tests for :mod:`skill_extractor.scoring.confidence`.

These tests verify the *properties* of the formula — monotonicity,
ordering, clamping, baseline anchor — rather than asserting specific
floating-point outputs (which would couple the tests to the exact
choice of saturation function).
"""

from __future__ import annotations

import math

import pytest

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.models import MatchKind, SectionLabel
from skill_extractor.scoring.confidence import (
    ConfidenceScorer,
    compute_confidence,
    frequency_saturation,
)


@pytest.fixture
def cfg() -> SkillExtractorConfig:
    return SkillExtractorConfig()


def _score(
    *,
    section: SectionLabel,
    match_kind: MatchKind,
    frequency: int,
    cfg: SkillExtractorConfig,
) -> float:
    return compute_confidence(
        section=section,
        match_kind=match_kind,
        frequency=frequency,
        section_weights=cfg.section_weights,
        match_quality_weights=cfg.match_quality_weights,
    )


# ---------------------------------------------------------------------------
# Frequency saturation function (helper)
# ---------------------------------------------------------------------------


class TestFrequencySaturation:
    def test_baseline(self) -> None:
        # f(1) = 1 + ln(2)
        assert frequency_saturation(1) == pytest.approx(1.0 + math.log(2))

    def test_monotone_increasing(self) -> None:
        prev = -math.inf
        for f in range(1, 50):
            curr = frequency_saturation(f)
            assert curr > prev
            prev = curr

    def test_zero_or_negative_returns_unit(self) -> None:
        """Defensive: out-of-domain inputs return 1.0 rather than NaN."""
        assert frequency_saturation(0) == 1.0
        assert frequency_saturation(-3) == 1.0

    def test_growth_is_sublinear(self) -> None:
        """Confirm the saturation property: doubling f grows the
        function strictly less than 2x."""
        s_1 = frequency_saturation(1)
        s_2 = frequency_saturation(2)
        # s(2) < 2 · s(1), i.e. growth-from-1-to-2 is sublinear.
        assert s_2 < 2 * s_1


# ---------------------------------------------------------------------------
# Baseline anchor — exact + skills + freq=1 → ~1.0
# ---------------------------------------------------------------------------


class TestBaselineAnchor:
    def test_exact_skills_freq_one_is_exactly_one(
        self, cfg: SkillExtractorConfig
    ) -> None:
        score = _score(
            section="skills", match_kind="exact", frequency=1, cfg=cfg
        )
        assert score == pytest.approx(1.0)

    def test_anything_higher_than_baseline_clamps_to_one(
        self, cfg: SkillExtractorConfig
    ) -> None:
        # Same baseline, but with frequency well above 1 → overflow → 1.0.
        score = _score(
            section="skills", match_kind="exact", frequency=50, cfg=cfg
        )
        assert score == 1.0


# ---------------------------------------------------------------------------
# Output range — clamping
# ---------------------------------------------------------------------------


class TestClamp:
    @pytest.mark.parametrize("freq", [1, 2, 5, 10, 100, 1_000])
    @pytest.mark.parametrize(
        "section",
        ["skills", "experience", "education", "profile", "languages", "other"],
    )
    @pytest.mark.parametrize("kind", ["exact", "alt", "lemma"])
    def test_all_outputs_in_unit_interval(
        self,
        section: SectionLabel,
        kind: MatchKind,
        freq: int,
        cfg: SkillExtractorConfig,
    ) -> None:
        score = _score(section=section, match_kind=kind, frequency=freq, cfg=cfg)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Monotonicity in frequency (within the unclamped region)
# ---------------------------------------------------------------------------


class TestMonotoneInFrequency:
    @pytest.mark.parametrize(
        "section,kind",
        [
            ("profile", "lemma"),
            ("education", "alt"),
            ("other", "lemma"),
            ("profile", "alt"),
        ],
    )
    def test_more_frequent_means_higher_or_equal(
        self,
        section: SectionLabel,
        kind: MatchKind,
        cfg: SkillExtractorConfig,
    ) -> None:
        prev = -math.inf
        for f in range(1, 20):
            curr = _score(section=section, match_kind=kind, frequency=f, cfg=cfg)
            assert curr >= prev - 1e-12  # tolerate float noise
            prev = curr


# ---------------------------------------------------------------------------
# Ordering between sections / match kinds
# ---------------------------------------------------------------------------


class TestOrdering:
    def test_match_kind_ordering_exact_alt_lemma(
        self, cfg: SkillExtractorConfig
    ) -> None:
        """Holding section + frequency fixed: exact > alt > lemma."""
        # Use a non-clamping section to surface the inequality.
        section: SectionLabel = "profile"
        e = _score(section=section, match_kind="exact", frequency=1, cfg=cfg)
        a = _score(section=section, match_kind="alt", frequency=1, cfg=cfg)
        le = _score(section=section, match_kind="lemma", frequency=1, cfg=cfg)
        assert e > a > le

    def test_section_ordering(
        self, cfg: SkillExtractorConfig
    ) -> None:
        """Holding match-kind + frequency fixed: skills >= experience
        >= education > profile, with experience == languages."""
        kind: MatchKind = "alt"  # not exact, so skills doesn't clamp
        s = _score(section="skills", match_kind=kind, frequency=1, cfg=cfg)
        x = _score(section="experience", match_kind=kind, frequency=1, cfg=cfg)
        lg = _score(section="languages", match_kind=kind, frequency=1, cfg=cfg)
        ed = _score(section="education", match_kind=kind, frequency=1, cfg=cfg)
        p = _score(section="profile", match_kind=kind, frequency=1, cfg=cfg)
        o = _score(section="other", match_kind=kind, frequency=1, cfg=cfg)

        assert s >= x
        assert x == pytest.approx(lg)  # both at 0.9
        assert lg > ed
        assert ed > p
        assert p == pytest.approx(o)  # both at 0.5


# ---------------------------------------------------------------------------
# Specific spot values (regression anchors)
# ---------------------------------------------------------------------------


class TestSpotValues:
    """Pin down a few representative outputs so we notice if someone
    silently changes the formula. The exact values are derived from
    the documented formula; the tests are not authoritative on what
    the formula *should* be — the docstring is."""

    def test_alt_skills_freq_one(self, cfg: SkillExtractorConfig) -> None:
        # 1.0 (skills) * 0.85 (alt) * s(1) / s(1) = 0.85
        score = _score(
            section="skills", match_kind="alt", frequency=1, cfg=cfg
        )
        assert score == pytest.approx(0.85)

    def test_lemma_profile_freq_one(self, cfg: SkillExtractorConfig) -> None:
        # 0.5 * 0.7 * s(1) / s(1) = 0.35
        score = _score(
            section="profile", match_kind="lemma", frequency=1, cfg=cfg
        )
        assert score == pytest.approx(0.35)

    def test_exact_other_freq_two(self, cfg: SkillExtractorConfig) -> None:
        # 0.5 * 1.0 * s(2)/s(1)
        sw = cfg.section_weights["other"]
        mq = cfg.match_quality_weights["exact"]
        sat_2 = frequency_saturation(2)
        sat_1 = frequency_saturation(1)
        expected = max(0.0, min(1.0, sw * mq * sat_2 / sat_1))
        score = _score(section="other", match_kind="exact", frequency=2, cfg=cfg)
        assert score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Error paths — invalid keys
# ---------------------------------------------------------------------------


class TestErrors:
    def test_unknown_section_raises(self, cfg: SkillExtractorConfig) -> None:
        with pytest.raises(KeyError):
            compute_confidence(
                section="bogus",  # type: ignore[arg-type]
                match_kind="exact",
                frequency=1,
                section_weights=cfg.section_weights,
                match_quality_weights=cfg.match_quality_weights,
            )

    def test_unknown_match_kind_raises(self, cfg: SkillExtractorConfig) -> None:
        with pytest.raises(KeyError):
            compute_confidence(
                section="skills",
                match_kind="bogus",  # type: ignore[arg-type]
                frequency=1,
                section_weights=cfg.section_weights,
                match_quality_weights=cfg.match_quality_weights,
            )


# ---------------------------------------------------------------------------
# ConfidenceScorer wrapper
# ---------------------------------------------------------------------------


class TestConfidenceScorer:
    def test_wrapper_matches_pure_function(
        self, cfg: SkillExtractorConfig
    ) -> None:
        scorer = ConfidenceScorer(config=cfg)
        for section in ("skills", "experience", "profile", "other"):
            for kind in ("exact", "alt", "lemma"):
                for freq in (1, 3, 10):
                    direct = _score(
                        section=section,  # type: ignore[arg-type]
                        match_kind=kind,  # type: ignore[arg-type]
                        frequency=freq,
                        cfg=cfg,
                    )
                    via_scorer = scorer.compute(
                        section=section,  # type: ignore[arg-type]
                        match_kind=kind,  # type: ignore[arg-type]
                        frequency=freq,
                    )
                    assert direct == via_scorer

    def test_wrapper_uses_default_config_when_none(self) -> None:
        # Should not raise, should produce a valid output.
        scorer = ConfidenceScorer()
        score = scorer.compute(
            section="skills", match_kind="exact", frequency=1
        )
        assert score == pytest.approx(1.0)
