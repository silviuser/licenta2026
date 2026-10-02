"""``POST /v1/extract`` tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from cv_extractor import ExtractionResult, PDFCorruptError


def test_extract_happy_path_returns_enriched(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Happy path: PDF + cv_id → ``ExtractResponse`` with three candidates."""
    response = test_client.post(
        "/v1/extract",
        data={"cv_id": "alice"},
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cv_id"] == "alice"
    assert body["detected_language"] == "en"
    assert len(body["candidates"]) == 3
    sources = {c["source"] for c in body["candidates"]}
    assert sources == {"lexical_kept", "lexical_dropped", "expansion"}


def test_extract_response_validates_against_schema(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Response body fully validates against ``ExtractResponse``."""
    from api.schemas import ExtractResponse

    response = test_client.post(
        "/v1/extract",
        data={"cv_id": "alice"},
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    parsed = ExtractResponse.model_validate(response.json())
    assert parsed.cv_id == "alice"
    assert parsed.pipeline_version  # Non-empty.


def test_extract_contact_field_present_and_empty_when_no_email(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """REWORK 4 (D40): ``contact`` is always present; empty when no address."""
    response = test_client.post(
        "/v1/extract",
        data={"cv_id": "alice"},
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    contact = response.json()["contact"]
    # The default mocked extraction text carries no email.
    assert contact == {"emails": [], "primary_email": None}


def test_extract_contact_populated_from_cv_text(
    test_client: TestClient,
    minimal_pdf_bytes: bytes,
    mock_extractor: MagicMock,
    sample_extraction_result: ExtractionResult,
) -> None:
    """The primary email is mined from Module 1's raw text (D41)."""
    sample_extraction_result.text = (
        "Ana Pop\nana.pop@example.com\nSenior engineer with Python and Java."
    )
    mock_extractor.process.return_value = sample_extraction_result

    response = test_client.post(
        "/v1/extract",
        data={"cv_id": "alice"},
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    contact = response.json()["contact"]
    assert contact["primary_email"] == "ana.pop@example.com"
    assert contact["emails"] == ["ana.pop@example.com"]


def test_extract_response_without_contact_revalidates_at_match(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """Back-compat: a pre-REWORK-4 extract (no ``contact``) still matches.

    ``extra="forbid"`` only rejects *unknown* fields; a *missing*
    ``contact`` falls back to the default, so old cached payloads
    round-trip through ``MatchRequest.enriched`` unchanged.
    """
    from tests.api.conftest import build_match_request_body

    extract = test_client.post(
        "/v1/extract",
        data={"cv_id": "alice"},
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    ).json()
    extract.pop("contact", None)  # Simulate a payload serialized before REWORK 4.

    match = test_client.post("/v1/match", json=build_match_request_body(extract))
    assert match.status_code == 200, match.text


def test_extract_pdf_corrupt_returns_400(
    test_client: TestClient,
    minimal_pdf_bytes: bytes,
    mock_extractor: MagicMock,
) -> None:
    """A ``PDFCorruptError`` from Module 1 maps to HTTP 400."""
    mock_extractor.process.side_effect = PDFCorruptError("malformed pdf trailer")
    response = test_client.post(
        "/v1/extract",
        data={"cv_id": "bob"},
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    body = response.json()
    # FastAPI wraps HTTPException(detail=...) in a top-level "detail"
    # field. Our error body lives inside it.
    detail: dict[str, Any] = body["detail"]
    assert detail["error"] == "pdf_corrupt"
    assert "malformed" in detail["detail"]


def test_extract_empty_upload_returns_400(test_client: TestClient) -> None:
    """An empty PDF upload returns 400 with ``empty_upload``."""
    response = test_client.post(
        "/v1/extract",
        data={"cv_id": "carol"},
        files={"cv_pdf": ("cv.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error"] == "empty_upload"


def test_extract_missing_cv_id_returns_422(
    test_client: TestClient, minimal_pdf_bytes: bytes
) -> None:
    """FastAPI's request validation rejects missing required fields."""
    response = test_client.post(
        "/v1/extract",
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 422


def test_extract_calls_link_with_correct_cv_id(
    test_client: TestClient,
    minimal_pdf_bytes: bytes,
    mock_matcher: MagicMock,
) -> None:
    """Module 3 Linker is invoked with the form's ``cv_id``."""
    test_client.post(
        "/v1/extract",
        data={"cv_id": "alice"},
        files={"cv_pdf": ("cv.pdf", minimal_pdf_bytes, "application/pdf")},
    )
    mock_matcher.link.assert_called_once()
    kwargs = mock_matcher.link.call_args.kwargs
    assert kwargs["cv_id"] == "alice"


def test_extract_payload_too_large_returns_413(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An upload exceeding ``max_pdf_size_mb`` returns 413."""
    # Patch the settings constructor used by the extract router to
    # return a tiny cap. The router constructs ``ApiSettings()``
    # fresh on each request so a monkeypatch on the class attribute
    # is the cleanest path.
    from api import settings as settings_module

    original_init = settings_module.ApiSettings.__init__

    def _tiny_init(self: settings_module.ApiSettings, **_kwargs: Any) -> None:
        original_init(self)
        # Force a 1-byte cap so any non-empty upload fails.
        object.__setattr__(self, "max_pdf_size_mb", 0)
        # ``max_pdf_size_bytes`` is a property — invalid bypass via
        # direct attribute write needs a tiny size_mb override
        # instead. Force size_mb=1 + multiplier hack:
        # 1 MB cap is still bigger than our 8-byte test payload, so
        # use the bytes property route instead — directly setting
        # ``max_pdf_size_mb=0`` would fail the pydantic ge=1 check.
        # Simpler approach: override max_pdf_size_bytes via property
        # patch on the instance.

    # Cleaner approach: just patch the property to return a tiny cap.
    monkeypatch.setattr(
        settings_module.ApiSettings,
        "max_pdf_size_bytes",
        property(lambda self: 1),
    )

    # 8 bytes > 1 byte cap.
    payload = b"%PDF-1.4"
    response = test_client.post(
        "/v1/extract",
        data={"cv_id": "alice"},
        files={"cv_pdf": ("cv.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"
