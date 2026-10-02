"""Pytest fixtures for the API test suite.

Two design constraints baked in here:

1. **No real model loads under unit tests.** The three pipelines
   (extractor, skill extractor, matcher) are replaced with hand-
   constructed mocks via FastAPI's ``app.dependency_overrides``
   mechanism. The slow E2E test (``test_e2e_slow.py``) opts back
   into real pipelines explicitly.

2. **Per-test app isolation.** ``app`` and ``test_client`` are
   function-scoped: each test gets a fresh app whose dependency
   overrides are torn down on exit. This prevents the
   ``@lru_cache`` singletons on ``api.deps`` from bleeding between
   tests.

The ``MockEncoder`` mentioned in the brief is intentionally not
re-imported here — it lives at ``skill_matcher.encoder.MockEncoder``
and is a public symbol. The API tests need a mock for the full
``(extractor, skill_extractor, matcher)`` tuple, not for a single
encoder; those mocks live below.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cv_extractor import ExtractionResult
from cv_extractor.models import (
    ExtractionMetadata,
    ExtractionMethod,
    PageInfo,
)
from skill_extractor import SkillExtractionResult
from skill_matcher.models import (
    EnrichedSkillResult,
    MatchCandidate,
    MatchedRequirement,
    MatchResult,
)

from api import create_app
from api.deps import (
    clear_dependency_caches,
    get_extraction_pipeline,
    get_skill_extractor,
    get_skill_matcher,
)
from api.settings import ApiSettings

# ---------------------------------------------------------------------------
# Minimal-but-valid fixture data
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_pdf_bytes() -> bytes:
    """Minimal byte buffer that looks like a PDF.

    Tests never actually invoke a PDF parser on this — the mocked
    extraction pipeline returns a stub ``ExtractionResult``. Eight
    bytes is enough to pass any naive magic-byte check the FastAPI
    multipart parser might apply.
    """
    return b"%PDF-1.4"


@pytest.fixture
def sample_extraction_result() -> ExtractionResult:
    """A minimal valid ``ExtractionResult`` for mocked Module 1 output."""
    return ExtractionResult(
        text="Experienced software engineer with Python and Java.",
        metadata=ExtractionMetadata(
            method_used=ExtractionMethod.PDFPLUMBER,
            total_pages=1,
            processing_time_ms=42,
            detected_language="en",
            is_scanned=False,
            quality_score=0.95,
            pages=[
                PageInfo(
                    page_number=1,
                    width=612.0,
                    height=792.0,
                    is_multi_column=False,
                    word_count=8,
                )
            ],
        ),
        warnings=[],
    )


@pytest.fixture
def sample_skill_extraction_result() -> SkillExtractionResult:
    """A minimal valid ``SkillExtractionResult`` for mocked Module 2 output."""
    return SkillExtractionResult(
        language="en",
        skills=[],  # Empty is fine — the matcher mock builds its own candidates.
        skill_count=0,
        processing_time_ms=12.0,
        warnings=[],
    )


@pytest.fixture
def sample_enriched_result() -> EnrichedSkillResult:
    """A minimal valid ``EnrichedSkillResult`` for mocked Linker output."""
    return EnrichedSkillResult(
        cv_id="test-cv",
        candidates=[
            MatchCandidate(
                skill_uri="http://data.europa.eu/esco/skill/python",
                skill_label="Python",
                confidence=0.85,
                source="lexical_kept",
                cv_evidence_text="Python",
                cv_evidence_offset=(35, 41),
                similarity_score=0.72,
                lexical_confidence=0.9,
            ),
            MatchCandidate(
                skill_uri="http://data.europa.eu/esco/skill/java",
                skill_label="Java",
                confidence=0.62,
                source="lexical_dropped",
                cv_evidence_text="Java",
                cv_evidence_offset=(46, 50),
                similarity_score=0.38,
                lexical_confidence=0.8,
            ),
            MatchCandidate(
                skill_uri="http://data.europa.eu/esco/skill/sw-eng",
                skill_label="software engineering",
                confidence=0.78,
                source="expansion",
                cv_evidence_text="Experienced software engineer with Python",
                cv_evidence_offset=None,
                similarity_score=0.81,
                lexical_confidence=None,
            ),
        ],
        detected_language="en",
        pipeline_version="skill_matcher@0.7.0+encoder=mock",
    )


@pytest.fixture
def sample_match_result(sample_enriched_result: EnrichedSkillResult) -> MatchResult:
    """A minimal valid ``MatchResult`` for mocked Scorer output."""
    python_candidate = sample_enriched_result.candidates[0]
    java_candidate = sample_enriched_result.candidates[1]

    from skill_matcher.models import JDRequirement

    req_python = JDRequirement(
        text="Python",
        skill_uri="http://data.europa.eu/esco/skill/python",
        skill_label="Python",
        importance="required",
        confidence=0.9,
    )
    req_java = JDRequirement(
        text="Java",
        skill_uri="http://data.europa.eu/esco/skill/java",
        skill_label="Java",
        importance="nice_to_have",
        confidence=0.5,
    )

    return MatchResult(
        # Echo the cv_id the match/full happy-path tests extract with
        # ("alice"). A real Scorer copies ``enriched.cv_id`` onto the
        # result; the mock must mirror that or the response cv_id would
        # never equal the request's.
        cv_id="alice",
        jd_id="test-jd",
        overall_score=0.072,  # Within Step 8 ``strong`` cut (>=0.060).
        required_coverage=1.0,
        nice_to_have_coverage=0.5,
        matched_required=[
            MatchedRequirement(
                requirement=req_python,
                cv_candidate=python_candidate,
                match_score=0.55,
            )
        ],
        matched_nice_to_have=[
            MatchedRequirement(
                requirement=req_java,
                cv_candidate=java_candidate,
                match_score=0.12,
            )
        ],
        unmatched_required=[],
        unmatched_nice_to_have=[],
        timestamp=dt.datetime(2026, 5, 17, 12, 0, 0, tzinfo=dt.timezone.utc),
        pipeline_version="skill_matcher@0.7.0+encoder=mock",
    )


# ---------------------------------------------------------------------------
# Mocked pipelines
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_extractor(sample_extraction_result: ExtractionResult) -> MagicMock:
    """A mock ``ExtractionPipeline`` whose ``.process`` returns a stub."""
    m = MagicMock()
    m.process.return_value = sample_extraction_result
    return m


@pytest.fixture
def mock_skill_extractor(
    sample_skill_extraction_result: SkillExtractionResult,
) -> MagicMock:
    """A mock ``SkillExtractor`` whose ``.extract`` returns a stub."""
    m = MagicMock()
    m.extract.return_value = sample_skill_extraction_result
    return m


@pytest.fixture
def mock_matcher(
    sample_enriched_result: EnrichedSkillResult,
    sample_match_result: MatchResult,
) -> MagicMock:
    """A mock ``SkillMatcher`` exposing ``.link``, ``.match`` and config."""
    from skill_matcher.config import SkillMatcherConfig

    m = MagicMock()
    m.link.return_value = sample_enriched_result
    m.match.return_value = sample_match_result
    m.config = SkillMatcherConfig()
    m._resolved_model_name = "mock-encoder"
    m._ensure_ready = MagicMock(return_value=None)
    return m


# ---------------------------------------------------------------------------
# App + TestClient wiring
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_esco_sha_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Make ``/v1/info`` use a fake ESCO SHA in unit tests.

    Without this, the info router would fall through to a real
    ``load_esco_concepts()`` call (which reads the on-disk taxonomy
    and takes hundreds of ms), making the unit test suite slow and
    coupled to fixture availability.
    """
    from api.routers import info as info_module

    monkeypatch.setattr(
        info_module,
        "_compute_esco_sha_if_missing",
        lambda _request: "deadbeef0000",
    )


