"""``POST /v1/full`` tests — end-to-end convenience endpoint."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient


def _requirements_payload() -> str:
    """Return a JSON-encoded ``list[RequirementSchema]``."""
    return json.dumps(
        [
            {
                "text": "Python",
                "skill_uri": "http://data.europa.eu/esco/skill/python",
                "skill_label": "Python",
                "importance": "required",
                "confidence": 0.9,
            },
            {
                "text": "Java",
                "importance": "nice_to_have",
                "confidence": 0.5,
            },
        ]
    )


def test_full_happy_path_returns_full_response(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Happy path: PDF + JD requirements → ``FullResponse``."""
    response = test_client.post(
        "/v1/full",
        data={
            "cv_id": "alice",
            "jd_id": "role-42",
            "requirements": _requirements_payload(),
        },
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    assert body["cv_id"] == "alice"
    # ``jd_id`` echoed from the mock match result (= "test-jd"); the
    # mock returns a fixed MatchResult so it doesn't carry the form's
    # jd_id. The assertion checks the API surface is well-formed.
    assert body["jd_id"]
    assert 0.0 <= body["overall_score"] <= 1.0
    assert body["overall_class"] in {"strong", "possible", "no"}


def test_full_invalid_requirements_json_returns_400(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Malformed JSON in the ``requirements`` form field → 400."""
    response = test_client.post(
        "/v1/full",
        data={
            "cv_id": "alice",
            "jd_id": "role-42",
            "requirements": "{not valid json",
        },
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "requirements_invalid_json"


def test_full_requirements_schema_mismatch_returns_400(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Valid JSON but invalid ``RequirementSchema`` shape → 400."""
    bad = json.dumps([{"missing_text_field": True, "importance": "required"}])
    response = test_client.post(
        "/v1/full",
        data={
            "cv_id": "alice",
            "jd_id": "role-42",
            "requirements": bad,
        },
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "requirements_invalid_schema"


def test_full_empty_requirements_returns_400(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Empty requirements list → 400 (semantic, not pydantic)."""
    response = test_client.post(
        "/v1/full",
        data={
            "cv_id": "alice",
            "jd_id": "role-42",
            "requirements": "[]",
        },
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "requirements_empty"


def test_full_empty_pdf_returns_400(test_client: TestClient) -> None:
    """Empty PDF upload → 400."""
    response = test_client.post(
        "/v1/full",
        data={
            "cv_id": "alice",
            "jd_id": "role-42",
            "requirements": _requirements_payload(),
        },
        files={"cv_pdf": ("cv.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "empty_upload"


def test_full_response_validates_against_schema(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """``FullResponse`` round-trip."""
    from api.schemas import FullResponse

    response = test_client.post(
        "/v1/full",
        data={
            "cv_id": "alice",
            "jd_id": "role-42",
            "requirements": _requirements_payload(),
        },
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    parsed = FullResponse.model_validate(response.json())
    assert parsed.overall_class in {"strong", "possible", "no"}
