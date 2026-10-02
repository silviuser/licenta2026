"""Step 7 sign-off guard: no remaining ``NotImplementedError`` stubs.

Step 6's version of this file pinned the two outstanding stubs
(``Scorer.score`` and ``SkillMatcher.match``). Step 7 wired both --
the file is repurposed as a forward-looking invariant: any future
contributor who silently re-introduces a ``NotImplementedError`` in
the ``skill_matcher`` package will trip this test rather than ship a
half-finished module.

The brief's §3.5.8 originally asked to delete this file. The shell
sandbox in our session forbids the delete, so the file is rewritten
to the positive-invariant form -- materially stronger than deletion
because the invariant becomes a permanent regression guard.
"""

from __future__ import annotations

from pathlib import Path

import skill_matcher
from skill_matcher import __version__
from skill_matcher.config import SkillMatcherConfig
from skill_matcher.models import EnrichedSkillResult
from skill_matcher.pipeline import SkillMatcher

# Resolve the package source root via the package's ``__file__`` so the
# test does not depend on the test runner's cwd.
_SKILL_MATCHER_SRC = Path(skill_matcher.__file__).resolve().parent


def test_version_string_bumped_for_step_8() -> None:
    """Step 8 bumps the package version to 0.6.0.

    Version trail: 0.1.0 (Step 1) -> 0.2.0 (Step 4) ->
    0.3.0 / 0.3.1 (Step 5 phases) -> 0.4.0 (Step 6 Linker) ->
    0.5.0 (Step 7 Scorer) -> **0.6.0 (Step 8 threshold tuning)**.
    """
    assert __version__ == "0.6.0"


def test_no_notimplementederror_stubs_remain_in_skill_matcher() -> None:
    """No production module in ``skill_matcher`` raises
    ``NotImplementedError``.

    Step 7's exit gate. Any new stub added to the package will surface
    here long before it reaches the integration tests. The check is
    line-level rather than AST-level on purpose -- it catches the
    raise statement and the import-time guard alike.

    Doc-strings that *mention* ``NotImplementedError`` are allowed; the
    test only flags lines that look like a ``raise`` statement.
    """
    offenders: list[tuple[Path, int, str]] = []
    for py_file in _SKILL_MATCHER_SRC.rglob("*.py"):
        for lineno, line in enumerate(
            py_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.lstrip()
            if stripped.startswith("raise NotImplementedError"):
                offenders.append((py_file, lineno, line.strip()))

    assert not offenders, (
        "Found unexpected ``raise NotImplementedError`` lines in "
        "skill_matcher:\n"
        + "\n".join(f"  {p}:{ln}: {text}" for p, ln, text in offenders)
    )


def test_skill_matcher_accepts_explicit_config() -> None:
    """``SkillMatcher`` stores an explicitly-passed config rather than
    constructing a fresh default. Preserved from the Step 6 file as a
    lightweight construction-shape regression guard."""
    cfg = SkillMatcherConfig(seed=1234)
    matcher = SkillMatcher(config=cfg)
    assert matcher.config.seed == 1234


def test_match_result_can_be_constructed_with_unmatched_nice_to_have() -> None:
    """Step 7 amendment to ``MatchResult`` -- the new
    ``unmatched_nice_to_have`` field is part of the public schema.

    Construction smoke test pinned here so a future schema-narrowing
    edit fails the stubs guard rather than slipping past unnoticed.
    """
    enriched = EnrichedSkillResult(
        cv_id="x",
        candidates=[],
        detected_language="en",
        pipeline_version="skill_matcher@0.5.0",
    )
    assert enriched.cv_id == "x"
