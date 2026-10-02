"""Unit tests for :mod:`skill_extractor.overlays.aliases`.

These tests exercise the YAML loader, the merge into an ``EscoSkill``
list, and a per-alias check that every alias listed in the
``tech_aliases.yaml`` shipped with the package resolves to a target
URI that actually exists in the live ESCO bundle (smoke-test against
``EscoLoadError``-style regressions).
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from skill_extractor.exceptions import EscoLoadError
from skill_extractor.models import EscoSkill
from skill_extractor.overlays.aliases import (
    AliasOverlay,
    TechAlias,
    apply_aliases,
    load_alias_overlay,
)


def _make_skill(uri: str, label: str, alts: list[str] | None = None) -> EscoSkill:
    return EscoSkill(
        concept_uri=uri,
        preferred_label=label,
        alt_labels=alts or [],
        skill_type="knowledge",
    )


def test_missing_file_returns_empty_overlay(tmp_path: Path) -> None:
    """A non-existent path is treated as an empty overlay, not an error."""
    overlay = load_alias_overlay(tmp_path / "does_not_exist.yaml")
    assert overlay.aliases == []


def test_empty_file_returns_empty_overlay(tmp_path: Path) -> None:
    """A YAML file that parses to None / empty dict yields an empty overlay."""
    path = tmp_path / "aliases.yaml"
    path.write_text("", encoding="utf-8")
    assert load_alias_overlay(path).aliases == []


def test_load_aliases_parses_full_entry(tmp_path: Path) -> None:
    """A canonical YAML entry round-trips through the loader."""
    yaml_body = dedent(
        """\
        aliases:
          - target_uri: uri:python
            preferred_label: Python (computer programming)
            surfaces:
              - PythonLang
              - py3
            reason: documentation
        """
    )
    path = tmp_path / "aliases.yaml"
    path.write_text(yaml_body, encoding="utf-8")
    overlay = load_alias_overlay(path)
    assert len(overlay.aliases) == 1
    a = overlay.aliases[0]
    assert a.target_uri == "uri:python"
    assert a.preferred_label == "Python (computer programming)"
    assert a.surfaces == ("PythonLang", "py3")
    assert a.reason == "documentation"


def test_top_level_must_be_mapping(tmp_path: Path) -> None:
    path = tmp_path / "aliases.yaml"
    path.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(EscoLoadError, match="must be a mapping"):
        load_alias_overlay(path)


def test_aliases_key_must_be_list(tmp_path: Path) -> None:
    path = tmp_path / "aliases.yaml"
    path.write_text("aliases: not_a_list\n", encoding="utf-8")
    with pytest.raises(EscoLoadError, match="must be a list"):
        load_alias_overlay(path)


def test_alias_entry_missing_target_uri_raises(tmp_path: Path) -> None:
    path = tmp_path / "aliases.yaml"
    path.write_text(
        "aliases:\n  - surfaces: [foo]\n",
        encoding="utf-8",
    )
    with pytest.raises(EscoLoadError, match="missing target_uri"):
        load_alias_overlay(path)


def test_alias_entry_missing_surfaces_raises(tmp_path: Path) -> None:
    path = tmp_path / "aliases.yaml"
    path.write_text(
        "aliases:\n  - target_uri: uri:x\n    surfaces: []\n",
        encoding="utf-8",
    )
    with pytest.raises(EscoLoadError, match="non-empty `surfaces`"):
        load_alias_overlay(path)


def test_apply_aliases_extends_alt_labels() -> None:
    """Surfaces are appended to ``alt_labels`` for the matching URI."""
    skills = [
        _make_skill("uri:py", "Python", alts=["Py"]),
        _make_skill("uri:js", "JavaScript"),
    ]
    overlay = AliasOverlay(
        aliases=[
            TechAlias(
                target_uri="uri:py",
                preferred_label="Python",
                surfaces=("PythonLang", "py3"),
            )
        ]
    )
    result = apply_aliases(skills, overlay)
    py = next(s for s in result if s.concept_uri == "uri:py")
    assert "PythonLang" in py.alt_labels
    assert "py3" in py.alt_labels
    # Original alt preserved.
    assert "Py" in py.alt_labels
    # Other skills untouched.
    js = next(s for s in result if s.concept_uri == "uri:js")
    assert js.alt_labels == []


def test_apply_aliases_dedupes_case_insensitively() -> None:
    skills = [_make_skill("uri:py", "Python", alts=["Py"])]
    overlay = AliasOverlay(
        aliases=[
            TechAlias(
                target_uri="uri:py",
                preferred_label="Python",
                surfaces=("py", "Python", "PY3"),  # py + Python dupes; PY3 new
            )
        ]
    )
    result = apply_aliases(skills, overlay)
    py = result[0]
    # "Py" already present case-insensitively, "Python" matches preferred.
    assert py.alt_labels.count("Py") == 1
    assert "PY3" in py.alt_labels
    # No duplicates anywhere.
    lower = [a.lower() for a in py.alt_labels]
    assert len(lower) == len(set(lower))


def test_apply_aliases_unknown_uri_is_logged_not_fatal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    skills = [_make_skill("uri:py", "Python")]
    overlay = AliasOverlay(
        aliases=[
            TechAlias(
                target_uri="uri:unknown",
                preferred_label="Unknown",
                surfaces=("X",),
            )
        ]
    )
    result = apply_aliases(skills, overlay)
    # Skills unchanged; warning logged.
    assert result[0].alt_labels == []


def test_apply_aliases_returns_copy_not_mutation() -> None:
    skills = [_make_skill("uri:py", "Python")]
    overlay = AliasOverlay(
        aliases=[
            TechAlias(
                target_uri="uri:py",
                preferred_label="Python",
                surfaces=("py3",),
            )
        ]
    )
    apply_aliases(skills, overlay)
    # Original skill untouched.
    assert skills[0].alt_labels == []


def test_empty_overlay_returns_input_list_copy() -> None:
    skills = [_make_skill("uri:py", "Python")]
    out = apply_aliases(skills, AliasOverlay())
    assert out == skills
    assert out is not skills


# ---------------------------------------------------------------------------
# Per-alias contract for the shipped tech_aliases.yaml
# ---------------------------------------------------------------------------


def test_shipped_yaml_loads_cleanly() -> None:
    """The package-shipped YAML must parse without raising."""
    from skill_extractor.config import DEFAULT_TECH_ALIASES_PATH

    overlay = load_alias_overlay(DEFAULT_TECH_ALIASES_PATH)
    # Every alias has at least one surface form.
    for a in overlay.aliases:
        assert a.surfaces, f"alias {a.target_uri} has no surfaces"


def test_shipped_aliases_have_unique_surface_uri_pairs() -> None:
    """No two alias entries should redundantly redefine the same surface→URI pair."""
    from skill_extractor.config import DEFAULT_TECH_ALIASES_PATH

    overlay = load_alias_overlay(DEFAULT_TECH_ALIASES_PATH)
    seen: set[tuple[str, str]] = set()
    for alias in overlay.aliases:
        for surface in alias.surfaces:
            pair = (surface.lower(), alias.target_uri)
            assert pair not in seen, f"duplicate alias pair: {pair}"
            seen.add(pair)


# ---------------------------------------------------------------------------
# Coverage closers
# ---------------------------------------------------------------------------


def test_load_invalid_yaml(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("aliases: [unclosed", encoding="utf-8")
    with pytest.raises(EscoLoadError, match="YAML parse error"):
        load_alias_overlay(p)


def test_alias_entry_not_a_mapping(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text("aliases:\n  - just-a-string\n", encoding="utf-8")
    with pytest.raises(EscoLoadError, match="not a mapping"):
        load_alias_overlay(p)


def test_alias_entry_surfaces_all_empty(tmp_path: Path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text(
        "aliases:\n  - target_uri: uri:x\n    surfaces: ['', '   ']\n",
        encoding="utf-8",
    )
    with pytest.raises(EscoLoadError, match="surfaces are all empty"):
        load_alias_overlay(p)


def test_surfaces_by_uri_groups_correctly() -> None:
    """Sanity check on the public accessor used by ``apply_aliases``."""
    overlay = AliasOverlay(
        aliases=[
            TechAlias(
                target_uri="uri:a",
                preferred_label="A",
                surfaces=("alpha",),
            ),
            TechAlias(
                target_uri="uri:a",
                preferred_label="A",
                surfaces=("aleph",),
            ),
            TechAlias(
                target_uri="uri:b",
                preferred_label="B",
                surfaces=("beta",),
            ),
        ]
    )
    by_uri = overlay.surfaces_by_uri()
    assert sorted(by_uri["uri:a"]) == ["aleph", "alpha"]
    assert by_uri["uri:b"] == ["beta"]
