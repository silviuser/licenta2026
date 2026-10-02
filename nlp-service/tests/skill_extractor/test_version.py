"""Drift-detection: ``skill_extractor.__version__`` MUST match pyproject.

Introduced in Step 10 alongside the new ``__version__`` constant. The
constant is read by ``api/routers/info.py`` to surface Module 2's
version on ``GET /v1/info``; if anyone bumps the project version in
``pyproject.toml`` without updating the ``__init__.py`` literal (or
vice-versa) the API would lie about which Module 2 produced a given
response. One assertion is cheaper than that bug.

The single-project / multi-package layout means all three modules
ship under one ``nlp-service`` distribution, so the expected version
is the ``[project].version`` field — not a per-package version.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import skill_extractor


def _project_version() -> str:
    """Return ``[project].version`` from ``nlp-service/pyproject.toml``."""
    # This test file lives at
    # ``nlp-service/tests/skill_extractor/test_version.py``. Going up
    # two parents lands at ``nlp-service/``.
    pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    version = data["project"]["version"]
    assert isinstance(version, str)
    return version


def test_skill_extractor_version_matches_pyproject() -> None:
    """``skill_extractor.__version__`` must equal ``pyproject.toml`` version."""
    assert skill_extractor.__version__ == _project_version(), (
        f"skill_extractor.__version__={skill_extractor.__version__!r} "
        f"diverged from pyproject project.version={_project_version()!r}. "
        "Update both literals together."
    )


def test_skill_extractor_version_is_semver_like() -> None:
    """Sanity: version is dotted digits (e.g. ``0.2.0``)."""
    parts = skill_extractor.__version__.split(".")
    assert len(parts) >= 2, skill_extractor.__version__
    assert all(p.isdigit() for p in parts[:2]), skill_extractor.__version__
