"""Convert raw .txt LinkedIn-style JDs into structured YAML fixtures.

Reads each ``.txt`` file in ``tests/fixtures/eval_corpus/jds_raw/`` and
writes a ``.yaml`` fixture in ``tests/fixtures/eval_corpus/jds/`` with:

* ``id`` — derived from filename (``jd1.txt`` → ``jd1``).
* ``title`` — first non-empty line of the raw text.
* ``language`` — detected via ``lingua`` over the full text.
* ``raw_text`` — the original ``.txt`` content, verbatim.
* ``required_skills`` / ``nice_to_have_skills`` — best-effort regex
  extraction from sections labelled "Required Skills", "Mandatory",
  "Must Have", "Nice to Have", "Optional", "Plus", etc. (English +
  Romanian variants).
* ``location``, ``category``, ``seniority``, ``source_anonymized``,
  ``notes`` — left as defaults for the human to review.

Run from the ``nlp-service/`` directory after activating the venv::

    python scripts/convert_jds.py

Idempotent: re-running overwrites the output YAMLs, so any manual edits
to the YAML files are lost on re-run. Treat the YAML files as the source
of truth once you have edited them, and edit the ``.txt`` only if the
raw scrape itself changes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# stdout reconfigure for Windows cp1252 console — Romanian / em-dash
# in titles breaks it otherwise.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, OSError):
    pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = _REPO_ROOT / "tests" / "fixtures" / "eval_corpus" / "jds_raw"
DEFAULT_OUT_DIR = _REPO_ROOT / "tests" / "fixtures" / "eval_corpus" / "jds"


# Section-header regexes — case-insensitive, matched on standalone lines.
# Order matters: more specific patterns first so they win over generic ones.
_REQUIRED_HEADERS = [
    # Strong, unambiguous required-section headers
    r"mandatory\s+skills?(?:\s+description)?",
    # "Required Skills" with optional middle word ("Required Technical Skills")
    r"required(?:\s+\w+)?\s+skills?(?:\s+description)?(?:\s*&\s*profile)?",
    r"must[\- ]have(?:\s+[\w/]+)*(?:\s+qualifications?|\s+skills?)?",
    r"tech\s+stack\s*\(?\s*required\s+skills?\s*\)?",
    r"qualifications?(?:\s*[/]\s*technical\s+skills?)?",
    r"technical\s+skills?",
    r"requirements?",
    # Weaker but common LinkedIn headers
    r"we\s+are\s+looking\s+for",
    r"what\s+(?:we\s+expect|you\s+(?:need|bring))",
    r"your\s+profile",
    r"you\s+should(?:\s+ideally)?\s+have",
    r"if\s+you\s+(?:are|have)",
    # Bare "Skills" as a last-resort fallback (low precision, but the
    # alternative is missing the section entirely).
    r"skills(?:\s+(?:&|and)\s+(?:profile|experience))?",
    # Romanian
    r"(?:abilităț?i|cerințe)\s+obligatorii?",
]
_NICE_HEADERS = [
    r"nice[\- ]to[\- ]have(?:\s+skills?)?(?:\s+description)?",
    r"would\s+be\s+(?:a\s+)?plus",
    r"optional(?:\s+skills?)?",
    r"bonus(?:\s+points?)?",
    r"plus(?:es)?",
    r"other\s+skills?",
    r"additional\s+skills?",
    r"(?:experience\s+of\s+)?the\s+following\s+is\s+(?:also\s+)?desirable",
    r"desirable\s+skills?",
    r"considered\s+a\s+plus",
    # Romanian
    r"(?:abilităț?i|cerințe)\s+opționale",
    r"considerate\s+ca\s+un\s+plus",
]
# Headers that terminate any preceding section.
_TERMINATOR_HEADERS = [
    r"benefits?",
    r"we\s+offer",
    r"what\s+we\s+offer",
    r"compensation\s+package",
    r"health\s+and\s+wellbeing",
    r"professional\s+growth",
    r"about\s+(?:us|the\s+company)",
    r"responsibilities",
    r"main\s+responsibilities",
    r"key\s+responsibilities",
    r"primary\s+functions",
    r"job\s+description",
    r"about\s+the\s+role",
    r"how\s+we\s+work",
    r"project\s+description",
    r"offer",
    r"for\s+more\s+information",
]


def _build_header_regex(patterns: list[str]) -> re.Pattern[str]:
    alternation = "|".join(f"(?:{p})" for p in patterns)
    # Optional leading decoration (emoji like "🧩" or bullet) + space.
    # After the keyword: optional decoration in parens/ampersand (up to
    # 60 chars) and optional punctuation. The whole line still has to
    # end there, so paragraph text like "Required skills are essential
    # for this role" does NOT match.
    return re.compile(
        rf"^\s*(?:[^\w\s]+\s+)?(?:{alternation})"
        rf"\s*(?:[\(\&][^\n]{{0,60}})?"
        rf"\s*[:\-–\.]?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )


_REQUIRED_RE = _build_header_regex(_REQUIRED_HEADERS)
_NICE_RE = _build_header_regex(_NICE_HEADERS)
_TERMINATOR_RE = _build_header_regex(
    _TERMINATOR_HEADERS + _REQUIRED_HEADERS + _NICE_HEADERS
)


def _extract_section(text: str, header_re: re.Pattern[str]) -> str | None:
    """Return the block of text after the first matching header, up to
    the next terminator (or end of text). ``None`` if no header found."""
    m = header_re.search(text)
    if not m:
        return None
    block_start = m.end()
    m_end = _TERMINATOR_RE.search(text, pos=block_start)
    block_end = m_end.start() if m_end else len(text)
    return text[block_start:block_end]


def _block_to_bullets(block: str) -> list[str]:
    """Extract bullet-like items from a free-form section block."""
    bullets: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        # Strip common bullet prefixes.
        line = re.sub(r"^[\-•▪●\*]+\s*", "", line)
        if not line or len(line) < 3 or len(line) > 240:
            continue
        bullets.append(line)
    return bullets


def _detect_language(text: str) -> str:
    """Return "en" or "ro" via ``lingua``. Falls back to "en" if the
    package is unavailable or the detector abstains."""
    try:
        from lingua import Language, LanguageDetectorBuilder
    except ImportError:
        return "en"
    detector = (
        LanguageDetectorBuilder.from_languages(
            Language.ENGLISH, Language.ROMANIAN
        ).build()
    )
    result = detector.detect_language_of(text)
    if result is None:
        return "en"
    return "ro" if "ROMANIAN" in result.name else "en"


def convert_jd(raw_path: Path, out_dir: Path) -> tuple[Path, dict[str, Any]]:
    """Convert one raw ``.txt`` JD into a YAML fixture."""
    text = raw_path.read_text(encoding="utf-8")
    non_empty = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = non_empty[0] if non_empty else "Untitled"

    language = _detect_language(text)

    req_block = _extract_section(text, _REQUIRED_RE)
    nice_block = _extract_section(text, _NICE_RE)
    required_skills = _block_to_bullets(req_block) if req_block else []
    nice_to_have_skills = _block_to_bullets(nice_block) if nice_block else []

    fixture: dict[str, Any] = {
        "id": raw_path.stem,
        "title": title,
        "language": language,
        "location": "",
        "category": "swe",
        "seniority": "unspecified",
        "source_anonymized": "",
        "raw_text": text,
        "required_skills": required_skills,
        "nice_to_have_skills": nice_to_have_skills,
        "notes": "",
    }
    out_path = out_dir / f"{raw_path.stem}.yaml"
    out_path.write_text(
        yaml.safe_dump(
            fixture, sort_keys=False, allow_unicode=True, width=120
        ),
        encoding="utf-8",
    )
    return out_path, fixture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert raw .txt JDs to YAML fixtures."
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    if not args.raw_dir.exists():
        print(f"ERROR: raw dir does not exist: {args.raw_dir}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(args.raw_dir.glob("jd*.txt"))
    if not raw_files:
        print(
            f"ERROR: no jd*.txt files found in {args.raw_dir}", file=sys.stderr
        )
        return 1

    print(f"Converting {len(raw_files)} JDs")
    print(f"  from: {args.raw_dir}")
    print(f"  into: {args.out_dir}")
    print()
    print(f"{'file':12s}  {'lang':4s}  {'req':>3s}  {'nice':>4s}  title")
    print("-" * 90)
    for raw_path in raw_files:
        _, fx = convert_jd(raw_path, args.out_dir)
        title_clip = fx["title"][:60]
        print(
            f"{raw_path.name:12s}  {fx['language']:4s}  "
            f"{len(fx['required_skills']):3d}  "
            f"{len(fx['nice_to_have_skills']):4d}  {title_clip}"
        )

    print()
    print(f"Wrote {len(raw_files)} YAML fixtures.")
    print("Next, edit each fixture and fill in:")
    print("  - required_skills / nice_to_have_skills (regex is best-effort)")
    print("  - category (swe | data | devops | qa | frontend | backend | non_tech)")
    print("  - seniority (junior | mid | senior | unspecified)")
    print("  - location (e.g. 'Bucharest', 'Remote')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
