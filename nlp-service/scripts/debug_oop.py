"""One-shot diagnostic: does Module 2 detect OOP on real_cv3?

Bypasses Streamlit entirely. Forces a fresh PhraseMatcher build (no cache
reuse) so any stale cache state cannot mask the answer. Reports every
skill detected plus an explicit OOP / object-oriented search across the
output.

Run::

    cd C:\\Users\\silvi\\Desktop\\licenta2026\\app\\nlp-service
    .\\.venv\\Scripts\\Activate.ps1
    python scripts\\debug_oop.py

If this script finds OOP, then Streamlit is the problem (stale cached
pipeline — fully restart it). If this script does NOT find OOP either,
Module 2 has a real bug at the matcher level and needs deeper
investigation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

NLP_SERVICE_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = NLP_SERVICE_ROOT / ".cache" / "skill_extractor"
CV_PATH = NLP_SERVICE_ROOT / "tests" / "fixtures" / "real_cv3.pdf"


def clear_matcher_cache() -> int:
    """Delete cached PhraseMatcher .pkl files so the next load rebuilds."""
    if not CACHE_DIR.exists():
        print(f"[info] cache dir does not exist: {CACHE_DIR}")
        return 0
    removed = 0
    for pkl in CACHE_DIR.glob("phrasematcher_*.pkl"):
        pkl.unlink()
        removed += 1
        print(f"[clear] removed {pkl.name}")
    return removed


def main() -> int:
    print("=" * 70)
    print("Debug script: does Module 2 detect OOP on real_cv3.pdf?")
    print("=" * 70)

    if not CV_PATH.exists():
        print(f"[error] CV not found: {CV_PATH}")
        return 1

    print(f"\n[step 1] Clearing matcher cache so build runs fresh...")
    n_removed = clear_matcher_cache()
    print(f"[step 1] removed {n_removed} stale cache files")

    print("\n[step 2] Loading Module 1 + Module 2 (this may take ~90 s for "
          "a cold PhraseMatcher build)...")
    from cv_extractor import ExtractionPipeline
    from skill_extractor import SkillExtractor

    extractor = ExtractionPipeline()
    sk = SkillExtractor()

    print("\n[step 3] Running extraction + skill detection on real_cv3.pdf...")
    extraction = extractor.process(CV_PATH)
    text = extraction.text
    print(f"[step 3] extracted {len(text):,} chars, "
          f"language = {getattr(getattr(extraction, 'metadata', None), 'detected_language', None)}")

    # Verify OOP literally appears in the text
    oop_hits_in_text = list(re.finditer(r"\bOOP\b", text))
    print(f"\n[step 4] Literal 'OOP' occurrences in extracted text: {len(oop_hits_in_text)}")
    for hit in oop_hits_in_text[:5]:
        start = max(0, hit.start() - 40)
        end = min(len(text), hit.end() + 40)
        ctx = text[start:end].replace("\n", " ")
        print(f"          ... {ctx} ...")

    print("\n[step 5] Running Module 2 SkillExtractor...")
    result = sk.extract(extraction)

    print(f"\n[step 6] Detected {len(result.skills)} skills total:")
    for s in result.skills:
        print(f"   - {s.preferred_label:50s} | matched='{s.matched_text}' | "
              f"sect={s.section} | conf={s.confidence:.3f} | is_custom={s.is_custom}")

    # Explicit OOP search across all skill fields
    print("\n[step 7] Searching for OOP / object-oriented across all detected skills...")
    oop_matches = []
    for s in result.skills:
        haystack = (
            (s.preferred_label or "").lower()
            + " "
            + (s.matched_text or "").lower()
            + " "
            + " ".join((a or "").lower() for a in getattr(s, "alt_labels", []) or [])
        )
        if "oop" in haystack or "object-oriented" in haystack or "object oriented" in haystack:
            oop_matches.append(s)

    if oop_matches:
        print(f"\n✅ FOUND {len(oop_matches)} OOP-related match(es):")
        for s in oop_matches:
            print(f"   - {s.preferred_label} (matched='{s.matched_text}')")
        print("\n→ Module 2 IS detecting OOP correctly.")
        print("→ If Streamlit still shows no OOP, kill its process (Ctrl+C the "
              "terminal, don't just close the browser) and restart cleanly.")
        return 0
    else:
        print("\n❌ NO OOP-related skill detected.")
        print("\n→ Module 2 is NOT detecting OOP even with a fresh cache rebuild "
              "and the new tech_aliases overlay.")
        print("→ Root cause is at the matcher/lemmatiser level, not at the "
              "Streamlit cache level.")
        print("→ Next step: inspect the PhraseMatcher's pattern set for the "
              "OOP target URI directly via spaCy.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
