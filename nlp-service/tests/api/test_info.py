"""``GET /v1/info`` tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

import cv_extractor
import skill_extractor
import skill_matcher


def test_info_returns_200_with_full_payload(test_client: TestClient) -> None:
    """``/v1/info`` returns 200 and a complete ``InfoResponse``."""
    response = test_client.get("/v1/info")
    assert response.status_code == 200, response.text
    body = response.json()

    # Module versions surfaced verbatim from the __init__.py constants.
    assert body["skill_matcher_version"] == skill_matcher.__version__
    assert body["skill_extractor_version"] == skill_extractor.__version__
    assert body["cv_extractor_version"] == cv_extractor.__version__

    # API surface has its own version.
    from api import __version__ as api_version

    assert body["nlp_service_version"] == api_version


def test_info_includes_placeholder_caveat(test_client: TestClient) -> None:
    """The Step 10 brief mandates surfacing the placeholder caveat."""
    response = test_client.get("/v1/info")
    body = response.json()
    caveat = body["placeholder_caveat"]
    assert "placeholder" in caveat.lower()
    assert len(caveat) > 50  # Non-trivial disclaimer, not just a token.


def test_info_includes_locked_thresholds(test_client: TestClient) -> None:
    """All seven Step 8 locked thresholds appear with correct keys."""
    response = test_client.get("/v1/info")
    thresholds = response.json()["locked_thresholds"]
    expected_keys = {
        "drop_threshold",
        "keep_threshold",
        "expansion_threshold",
        "per_requirement_keep_threshold",
        "required_weight",
        "t1_strong_threshold",
        "t2_possible_threshold",
    }
    assert set(thresholds.keys()) == expected_keys
    # Step 8 invariant: T2 < T1.
    assert thresholds["t2_possible_threshold"] < thresholds["t1_strong_threshold"]


def test_info_includes_encoder_identity(test_client: TestClient) -> None:
    """Encoder path and SHA are surfaced."""
    response = test_client.get("/v1/info")
    body = response.json()
    assert body["encoder_path"]  # Non-empty.
    assert body["encoder_sha"] is None or (
        isinstance(body["encoder_sha"], str) and len(body["encoder_sha"]) == 12
    )


def test_info_response_validates_against_schema(test_client: TestClient) -> None:
    """Full round-trip through ``InfoResponse``."""
    from api.schemas import InfoResponse

    response = test_client.get("/v1/info")
    parsed = InfoResponse.model_validate(response.json())
    assert parsed.skill_matcher_version == skill_matcher.__version__
