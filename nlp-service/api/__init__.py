"""HR Helper NLP Service — FastAPI surface (Step 10 deliverable).

This package wraps the framework-agnostic ``skill_matcher`` /
``skill_extractor`` / ``cv_extractor`` triple in an HTTP service.
It is intentionally not part of the wheel (see
``pyproject.toml`` -> ``[tool.hatch.build.targets.wheel]``) — the
service is a deployment artefact run by source checkout.

Public symbols re-exported for convenience:
    - ``create_app`` — FastAPI factory
    - ``ApiSettings`` — env-var-backed settings
    - every request / response schema

The package version (``__version__``) is independent of the three
underlying-module versions; bumps signal contract-level changes
(e.g. a new endpoint, a breaking schema change).
"""

__version__ = "0.1.0"

from api.main import create_app
from api.schemas import (
    CandidateSchema,
    CandidateSourceLiteral,
    ErrorResponse,
    ExtractResponse,
    FullResponse,
    HealthResponse,
    ImportanceLiteral,
    InfoResponse,
    LanguageCode,
    MatchRequest,
    MatchResponse,
    MatchedRequirementSchema,
    OverallClassLiteral,
    ReadinessResponse,
    RequirementSchema,
)
from api.settings import ApiSettings

__all__ = [
    "ApiSettings",
    "CandidateSchema",
    "CandidateSourceLiteral",
    "ErrorResponse",
    "ExtractResponse",
    "FullResponse",
    "HealthResponse",
    "ImportanceLiteral",
    "InfoResponse",
    "LanguageCode",
    "MatchRequest",
    "MatchResponse",
    "MatchedRequirementSchema",
    "OverallClassLiteral",
    "ReadinessResponse",
    "RequirementSchema",
    "__version__",
    "create_app",
]
