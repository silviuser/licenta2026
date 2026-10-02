"""Tests for the Romanian-label overlay (``overlays/multilingual.py``).

The overlay folds ESCO Romanian surface forms onto the English concepts so
the Module 2 PhraseMatcher can recognise Romanian-language skills. These
tests cover the two public functions plus the diacritic-folding / junk-
filtering behaviour, using small in-memory CSVs (no real ESCO bundle, no
spaCy) so they run in milliseconds.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from skill_extractor.exceptions import EscoLoadError
from skill_extractor.models import EscoSkill
from skill_extractor.overlays.multilingual import (
    apply_ro_labels,
    load_ro_label_surfaces,
)

_DB_URI = "http://data.europa.eu/esco/skill/db-test"


def _write_ro_csv(path: Path, rows: list[tuple[str, str, str]]) -> None:
    """Write a minimal ``skills_ro.csv`` with the columns the overlay reads."""
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["conceptUri", "preferredLabel", "altLabels"])
        for uri, pref, alts in rows:
            writer.writerow([uri, pref, alts])


# ---------------------------------------------------------------------------
# load_ro_label_surfaces
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    """A non-existent bundle degrades gracefully to an empty overlay."""
    assert load_ro_label_surfaces(tmp_path / "nope.csv") == {}


def test_load_missing_columns_raises(tmp_path: Path) -> None:
    """A structurally wrong file fails fast rather than silently empty."""
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(EscoLoadError):
        load_ro_label_surfaces(bad)


def test_load_extracts_preferred_and_alt_labels(tmp_path: Path) -> None:
    path = tmp_path / "skills_ro.csv"
    _write_ro_csv(
        path,
        [
            (
                _DB_URI,
                "bază de date",
                "baze de date relaționale\ntipuri de baze de date",
            )
        ],
    )
    surfaces = load_ro_label_surfaces(path)
    got = {s.lower() for s in surfaces[_DB_URI]}
    assert "bază de date" in got
    assert "baze de date relaționale" in got
    assert "tipuri de baze de date" in got


def test_load_adds_diacritic_free_variant(tmp_path: Path) -> None:
    """Every accented surface also yields an ASCII-folded variant — Romanian
    CVs are routinely typed without diacritics."""
    path = tmp_path / "skills_ro.csv"
    _write_ro_csv(path, [(_DB_URI, "bază de date", "")])
    got = {s.lower() for s in load_ro_label_surfaces(path)[_DB_URI]}
    assert "bază de date" in got  # original
    assert "baza de date" in got  # folded


def test_load_drops_numeric_and_single_char_junk(tmp_path: Path) -> None:
    """The RO bundle has stray cells such as ``0.0``; they must not become
    match patterns."""
    path = tmp_path / "skills_ro.csv"
    _write_ro_csv(path, [(_DB_URI, "bază de date", "0.0\nx\n3.14")])
    got = {s.lower() for s in load_ro_label_surfaces(path)[_DB_URI]}
    assert "0.0" not in got
    assert "3.14" not in got
    assert "x" not in got


# ---------------------------------------------------------------------------
# apply_ro_labels
# ---------------------------------------------------------------------------


def _skill(uri: str, pref: str, alts: list[str] | None = None) -> EscoSkill:
    return EscoSkill(
        concept_uri=uri,
        preferred_label=pref,
        alt_labels=alts or [],
        skill_type="knowledge",
    )


def test_apply_merges_by_uri_non_destructively() -> None:
    skills = [_skill(_DB_URI, "database", ["relational database"])]
    surfaces = {_DB_URI: ["bază de date", "baza de date"]}

    merged = apply_ro_labels(skills, surfaces)

    # Input list is not mutated.
    assert skills[0].alt_labels == ["relational database"]
    # URI + canonical English label are preserved; RO surfaces are added.
    out = merged[0]
    assert out.concept_uri == _DB_URI
    assert out.preferred_label == "database"
    assert "relational database" in out.alt_labels
    assert "bază de date" in out.alt_labels
    assert "baza de date" in out.alt_labels


def test_apply_dedupes_case_insensitively() -> None:
    skills = [_skill(_DB_URI, "database", ["Relational Database"])]
    merged = apply_ro_labels(skills, {_DB_URI: ["relational database"]})
    lowered = [a.lower() for a in merged[0].alt_labels]
    assert lowered.count("relational database") == 1


def test_apply_skips_romanian_only_uris() -> None:
    """RO concepts with no English counterpart are skipped (this overlay
    augments existing concepts, it does not introduce new ones)."""
    skills = [_skill(_DB_URI, "database")]
    merged = apply_ro_labels(
        skills,
        {"http://data.europa.eu/esco/skill/ghost": ["fantomă"]},
    )
    assert len(merged) == 1
    assert merged[0].alt_labels == []


def test_apply_empty_overlay_is_noop() -> None:
    skills = [_skill(_DB_URI, "database")]
    merged = apply_ro_labels(skills, {})
    assert merged[0].alt_labels == []
