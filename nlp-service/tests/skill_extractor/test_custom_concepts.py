"""Unit tests for :mod:`skill_extractor.overlays.custom`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_extractor.exceptions import EscoLoadError
from skill_extractor.models import EscoSkill
from skill_extractor.overlays.custom import (
    CUSTOM_URI_PREFIX,
    CustomConceptOverlay,
    load_custom_overlay,
    merge_custom_concepts,
)


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_file_returns_empty_overlay(tmp_path: Path) -> None:
    assert load_custom_overlay(tmp_path / "no.json").concepts == []


def test_load_minimal_concept(tmp_path: Path) -> None:
    path = tmp_path / "custom.json"
    _write(
        path,
        {
            "concepts": [
                {
                    "id": "CUST:foo",
                    "preferred_label": "Foo",
                    "alt_labels": ["fooalias", "FOO ALIAS"],
                    "skill_type": "knowledge",
                    "description": "test",
                    "source_url": "https://example.com",
                }
            ]
        },
    )
    overlay = load_custom_overlay(path)
    assert len(overlay.concepts) == 1
    c = overlay.concepts[0]
    assert c.concept_uri == "CUST:foo"
    assert c.preferred_label == "Foo"
    # Alt labels equal to the preferred label (case-insensitive) are
    # dropped by the loader; the two distinct alts survive.
    assert c.alt_labels == ["fooalias", "FOO ALIAS"]
    assert c.is_custom is True
    assert c.skill_type == "knowledge"
    assert c.reuse_level == "https://example.com"  # source_url is stored here


def test_load_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    _write(path, ["not", "an", "object"])
    with pytest.raises(EscoLoadError, match="must be an object"):
        load_custom_overlay(path)


def test_load_rejects_concepts_not_list(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    _write(path, {"concepts": "not-a-list"})
    with pytest.raises(EscoLoadError, match="must be a list"):
        load_custom_overlay(path)


def test_load_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid", encoding="utf-8")
    with pytest.raises(EscoLoadError, match="JSON parse error"):
        load_custom_overlay(path)


def test_concept_missing_id(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    _write(path, {"concepts": [{"preferred_label": "Foo", "skill_type": "knowledge"}]})
    with pytest.raises(EscoLoadError, match="missing `id`"):
        load_custom_overlay(path)


def test_concept_id_must_have_prefix(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    _write(
        path,
        {
            "concepts": [
                {
                    "id": "esco:bad",
                    "preferred_label": "Foo",
                    "skill_type": "knowledge",
                }
            ]
        },
    )
    with pytest.raises(EscoLoadError, match="must start with"):
        load_custom_overlay(path)


def test_concept_missing_preferred_label(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    _write(
        path,
        {"concepts": [{"id": "CUST:x", "skill_type": "knowledge"}]},
    )
    with pytest.raises(EscoLoadError, match="missing\\s+`preferred_label`"):
        load_custom_overlay(path)


def test_concept_unknown_skill_type(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    _write(
        path,
        {
            "concepts": [
                {
                    "id": "CUST:x",
                    "preferred_label": "X",
                    "skill_type": "transversal",
                }
            ]
        },
    )
    with pytest.raises(EscoLoadError, match="unknown\\s+skill_type"):
        load_custom_overlay(path)


def test_concept_alt_labels_must_be_list(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    _write(
        path,
        {
            "concepts": [
                {
                    "id": "CUST:x",
                    "preferred_label": "X",
                    "skill_type": "knowledge",
                    "alt_labels": "not-a-list",
                }
            ]
        },
    )
    with pytest.raises(EscoLoadError, match="alt_labels must be a list"):
        load_custom_overlay(path)


def test_concept_duplicate_id(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    _write(
        path,
        {
            "concepts": [
                {
                    "id": "CUST:x",
                    "preferred_label": "X",
                    "skill_type": "knowledge",
                },
                {
                    "id": "CUST:x",
                    "preferred_label": "X copy",
                    "skill_type": "knowledge",
                },
            ]
        },
    )
    with pytest.raises(EscoLoadError, match="Duplicate custom concept id"):
        load_custom_overlay(path)


def test_alt_labels_dedupe_and_strip_preferred(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    _write(
        path,
        {
            "concepts": [
                {
                    "id": "CUST:x",
                    "preferred_label": "Foo",
                    "skill_type": "knowledge",
                    "alt_labels": ["foo", "FOO", "Bar", "bar", "  ", "Foo"],
                }
            ]
        },
    )
    overlay = load_custom_overlay(path)
    c = overlay.concepts[0]
    # "foo"/"FOO" match preferred label and are removed; "bar"/"Bar" dedupe.
    lowered = [a.lower() for a in c.alt_labels]
    assert "foo" not in lowered
    assert lowered.count("bar") == 1


def test_merge_appends_custom_after_esco() -> None:
    esco = [
        EscoSkill(
            concept_uri="http://data.europa.eu/esco/skill/abc",
            preferred_label="A",
            skill_type="knowledge",
        )
    ]
    overlay = CustomConceptOverlay(
        concepts=[
            EscoSkill(
                concept_uri="CUST:custom",
                preferred_label="C",
                skill_type="knowledge",
                is_custom=True,
            )
        ]
    )
    merged = merge_custom_concepts(esco, overlay)
    assert merged[0].concept_uri == "http://data.europa.eu/esco/skill/abc"
    assert merged[1].concept_uri == "CUST:custom"
    assert merged[1].is_custom is True


def test_merge_rejects_collision_with_esco() -> None:
    """A CUST:id colliding with a native ESCO URI raises."""
    # Synthesise the collision by giving an "ESCO" skill the CUST: prefix.
    esco = [
        EscoSkill(
            concept_uri="CUST:foo",  # pretend it's an ESCO URI
            preferred_label="Foo (native)",
            skill_type="knowledge",
        )
    ]
    overlay = CustomConceptOverlay(
        concepts=[
            EscoSkill(
                concept_uri="CUST:foo",
                preferred_label="Foo (custom)",
                skill_type="knowledge",
                is_custom=True,
            )
        ]
    )
    with pytest.raises(EscoLoadError, match="collide with ESCO URIs"):
        merge_custom_concepts(esco, overlay)


def test_merge_empty_overlay_returns_copy() -> None:
    esco = [
        EscoSkill(
            concept_uri="uri:a",
            preferred_label="A",
            skill_type="knowledge",
        )
    ]
    out = merge_custom_concepts(esco, CustomConceptOverlay())
    assert out == esco
    assert out is not esco


# ---------------------------------------------------------------------------
# Shipped overlay smoke test
# ---------------------------------------------------------------------------


def test_shipped_custom_overlay_loads() -> None:
    """The packaged custom_concepts.json must parse and have no ESCO collisions."""
    from skill_extractor.config import DEFAULT_CUSTOM_CONCEPTS_PATH

    overlay = load_custom_overlay(DEFAULT_CUSTOM_CONCEPTS_PATH)
    assert overlay.concepts, "shipped custom overlay must not be empty"
    for c in overlay.concepts:
        assert c.is_custom is True
        assert c.concept_uri.startswith(CUSTOM_URI_PREFIX)


def test_shipped_overlay_ids_are_unique() -> None:
    """No two custom concepts in the shipped overlay share an id."""
    from skill_extractor.config import DEFAULT_CUSTOM_CONCEPTS_PATH

    overlay = load_custom_overlay(DEFAULT_CUSTOM_CONCEPTS_PATH)
    ids = [c.concept_uri for c in overlay.concepts]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Coverage closers
# ---------------------------------------------------------------------------


def test_by_uri_round_trip() -> None:
    """``CustomConceptOverlay.by_uri`` returns a URI-keyed dict."""
    a = EscoSkill(
        concept_uri="CUST:a",
        preferred_label="A",
        skill_type="knowledge",
        is_custom=True,
    )
    b = EscoSkill(
        concept_uri="CUST:b",
        preferred_label="B",
        skill_type="knowledge",
        is_custom=True,
    )
    overlay = CustomConceptOverlay(concepts=[a, b])
    by_uri = overlay.by_uri()
    assert by_uri["CUST:a"] is a
    assert by_uri["CUST:b"] is b


def test_concept_entry_not_object(tmp_path: Path) -> None:
    """A non-dict entry inside ``concepts`` raises."""
    path = tmp_path / "x.json"
    _write(path, {"concepts": ["just-a-string"]})
    with pytest.raises(EscoLoadError, match="not an object"):
        load_custom_overlay(path)


def test_concept_skill_competence_type_routed_correctly(tmp_path: Path) -> None:
    """``skill/competence`` skill type round-trips through the loader."""
    path = tmp_path / "x.json"
    _write(
        path,
        {
            "concepts": [
                {
                    "id": "CUST:x",
                    "preferred_label": "X",
                    "skill_type": "skill/competence",
                }
            ]
        },
    )
    overlay = load_custom_overlay(path)
    assert overlay.concepts[0].skill_type == "skill/competence"


def test_concept_language_type_routed_correctly(tmp_path: Path) -> None:
    """``language`` skill type round-trips through the loader."""
    path = tmp_path / "x.json"
    _write(
        path,
        {
            "concepts": [
                {
                    "id": "CUST:lang",
                    "preferred_label": "Klingon",
                    "skill_type": "language",
                }
            ]
        },
    )
    overlay = load_custom_overlay(path)
    assert overlay.concepts[0].skill_type == "language"
