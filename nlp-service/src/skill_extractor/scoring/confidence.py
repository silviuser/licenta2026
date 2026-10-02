"""Confidence scoring for skill matches.

Formula
-------
.. math::

    \\text{confidence} = \\frac{
        w_{\\text{section}}
        \\times w_{\\text{match}}
        \\times s(f)
    }{
        s(1)
    }
    \\quad \\text{clamped to } [0, 1]

where

* :math:`w_{\\text{section}}` is the section weight from
  :attr:`SkillExtractorConfig.section_weights` (1.0 for the canonical
  Skills section, lower for less-canonical sections);
* :math:`w_{\\text{match}}` is the match-quality weight from
  :attr:`SkillExtractorConfig.match_quality_weights`
  (``exact`` > ``alt`` > ``lemma``);
* :math:`s(f) = 1 + \\ln(1 + f)` is a logarithmic frequency-saturation
  function (monotone increasing, slow growth);
* the divisor :math:`s(1) = 1 + \\ln 2 \\approx 1.693` is chosen so
  that a single (``exact``, ``skills``) hit lands exactly at
  confidence ``1.0`` before clamping.

Justification
-------------
1. **Section weight.** A skill listed under "Skills" is the most
   canonical evidence the candidate has it (1.0). A skill mentioned in
   "Experience" is direct, contextualised evidence (0.9). Education
   typically lists *taught* topics rather than self-asserted
   competencies (0.7). The "Profile" / "Summary" is marketing copy and
   the least reliable channel (0.5).
2. **Match quality.** An exact match on the canonical
   ``preferredLabel`` is an unambiguous link to the ESCO concept
   (1.0). A match on one of the curated ``altLabels`` is high-quality
   but introduces a small possibility of homonymy (0.85). A
   lemma-only match (different surface form) has the highest residual
   ambiguity (0.7).
3. **Frequency saturation.** Listing a skill ten times is not ten
   times more credible than listing it once. Logarithmic saturation
   models diminishing returns: each additional mention contributes
   less than the previous one. At the same time, repeated mentions
   *do* corroborate weaker evidence — a lemma-only match in the
   Profile that recurs in Experience deserves a higher score than a
   single isolated mention.
4. **Normaliser.** Choosing :math:`s(1)` as the divisor anchors the
   formula so that the *baseline* (single hit, perfect section,
   perfect match-kind) sits at the top of the confidence range
   exactly. Anything more (extra frequency) overflows and is clamped
   to ``1.0`` — saturated, as designed.

This function is deliberately a *pure* function of its arguments; no
state, no I/O, no side effects. Trivial to unit-test and audit.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.models import MatchKind, SectionLabel

if TYPE_CHECKING:  # pragma: no cover
    pass


def frequency_saturation(frequency: int) -> float:
    """Logarithmic saturation function :math:`1 + \\ln(1 + f)`.

    Defined as a stand-alone helper so unit tests can verify the
    monotonicity property in isolation.
    """
    if frequency < 1:
        # Defensive: by construction we never compute confidence for a
        # zero-frequency match, but make the function robust anyway.
        return 1.0
    return 1.0 + math.log(1 + frequency)


# Pre-computed denominator. Cached at import time because ``compute``
# is potentially called per-match for hundreds of matches per CV; we
# don't want a math.log call on the hot path.
_BASELINE_DENOMINATOR: float = frequency_saturation(1)


def compute_confidence(
    *,
    section: SectionLabel,
    match_kind: MatchKind,
    frequency: int,
    section_weights: dict[SectionLabel, float],
    match_quality_weights: dict[MatchKind, float],
) -> float:
    """Compute the confidence score for a single :class:`SkillMatch`.

    The function is pure: it does not read configuration off any
    instance, does not mutate inputs, and returns a deterministic
    value for any fixed argument tuple.

    Parameters
    ----------
    section
        Which CV section the match was assigned to.
    match_kind
        How the surface form was matched (``exact``, ``alt``, ``lemma``).
    frequency
        How many times the same ESCO concept was matched in the CV.
        Must be ``>= 1``.
    section_weights
        Mapping from section label to weight in ``[0, 1]``. Typically
        :attr:`SkillExtractorConfig.section_weights`.
    match_quality_weights
        Mapping from match kind to weight in ``[0, 1]``. Typically
        :attr:`SkillExtractorConfig.match_quality_weights`.

    Returns
    -------
    float
        Confidence in ``[0.0, 1.0]``.

    Raises
    ------
    KeyError
        If ``section`` or ``match_kind`` is missing from the supplied
        weight dictionaries. This is intentional: silently falling
        back to a default would make scoring bugs invisible.
    """
    sw = section_weights[section]
    mq = match_quality_weights[match_kind]
    sat = frequency_saturation(frequency)
    raw = sw * mq * sat / _BASELINE_DENOMINATOR
    # Clamp to [0, 1]. Saturated cases overflow on the upper bound;
    # the lower bound is defensive only (would require a negative
    # weight to ever fire).
    return max(0.0, min(1.0, raw))


class ConfidenceScorer:
    """Convenience wrapper that bakes the weight tables from a config.

    Use this when you have a long-lived
    :class:`~skill_extractor.config.SkillExtractorConfig` and don't
    want to thread the weight dicts through call sites. The pure
    :func:`compute_confidence` is the canonical entry point and is
    used directly in the test suite.
    """

    def __init__(self, config: SkillExtractorConfig | None = None) -> None:
        self._config = config or SkillExtractorConfig()

    def compute(
        self,
        *,
        section: SectionLabel,
        match_kind: MatchKind,
        frequency: int,
    ) -> float:
        """See :func:`compute_confidence`."""
        return compute_confidence(
            section=section,
            match_kind=match_kind,
            frequency=frequency,
            section_weights=self._config.section_weights,
            match_quality_weights=self._config.match_quality_weights,
        )
