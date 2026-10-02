"""OpenAPI generation tests — guards against internal-type leakage.

Risk #5 from Pre-Flight: pydantic auto-generation could leak internal
``skill_matcher.models`` types into the OpenAPI spec. These tests
assert that every named schema in ``app.openapi()`` belongs to the
``api.schemas`` namespace.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import api.schemas as api_schemas


def _api_schema_names() -> set[str]:
    """Return the set of pydantic class names exported from ``api.schemas``."""
    out: set[str] = set()
    for name in api_schemas.__all__:
        obj = getattr(api_schemas, name)
        if isinstance(obj, type):
            out.add(obj.__name__)
    return out


def test_openapi_components_only_reference_api_schemas(
    test_client: TestClient,
) -> None:
    """Every component schema name in the OpenAPI spec is an API schema.

    FastAPI / pydantic add a few framework-owned schemas
    (``HTTPValidationError``, ``ValidationError``) which are
    explicitly allowed.
    """
    spec = test_client.app.openapi()  # type: ignore[attr-defined]
    components = spec.get("components", {}).get("schemas", {})
    api_names = _api_schema_names()
    framework_allowed = {
        "HTTPValidationError",
        "ValidationError",
        "Body_extract_v1_extract_post",
        "Body_full_v1_full_post",
    }
    leaked = set(components.keys()) - api_names - framework_allowed
    assert not leaked, (
        f"Internal types leaked into the OpenAPI spec: {sorted(leaked)}"
    )


def test_openapi_lists_all_v1_endpoints(test_client: TestClient) -> None:
    """All five v1 endpoints appear in the OpenAPI paths."""
    spec = test_client.app.openapi()  # type: ignore[attr-defined]
    paths = set(spec["paths"].keys())
    expected = {
        "/v1/health",
        "/v1/readyz",
        "/v1/info",
        "/v1/extract",
        "/v1/match",
        "/v1/full",
    }
    assert expected.issubset(paths), (
        f"Missing endpoints in OpenAPI: {expected - paths}"
    )


def test_openapi_title_and_description(test_client: TestClient) -> None:
    """OpenAPI ``info`` title + description follow Q3 decision."""
    spec = test_client.app.openapi()  # type: ignore[attr-defined]
    assert spec["info"]["title"] == "HR Helper NLP Service"
    description = spec["info"]["description"]
    assert "APLICAȚIE DE ANALIZĂ" in description
    assert "ASE / CSIE Bucharest" in description
