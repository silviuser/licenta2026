"""Shared pytest fixtures for the cv_extractor test suite.

Fixture PDFs are generated at session scope using reportlab so the test suite
has no dependency on committed binary files.  Replace them with real anonymised
CVs for more meaningful integration coverage (see README).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cv_extractor.config import ExtractorConfig
from cv_extractor.models import ExtractionMethod, PageInfo, RawExtraction

# ---------------------------------------------------------------------------
# Helpers — PDF generation via reportlab
# ---------------------------------------------------------------------------

def _make_reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def _generate_single_column_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    lines = [
        "John Doe",
        "Software Engineer",
        "",
        "Experience",
        "Senior Developer at Acme Corp, 2020-2024",
        "Worked on backend systems and microservices.",
        "",
        "Education",
        "B.Sc. Computer Science, University of Bucharest, 2016-2020",
        "",
        "Skills",
        "Python, Java, SQL, Docker, Kubernetes",
        "",
        "Languages",
        "English (fluent), Romanian (native)",
        "",
        "Contact",
        "john.doe@example.com | +40 700 000 000",
    ]

    y = height - 50
    for line in lines:
        c.drawString(50, y, line)
        y -= 20

    c.save()


def _generate_two_column_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    mid = width / 2

    left_lines = [
        "Jane Smith",
        "Data Scientist",
        "",
        "Contact",
        "jane@example.com",
        "+40 711 222 333",
        "",
        "Skills",
        "Python",
        "Machine Learning",
        "SQL",
        "TensorFlow",
        "",
        "Languages",
        "English",
        "Romanian",
    ]

    right_lines = [
        "Experience",
        "ML Engineer, TechCorp 2021-2024",
        "Built recommendation systems.",
        "",
        "Data Analyst, StartupXYZ 2019-2021",
        "Analyzed user behaviour data.",
        "",
        "Education",
        "M.Sc. AI, Polytechnic 2017-2019",
        "B.Sc. Math, University 2013-2017",
        "",
        "Projects",
        "CV Screening Tool (Python)",
        "Sales Forecasting Dashboard",
    ]

    y = height - 50
    for line in left_lines:
        c.drawString(30, y, line)
        y -= 20

    y = height - 50
    for line in right_lines:
        c.drawString(mid + 20, y, line)
        y -= 20

    c.save()


def _generate_minimal_pdf(path: Path) -> None:
    """A valid but nearly empty PDF (triggers low-quality / fallback paths)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawString(100, 700, "   ")
    c.save()


def _generate_corrupt_pdf(path: Path) -> None:
    """Write a file with a PDF header but corrupt body."""
    path.write_bytes(b"%PDF-1.4\n%%garbage\x00\xff\xfe broken content")


# ---------------------------------------------------------------------------
# Session-scoped fixture PDF generation
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def generate_fixture_pdfs() -> None:
    """Generate sample PDFs once per test session if reportlab is available."""
    FIXTURE_DIR.mkdir(exist_ok=True)

    if not _make_reportlab_available():
        pytest.skip("reportlab not installed — cannot generate fixture PDFs")
        return

    _generate_single_column_pdf(FIXTURE_DIR / "single_column.pdf")
    _generate_two_column_pdf(FIXTURE_DIR / "two_column.pdf")
    _generate_minimal_pdf(FIXTURE_DIR / "minimal.pdf")
    _generate_corrupt_pdf(FIXTURE_DIR / "corrupt.pdf")


# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def extractor_config() -> ExtractorConfig:
    """Return a test-friendly config with relaxed thresholds."""
    return ExtractorConfig(
        min_chars_per_page=10,
        min_quality_score=0.1,
        column_gap_ratio=0.1,
        column_min_words=5,
        log_level="DEBUG",
    )


# ---------------------------------------------------------------------------
# Path fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_column_pdf() -> Path:
    return FIXTURE_DIR / "single_column.pdf"


@pytest.fixture
def two_column_pdf() -> Path:
    return FIXTURE_DIR / "two_column.pdf"


@pytest.fixture
def minimal_pdf() -> Path:
    return FIXTURE_DIR / "minimal.pdf"


@pytest.fixture
def corrupt_pdf() -> Path:
    return FIXTURE_DIR / "corrupt.pdf"


# ---------------------------------------------------------------------------
# Mock pdfplumber page fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_pdfplumber_page() -> MagicMock:
    """A MagicMock that mimics a pdfplumber Page object."""
    page = MagicMock()
    page.page_number = 1
    page.width = 595.0
    page.height = 842.0
    page.bbox = (0, 0, 595.0, 842.0)
    page.extract_words.return_value = [
        {"x0": 50.0, "top": 100, "text": "Experience"},
        {"x0": 50.0, "top": 120, "text": "Engineer"},
        {"x0": 50.0, "top": 140, "text": "Education"},
        {"x0": 50.0, "top": 160, "text": "Skills"},
        {"x0": 50.0, "top": 180, "text": "Python"},
    ]
    page.extract_text.return_value = (
        "Experience Engineer Education Skills Python"
    )
    return page


# ---------------------------------------------------------------------------
# Raw extraction fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_raw_extraction() -> RawExtraction:
    return RawExtraction(
        text="John Doe\n\nExperience\nSenior Engineer\n\nEducation\nB.Sc. CS\n\nSkills\nPython",
        method=ExtractionMethod.PDFPLUMBER,
        pages_info=[
            PageInfo(
                page_number=1,
                width=595.0,
                height=842.0,
                is_multi_column=False,
                word_count=12,
            )
        ],
    )
