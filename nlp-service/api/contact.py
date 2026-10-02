"""Email extraction from raw CV text (REWORK 4 D40 / D41).

A small, dependency-free helper that mines email addresses out of the
text Module 1 already produced (``ExtractionResult.text``) — no second
PDF parse, no ML, no retraining. It lives next to the API surface
(rather than inside ``cv_extractor``) so Module 1 stays untouched and
the logic is trivially unit-testable in isolation.

Phase-1 scope (D40, open-question §8): standard ``local@domain.tld``
form only. Simple obfuscations such as ``name [at] domain.com`` are
deliberately *not* handled yet — they cause more false positives than
they are worth on real CVs. :class:`api.schemas.ContactSchema` is the
extensible carrier if that (or phone / LinkedIn) is added later.
"""

from __future__ import annotations

import re

from api.schemas import ContactSchema

# Pragmatic, conservative email pattern. The TLD anchor ``\.[A-Za-z]{2,}``
# keeps version-like strings (``skill_matcher@0.7.0``) from matching —
# a numeric TLD is rejected. Wrapping punctuation (``<a@b.com>``,
# ``a@b.com,``) is shaved off in post-processing rather than baked into
# the pattern, which keeps the regex readable.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Characters that may cling to an address inside prose (trailing comma,
# closing angle bracket, sentence period, …). Stripped from both ends.
_TRIM_CHARS = ".,;:<>()[]{}\"'"


def extract_emails(text: str | None) -> list[str]:
    """Return all valid addresses, lowercased, deduplicated, in order.

    Order is *document order* — the first hit (usually the CV header)
    is what :func:`extract_contact` promotes to ``primary_email``.
    Deduplication is case-insensitive and preserves first appearance
    (``Ana@Example.com`` then ``ana@example.com`` yields one entry).
    """
    if not text:
        return []

    # dict preserves insertion order while collapsing duplicates.
    seen: dict[str, None] = {}
    for raw in _EMAIL_RE.findall(text):
        email = raw.strip().strip(_TRIM_CHARS).lower()
        if _is_plausible(email):
            seen.setdefault(email, None)
    return list(seen.keys())


def extract_contact(text: str | None) -> ContactSchema:
    """Build a :class:`ContactSchema` from raw CV text (D41 heuristic)."""
    emails = extract_emails(text)
    return ContactSchema(
        emails=emails,
        primary_email=emails[0] if emails else None,
    )


def _is_plausible(email: str) -> bool:
    """Cheap sanity gate after trimming — exactly one ``@`` and a dotted domain."""
    if email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain:
        return False
    # Domain must have a dot and a non-empty label on each side of it.
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return False
    return True


__all__ = ["extract_contact", "extract_emails"]
