#!/usr/bin/env python3
"""Benchmark all three extractors against a directory of PDF CVs.

Usage::

    python scripts/benchmark.py /path/to/cvs/
    python scripts/benchmark.py /path/to/cvs/ --output results.csv

Output columns: filename, method, chars_extracted, time_ms, quality_score, error
"""

import argparse
import csv
import sys
import time
from pathlib import Path

# Force UTF-8 stdout/stderr so we can print filenames containing non-cp1252
# characters (e.g. Romanian "ț") on Windows consoles without crashing.
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")

# Allow running without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cv_extractor.config import ExtractorConfig
from cv_extractor.exceptions import CVExtractorError
from cv_extractor.extractors.ocr_extractor import OCRExtractor
from cv_extractor.extractors.pdfplumber_extractor import PdfPlumberExtractor
from cv_extractor.extractors.pymupdf_extractor import PyMuPDFExtractor
from cv_extractor.postprocess import QualityChecker, postprocess_text
from cv_extractor.utils.logging import configure_logging


def benchmark_file(
    pdf_path: Path,
    config: ExtractorConfig,
    checker: QualityChecker,
) -> list[dict[str, str]]:
    """Run all three extractors on one PDF and return a row per extractor."""
    extractors = [
        PdfPlumberExtractor(config),
        PyMuPDFExtractor(config),
        OCRExtractor(config),
    ]
    rows: list[dict[str, str]] = []

    for extractor in extractors:
        start = time.monotonic()
        chars = 0
        quality = 0.0
        error = ""

        try:
            raw = extractor.extract(pdf_path)
            text = postprocess_text(raw.text, was_ocr=(extractor.name == "ocr_tesseract"))
            chars = len(text)
            total_pages = len(raw.pages_info)
            quality = checker.score(text, total_pages)
        except CVExtractorError as exc:
            error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            error = f"Unexpected: {exc}"

        elapsed_ms = int((time.monotonic() - start) * 1000)
        rows.append(
            {
                "filename": pdf_path.name,
                "method": extractor.name,
                "chars_extracted": str(chars),
                "time_ms": str(elapsed_ms),
                "quality_score": f"{quality:.4f}",
                "error": error,
            }
        )

    return rows


def print_summary(rows: list[dict[str, str]]) -> None:
    """Print a grouped summary table to stdout."""
    from collections import defaultdict

    method_stats: dict[str, list[float]] = defaultdict(list)
    method_times: dict[str, list[int]] = defaultdict(list)
    method_errors: dict[str, int] = defaultdict(int)

    for row in rows:
        m = row["method"]
        if row["error"]:
            method_errors[m] += 1
        else:
            method_stats[m].append(float(row["quality_score"]))
            method_times[m].append(int(row["time_ms"]))

    header = f"{'Method':<20} {'Files OK':>8} {'Errors':>8} {'Avg Quality':>12} {'Avg Time (ms)':>14}"
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))

    for method in ("pdfplumber", "pymupdf", "ocr_tesseract"):
        scores = method_stats.get(method, [])
        times = method_times.get(method, [])
        errors = method_errors.get(method, 0)
        avg_q = sum(scores) / len(scores) if scores else 0.0
        avg_t = sum(times) // len(times) if times else 0
        print(f"{method:<20} {len(scores):>8} {errors:>8} {avg_q:>12.4f} {avg_t:>14}")

    print("=" * len(header) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark CV extractors")
    parser.add_argument("pdf_dir", type=Path, help="Directory containing PDF files")
    parser.add_argument("--output", type=Path, default=Path("benchmark_results.csv"))
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

    print(f"Benchmarking {len(pdfs)} PDF(s) with 3 extractors each…")

    config = ExtractorConfig()
    checker = QualityChecker(config)
    all_rows: list[dict[str, str]] = []

    for i, pdf_path in enumerate(pdfs, start=1):
        print(f"  [{i}/{len(pdfs)}] {pdf_path.name}", end="\r", flush=True)
        all_rows.extend(benchmark_file(pdf_path, config, checker))

    print()

    fieldnames = ["filename", "method", "chars_extracted", "time_ms", "quality_score", "error"]
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Results written to: {args.output}")
    print_summary(all_rows)


if __name__ == "__main__":
    main()
