"""Step 7 eval-corpus adapter — :class:`JDFixture` to ``list[JDRequirement]``.

This module is **not** the production JD parser. The production parser
(future step) will take raw JD text and emit
:class:`~skill_matcher.models.JDRequirement` instances directly, with
URI resolution backed by a JD-side ESCO matcher. Until that ships, the
Step 7 evaluation pipeline uses the eval corpus's hand-curated
``required_skills`` / ``nice_to_have_skills`` lists as JD requirements;
:func:`jd_fixture_to_requirements` is the format adapter that bridges
them.

Coupling note
-------------
This is the only module in :mod:`skill_matcher` that imports
:mod:`skill_matcher.eval_corpus` (an otherwise eval-only loader). The
:func:`jd_fixture_to_requirements` function is therefore the
narrow waist between the eval corpus and the production type
:class:`~skill_matcher.models.JDRequirement`. The production JD parser
will replace it without touching :class:`skill_matcher.scorer.Scorer`
or :class:`skill_matcher.pipeline.SkillMatcher`.

Confidence assignment
---------------------
Eval-corpus JD fixtures store skill labels as plain strings (the
``JDFixture`` schema enforces ``list[str]``). The adapter therefore
assigns ``skill_uri=None`` and ``confidence=0.5`` to every produced
:class:`JDRequirement` — the resolution to a concrete ESCO URI happens
online inside :class:`~skill_matcher.scorer.Scorer.score` via
:meth:`Scorer._resolve_requirement`. ``confidence=0.5`` is the
"medium-confidence" prior; the Scorer's tri-factor product will then
weight the match by the encoder's actual top-1 cosine similarity for
the requirement text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from skill_matcher.models import JDRequirement

if TYPE_CHECKING:
    from skill_matcher.eval_corpus import JDFixture


# Confidence prior assigned to JD requirements parsed from the eval
# corpus's plain-string skill labels. The Scorer overwrites this iff
# the prior is exactly zero and a URI resolution succeeds; otherwise
# the prior is preserved so the tri-factor product reflects the
# reviewer's "medium" confidence in the labelling.
_DEFAULT_UNRESOLVED_CONFIDENCE = 0.5


def jd_fixture_to_requirements(fixture: JDFixture) -> list[JDRequirement]:
    """Convert a :class:`JDFixture` into a list of :class:`JDRequirement`.

    Iterates ``fixture.required_skills`` (yields ``importance="required"``
    entries) followed by ``fixture.nice_to_have_skills`` (yields
    ``importance="nice_to_have"`` entries). Order is preserved within
    each group so the Scorer's per-requirement decisions are stable
    across reruns.

    Parameters
    ----------
    fixture
        A :class:`JDFixture` loaded by
        :func:`skill_matcher.eval_corpus.load_eval_corpus`.

    Returns
    -------
    list[JDRequirement]
        Required requirements first (in YAML order), then nice-to-have
        requirements. Both groups carry ``skill_uri=None`` and
        ``confidence=0.5``; the Scorer resolves URIs at match time.

    Notes
    -----
    Empty input lists produce empty output groups — never raises on
    well-formed input. Per the :class:`JDFixture` pydantic schema,
    ``required_skills`` / ``nice_to_have_skills`` are typed
    ``list[str]``, so this adapter does **not** need to branch on
    dict-form entries; if a future schema bump introduces structured
    entries, this helper is the place to extend.
    """
    requirements: list[JDRequirement] = []

    for text in fixture.required_skills:
        requirements.append(
            JDRequirement(
                text=text,
                skill_uri=None,
                skill_label=None,
                importance="required",
                confidence=_DEFAULT_UNRESOLVED_CONFIDENCE,
            )
        )

    for text in fixture.nice_to_have_skills:
        requirements.append(
            JDRequirement(
                text=text,
                skill_uri=None,
                skill_label=None,
                importance="nice_to_have",
                confidence=_DEFAULT_UNRESOLVED_CONFIDENCE,
            )
        )

    return requirements


__all__ = ["jd_fixture_to_requirements"]