@pytest.fixture
def app(
    mock_extractor: MagicMock,
    mock_skill_extractor: MagicMock,
    mock_matcher: MagicMock,
) -> Generator[FastAPI, None, None]:
    """Build a fresh FastAPI app per test with mocked pipelines.

    Dependency overrides are installed BEFORE the lifespan runs (we
    skip the eager warm-up via ``warmup_on_startup=False`` so the
    real ``SkillMatcher`` is never constructed during tests).
    """
    settings = ApiSettings(warmup_on_startup=False, cors_allow_origins=[])
    application = create_app(settings)
    application.dependency_overrides[get_extraction_pipeline] = lambda: mock_extractor
    application.dependency_overrides[get_skill_extractor] = lambda: mock_skill_extractor
    application.dependency_overrides[get_skill_matcher] = lambda: mock_matcher

    yield application

    application.dependency_overrides.clear()
    clear_dependency_caches()


@pytest.fixture
def test_client(app: FastAPI) -> Generator[TestClient, None, None]:
    """Return a ``TestClient`` over the per-test app."""
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Convenience: a small valid MatchRequest body builder
# ---------------------------------------------------------------------------


def build_match_request_body(extract_response_json: dict[str, Any]) -> dict[str, Any]:
    """Build a valid ``MatchRequest`` body around a previously-returned extract."""
    return {
        "cv_id": extract_response_json["cv_id"],
        "enriched": extract_response_json,
        "jd_id": "test-jd",
        "requirements": [
            {
                "text": "Python",
                "skill_uri": "http://data.europa.eu/esco/skill/python",
                "skill_label": "Python",
                "importance": "required",
                "confidence": 0.9,
            },
            {
                "text": "Java",
                "skill_uri": "http://data.europa.eu/esco/skill/java",
                "skill_label": "Java",
                "importance": "nice_to_have",
                "confidence": 0.5,
            },
        ],
    }


