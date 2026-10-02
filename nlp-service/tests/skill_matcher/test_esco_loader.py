"""Tests for :mod:`skill_matcher.esco_loader`.

Fast tests use small inline CSV / JSON fixtures so the suite stays in
the sub-second range and is stable across ESCO version bumps. The
real ESCO bundle is exercised by the slow ``test_esco_index.py``
suite and by the baseline runner.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.esco.loader import EscoLoader
from skill_matcher.esco_loader import (
    EscoConcept,
    compute_esco_file_sha,
    compute_esco_sha,
    load_esco_concepts,
)

# ---------------------------------------------------------------------------
# Fixture builders — minimal but representative ESCO + custom overlay
# ---------------------------------------------------------------------------

_SKILLS_CSV = dedent(
    """\
    conceptType,conceptUri,skillType,reuseLevel,preferredLabel,altLabels,hiddenLabels,status,modifiedDate,scopeNote,definition,inScheme,description
    KnowledgeSkillCompetence,uri:python,knowledge,cross-sector,Python (computer programming),"Python3
    py
    Python",,released,2024-01-01,,,scheme,The Python language.
    KnowledgeSkillCompetence,uri:sql,knowledge,transversal,SQL,,,released,2024-01-01,,,scheme,Structured Query Language.
    KnowledgeSkillCompetence,uri:write-en,skill/competence,transversal,write English,"correspond in written English",,released,2024-01-01,,,scheme,Compose written texts in English.
    """
)

_LANGUAGE_CSV = dedent(
    """\
    conceptType,conceptUri,skillType,reuseLevel,preferredLabel,status,altLabels,description,broaderConceptUri,broaderConceptPT
    KnowledgeSkillCompetence,uri:write-en,skill/competence,transversal,write English,released,correspond in written English,Compose written texts in English.,uri:english,English
    """
)


def _custom_concepts_json() -> str:
    return json.dumps(
        {
            "concepts": [
                {
                    "id": "CUST:docker",
                    "preferred_label": "Docker",
                    "alt_labels": ["containerd", "Docker Engine"],
                    "skill_type": "knowledge",
                    "description": "Container runtime and image format.",
                    "source_url": "https://docker.com",
                },
                {
                    "id": "CUST:react",
                    "preferred_label": "React",
                    "alt_labels": ["ReactJS"],
                    "skill_type": "knowledge",
                    "description": "JavaScript UI library.",
                    "source_url": "https://react.dev",
                },
            ]
        }
    )


@pytest.fixture
def fixture_config(tmp_path: Path) -> SkillExtractorConfig:
    """A :class:`SkillExtractorConfig` pointing at fixture ESCO + custom files."""
    esco_dir = tmp_path / "esco"
    esco_dir.mkdir()
    (esco_dir / EscoLoader.SKILLS_FILE).write_text(_SKILLS_CSV, encoding="utf-8")
    (esco_dir / EscoLoader.LANGUAGE_FILE).write_text(
        _LANGUAGE_CSV, encoding="utf-8"
    )
    custom_path = tmp_path / "custom_concepts.json"
    custom_path.write_text(_custom_concepts_json(), encoding="utf-8")
    return SkillExtractorConfig(
        esco_dir=esco_dir,
        custom_concepts_path=custom_path,
    )


# ---------------------------------------------------------------------------
# load_esco_concepts
# ---------------------------------------------------------------------------


def test_load_returns_ordered_concepts(fixture_config: SkillExtractorConfig) -> None:
    """Output is sorted by URI for determinism."""
    concepts = load_esco_concepts(config=fixture_config)
    uris = [c.uri for c in concepts]
    assert uris == sorted(uris)


def test_load_includes_custom_overlay_by_default(
    fixture_config: SkillExtractorConfig,
) -> None:
    """Custom-overlay concepts are folded in unless explicitly disabled."""
    concepts = load_esco_concepts(config=fixture_config)
    cust = [c for c in concepts if c.is_custom]
    assert {c.uri for c in cust} == {"CUST:docker", "CUST:react"}


def test_load_can_exclude_custom_overlay(
    fixture_config: SkillExtractorConfig,
) -> None:
    """Ablation flag must work — pure-ESCO universe is reachable."""
    concepts = load_esco_concepts(
        config=fixture_config, include_custom_overlay=False
    )
    assert not any(c.is_custom for c in concepts)
    assert all(c.uri.startswith("uri:") for c in concepts)


def test_load_preserves_module2_skill_type_literal(
    fixture_config: SkillExtractorConfig,
) -> None:
    """``skill_type`` stays in Module 2's vocabulary (Q2 decision).

    The language overlay must have rewritten ``uri:write-en`` to
    ``"language"``; the custom Docker entry's declared ``"knowledge"``
    must survive verbatim.
    """
    concepts = load_esco_concepts(config=fixture_config)
    by_uri = {c.uri: c for c in concepts}
    assert by_uri["uri:write-en"].skill_type == "language"
    assert by_uri["uri:python"].skill_type == "knowledge"
    assert by_uri["CUST:docker"].skill_type == "knowledge"


def test_load_projects_alt_labels_as_immutable_tuple(
    fixture_config: SkillExtractorConfig,
) -> None:
    """``alt_labels`` is a tuple so EscoConcept stays hashable."""
    concepts = load_esco_concepts(config=fixture_config)
    by_uri = {c.uri: c for c in concepts}
    assert isinstance(by_uri["uri:python"].alt_labels, tuple)
    # The python fixture has 3 altLabels in the CSV ("Python3", "py", "Python");
    # the preferred label is "Python (computer programming)" so none are dropped.
    assert "Python3" in by_uri["uri:python"].alt_labels


def test_load_is_deterministic_across_calls(
    fixture_config: SkillExtractorConfig,
) -> None:
    """Two calls produce byte-identical tuple representations."""
    first = load_esco_concepts(config=fixture_config)
    second = load_esco_concepts(config=fixture_config)
    assert first == second


# ---------------------------------------------------------------------------
# EscoConcept dataclass
# ---------------------------------------------------------------------------


def test_esco_concept_is_frozen_and_hashable() -> None:
    """Frozen + hashable = usable as dict keys / set members."""
    c = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=("alpha", "beta"),
        description="",
        skill_type="knowledge",
        is_custom=False,
    )
    # Frozen — cannot mutate.
    with pytest.raises((AttributeError, Exception)):
        c.uri = "y"  # type: ignore[misc]
    # Hashable — usable in a set without TypeError.
    container = {c}
    assert c in container


# ---------------------------------------------------------------------------
# SHA helpers
# ---------------------------------------------------------------------------


def test_compute_esco_file_sha_changes_when_source_changes(
    tmp_path: Path,
) -> None:
    """A byte change in any source file invalidates the cache key."""
    esco_dir = tmp_path / "esco"
    esco_dir.mkdir()
    (esco_dir / EscoLoader.SKILLS_FILE).write_text(_SKILLS_CSV, encoding="utf-8")
    (esco_dir / EscoLoader.LANGUAGE_FILE).write_text(
        _LANGUAGE_CSV, encoding="utf-8"
    )
    custom = tmp_path / "custom.json"
    custom.write_text(_custom_concepts_json(), encoding="utf-8")
    cfg = SkillExtractorConfig(esco_dir=esco_dir, custom_concepts_path=custom)

    sha_before = compute_esco_file_sha(config=cfg)
    # Mutate the custom-concepts JSON; the file SHA must change.
    custom.write_text(
        json.dumps({"concepts": []}, sort_keys=True), encoding="utf-8"
    )
    sha_after = compute_esco_file_sha(config=cfg)
    assert sha_before != sha_after


def test_compute_esco_file_sha_excluding_custom_differs(
    fixture_config: SkillExtractorConfig,
) -> None:
    """Toggling the custom overlay must change the cache key.

    Otherwise an index built with the overlay would be silently
    served to a caller that asked for the pure-ESCO universe.
    """
    with_custom = compute_esco_file_sha(
        config=fixture_config, include_custom_overlay=True
    )
    without_custom = compute_esco_file_sha(
        config=fixture_config, include_custom_overlay=False
    )
    assert with_custom != without_custom


def test_compute_esco_sha_is_deterministic(
    fixture_config: SkillExtractorConfig,
) -> None:
    """The parsed-concept SHA matches across two loader calls."""
    a = compute_esco_sha(load_esco_concepts(config=fixture_config))
    b = compute_esco_sha(load_esco_concepts(config=fixture_config))
    assert a == b


def test_compute_esco_sha_is_64_hex_chars(
    fixture_config: SkillExtractorConfig,
) -> None:
    """SHA-256 returns a 64-char hex digest unchanged (no truncation)."""
    digest = compute_esco_sha(load_esco_concepts(config=fixture_config))
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


def test_compute_esco_sha_ignores_alt_label_order() -> None:
    """Two concept lists differing only in altLabel order produce
    the same digest — defends against CSV-author drift."""
    c1 = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=("alpha", "beta"),
        description="d",
        skill_type="knowledge",
        is_custom=False,
    )
    c2 = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=("beta", "alpha"),
        description="d",
        skill_type="knowledge",
        is_custom=False,
    )
    assert compute_esco_sha([c1]) == compute_esco_sha([c2])


def test_compute_esco_sha_reflects_skill_type_change() -> None:
    """A skill_type change must change the digest — the loader cannot
    have collapsed Module 2's taxonomy silently."""
    base = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=(),
        description="",
        skill_type="knowledge",
        is_custom=False,
    )
    flipped = EscoConcept(
        uri="x",
        pref_label="X",
        alt_labels=(),
        description="",
        skill_type="skill/competence",
        is_custom=False,
    )
    assert compute_esco_sha([base]) != compute_esco_sha([flipped])
