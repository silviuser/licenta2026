#!/usr/bin/env python3
"""Analyse a dataset folder of CV PDFs and emit a JSON report.

Usage::

    python scripts/analyze_dataset.py /path/to/cvs/
    python scripts/analyze_dataset.py /path/to/cvs/ --output report.json

Report fields:
  - total_count           Total PDFs found
  - avg_pages             Average page count
  - layout_distribution   {single_column, two_column, unknown} counts
  - scanned_vs_digital    {scanned, digital} counts
  - language_distribution {en, ro, unknown, …} counts
  - errors                List of {filename, error} for failed files
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

# Force UTF-8 stdout/stderr so we can print filenames containing non-cp1252
# characters (e.g. Romanian "ț") on Windows consoles without crashing.
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import CVExtractorError
from cv_extractor.pipeline import ExtractionPipeline, _detect_language
from cv_extractor.utils.logging import configure_logging


def analyse_file(
    pdf_path: Path,
    pipeline: ExtractionPipeline,
) -> dict[str, object]:
    """Extract metadata from a single PDF.

    Returns a dict with: pages, layout, scanned, language, error.
    """
    try:
        result = pipeline.process(pdf_path)
        meta = result.metadata

        multi_column_pages = sum(1 for p in meta.pages if p.is_multi_column)
        if multi_column_pages > 0:
            layout = "two_column"
        else:
            layout = "single_column"

        return {
            "pages": meta.total_pages,
            "layout": layout,
            "scanned": meta.is_scanned,
            "language": meta.detected_language or "unknown",
            "error": None,
        }
    except CVExtractorError as exc:
        return {
            "pages": 0,
            "layout": "unknown",
            "scanned": False,
            "language": "unknown",
            "error": f"{type(exc).__name__}: {exc}",
        }
    except Exception as exc:
        return {
            "pages": 0,
            "layout": "unknown",
            "scanned": False,
            "language": "unknown",
            "error": f"Unexpected: {exc}",
        }


def build_report(
    results: list[tuple[str, dict[str, object]]],
) -> dict[str, object]:
    """Aggregate per-file results into a summary report."""
    total = len(results)
    page_counts: list[int] = []
    layout_counter: Counter[str] = Counter()
    scanned_counter: Counter[str] = Counter()
    language_counter: Counter[str] = Counter()
    errors: list[dict[str, str]] = []

    for filename, data in results:
        if data["error"]:
            errors.append({"filename": filename, "error": str(data["error"])})
            continue

        page_counts.append(int(data["pages"]))  # type: ignore[arg-type]
        layout_counter[str(data["layout"])] += 1
        scanned_counter["scanned" if data["scanned"] else "digital"] += 1
        language_counter[str(data["language"])] += 1

    avg_pages = sum(page_counts) / len(page_counts) if page_counts else 0.0

    return {
        "total_count": total,
        "avg_pages": round(avg_pages, 2),
        "layout_distribution": dict(layout_counter),
        "scanned_vs_digital": dict(scanned_counter),
        "language_distribution": dict(language_counter),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse a CV dataset directory")
    parser.add_argument("pdf_dir", type=Path, help="Directory containing PDF files")
    parser.add_argument("--output", type=Path, default=Path("dataset_report.json"))
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    configure_logging(args.log_level)

    pdf_dir: Path = args.pdf_dir
    if not pdf_dir.is_dir():
        print(f"Error: {pdf_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF files found in {pdf_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Analysing {len(pdfs)} CV(s)…")

    config = ExtractorConfig(min_quality_score=0.1)
    pipeline = ExtractionPipeline(config=config, raise_on_low_quality=False)

    per_file_results: list[tuple[str, dict[str, object]]] = []
    for i, pdf_path in enumerate(pdfs, start=1):
        print(f"  [{i}/{len(pdfs)}] {pdf_path.name}", end="\r", flush=True)
        per_file_results.append((pdf_path.name, analyse_file(pdf_path, pipeline)))

    print()

    report = build_report(per_file_results)

    with args.output.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Report written to: {args.output}")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
