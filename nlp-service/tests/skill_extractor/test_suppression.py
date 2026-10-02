"""Unit tests for :mod:`skill_extractor.overlays.suppression`.

Covers:

* YAML loading happy / error paths;
* the indexed lookup hot path;
* every documented context-narrowing knob (allowed/forbidden sections,
  surrounding-term presence/absence, window override).
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from skill_extractor.exceptions import EscoLoadError
from skill_extractor.overlays.suppression import (
    ContextRequirement,
    SuppressionFilter,
    SuppressionRule,
    SuppressionRuleSet,
    load_suppression_rules,
)


def _yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(dedent(body), encoding="utf-8")
    return p


def test_load_minimal_rule(tmp_path: Path) -> None:
    path = _yaml(
        tmp_path,
        """\
        rules:
          - surface_pattern: ".NET"
            target_concept_uri: uri:vb
            reason: test
        """,
    )
    rs = load_suppression_rules(path)
    assert len(rs.rules) == 1
    rule = rs.rules[0]
    assert rule.surface_pattern == ".NET"
    assert rule.target_concept_uri == "uri:vb"
    assert rule.case_sensitive is False
    assert rule.context is None


def test_load_full_context_rule(tmp_path: Path) -> None:
    path = _yaml(
        tmp_path,
        """\
        rules:
          - surface_pattern: lecture
            target_concept_uri: uri:lect
            case_sensitive: false
            context_required:
              forbidden_sections: [skills]
              allowed_sections: [education]
              surrounding_terms_any: ["the lecture", "lectures"]
              forbidden_surrounding_terms_any: ["lecturer"]
              surrounding_window_chars: 100
        """,
    )
    rs = load_suppression_rules(path)
    rule = rs.rules[0]
    assert rule.context is not None
    ctx = rule.context
    assert "skills" in ctx.forbidden_sections
    assert "education" in ctx.allowed_sections
    assert "lecturer" in ctx.forbidden_surrounding_terms_any
    assert ctx.window_chars == 100


def test_load_missing_surface_pattern(tmp_path: Path) -> None:
    path = _yaml(
        tmp_path,
        """\
        rules:
          - target_concept_uri: uri:x
        """,
    )
    with pytest.raises(EscoLoadError, match="missing surface_pattern"):
        load_suppression_rules(path)


def test_load_missing_target_uri(tmp_path: Path) -> None:
    path = _yaml(
        tmp_path,
        """\
        rules:
          - surface_pattern: foo
        """,
    )
    with pytest.raises(EscoLoadError, match="missing target_concept_uri"):
        load_suppression_rules(path)


def test_load_bad_window_chars(tmp_path: Path) -> None:
    path = _yaml(
        tmp_path,
        """\
        rules:
          - surface_pattern: foo
            target_concept_uri: uri:x
            context_required:
              surrounding_window_chars: 0
        """,
    )
    with pytest.raises(EscoLoadError, match="positive int"):
        load_suppression_rules(path)


def test_load_terms_must_be_list_of_strings(tmp_path: Path) -> None:
    path = _yaml(
        tmp_path,
        """\
        rules:
          - surface_pattern: foo
            target_concept_uri: uri:x
            context_required:
              surrounding_terms_any: "not-a-list"
        """,
    )
    with pytest.raises(EscoLoadError, match="must be a list of strings"):
        load_suppression_rules(path)


# ---------------------------------------------------------------------------
# Filter behaviour
# ---------------------------------------------------------------------------


def _rule(
    surface: str,
    uri: str,
    *,
    case_sensitive: bool = False,
    context: ContextRequirement | None = None,
) -> SuppressionRule:
    return SuppressionRule(
        surface_pattern=surface,
        target_concept_uri=uri,
        case_sensitive=case_sensitive,
        context=context,
    )


def test_case_insensitive_default() -> None:
    rs = SuppressionRuleSet(rules=[_rule(".NET", "uri:vb")])
    filt = SuppressionFilter(rs)
    hit = filt.should_suppress(
        text="working with .NET",
        surface=".net",
        target_uri="uri:vb",
        section="skills",
        char_start=13,
        char_end=17,
    )
    assert hit is not None


def test_case_sensitive_pronoun_It() -> None:
    rs = SuppressionRuleSet(
        rules=[_rule("It", "uri:it", case_sensitive=True)]
    )
    filt = SuppressionFilter(rs)
    # Title-case "It" → suppressed.
    assert (
        filt.should_suppress(
            text="It works",
            surface="It",
            target_uri="uri:it",
            section="profile",
            char_start=0,
            char_end=2,
        )
        is not None
    )
    # All-lower "it" → kept.
    assert (
        filt.should_suppress(
            text="it works",
            surface="it",
            target_uri="uri:it",
            section="profile",
            char_start=0,
            char_end=2,
        )
        is None
    )


def test_no_match_returns_none() -> None:
    rs = SuppressionRuleSet(rules=[_rule(".NET", "uri:vb")])
    filt = SuppressionFilter(rs)
    assert (
        filt.should_suppress(
            text="any",
            surface="Python",
            target_uri="uri:py",
            section="skills",
            char_start=0,
            char_end=6,
        )
        is None
    )


def test_allowed_sections_narrows_rule() -> None:
    rs = SuppressionRuleSet(
        rules=[
            _rule(
                "document management",
                "uri:doc",
                context=ContextRequirement(
                    allowed_sections=("skills",),
                ),
            )
        ]
    )
    filt = SuppressionFilter(rs)
    # ``allowed_sections=skills`` means the rule fires ONLY in the
    # ``skills`` section; other sections keep the match.
    fired = filt.should_suppress(
        text="document management of files",
        surface="document management",
        target_uri="uri:doc",
        section="skills",
        char_start=0,
        char_end=19,
    )
    assert fired is not None
    not_fired = filt.should_suppress(
        text="document management of files",
        surface="document management",
        target_uri="uri:doc",
        section="experience",
        char_start=0,
        char_end=19,
    )
    assert not_fired is None


def test_forbidden_sections_blocks_rule() -> None:
    rs = SuppressionRuleSet(
        rules=[
            _rule(
                "communication",
                "uri:comm",
                context=ContextRequirement(
                    forbidden_sections=("skills",),
                ),
            )
        ]
    )
    filt = SuppressionFilter(rs)
    # Forbidden section: rule does NOT fire.
    assert (
        filt.should_suppress(
            text="communication",
            surface="communication",
            target_uri="uri:comm",
            section="skills",
            char_start=0,
            char_end=13,
        )
        is None
    )
    # Other section: rule fires.
    assert (
        filt.should_suppress(
            text="communication",
            surface="communication",
            target_uri="uri:comm",
            section="experience",
            char_start=0,
            char_end=13,
        )
        is not None
    )


def test_surrounding_terms_any() -> None:
    """Rule requires at least one term in the window."""
    rs = SuppressionRuleSet(
        rules=[
            _rule(
                "statistics",
                "uri:stat",
                context=ContextRequirement(
                    surrounding_terms_any=("match",),
                    window_chars=60,
                ),
            )
        ]
    )
    filt = SuppressionFilter(rs)
    fired = filt.should_suppress(
        text="analysed match statistics from the season",
        surface="statistics",
        target_uri="uri:stat",
        section="education",
        char_start=14,
        char_end=24,
    )
    assert fired is not None
    not_fired = filt.should_suppress(
        text="published statistics about churn",
        surface="statistics",
        target_uri="uri:stat",
        section="education",
        char_start=10,
        char_end=20,
    )
    assert not_fired is None


def test_forbidden_surrounding_terms_any() -> None:
    """Rule does NOT fire when any forbidden term is in the window."""
    rs = SuppressionRuleSet(
        rules=[
            _rule(
                "designed",
                "uri:think",
                context=ContextRequirement(
                    forbidden_surrounding_terms_any=("graphic design",),
                    window_chars=80,
                ),
            )
        ]
    )
    filt = SuppressionFilter(rs)
    # Real graphic-design context: rule must NOT fire.
    keep = filt.should_suppress(
        text="Graphic Design Artist designed the campaign",
        surface="designed",
        target_uri="uri:think",
        section="experience",
        char_start=22,
        char_end=30,
    )
    assert keep is None
    # Software-design context: rule fires.
    fired = filt.should_suppress(
        text="I designed and developed the backend",
        surface="designed",
        target_uri="uri:think",
        section="experience",
        char_start=2,
        char_end=10,
    )
    assert fired is not None


def test_window_chars_default() -> None:
    """Default 60-char window contains nearby terms but cuts off far ones."""
    ctx = ContextRequirement(surrounding_terms_any=("match",))
    rs = SuppressionRuleSet(
        rules=[_rule("statistics", "uri:stat", context=ctx)]
    )
    filt = SuppressionFilter(rs)
    # ``match`` is far away (>60 chars before "statistics").
    text = "match " + "x" * 100 + " statistics"
    stats_pos = text.index("statistics")
    not_fired = filt.should_suppress(
        text=text,
        surface="statistics",
        target_uri="uri:stat",
        section="other",
        char_start=stats_pos,
        char_end=stats_pos + len("statistics"),
    )
    assert not_fired is None


def test_empty_ruleset_is_noop() -> None:
    filt = SuppressionFilter()
    assert (
        filt.should_suppress(
            text="x",
            surface="x",
            target_uri="uri:any",
            section="skills",
            char_start=0,
            char_end=1,
        )
        is None
    )


# ---------------------------------------------------------------------------
# Shipped YAML smoke test
# ---------------------------------------------------------------------------


def test_shipped_rules_load() -> None:
    from skill_extractor.config import DEFAULT_SUPPRESSION_RULES_PATH

    rs = load_suppression_rules(DEFAULT_SUPPRESSION_RULES_PATH)
    assert rs.rules, "shipped suppression rules should not be empty"
    # The 14 FP families documented in the validation report:
    surfaces = {r.surface_pattern.lower() for r in rs.rules}
    for required in [
        ".net",
        "visual studio",
        "it",
        "security",
        "integrity",
        "banking",
        "tailored",
        "called",
        "logic",
        "statistics",
        "lecture",
        "communication",
        "communications",
        "document management",
    ]:
        assert required in surfaces, f"shipped rules missing surface {required}"


def test_shipped_dotnet_rule_targets_visual_basic_uri() -> None:
    """The .NET → Visual Basic rule must target the published ESCO URI."""
    from skill_extractor.config import DEFAULT_SUPPRESSION_RULES_PATH

    rs = load_suppression_rules(DEFAULT_SUPPRESSION_RULES_PATH)
    dotnet_rules = [r for r in rs.rules if r.surface_pattern == ".NET"]
    assert dotnet_rules, "missing .NET suppression rule"
    assert any(
        "13bdd41a-2a18-441f-96db-41252c519413" in r.target_concept_uri
        for r in dotnet_rules
    ), ".NET rule must target the Visual Basic ESCO URI"


# ---------------------------------------------------------------------------
# Coverage closers — exercise the error branches the happy-path tests miss
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    """The optional-feature contract: missing file → empty rule set."""
    rs = load_suppression_rules(tmp_path / "does_not_exist.yaml")
    assert rs.rules == []


def test_load_invalid_yaml(tmp_path: Path) -> None:
    """A malformed YAML must raise ``EscoLoadError`` (not bubble yaml.YAMLError)."""
    p = tmp_path / "bad.yaml"
    p.write_text("rules: [unclosed", encoding="utf-8")
    with pytest.raises(EscoLoadError, match="YAML parse error"):
        load_suppression_rules(p)


def test_load_yaml_none_returns_empty(tmp_path: Path) -> None:
    """A YAML file with only comments parses to ``None`` and yields an empty set."""
    p = tmp_path / "comments.yaml"
    p.write_text("# only a comment\n", encoding="utf-8")
    assert load_suppression_rules(p).rules == []


def test_load_top_level_must_be_mapping(tmp_path: Path) -> None:
    p = _yaml(tmp_path, "- not a mapping\n")
    with pytest.raises(EscoLoadError, match="must be a mapping"):
        load_suppression_rules(p)


def test_load_rule_entry_not_mapping(tmp_path: Path) -> None:
    p = _yaml(tmp_path, "rules:\n  - just-a-string\n")
    with pytest.raises(EscoLoadError, match="not a mapping"):
        load_suppression_rules(p)


def test_load_context_required_not_mapping(tmp_path: Path) -> None:
    p = _yaml(
        tmp_path,
        """\
        rules:
          - surface_pattern: foo
            target_concept_uri: uri:x
            context_required: not-a-mapping
        """,
    )
    with pytest.raises(EscoLoadError, match="context_required must be a mapping"):
        load_suppression_rules(p)


def test_load_terms_list_with_non_string(tmp_path: Path) -> None:
    p = _yaml(
        tmp_path,
        """\
        rules:
          - surface_pattern: foo
            target_concept_uri: uri:x
            context_required:
              surrounding_terms_any: [valid, 42]
        """,
    )
    with pytest.raises(EscoLoadError, match="non-string entry"):
        load_suppression_rules(p)


def test_filter_ruleset_property_returns_underlying_ruleset() -> None:
    rs = SuppressionRuleSet(rules=[_rule(".NET", "uri:vb")])
    filt = SuppressionFilter(rs)
    assert filt.ruleset is rs


def test_case_sensitive_rule_does_not_match_different_case() -> None:
    """A case-sensitive rule for 'Foo' must NOT fire on surface 'foo'."""
    rs = SuppressionRuleSet(
        rules=[_rule("Foo", "uri:x", case_sensitive=True)]
    )
    filt = SuppressionFilter(rs)
    assert (
        filt.should_suppress(
            text="foo bar",
            surface="foo",  # lower-case, rule expects "Foo"
            target_uri="uri:x",
            section="skills",
            char_start=0,
            char_end=3,
        )
        is None
    )


def test_lookup_lowercase_surface_with_alternate_index_path() -> None:
    """Exercise the ``else`` branch of ``SuppressionRuleSet.lookup``.

    When the matched surface is already lower-cased, the first lookup
    finds the case-insensitive rules. The fallback ``else`` branch
    then re-consults the case-sensitive bucket (a no-op when no
    case-sensitive rule for the same lowered surface exists).
    """
    rs = SuppressionRuleSet(
        rules=[
            _rule("design", "uri:x"),                # case-insensitive
            _rule("design", "uri:x", case_sensitive=True),  # case-sensitive
        ]
    )
    hits = rs.lookup(surface="design", target_uri="uri:x")
    # Both rules are returned (the dedup branch in lookup must run).
    assert len(hits) == 2
