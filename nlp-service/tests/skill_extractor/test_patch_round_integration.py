"""End-to-end integration tests for the May-2026 patch round.

Uses ``spacy.blank("en")`` plus a tiny inline ESCO bundle so the tests
run in seconds without requiring a downloaded language model. The
production pipeline integration with full models is exercised by
``test_pipeline_e2e.py`` and by ``scripts/skill_extraction_validation.py``.

Each test below targets one of the five deliverables of the patch
round (tech aliases, suppression, custom overlay, slash segmentation,
language section) by constructing the smallest possible CV text that
exercises that deliverable in isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

spacy = pytest.importorskip("spacy")

from skill_extractor.config import SkillExtractorConfig  # noqa: E402
from skill_extractor.esco.loader import EscoLoader  # noqa: E402
from skill_extractor.pipeline import SkillExtractor  # noqa: E402

# ---------------------------------------------------------------------------
# Tiny inline ESCO bundle. The URIs match the ones used in the
# shipped tech_aliases.yaml / suppression_rules.yaml so the overlay
# loaders find their targets without us needing the full 13.9k-row
# ESCO bundle for these tests.
# ---------------------------------------------------------------------------

_VB_URI = "http://data.europa.eu/esco/skill/13bdd41a-2a18-441f-96db-41252c519413"
_PG_URI = "http://data.europa.eu/esco/skill/a8d07b5a-c1a1-42c6-9d53-db9c7a2ca996"
_PY_URI = "http://data.europa.eu/esco/skill/ccd0a1d9-afda-43d9-b901-96344886e14d"
_C_URI = "http://data.europa.eu/esco/skill/00000000-0000-0000-0000-c00000000001"
_CPP_URI = "http://data.europa.eu/esco/skill/b633eb55-8f1f-4ae6-ab4c-2022ffe2cb7f"
_THINK_URI = "http://data.europa.eu/esco/skill/c624c6a3-b0ba-4a31-a296-0d433fe47e41"
_IT_URI = "http://data.europa.eu/esco/skill/ddc3119d-1d6e-4324-9125-a3380d299ac5"

_SKILLS_CSV = (
    "conceptType,conceptUri,skillType,reuseLevel,preferredLabel,altLabels,"
    "hiddenLabels,status,modifiedDate,scopeNote,definition,inScheme,description\n"
    f"K,{_PY_URI},knowledge,cs,Python (computer programming),Python,,r,d,,,s,Python.\n"
    f"K,{_PG_URI},knowledge,cs,PostgreSQL,,,r,d,,,s,Postgres.\n"
    f"K,{_VB_URI},knowledge,cs,Visual Basic,.NET|Visual Studio,,r,d,,,s,VB.\n"
    f"K,{_THINK_URI},skill/competence,cs,think creatively,design|designed|designing,,r,d,,,s,T.\n"
    f"K,{_IT_URI},knowledge,cs,computer technology,IT,,r,d,,,s,IT.\n"
    f"K,{_C_URI},knowledge,cs,C,,,r,d,,,s,C language.\n"
    f"K,{_CPP_URI},knowledge,cs,C++,,,r,d,,,s,C plus plus.\n"
)

_LANGUAGE_CSV = (
    "conceptType,conceptUri,skillType,reuseLevel,preferredLabel,status,"
    "altLabels,description,broaderConceptUri,broaderConceptPT\n"
)


@pytest.fixture
def esco_dir(tmp_path: Path) -> Path:
    (tmp_path / EscoLoader.SKILLS_FILE).write_text(_SKILLS_CSV, encoding="utf-8")
    (tmp_path / EscoLoader.LANGUAGE_FILE).write_text(_LANGUAGE_CSV, encoding="utf-8")
    return tmp_path


@pytest.fixture
def tech_aliases_yaml(tmp_path: Path) -> Path:
    body = dedent(
        f"""\
        aliases:
          - target_uri: {_PG_URI}
            preferred_label: PostgreSQL
            surfaces: [Postgres, postgres]
            reason: alias test
        """
    )
    path = tmp_path / "tech_aliases.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def suppression_yaml(tmp_path: Path) -> Path:
    body = dedent(
        f"""\
        rules:
          - surface_pattern: ".NET"
            target_concept_uri: {_VB_URI}
            reason: ".NET → Visual Basic"
          - surface_pattern: "Visual Studio"
            target_concept_uri: {_VB_URI}
            reason: "Visual Studio → Visual Basic"
          - surface_pattern: "design"
            target_concept_uri: {_THINK_URI}
            context_required:
              forbidden_surrounding_terms_any: ["graphic design", "Canva", "Figma"]
              surrounding_window_chars: 80
            reason: "design verb is not 'think creatively'"
          - surface_pattern: "designed"
            target_concept_uri: {_THINK_URI}
            context_required:
              forbidden_surrounding_terms_any: ["graphic design", "Canva", "Figma"]
              surrounding_window_chars: 80
            reason: "designed is the past tense — same rule"
          - surface_pattern: "designing"
            target_concept_uri: {_THINK_URI}
            context_required:
              forbidden_surrounding_terms_any: ["graphic design", "Canva", "Figma"]
              surrounding_window_chars: 80
            reason: "designing is the gerund — same rule"
          - surface_pattern: "It"
            case_sensitive: true
            target_concept_uri: {_IT_URI}
            reason: "pronoun It"
        """
    )
    path = tmp_path / "suppression_rules.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def custom_json(tmp_path: Path) -> Path:
    payload = {
        "concepts": [
            {
                "id": "CUST:docker",
                "preferred_label": "Docker",
                "alt_labels": ["docker"],
                "skill_type": "knowledge",
                "description": "Container runtime.",
                "source_url": "https://docker.com",
            },
            {
                "id": "CUST:react",
                "preferred_label": "React",
                "alt_labels": ["React.js"],
                "skill_type": "knowledge",
                "description": "JS library.",
                "source_url": "https://react.dev",
            },
        ]
    }
    path = tmp_path / "custom_concepts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def config(
    esco_dir: Path,
    tmp_path: Path,
    tech_aliases_yaml: Path,
    suppression_yaml: Path,
    custom_json: Path,
) -> SkillExtractorConfig:
    return SkillExtractorConfig(
        esco_dir=esco_dir,
        cache_dir=tmp_path / "matcher_cache",
        phrase_attr="LOWER",  # blank pipelines have no lemmatiser
        tech_aliases_path=tech_aliases_yaml,
        suppression_rules_path=suppression_yaml,
        custom_concepts_path=custom_json,
    )


@pytest.fixture
def extractor(config: SkillExtractorConfig) -> SkillExtractor:
    return SkillExtractor(
        config=config,
        nlp_factory=lambda lang: spacy.blank("en" if lang == "en" else "ro"),
    )


# ---------------------------------------------------------------------------
# Deliverable 1: tech aliases bring Postgres → PostgreSQL URI
# ---------------------------------------------------------------------------


def test_tech_alias_picks_up_postgres(extractor: SkillExtractor) -> None:
    text = "Skills\nPython, Postgres, SQL\n"
    result = extractor.extract((text, "en"))
    uris = {s.esco_uri for s in result.skills}
    assert _PG_URI in uris, f"Postgres alias should surface PostgreSQL URI; got {uris}"


# ---------------------------------------------------------------------------
# Deliverable 2: suppression filters
# ---------------------------------------------------------------------------


def test_dotnet_does_not_become_visual_basic(extractor: SkillExtractor) -> None:
    text = "Skills\nC# .NET, Python\n"
    result = extractor.extract((text, "en"))
    labels = {s.preferred_label for s in result.skills}
    assert "Visual Basic" not in labels, (
        ".NET surface should NOT map to Visual Basic"
    )


def test_visual_studio_does_not_become_visual_basic(
    extractor: SkillExtractor,
) -> None:
    text = "Tools\nUsed Visual Studio to build\n"
    result = extractor.extract((text, "en"))
    labels = {s.preferred_label for s in result.skills}
    assert "Visual Basic" not in labels


def test_design_verb_is_not_think_creatively(extractor: SkillExtractor) -> None:
    text = "Profile\nI designed and implemented backend microservices.\n"
    result = extractor.extract((text, "en"))
    labels = {s.preferred_label for s in result.skills}
    assert "think creatively" not in labels


def test_design_in_graphic_design_context_kept(extractor: SkillExtractor) -> None:
    """The Graphic Design Artist TP must survive the suppression."""
    text = "Experience\nGraphic design: I designed posters in Canva\n"
    result = extractor.extract((text, "en"))
    labels = {s.preferred_label for s in result.skills}
    assert "think creatively" in labels


def test_pronoun_It_is_not_IT(extractor: SkillExtractor) -> None:
    text = "Profile\nIt is a fine day for shipping\n"
    result = extractor.extract((text, "en"))
    uris = {s.esco_uri for s in result.skills}
    assert _IT_URI not in uris


# ---------------------------------------------------------------------------
# Deliverable 3: custom overlay
# ---------------------------------------------------------------------------


def test_custom_concept_docker_detected(extractor: SkillExtractor) -> None:
    text = "Skills\nPython, Docker\n"
    result = extractor.extract((text, "en"))
    custom = [s for s in result.skills if s.is_custom]
    docker = next((s for s in custom if s.preferred_label == "Docker"), None)
    assert docker is not None
    assert docker.esco_uri == "CUST:docker"
    assert docker.is_custom is True


def test_custom_concept_react_via_alt_label(extractor: SkillExtractor) -> None:
    text = "Skills\nReact.js, Python\n"
    result = extractor.extract((text, "en"))
    react = next(
        (s for s in result.skills if s.preferred_label == "React"), None
    )
    assert react is not None
    assert react.is_custom is True


# ---------------------------------------------------------------------------
# Deliverable 4: slash segmenter
# ---------------------------------------------------------------------------


def test_c_cpp_slash_split(extractor: SkillExtractor) -> None:
    text = "Skills\nC/C++, Python\n"
    result = extractor.extract((text, "en"))
    uris = {s.esco_uri for s in result.skills}
    assert _C_URI in uris, "C must surface"
    assert _CPP_URI in uris, "C++ must surface"


def test_unknown_slash_token_not_split(extractor: SkillExtractor) -> None:
    text = "Skills\nclient/server, Python\n"
    result = extractor.extract((text, "en"))
    # No new noise — only Python in the limited fixture vocab.
    labels = {s.preferred_label for s in result.skills}
    assert "Python (computer programming)" in labels


# ---------------------------------------------------------------------------
# Deliverable 5: language section
# ---------------------------------------------------------------------------


def test_language_section_b2(extractor: SkillExtractor) -> None:
    text = "Languages\nEnglish (B2)\nRomanian (native)\n"
    result = extractor.extract((text, "en"))
    en = next(
        (s for s in result.skills if s.preferred_label == "English"), None
    )
    assert en is not None
    assert en.skill_type == "language"
    assert en.cefr_level == "B2"
    ro = next(
        (s for s in result.skills if s.preferred_label == "Romanian"), None
    )
    assert ro is not None
    assert ro.cefr_level == "native"


def test_language_fluent_label(extractor: SkillExtractor) -> None:
    text = "Languages\nEnglish (fluent)\n"
    result = extractor.extract((text, "en"))
    en = next(
        (s for s in result.skills if s.preferred_label == "English"), None
    )
    assert en is not None
    assert en.cefr_level == "fluent"


# ---------------------------------------------------------------------------
# Config flags — disabling an overlay must produce the unpatched behaviour
# ---------------------------------------------------------------------------


def test_disable_suppression_brings_back_dotnet_fp(
    esco_dir: Path,
    tmp_path: Path,
    tech_aliases_yaml: Path,
    suppression_yaml: Path,
    custom_json: Path,
) -> None:
    cfg = SkillExtractorConfig(
        esco_dir=esco_dir,
        cache_dir=tmp_path / "cache_off",
        phrase_attr="LOWER",
        tech_aliases_path=tech_aliases_yaml,
        suppression_rules_path=suppression_yaml,
        custom_concepts_path=custom_json,
        enable_suppression=False,
    )
    ext = SkillExtractor(
        config=cfg,
        nlp_factory=lambda lang: spacy.blank("en" if lang == "en" else "ro"),
    )
    text = "Skills\nC# .NET, Python\n"
    result = ext.extract((text, "en"))
    labels = {s.preferred_label for s in result.skills}
    assert "Visual Basic" in labels


def test_disable_custom_overlay_hides_docker(
    esco_dir: Path,
    tmp_path: Path,
    tech_aliases_yaml: Path,
    suppression_yaml: Path,
    custom_json: Path,
) -> None:
    cfg = SkillExtractorConfig(
        esco_dir=esco_dir,
        cache_dir=tmp_path / "cache_off2",
        phrase_attr="LOWER",
        tech_aliases_path=tech_aliases_yaml,
        suppression_rules_path=suppression_yaml,
        custom_concepts_path=custom_json,
        enable_custom_overlay=False,
    )
    ext = SkillExtractor(
        config=cfg,
        nlp_factory=lambda lang: spacy.blank("en" if lang == "en" else "ro"),
    )
    text = "Skills\nPython, Docker\n"
    result = ext.extract((text, "en"))
    labels = {s.preferred_label for s in result.skills}
    assert "Docker" not in labels


def test_disable_language_section(
    esco_dir: Path,
    tmp_path: Path,
    tech_aliases_yaml: Path,
    suppression_yaml: Path,
    custom_json: Path,
) -> None:
    cfg = SkillExtractorConfig(
        esco_dir=esco_dir,
        cache_dir=tmp_path / "cache_off3",
        phrase_attr="LOWER",
        tech_aliases_path=tech_aliases_yaml,
        suppression_rules_path=suppression_yaml,
        custom_concepts_path=custom_json,
        enable_language_section=False,
    )
    ext = SkillExtractor(
        config=cfg,
        nlp_factory=lambda lang: spacy.blank("en" if lang == "en" else "ro"),
    )
    text = "Languages\nEnglish (B2)\n"
    result = ext.extract((text, "en"))
    langs = [s for s in result.skills if s.skill_type == "language"]
    assert langs == []


def test_disable_slash_segmentation_skips_rewrite(
    esco_dir: Path,
    tmp_path: Path,
    tech_aliases_yaml: Path,
    suppression_yaml: Path,
    custom_json: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``enable_slash_segmentation=False`` MUST bypass the segmenter call.

    We assert by spying on the segmenter's :meth:`segment` method —
    whether the underlying tokenizer happens to split slashes anyway is
    model-dependent and not what this test is asserting.
    """
    cfg = SkillExtractorConfig(
        esco_dir=esco_dir,
        cache_dir=tmp_path / "cache_off4",
        phrase_attr="LOWER",
        tech_aliases_path=tech_aliases_yaml,
        suppression_rules_path=suppression_yaml,
        custom_concepts_path=custom_json,
        enable_slash_segmentation=False,
    )
    ext = SkillExtractor(
        config=cfg,
        nlp_factory=lambda lang: spacy.blank("en" if lang == "en" else "ro"),
    )
    calls: list[str] = []

    real_segment_attr = "_ensure_slash_segmenter"
    real_segment = getattr(ext, real_segment_attr)

    def spy() -> object:  # pragma: no cover — invoked only if the flag was True
        calls.append("ensure")
        return real_segment()

    monkeypatch.setattr(ext, real_segment_attr, spy)
    ext.extract(("Skills\nC/C++\n", "en"))
    assert calls == [], "Slash segmenter must not be invoked when flag is False"
