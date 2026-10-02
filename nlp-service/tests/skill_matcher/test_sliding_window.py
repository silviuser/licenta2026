"""Tests for :mod:`skill_matcher.sliding_window`."""

from __future__ import annotations

import pytest

from skill_matcher.sliding_window import (
    Window,
    count_windows,
    generate_windows,
    tokenize,
)

# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------


def test_tokenize_simple_sentence() -> None:
    """One token per whitespace-separated word."""
    tokens = tokenize("hello world from python")
    assert [t.text for t in tokens] == ["hello", "world", "from", "python"]


def test_tokenize_preserves_offsets() -> None:
    """Token offsets are absolute positions in the source string."""
    text = "alpha beta gamma"
    tokens = tokenize(text)
    for t in tokens:
        assert text[t.start : t.end] == t.text


def test_tokenize_keeps_cpp_as_single_token() -> None:
    """``C++`` is one token, not three (C, +, +)."""
    tokens = tokenize("I program in C++ daily")
    assert "C++" in [t.text for t in tokens]


def test_tokenize_keeps_dotted_tokens() -> None:
    """``.NET`` / ``Node.js`` style tokens stay glued.

    The regex requires the dot to sit between word chars; trailing
    dots (sentence terminators) do NOT get absorbed.
    """
    tokens = [t.text for t in tokenize("Built backends in Node.js for years.")]
    assert "Node.js" in tokens


def test_tokenize_keeps_slash_tokens() -> None:
    """``CI/CD`` style tokens stay glued."""
    tokens = [t.text for t in tokenize("Owns the CI/CD pipeline")]
    assert "CI/CD" in tokens


def test_tokenize_keeps_hyphen_tokens() -> None:
    """Hyphenated tokens like ``Java-EE`` stay glued."""
    tokens = [t.text for t in tokenize("Java-EE legacy migration")]
    assert "Java-EE" in tokens


def test_tokenize_strips_trailing_punctuation() -> None:
    """A trailing period is not part of any token."""
    tokens = [t.text for t in tokenize("Python.")]
    assert tokens == ["Python"]


def test_tokenize_empty_input_returns_empty_list() -> None:
    assert tokenize("") == []
    assert tokenize("   \n  ") == []


# ---------------------------------------------------------------------------
# generate_windows
# ---------------------------------------------------------------------------


def test_generate_windows_short_text_returns_single_window() -> None:
    """Text shorter than window_size collapses to one window covering all."""
    windows = generate_windows(
        "alpha beta gamma", window_size_tokens=10, stride_tokens=5
    )
    assert len(windows) == 1
    assert windows[0].token_count == 3
    assert windows[0].text == "alpha beta gamma"


def test_generate_windows_overlapping_stride() -> None:
    """5-token window with stride 2 over 9 tokens → 3 windows."""
    text = "t1 t2 t3 t4 t5 t6 t7 t8 t9"
    windows = generate_windows(text, window_size_tokens=5, stride_tokens=2)
    # i=0: t1..t5; i=2: t3..t7; i=4: t5..t9
    assert len(windows) == 3
    assert all(w.token_count == 5 for w in windows)


def test_generate_windows_tail_handling() -> None:
    """Final window always covers the last token, even with awkward stride."""
    text = "t1 t2 t3 t4 t5 t6 t7"
    windows = generate_windows(text, window_size_tokens=3, stride_tokens=2)
    # i=0: t1..t3; i=2: t3..t5; i=4: t5..t7. Final covers t7.
    assert windows[-1].text.endswith("t7")


def test_generate_windows_non_overlapping_stride_equals_window() -> None:
    """Stride == window_size → contiguous, non-overlapping windows."""
    text = "t1 t2 t3 t4 t5 t6"
    windows = generate_windows(text, window_size_tokens=3, stride_tokens=3)
    assert [w.token_count for w in windows] == [3, 3]


def test_generate_windows_preserves_original_text_punctuation() -> None:
    """Window text is original substring, NOT a token re-join.

    This locks the contract that the encoder sees natural-looking
    text rather than a space-joined token sequence stripped of
    punctuation.
    """
    text = "Built in C++, deployed via CI/CD pipelines."
    windows = generate_windows(text, window_size_tokens=10, stride_tokens=5)
    assert "C++," in windows[0].text
    assert "CI/CD" in windows[0].text


def test_generate_windows_empty_text_returns_empty_list() -> None:
    assert generate_windows("", window_size_tokens=5, stride_tokens=3) == []
    assert generate_windows("   ", window_size_tokens=5, stride_tokens=3) == []


def test_generate_windows_rejects_zero_window_size() -> None:
    with pytest.raises(ValueError, match="window_size_tokens"):
        generate_windows("x y", window_size_tokens=0, stride_tokens=1)


def test_generate_windows_rejects_zero_stride() -> None:
    with pytest.raises(ValueError, match="stride_tokens"):
        generate_windows("x y", window_size_tokens=5, stride_tokens=0)


def test_generate_windows_offsets_reconstruct_text() -> None:
    """Concatenating window starts/ends recovers the original char ranges."""
    text = "the quick brown fox jumps over the lazy dog"
    windows = generate_windows(text, window_size_tokens=4, stride_tokens=2)
    for w in windows:
        assert text[w.start : w.end] == w.text


# ---------------------------------------------------------------------------
# count_windows
# ---------------------------------------------------------------------------


def test_count_windows_matches_generate_windows_length() -> None:
    """``count_windows`` must agree with the materialised list length."""
    text = " ".join(f"t{i}" for i in range(100))
    for window_size, stride in [(30, 15), (20, 20), (10, 5), (5, 1), (200, 50)]:
        materialised = generate_windows(
            text, window_size_tokens=window_size, stride_tokens=stride
        )
        counted = count_windows(
            text, window_size_tokens=window_size, stride_tokens=stride
        )
        assert counted == len(materialised), (
            f"mismatch at window_size={window_size}, stride={stride}: "
            f"counted={counted}, actual={len(materialised)}"
        )


def test_count_windows_empty_text_zero() -> None:
    assert count_windows("", window_size_tokens=5, stride_tokens=2) == 0


# ---------------------------------------------------------------------------
# Window dataclass invariants
# ---------------------------------------------------------------------------


def test_window_is_frozen() -> None:
    w = Window(text="x", start=0, end=1, token_count=1)
    with pytest.raises((AttributeError, Exception)):
        w.start = 99  # type: ignore[misc]
