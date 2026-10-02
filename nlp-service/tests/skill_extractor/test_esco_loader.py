"""Unit tests for :mod:`skill_extractor.esco.loader`.

These tests use small inline CSV fixtures, never the real ESCO bundle,
so they execute in milliseconds and are stable across ESCO version bumps.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from skill_extractor.config import SkillExtractorConfig
from skill_extractor.esco.loader import EscoLoader
from skill_extractor.exceptions import EscoLoadError

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

# Minimal but representative skills_en.csv covering:
# - knowledge skill with multiple altLabels separated by \n
# - skill/competence with newline-separated altLabels
# - empty altLabels cell
# - row that will later be language-overridden
# Header must include all columns the loader requires.
_SKILLS_CSV = dedent(
    """\
    conceptType,conceptUri,skillType,reuseLevel,preferredLabel,altLabels,hiddenLabels,status,modifiedDate,scopeNote,definition,inScheme,description
    KnowledgeSkillCompetence,uri:python,knowledge,cross-sector,Python (computer programming),"Python3
    Python 3
    py
    Python",,released,2024-01-01,,,scheme,The Python language.
    KnowledgeSkillCompetence,uri:manage-staff,skill/competence,sector-specific,manage musical staff,"manage music staff
    coordinate duties of musical staff",,released,2024-01-01,,,scheme,Manage staff in music settings.
    KnowledgeSkillCompetence,uri:short,knowledge,transversal,SQL,,,released,2024-01-01,,,scheme,Structured Query Language.
    KnowledgeSkillCompetence,uri:write-en,skill/competence,transversal,write English,"correspond in written English
    show competency in written English",,released,2024-01-01,,,scheme,Compose written texts in English.
    KnowledgeSkillCompetence,uri:bad-type,bogus-type,transversal,Strange Skill,,,released,2024-01-01,,,scheme,A skill with a bad type cell.
    """
)

# Language collection uses ` | ` as separator and a different column order.
# - uri:write-en is in the primary file → its skill_type must become "language"
# - uri:speak-fr does NOT exist in primary → must be added as a new EscoSkill
_LANGUAGE_CSV = dedent(
    """\
    conceptType,conceptUri,skillType,reuseLevel,preferredLabel,status,altLabels,description,broaderConceptUri,broaderConceptPT
    KnowledgeSkillCompetence,uri:write-en,skill/competence,transversal,write English,released,correspond in written English | show competency in written English,Compose written texts in English.,uri:english,English
    KnowledgeSkillCompetence,uri:speak-fr,skill/competence,transversal,speak French,released,communicate in French | converse in French,Speak French.,uri:french,French
    """
)


@pytest.fixture
def esco_dir(tmp_path: Path) -> Path:
    """Materialise a minimal ESCO bundle directory in tmp_path."""
    (tmp_path / EscoLoader.SKILLS_FILE).write_text(_SKILLS_CSV, encoding="utf-8")
    (tmp_path / EscoLoader.LANGUAGE_FILE).write_text(
        _LANGUAGE_CSV, encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def loader(esco_dir: Path) -> EscoLoader:
    return EscoLoader(SkillExtractorConfig(esco_dir=esco_dir))


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_load_returns_all_rows(loader: EscoLoader) -> None:
    """5 rows in the primary CSV + 1 language-only addition = 6 skills."""
    skills = loader.load()
    assert len(skills) == 6


def test_load_is_sorted_by_uri(loader: EscoLoader) -> None:
    skills = loader.load()
    uris = [s.concept_uri for s in skills]
    assert uris == sorted(uris)


def test_python_skill_alt_labels_parsed_intact(loader: EscoLoader) -> None:
    """All four altLabels from the multi-line cell survive the parse."""
    skills = {s.concept_uri: s for s in loader.load()}
    py = skills["uri:python"]
    assert py.preferred_label == "Python (computer programming)"
    assert py.skill_type == "knowledge"
    # Preferred label is "Python (computer programming)", which does NOT
    # equal any altLabel case-insensitively, so all four are preserved.
    assert set(py.alt_labels) == {"Python3", "Python 3", "py", "Python"}


def test_alt_labels_drop_when_equal_to_preferred_label(tmp_path: Path) -> None:
    """An altLabel that equals the preferred label (case-insensitive) is
    silently dropped to avoid duplicate matcher patterns later."""
    csv_text = (
        "conceptType,conceptUri,skillType,reuseLevel,preferredLabel,"
        "altLabels,hiddenLabels,status,modifiedDate,scopeNote,"
        "definition,inScheme,description\n"
        'X,uri:java,knowledge,t,Java,"Java\nJAVA\njava\nJAVA SE",,'
        "released,2024-01-01,,,scheme,desc\n"
    )
    (tmp_path / EscoLoader.SKILLS_FILE).write_text(csv_text, encoding="utf-8")
    loader = EscoLoader(SkillExtractorConfig(esco_dir=tmp_path))
    skills = loader.load()
    assert len(skills) == 1
    java = skills[0]
    # All three case variants of "java" drop (== preferred label "Java");
    # only "JAVA SE" survives.
    assert java.alt_labels == ["JAVA SE"]


def test_alt_labels_dedup_case_insensitive(tmp_path: Path) -> None:
    """Duplicates differing only in case collapse to a single entry,
    with the first-seen casing preserved."""
    csv_text = (
        "conceptType,conceptUri,skillType,reuseLevel,preferredLabel,"
        "altLabels,hiddenLabels,status,modifiedDate,scopeNote,"
        "definition,inScheme,description\n"
        'X,uri:dup,knowledge,t,Kubernetes,"k8s\nK8S\nK8s\nKUBE",,'
        "released,2024-01-01,,,scheme,desc\n"
    )
    (tmp_path / EscoLoader.SKILLS_FILE).write_text(csv_text, encoding="utf-8")
    loader = EscoLoader(SkillExtractorConfig(esco_dir=tmp_path))
    skill = loader.load()[0]
    # First seen is "k8s", the next two collapse into it; "KUBE" survives.
    assert skill.alt_labels == ["k8s", "KUBE"]


def test_empty_alt_labels_cell(loader: EscoLoader) -> None:
    skills = {s.concept_uri: s for s in loader.load()}
    sql = skills["uri:short"]
    assert sql.alt_labels == []


def test_bad_skill_type_normalises_to_competence(loader: EscoLoader) -> None:
    skills = {s.concept_uri: s for s in loader.load()}
    bad = skills["uri:bad-type"]
    assert bad.skill_type == "skill/competence"


# ---------------------------------------------------------------------------
# Language-overlay behaviour
# ---------------------------------------------------------------------------


def test_language_overlay_overrides_existing_uri(loader: EscoLoader) -> None:
    """``uri:write-en`` exists in primary as ``skill/competence`` and must
    be flipped to ``language`` by the overlay."""
    skills = {s.concept_uri: s for s in loader.load()}
    write_en = skills["uri:write-en"]
    assert write_en.skill_type == "language"
    # Other fields preserved from the primary row.
    assert write_en.preferred_label == "write English"


def test_language_overlay_adds_missing_uri(loader: EscoLoader) -> None:
    """``uri:speak-fr`` is only in the overlay → must be present with
    ``skill_type='language'`` and altLabels parsed via the ` | ` separator."""
    skills = {s.concept_uri: s for s in loader.load()}
    fr = skills["uri:speak-fr"]
    assert fr.skill_type == "language"
    assert fr.preferred_label == "speak French"
    assert "communicate in French" in fr.alt_labels
    assert "converse in French" in fr.alt_labels


def test_missing_language_overlay_is_non_fatal(tmp_path: Path) -> None:
    """If the language collection file is absent, loader still returns
    the primary skills (with no overrides)."""
    (tmp_path / EscoLoader.SKILLS_FILE).write_text(
        _SKILLS_CSV, encoding="utf-8"
    )
    loader = EscoLoader(SkillExtractorConfig(esco_dir=tmp_path))
    skills = loader.load()
    assert len(skills) == 5
    # uri:write-en stays at its native type because no overlay applied.
    by_uri = {s.concept_uri: s for s in skills}
    assert by_uri["uri:write-en"].skill_type == "skill/competence"


# ---------------------------------------------------------------------------
# Splitter robustness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        ("   ", []),
        ("a\nb\nc", ["a", "b", "c"]),
        ("a | b | c", ["a", "b", "c"]),
        ("a|b|c", ["a", "b", "c"]),
        ("a; b ;c", ["a", "b", "c"]),
        ("a\nb | c;d", ["a", "b", "c", "d"]),
        ("\n\na\n\n", ["a"]),
        ("only-one", ["only-one"]),
    ],
)
def test_split_alt_labels(raw: str, expected: list[str]) -> None:
    assert EscoLoader._split_alt_labels(raw) == expected


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_skills_file_raises(tmp_path: Path) -> None:
    loader = EscoLoader(SkillExtractorConfig(esco_dir=tmp_path))
    with pytest.raises(EscoLoadError) as excinfo:
        loader.load()
    assert "skills_en.csv" in str(excinfo.value)
    assert excinfo.value.path is not None


def test_missing_required_column_raises(tmp_path: Path) -> None:
    """A header without ``preferredLabel`` is rejected up-front."""
    bad_csv = "conceptType,conceptUri,skillType,reuseLevel,altLabels,description\n"
    (tmp_path / EscoLoader.SKILLS_FILE).write_text(bad_csv, encoding="utf-8")
    loader = EscoLoader(SkillExtractorConfig(esco_dir=tmp_path))
    with pytest.raises(EscoLoadError) as excinfo:
        loader.load()
    assert "preferredLabel" in str(excinfo.value)


def test_empty_skills_file_raises(tmp_path: Path) -> None:
    """Header-only CSV is rejected to catch truncation early."""
    header_only = (
        "conceptType,conceptUri,skillType,reuseLevel,preferredLabel,"
        "altLabels,hiddenLabels,status,modifiedDate,scopeNote,"
        "definition,inScheme,description\n"
    )
    (tmp_path / EscoLoader.SKILLS_FILE).write_text(
        header_only, encoding="utf-8"
    )
    loader = EscoLoader(SkillExtractorConfig(esco_dir=tmp_path))
    with pytest.raises(EscoLoadError) as excinfo:
        loader.load()
    assert "zero rows" in str(excinfo.value)


def test_missing_uri_or_label_row_skipped(tmp_path: Path) -> None:
    """Rows missing either ``conceptUri`` or ``preferredLabel`` are
    skipped silently rather than aborting the entire load."""
    csv_text = (
        "conceptType,conceptUri,skillType,reuseLevel,preferredLabel,"
        "altLabels,hiddenLabels,status,modifiedDate,scopeNote,"
        "definition,inScheme,description\n"
        "X,uri:ok,knowledge,t,Good,,,,,,,,desc\n"
        "X,,knowledge,t,Bad-NoUri,,,,,,,,desc\n"
        "X,uri:bad,knowledge,t,,,,,,,,,desc\n"
    )
    (tmp_path / EscoLoader.SKILLS_FILE).write_text(csv_text, encoding="utf-8")
    loader = EscoLoader(SkillExtractorConfig(esco_dir=tmp_path))
    skills = loader.load()
    assert len(skills) == 1
    assert skills[0].concept_uri == "uri:ok"


# ---------------------------------------------------------------------------
# Real ESCO bundle smoke test
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_real_esco_bundle_loads() -> None:
    """End-to-end smoke test against the real ESCO data shipped with
    the repo. Marked ``slow`` because parsing 13.9k skills takes a few
    seconds; run by default but skippable with ``-m "not slow"``."""
    skills = EscoLoader().load()
    assert len(skills) > 13_000
    # Sanity: at least a few language overrides applied.
    languages = [s for s in skills if s.skill_type == "language"]
    assert len(languages) > 100, (
        f"Expected the language overlay to mark at least 100 skills "
        f"as 'language', got {len(languages)}."
    )
    # Every skill has a non-empty preferred_label and concept_uri.
    for s in skills[:100]:
        assert s.preferred_label
        assert s.concept_uri.startswith("http")
