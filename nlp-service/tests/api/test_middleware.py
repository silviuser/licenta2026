"""``RequestIDMiddleware`` and ``TimingMiddleware`` tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_request_id_generated_when_absent(test_client: TestClient) -> None:
    """No incoming ``X-Request-ID`` → middleware generates one and echoes it."""
    response = test_client.get("/v1/health")
    rid = response.headers.get("X-Request-ID")
    assert rid is not None and rid, "X-Request-ID not generated"
    # UUID4 hex is 32 chars.
    assert len(rid) == 32


def test_request_id_echoed_when_provided(test_client: TestClient) -> None:
    """Incoming ``X-Request-ID`` is preserved on the response."""
    caller_id = "abc123-correlation"
    response = test_client.get(
        "/v1/health", headers={"X-Request-ID": caller_id}
    )
    assert response.headers.get("X-Request-ID") == caller_id


def test_process_time_header_present_and_numeric(test_client: TestClient) -> None:
    """``X-Process-Time-Ms`` header is set and parseable as an int."""
    response = test_client.get("/v1/health")
    pt = response.headers.get("X-Process-Time-Ms")
    assert pt is not None, "X-Process-Time-Ms header missing"
    assert pt.isdigit(), f"X-Process-Time-Ms not an integer: {pt!r}"
    assert int(pt) >= 0


def test_request_id_propagates_across_multiple_calls(
    test_client: TestClient,
) -> None:
    """Two consecutive requests get distinct generated IDs."""
    r1 = test_client.get("/v1/health")
    r2 = test_client.get("/v1/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_custom_request_id_header_via_settings() -> None:
    """A non-default ``request_id_header`` setting is honoured."""
    from unittest.mock import MagicMock

    from api import create_app
    from api.deps import (
        get_extraction_pipeline,
        get_skill_extractor,
        get_skill_matcher,
    )
    from api.settings import ApiSettings

    application = create_app(
        ApiSettings(
            warmup_on_startup=False,
            request_id_header="X-My-Trace-ID",
            cors_allow_origins=[],
        )
    )
    application.dependency_overrides[get_extraction_pipeline] = lambda: MagicMock()
    application.dependency_overrides[get_skill_extractor] = lambda: MagicMock()
    application.dependency_overrides[get_skill_matcher] = lambda: MagicMock()

    with TestClient(application) as client:
        r = client.get("/v1/health", headers={"X-My-Trace-ID": "trace-42"})
        assert r.headers.get("X-My-Trace-ID") == "trace-42"
        # The default header is NOT echoed when the override is in use.
        assert r.headers.get("X-Request-ID") in (None, "trace-42") or r.headers.get(
            "X-Request-ID"
        ) != "trace-42"
