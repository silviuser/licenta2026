"""Smoke tests for :mod:`skill_extractor.exceptions`."""

from __future__ import annotations

import pytest

from skill_extractor.exceptions import (
    EscoLoadError,
    MatcherCacheError,
    NotACVError,
    SkillExtractorError,
    UnsupportedLanguageError,
)


def test_hierarchy() -> None:
    """All custom errors subclass :class:`SkillExtractorError`."""
    for cls in (
        UnsupportedLanguageError,
        NotACVError,
        EscoLoadError,
        MatcherCacheError,
    ):
        assert issubclass(cls, SkillExtractorError)


def test_unsupported_language_carries_value() -> None:
    err = UnsupportedLanguageError("fr")
    assert err.language == "fr"
    assert "fr" in str(err)
    assert "en" in str(err) and "ro" in str(err)


def test_unsupported_language_with_none() -> None:
    """``ExtractionMetadata.detected_language`` is ``str | None`` — None
    must be accepted by the exception."""
    err = UnsupportedLanguageError(None)
    assert err.language is None


def test_not_a_cv_default_message() -> None:
    err = NotACVError()
    assert "not classified as a CV" in str(err)


def test_not_a_cv_custom_message() -> None:
    err = NotACVError("my custom message")
    assert "my custom message" in str(err)


def test_esco_load_error_with_path() -> None:
    err = EscoLoadError("bad header", path="/tmp/skills.csv")
    assert err.path == "/tmp/skills.csv"
    assert "bad header" in str(err)


def test_can_catch_via_base() -> None:
    with pytest.raises(SkillExtractorError):
        raise UnsupportedLanguageError("klingon")
