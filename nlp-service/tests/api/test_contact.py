"""Unit tests for email extraction (REWORK 4 D40 / D41).

Pure-function tests on :mod:`api.contact` — no FastAPI, no pipeline.
"""

from __future__ import annotations

import pytest

from api.contact import extract_contact, extract_emails


def test_single_email() -> None:
    assert extract_emails("Contact: ana.pop@example.com") == ["ana.pop@example.com"]


def test_no_email_returns_empty() -> None:
    assert extract_emails("Experienced engineer, no contact details here.") == []


def test_empty_and_none_text() -> None:
    assert extract_emails("") == []
    assert extract_emails(None) == []


def test_multiple_emails_preserve_document_order() -> None:
    text = "Primary ana@example.com then secondary ion@work.org"
    assert extract_emails(text) == ["ana@example.com", "ion@work.org"]


def test_primary_is_first_in_document_order() -> None:
    # Header address should win over one appearing later (e.g. a footer).
    text = "ana.pop@example.com\n...\nReferee: prof@uni.ro"
    contact = extract_contact(text)
    assert contact.primary_email == "ana.pop@example.com"
    assert contact.emails == ["ana.pop@example.com", "prof@uni.ro"]


def test_case_insensitive_dedup_keeps_first_and_lowercases() -> None:
    text = "Ana@Example.com wrote, and later ana@example.com replied."
    assert extract_emails(text) == ["ana@example.com"]


def test_trailing_punctuation_and_brackets_trimmed() -> None:
    assert extract_emails("Reach me at <ana@example.com>.") == ["ana@example.com"]
    assert extract_emails("email: ana@example.com, phone: ...") == ["ana@example.com"]


def test_version_like_string_is_not_an_email() -> None:
    # A numeric TLD must not match — guards against pipeline-version noise.
    assert extract_emails("built with skill_matcher@0.7.0 today") == []


def test_subdomain_and_multi_label_tld() -> None:
    text = "jobs@careers.example.co.uk"
    assert extract_emails(text) == ["jobs@careers.example.co.uk"]


def test_plus_addressing_and_digits() -> None:
    assert extract_emails("ana+jobs2026@example.com") == ["ana+jobs2026@example.com"]


def test_extract_contact_empty_when_no_email() -> None:
    contact = extract_contact("nothing to see")
    assert contact.emails == []
    assert contact.primary_email is None


@pytest.mark.parametrize(
    "text",
    ["plain text", "@", "a@", "@b.com", "a@b", "a@b."],
)
def test_invalid_shapes_rejected(text: str) -> None:
    assert extract_emails(text) == []
