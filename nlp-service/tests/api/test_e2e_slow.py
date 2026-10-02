"""Slow end-to-end test — real Module 1 + 2 + 3 against eval-corpus inputs.

Marked ``@pytest.mark.slow`` so the default fast suite skips it. Run
with ``pytest -m slow tests/api/test_e2e_slow.py`` after the
``[ml,api]`` extras are installed. Spends ~30-60 s the first time
(encoder + ESCO index cold load) and ~5-15 s on subsequent runs
(ESCO index cache hit).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.slow


@pytest.fixture
def real_app() -> Any:
    """Build a real app — NO dependency overrides — for the slow test."""
    from api import create_app
    from api.deps import clear_dependency_caches
    from api.settings import ApiSettings

    clear_dependency_caches()
    application = create_app(ApiSettings(warmup_on_startup=False))
    yield application
    application.dependency_overrides.clear()
    clear_dependency_caches()


def test_full_endpoint_against_real_cv1_and_jd1(
    real_app: Any,
    real_cv1_pdf_path: Path,
    jd1_requirements_json: list[dict[str, Any]],
) -> None:
    """End-to-end ``/v1/full`` with the real encoder and ESCO index."""
    with TestClient(real_app) as client:
        with real_cv1_pdf_path.open("rb") as fh:
            response = client.post(
                "/v1/full",
                data={
                    "cv_id": "real_cv1",
                    "jd_id": "jd1",
                    "requirements": json.dumps(jd1_requirements_json),
                },
                files={
                    "cv_pdf": (
                        real_cv1_pdf_path.name,
                        fh.read(),
                        "application/pdf",
                    )
                },
            )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cv_id"] == "real_cv1"
    assert 0.0 <= body["overall_score"] <= 1.0
    assert body["overall_class"] in {"strong", "possible", "no"}
    # The pipeline_version string carries the encoder identity; this
    # lets the thesis defence answer "which model produced this?"
    assert body["pipeline_version"].startswith("skill_matcher@")


def test_health_and_info_against_real_app(real_app: Any) -> None:
    """The real (un-mocked) app responds on ``/v1/health`` and ``/v1/info``."""
    with TestClient(real_app) as client:
        r1 = client.get("/v1/health")
        assert r1.status_code == 200
        r2 = client.get("/v1/info")
        assert r2.status_code == 200
        body = r2.json()
        # Encoder path is either a HF ID or a local path — both non-empty.
        assert body["encoder_path"]
        assert len(body["esco_sha"]) == 12
