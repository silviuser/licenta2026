"""``POST /v1/match`` tests."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import build_match_request_body


def _extract_first(test_client: TestClient, minimal_pdf_bytes: bytes) -> dict[str, Any]:
    """Helper — run extract, return the response JSON for /v1/match input."""
    r = test_client.post(
        "/v1/extract",
        data={"cv_id": "alice"},
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_match_happy_path_returns_match_response(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """End-to-end happy path: /extract → /match → MatchResponse."""
    extract_body = _extract_first(test_client, minimal_pdf_bytes)
    match_body = build_match_request_body(extract_body)

    response = test_client.post("/v1/match", json=match_body)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cv_id"] == "alice"
    assert body["jd_id"] == "test-jd"
    assert 0.0 <= body["overall_score"] <= 1.0
    assert body["overall_class"] in {"strong", "possible", "no"}


def test_match_overall_class_projection_matches_locked_thresholds(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """``overall_class`` is computed from locked T1/T2.

    The mock matcher returns ``overall_score=0.072`` (above the
    Step 8 lock T1=0.060), so ``overall_class`` MUST be ``strong``.
    """
    extract_body = _extract_first(test_client, minimal_pdf_bytes)
    match_body = build_match_request_body(extract_body)
    response = test_client.post("/v1/match", json=match_body)
    assert response.json()["overall_class"] == "strong"


def test_match_cv_id_mismatch_returns_400(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Mismatch between top-level ``cv_id`` and ``enriched.cv_id`` is 400."""
    extract_body = _extract_first(test_client, minimal_pdf_bytes)
    match_body = build_match_request_body(extract_body)
    match_body["cv_id"] = "different_cv"  # Cause a mismatch.
    response = test_client.post("/v1/match", json=match_body)
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "cv_id_mismatch"


def test_match_requires_non_empty_requirements(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Empty ``requirements`` list triggers 422 (pydantic min_length=1)."""
    extract_body = _extract_first(test_client, minimal_pdf_bytes)
    match_body = build_match_request_body(extract_body)
    match_body["requirements"] = []
    response = test_client.post("/v1/match", json=match_body)
    assert response.status_code == 422


def test_match_response_validates_against_schema(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Round-trip through ``MatchResponse``."""
    from api.schemas import MatchResponse

    extract_body = _extract_first(test_client, minimal_pdf_bytes)
    match_body = build_match_request_body(extract_body)
    response = test_client.post("/v1/match", json=match_body)
    parsed = MatchResponse.model_validate(response.json())
    assert parsed.overall_class in {"strong", "possible", "no"}


def test_match_passes_locked_thresholds_to_adapter(
    test_client: TestClient,
    minimal_pdf_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The match router pulls T1/T2 from ``matcher.config``, not constants."""
    extract_body = _extract_first(test_client, minimal_pdf_bytes)
    match_body = build_match_request_body(extract_body)
    # Bump T1 above the mocked overall_score (0.072) so the projection
    # collapses to "possible" instead of "strong".
    from api.routers import match as match_module

    captured_kwargs: dict[str, Any] = {}
    original = match_module.match_result_to_response

    def _capture(*args: Any, **kwargs: Any) -> Any:
        captured_kwargs.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(match_module, "match_result_to_response", _capture)
    response = test_client.post("/v1/match", json=match_body)
    assert response.status_code == 200
    assert "t1_strong_threshold" in captured_kwargs
    assert "t2_possible_threshold" in captured_kwargs
    assert captured_kwargs["t2_possible_threshold"] < captured_kwargs["t1_strong_threshold"]