# ---------------------------------------------------------------------------
# Slow-test fixture: real eval-corpus CV + JD
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def real_cv1_pdf_path() -> Path:
    """Path to the real ``real_cv1.pdf`` fixture (used by slow tests)."""
    p = _REPO_ROOT / "tests" / "fixtures" / "real_cv1.pdf"
    if not p.exists():
        pytest.skip(f"Real CV fixture not present: {p}")
    return p


_REQUIRED_RE = re.compile(r"^required_skills:\n((?:- .*\n)+)", re.MULTILINE)
_NICE_RE = re.compile(r"^nice_to_have_skills:\n((?:- .*\n)+)", re.MULTILINE)


def _parse_jd_yaml(text: str) -> tuple[list[str], list[str]]:
    """Tiny YAML parser for the eval-corpus JD shape — required + nice lists.

    The eval-corpus YAML is hand-curated and uses a fixed schema; a
    full ``PyYAML`` import would work too, but this is dependency-
    free and easier to reason about under test.
    """

    def _extract(pattern: re.Pattern[str]) -> list[str]:
        match = pattern.search(text)
        if not match:
            return []
        block = match.group(1)
        return [line[2:].strip() for line in block.splitlines() if line.startswith("- ")]

    return _extract(_REQUIRED_RE), _extract(_NICE_RE)


@pytest.fixture
def jd1_requirements_json() -> list[dict[str, Any]]:
    """Return a small ``list[RequirementSchema]`` derived from ``jd1.yaml``."""
    p = _REPO_ROOT / "tests" / "fixtures" / "eval_corpus" / "jds" / "jd1.yaml"
    if not p.exists():
        pytest.skip(f"JD fixture not present: {p}")
    required, nice = _parse_jd_yaml(p.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    # Use a small number so the slow test doesn't blow up runtime.
    for label in required[:3]:
        out.append(
            {
                "text": label,
                "importance": "required",
                "confidence": 0.5,
            }
        )
    for label in nice[:2]:
        out.append(
            {
                "text": label,
                "importance": "nice_to_have",
                "confidence": 0.5,
            }
        )
    return out
