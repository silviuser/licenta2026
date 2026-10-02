"""``POST /v1/extract-jd`` tests (REWORK 1).

Covers the router (happy path, schema validation, language handling,
error envelopes) and the ``enriched_to_jd_response`` adapter shaping
rules (drop ``lexical_dropped``, dedupe by URI, sort by confidence).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from skill_extractor.exceptions import UnsupportedLanguageError

_JD_TEXT = (
    "We are looking for a backend engineer with strong Python and "
    "Java experience to build and maintain our data services."
)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def test_extract_jd_happy_path_returns_requirements(test_client: TestClient) -> None:
    """JD text → deduped, confidence-sorted requirements without importance."""
    response = test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": _JD_TEXT, "language": "en"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["jd_id"] == "jd-1"
    assert body["detected_language"] == "en"

    # mock Linker returns python (kept, 0.85), java (dropped, 0.62),
    # sw-eng (expansion, 0.78). The dropped one is filtered out.
    reqs = body["requirements"]
    assert len(reqs) == 2
    assert [r["skill_label"] for r in reqs] == ["Python", "software engineering"]

    # Confidence sorted descending.
    confidences = [r["confidence"] for r in reqs]
    assert confidences == sorted(confidences, reverse=True)

    # Importance is NOT decided by the NLP service (D18).
    for r in reqs:
        assert "importance" not in r
        assert set(r) == {"text", "skill_uri", "skill_label", "confidence"}


def test_extract_jd_response_validates_against_schema(
    test_client: TestClient,
) -> None:
    """Response body fully validates against ``ExtractJdResponse``."""
    from api.schemas import ExtractJdResponse

    response = test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": _JD_TEXT, "language": "en"},
    )
    parsed = ExtractJdResponse.model_validate(response.json())
    assert parsed.jd_id == "jd-1"
    assert parsed.pipeline_version  # Non-empty.


def test_extract_jd_language_override_is_forwarded(
    test_client: TestClient, mock_skill_extractor: MagicMock
) -> None:
    """An explicit ``language`` is passed straight to the extractor."""
    test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": _JD_TEXT, "language": "ro"},
    )
    mock_skill_extractor.extract.assert_called_once()
    (arg,) = mock_skill_extractor.extract.call_args.args
    text, language = arg
    assert language == "ro"
    assert text == _JD_TEXT


def test_extract_jd_auto_detects_language_when_absent(
    test_client: TestClient,
    mock_skill_extractor: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``language`` is omitted the lingua detector decides it."""
    import cv_extractor.pipeline as cv_pipeline

    monkeypatch.setattr(cv_pipeline, "_detect_language", lambda _text: "ro")

    response = test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": _JD_TEXT},
    )
    assert response.status_code == 200, response.text
    assert response.json()["detected_language"] == "ro"
    (arg,) = mock_skill_extractor.extract.call_args.args
    assert arg[1] == "ro"


def test_extract_jd_falls_back_to_en_when_detection_abstains(
    test_client: TestClient,
    mock_skill_extractor: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detection abstaining (``None``) falls back to English."""
    import cv_extractor.pipeline as cv_pipeline

    monkeypatch.setattr(cv_pipeline, "_detect_language", lambda _text: None)

    response = test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": _JD_TEXT},
    )
    assert response.status_code == 200, response.text
    assert response.json()["detected_language"] == "en"


def test_extract_jd_empty_text_returns_400(test_client: TestClient) -> None:
    """Whitespace-only text passes pydantic but is rejected as empty."""
    response = test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": "   "},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "empty_text"


def test_extract_jd_missing_jd_id_returns_422(test_client: TestClient) -> None:
    """FastAPI request validation rejects a missing required field."""
    response = test_client.post("/v1/extract-jd", json={"text": _JD_TEXT})
    assert response.status_code == 422


def test_extract_jd_invalid_language_returns_422(test_client: TestClient) -> None:
    """A language outside ``{en, ro}`` is rejected at the schema boundary."""
    response = test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": _JD_TEXT, "language": "fr"},
    )
    assert response.status_code == 422


def test_extract_jd_unsupported_language_maps_to_400(
    test_client: TestClient, mock_skill_extractor: MagicMock
) -> None:
    """An ``UnsupportedLanguageError`` from Module 2 maps to HTTP 400."""
    mock_skill_extractor.extract.side_effect = UnsupportedLanguageError("xx")
    response = test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": _JD_TEXT, "language": "en"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "unsupported_language"


def test_extract_jd_unexpected_error_maps_to_500(
    test_client: TestClient, mock_matcher: MagicMock
) -> None:
    """An unexpected error from the Linker maps to a uniform 500 envelope."""
    mock_matcher.link.side_effect = RuntimeError("boom")
    response = test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": _JD_TEXT, "language": "en"},
    )
    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "extract_jd_error"


def test_extract_jd_does_not_touch_module1(
    test_client: TestClient, mock_extractor: MagicMock
) -> None:
    """The JD path never invokes the PDF extraction pipeline (Module 1)."""
    test_client.post(
        "/v1/extract-jd",
        json={"jd_id": "jd-1", "text": _JD_TEXT, "language": "en"},
    )
    mock_extractor.process.assert_not_called()


# ---------------------------------------------------------------------------
# Adapter unit test
# ---------------------------------------------------------------------------


def _candidate(uri: str, label: str, conf: float, source: str) -> Any:
    from skill_matcher.models import MatchCandidate

    return MatchCandidate(
        skill_uri=uri,
        skill_label=label,
        confidence=conf,
        source=source,
        cv_evidence_text=label,
        cv_evidence_offset=None,
        similarity_score=conf,
        lexical_confidence=None,
    )


def test_enriched_to_jd_response_filters_dedupes_and_sorts() -> None:
    """``lexical_dropped`` dropped; same URI deduped (max conf); sorted desc."""
    from skill_matcher.models import EnrichedSkillResult

    from api.adapters import enriched_to_jd_response

    enriched = EnrichedSkillResult(
        cv_id="jd-1",
        candidates=[
            _candidate("uri:python", "Python", 0.50, "lexical_kept"),
            _candidate("uri:python", "Python", 0.80, "expansion"),  # dup, higher
            _candidate("uri:java", "Java", 0.62, "lexical_dropped"),  # filtered
            _candidate("uri:aws", "AWS", 0.90, "lexical_kept"),
        ],
        detected_language="en",
        pipeline_version="skill_matcher@test+encoder=mock",
    )

    resp = enriched_to_jd_response(
        jd_id="jd-1", language="en", enriched=enriched, extra_warnings=["w1"]
    )

    assert [r.skill_label for r in resp.requirements] == ["AWS", "Python"]
    assert [r.confidence for r in resp.requirements] == [0.90, 0.80]
    assert {r.skill_uri for r in resp.requirements} == {"uri:aws", "uri:python"}
    assert resp.warnings == ["w1"]
    assert resp.detected_language == "en"


def test_enriched_to_jd_response_coerces_unknown_language_to_none() -> None:
    """A language outside ``{en, ro}`` is surfaced as ``None`` (contract honesty)."""
    from skill_matcher.models import EnrichedSkillResult

    from api.adapters import enriched_to_jd_response

    enriched = EnrichedSkillResult(
        cv_id="jd-1",
        candidates=[],
        detected_language=None,
        pipeline_version="skill_matcher@test+encoder=mock",
    )
    resp = enriched_to_jd_response(jd_id="jd-1", language="fr", enriched=enriched)
    assert resp.detected_language is None
    assert resp.requirements == []
