"""Unit tests for :mod:`skill_extractor.tokenization.slash_segmenter`."""

from __future__ import annotations

import pytest

from skill_extractor.tokenization.slash_segmenter import SlashSegmenter


@pytest.fixture
def segmenter() -> SlashSegmenter:
    return SlashSegmenter.from_surface_lists(
        ["C", "C++", "C#", "HTML", "CSS", "Python", "Java"]
    )


def test_segments_c_cpp(segmenter: SlashSegmenter) -> None:
    """``C/C++`` must split into two tokens with a separator."""
    out = segmenter.segment("Competențe digitale: C/C++, C#")
    assert "C / C++" in out
    # Both sides remain searchable as distinct tokens (no consecutive slash).
    assert "C/C++" not in out


def test_segments_html_css(segmenter: SlashSegmenter) -> None:
    out = segmenter.segment("Languages: JavaScript, HTML/CSS, SQL")
    assert "HTML / CSS" in out
    assert "HTML/CSS" not in out


def test_leaves_client_server_intact(segmenter: SlashSegmenter) -> None:
    """``client/server`` is left alone — neither side is in the skill list."""
    out = segmenter.segment("Built a client/server application")
    assert out == "Built a client/server application"


def test_leaves_partial_match_intact(segmenter: SlashSegmenter) -> None:
    """When only one side is a known skill the run is left intact."""
    out = segmenter.segment("Worked with Python/foobar over the years")
    assert "Python/foobar" in out


def test_triple_split(segmenter: SlashSegmenter) -> None:
    """Three consecutive slash-joined skills should split all three."""
    out = segmenter.segment("Stack: HTML/CSS/Python")
    assert "HTML / CSS / Python" in out


def test_no_slash_returns_input(segmenter: SlashSegmenter) -> None:
    text = "plain text with no slash"
    assert segmenter.segment(text) is text or segmenter.segment(text) == text


def test_empty_input(segmenter: SlashSegmenter) -> None:
    assert segmenter.segment("") == ""
    assert segmenter.segment("   ") == "   "


def test_case_insensitive_lookup() -> None:
    seg = SlashSegmenter.from_surface_lists(["c", "c++"])
    out = seg.segment("Languages: C/C++")
    assert "C / C++" in out


def test_does_not_segment_inside_url() -> None:
    """URLs are left untouched because their parts aren't skill tokens."""
    seg = SlashSegmenter.from_surface_lists(["C", "C++"])
    out = seg.segment("See https://example.com/path/file for details")
    assert "https://example.com/path/file" in out


def test_from_surface_lists_dedupes_and_lower_cases() -> None:
    seg = SlashSegmenter.from_surface_lists(
        ["Python", "python", "PYTHON"],
        ["Java", "Java"],
    )
    assert seg.known_skills == frozenset({"python", "java"})


def test_separator_is_configurable() -> None:
    seg = SlashSegmenter(
        known_skills=frozenset({"c", "c++"}),
        separator=" | ",
    )
    out = seg.segment("C/C++ stack")
    assert "C | C++ stack" == out
