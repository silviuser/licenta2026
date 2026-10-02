"""Context-window clipping helper for training-pair generation.

The training-dataset build script (Step 3) emits a fixed-size context
window around every detected skill span so the encoder can resolve
polysemy at fine-tune time (``"security audit findings"`` vs
``"securities trading desk"``).

The clipping rule is intentionally simple:

1. Start from the ±``max_chars`` characters surrounding the span.
2. Expand each side **inward** to the nearest sentence boundary
   (``.``, ``!``, ``?``, or hard newline). The expansion is *inward*
   because we prefer trimming a partial sentence over emitting one
   that bleeds into the previous / next thought.
3. Strip whitespace from both ends so the on-disk JSONL stays tidy.

This module deliberately does **not** depend on spaCy or NLTK: the
sentence-boundary detection is regex-based. Module 2 already pays the
spaCy cost; threading the ``Doc`` through is more coupling than the
context-window helper deserves, and a regex on
``[.!?]\\s+|\\n+`` is accurate enough for the CV genre.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Characters that terminate a sentence in CV-style writing. We treat a
# run of one-or-more newlines as a sentence boundary as well so bullet
# lists do not glue together. Apostrophes and hyphens are explicitly
# *not* treated as boundaries even though some text-rendering bugs in
# Module 1's PDF output have produced them in odd places.
_SENTENCE_BOUNDARY_REGEX = re.compile(r"(?:[.!?]+\s+)|(?:\n+)")


@dataclass(frozen=True)
class ContextWindow:
    """The result of clipping a context window around a span.

    Attributes
    ----------
    before
        The cleaned-up text preceding the span, length ≤ ``max_chars``.
    after
        The cleaned-up text following the span, length ≤ ``max_chars``.
    """

    before: str
    after: str


def clip_context(
    text: str,
    span_start: int,
    span_end: int,
    max_chars: int = 50,
) -> ContextWindow:
    """Build a sentence-aware ±``max_chars`` context window.

    Parameters
    ----------
    text
        Full source-CV text. Same string Module 2 saw, including any
        slash-segmenter rewrites — caller's responsibility to keep
        the offsets aligned.
    span_start, span_end
        Character offsets defining the span the window surrounds.
        Must satisfy ``0 <= span_start < span_end <= len(text)``.
    max_chars
        Maximum window width on each side. Defaults to 50, matching
        the kickoff spec. Values < 1 are clamped to 1; values larger
        than ``len(text)`` are clipped on the file boundary anyway.

    Returns
    -------
    ContextWindow
        Trimmed ``before`` and ``after`` strings. Both are stripped of
        leading and trailing whitespace.
    """
    if not text:
        return ContextWindow(before="", after="")
    if span_start < 0 or span_end <= span_start or span_end > len(text):
        raise ValueError(
            f"Invalid span ({span_start}, {span_end}) for text of length "
            f"{len(text)}."
        )

    width = max(1, max_chars)

    # --- Left side: window is ``text[left_bound:span_start]``.
    left_bound = max(0, span_start - width)
    left_window = text[left_bound:span_start]
    # Trim from the LEFT until we land just AFTER a sentence boundary.
    # ``finditer`` returns boundaries inside the window; the rightmost
    # one tells us where the last sentence ended — we keep everything
    # after that.
    last_boundary_end = 0
    for match in _SENTENCE_BOUNDARY_REGEX.finditer(left_window):
        last_boundary_end = match.end()
    before_text = left_window[last_boundary_end:].strip()

    # --- Right side: window is ``text[span_end:right_bound]``.
    right_bound = min(len(text), span_end + width)
    right_window = text[span_end:right_bound]
    # Trim from the RIGHT until we land just BEFORE a sentence boundary.
    # The first boundary inside the window terminates the sentence the
    # span lives in.
    first_boundary = _SENTENCE_BOUNDARY_REGEX.search(right_window)
    if first_boundary is not None:
        after_text = right_window[: first_boundary.start()].strip()
    else:
        after_text = right_window.strip()

    return ContextWindow(before=before_text, after=after_text)


__all__ = ["ContextWindow", "clip_context"]
