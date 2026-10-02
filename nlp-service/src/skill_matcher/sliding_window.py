"""Sliding-window tokeniser for CV text.

The zero-shot baseline's expansion stage scans every CV with a
fixed-width window, encodes each window with the
:class:`~skill_matcher.encoder.Encoder`, and queries the
:class:`~skill_matcher.esco_index.EscoIndex` for the top-k nearest
concepts per window. This module provides the windowing primitive.

Why a separate module
---------------------
:mod:`skill_matcher.context_window` solves a *different* problem —
clipping a sentence-aware ±N character context window around one
known span, used by Step 3's training-pair builder. Sliding-window
retrieval is a forward scan with no anchor span and uses tokens (not
characters) so the granularity matches what the encoder sees. Sharing
the two would couple two unrelated lifecycles; keeping them in
sibling modules makes the distinction obvious from
``ls src/skill_matcher/``.

Tokenisation strategy
---------------------
Whitespace + punctuation tokeniser, regex-based:

* A token is a maximal run of word characters (``[A-Za-z0-9_]+``)
  optionally extended with ``+``, ``-``, ``#``, ``.``, ``/``
  characters that are immediately surrounded by word characters.
  This keeps ``C++``, ``.NET``, ``Node.js``, ``CI/CD``, ``Java-EE``
  as single tokens, which matters for semantic retrieval because the
  encoder was trained on the full surface form, not on isolated
  letters.
* Bare punctuation (commas, periods, semicolons, parens) is
  *consumed* by the tokeniser but never produced as a token. The
  encoder sees the original text slice between the first token's
  start and the last token's end, so any in-window punctuation is
  preserved verbatim.
* No language model needed — this is deliberately Module-1/Module-2-
  agnostic so Step 7 (JD scoring) can reuse it on JD free-text.

The tokeniser is fast (one regex pass, O(N) chars). For a 30k-char
CV the wall-clock cost is sub-millisecond, dwarfed by encoding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


# Pattern explanation, left to right:
#   \.?                         — an optional leading dot (so ``.NET`` glues)
#   [A-Za-z0-9_]+               — a run of word chars
#   (?: ... )*                  — followed by zero or more of …
#       [+\-#./]                — a single +/-/#/./ symbol
#       [A-Za-z0-9_]+           — followed by more word chars
#   [+#]*                       — optional trailing +/# run (so ``C++``,
#                                 ``C#``, ``F#`` stay glued without a
#                                 word char between every special symbol)
# The trailing-period case (sentence terminator) stays excluded because
# ``.`` is not in the trailing class; a trailing ``+`` / ``#`` is rare
# enough outside identifiers that the false-positive risk is negligible.
_TOKEN_REGEX = re.compile(
    r"\.?[A-Za-z0-9_]+(?:[+\-#./][A-Za-z0-9_]+)*[+#]*"
)


@dataclass(frozen=True, slots=True)
class TokenSpan:
    """One token along with its character offsets in the source text."""

    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Window:
    """One sliding window: the *original* text slice covered, plus offsets.

    ``text`` is ``source_text[start:end]`` — original casing,
    punctuation and whitespace preserved. The encoder sees the same
    surface form a human would, which matters because SBERT was
    trained on natural text.
    """

    text: str
    start: int
    end: int
    token_count: int


def tokenize(text: str) -> list[TokenSpan]:
    """Tokenise ``text`` into ``TokenSpan`` objects.

    Returns an empty list for empty / whitespace-only input. Token
    offsets are absolute character positions in ``text`` so callers
    can reconstruct the original slice between any two tokens via
    ``text[a.start:b.end]``.
    """
    if not text or not text.strip():
        return []
    return [
        TokenSpan(text=m.group(0), start=m.start(), end=m.end())
        for m in _TOKEN_REGEX.finditer(text)
    ]


def generate_windows(
    text: str,
    *,
    window_size_tokens: int,
    stride_tokens: int,
) -> list[Window]:
    """Sliding window over ``text``.

    Parameters
    ----------
    text
        Full source text (CV body, JD body, …).
    window_size_tokens
        Number of tokens per window. Empirically tuned in Step 4
        (default elsewhere: 30).
    stride_tokens
        Step size in tokens. ``stride_tokens < window_size_tokens``
        produces overlapping windows; ``==`` produces back-to-back
        windows with no overlap.

    Returns
    -------
    list[Window]
        One window per stride step until ``text`` is exhausted. If
        the text is shorter than ``window_size_tokens``, exactly one
        window is returned spanning all tokens. Empty text returns
        an empty list.

    Notes
    -----
    Every window's ``text`` is the *original* substring
    ``text[start:end]`` — punctuation, whitespace and casing
    preserved. This is what the sentence-transformer is trained on;
    re-joining tokens with spaces would strip punctuation that
    contributes to semantic meaning (e.g. ``"C/C++"`` vs ``"C C"``).
    """
    if window_size_tokens < 1:
        raise ValueError(
            f"window_size_tokens must be >= 1, got {window_size_tokens}"
        )
    if stride_tokens < 1:
        raise ValueError(f"stride_tokens must be >= 1, got {stride_tokens}")

    tokens = tokenize(text)
    if not tokens:
        return []

    # Tail-handling rule: the last window starts at the smallest index
    # i such that i + window_size_tokens covers the final token. This
    # guarantees every token appears in at least one window even when
    # ``len(tokens) % stride_tokens != 0``.
    windows: list[Window] = []
    n = len(tokens)
    i = 0
    while i < n:
        j = min(i + window_size_tokens, n)
        start = tokens[i].start
        end = tokens[j - 1].end
        windows.append(
            Window(
                text=text[start:end],
                start=start,
                end=end,
                token_count=j - i,
            )
        )
        if j == n:
            # Reached the tail; subsequent strides would produce
            # duplicate windows.
            break
        i += stride_tokens

    return windows


def count_windows(
    text: str,
    *,
    window_size_tokens: int,
    stride_tokens: int,
) -> int:
    """Cheap helper: number of windows :func:`generate_windows` would emit.

    Used by the baseline runner for log lines and progress reporting
    without paying for the full ``Window`` materialisation.
    """
    tokens = tokenize(text)
    n = len(tokens)
    if n == 0:
        return 0
    if n <= window_size_tokens:
        return 1
    # Steps until the window covers the final token:
    #   need smallest k >= 0 such that k * stride + window_size >= n
    extra = n - window_size_tokens
    return 1 + (extra + stride_tokens - 1) // stride_tokens


__all__ = [
    "TokenSpan",
    "Window",
    "count_windows",
    "generate_windows",
    "tokenize",
]
