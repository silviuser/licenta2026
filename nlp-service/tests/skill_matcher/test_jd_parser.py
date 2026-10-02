"""Tests for :mod:`skill_matcher.jd_parser`.

Covers the small format-adapter that bridges :class:`JDFixture` (eval
corpus loader output, plain-string skill labels) to
:class:`JDRequirement` (the production type consumed by the Scorer).
The adapter is intentionally minimal — every Step 7 contract it
preserves is asserted explicitly here.
"""

from __future__ import annotations

from skill_matcher.eval_corpus import JDFixture
from skill_matcher.jd_parser import jd_fixture_to_requirements
from skill_matcher.models import JDRequirement


def _make_fixture(
    *,
    required_skills: list[str] | None = None,
    nice_to_have_skills: list[str] | None = None,
) -> JDFixture:
    """Construct a minimal valid JDFixture for adapter tests."""
    return JDFixture(
        id="jd_test",
        title="Test JD",
        language="en",
        location="",
        category="backend",
        seniority="junior",
        source_anonymized="",
        raw_text="placeholder text body for schema validation",
        required_skills=required_skills if required_skills is not None else [],
        nice_to_have_skills=nice_to_have_skills if nice_to_have_skills is not None else [],
        notes="",
    )


def test_required_only_round_trip() -> None:
    """Plain-string ``required_skills`` produce ``importance='required'``
    requirements with ``skill_uri=None``."""
    fixture = _make_fixture(required_skills=["Java", "Spring", "Maven"])
    reqs = jd_fixture_to_requirements(fixture)

    assert len(reqs) == 3
    assert all(isinstance(r, JDRequirement) for r in reqs)
    assert [r.text for r in reqs] == ["Java", "Spring", "Maven"]
    assert all(r.importance == "required" for r in reqs)
    assert all(r.skill_uri is None for r in reqs)
    assert all(r.skill_label is None for r in reqs)
    assert all(r.confidence == 0.5 for r in reqs)


def test_nice_to_have_only() -> None:
    """Plain-string ``nice_to_have_skills`` produce
    ``importance='nice_to_have'`` requirements."""
    fixture = _make_fixture(nice_to_have_skills=["Kubernetes", "Docker"])
    reqs = jd_fixture_to_requirements(fixture)

    assert len(reqs) == 2
    assert [r.text for r in reqs] == ["Kubernetes", "Docker"]
    assert all(r.importance == "nice_to_have" for r in reqs)


def test_required_then_nice_to_have_ordering() -> None:
    """Required requirements are emitted before nice-to-haves; the
    YAML order is preserved within each group."""
    fixture = _make_fixture(
        required_skills=["Java", "Spring"],
        nice_to_have_skills=["Camel", "JMS"],
    )
    reqs = jd_fixture_to_requirements(fixture)

    assert [r.text for r in reqs] == ["Java", "Spring", "Camel", "JMS"]
    assert [r.importance for r in reqs] == [
        "required",
        "required",
        "nice_to_have",
        "nice_to_have",
    ]


def test_empty_fixture_produces_empty_list() -> None:
    """A fixture with no skills produces an empty list, never raises."""
    fixture = _make_fixture()
    assert jd_fixture_to_requirements(fixture) == []


def test_confidence_default_is_medium_for_unresolved() -> None:
    """Every produced :class:`JDRequirement` carries the 0.5 medium-
    confidence prior so the Scorer's tri-factor product remains
    monotonic in the actual encoder similarity."""
    fixture = _make_fixture(
        required_skills=["X"],
        nice_to_have_skills=["Y"],
    )
    reqs = jd_fixture_to_requirements(fixture)
    assert all(r.confidence == 0.5 for r in reqs)
