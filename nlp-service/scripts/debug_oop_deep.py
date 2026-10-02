"""Deep diagnostic for the OOP non-match — inspect runtime matcher state.

Prints:
1. DEFAULT_PHRASE_ATTR currently in the imported module
2. Cache file phrase_attr metadata (what attr was used at build time)
3. Whether the built PhraseMatcher has a pattern for the OOP URIs
4. Raw PhraseMatcher output on synthetic and real-CV text
5. Section assignment of any OOP match
6. Disambiguation filter outcome for the OOP match

Run::

    cd C:\\Users\\silvi\\Desktop\\licenta2026\\app\\nlp-service
    .\\.venv\\Scripts\\Activate.ps1
    python scripts\\debug_oop_deep.py
"""

from __future__ import annotations

import sys
from pathlib import Path

NLP_SERVICE_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = NLP_SERVICE_ROOT / ".cache" / "skill_extractor"
CV_PATH = NLP_SERVICE_ROOT / "tests" / "fixtures" / "real_cv3.pdf"


def main() -> int:
    print("=" * 70)
    print("STEP 1 — DEFAULT_PHRASE_ATTR at runtime")
    print("=" * 70)
    from skill_extractor.esco import matcher as matcher_mod

    print(f"  matcher_mod.DEFAULT_PHRASE_ATTR = {matcher_mod.DEFAULT_PHRASE_ATTR!r}")

    print()
    print("=" * 70)
    print("STEP 2 — Cache files on disk + their stored phrase_attr metadata")
    print("=" * 70)
    import pickle

    for pkl in CACHE_DIR.glob("phrasematcher_*.pkl"):
        try:
            with pkl.open("rb") as f:
                payload = pickle.load(f)
            stored_attr = getattr(payload, "phrase_attr", "<missing>")
            print(f"  {pkl.name}: phrase_attr = {stored_attr!r}")
        except Exception as e:
            print(f"  {pkl.name}: failed to inspect: {e}")

    print()
    print("=" * 70)
    print("STEP 3 — Load Module 2 and inspect the built matcher")
    print("=" * 70)
    from skill_extractor import SkillExtractor

    sk = SkillExtractor()
    # Trigger eager build by reaching into private state
    # The actual access path depends on internal structure — try common names
    print("  Triggering matcher build/load by extracting on a tiny text...")
    from cv_extractor.models import ExtractionResult

    er = ExtractionResult(
        text="I know OOP and Python.",
        method="test",
        chars=22,
        quality_score=1.0,
        elapsed_ms=0.0,
        warnings=[],
        metadata={"detected_language": "en"},
        is_likely_cv=True,
    )
    tiny_result = sk.extract(er)
    print(f"  Tiny extract: {len(tiny_result.skills)} skills detected")
    for s in tiny_result.skills:
        print(f"    - {s.preferred_label!r} matched={s.matched_text!r}")

    # Try to inspect the live matcher
    print()
    print("  Inspecting live matcher (best-effort, depends on internals)...")
    candidates = [
        "_built_matcher_en", "_matcher_en", "_built", "matcher_en",
        "_matchers", "_pipelines", "_matchers_by_lang",
    ]
    found = None
    for name in candidates:
        if hasattr(sk, name):
            print(f"    SkillExtractor has attribute: {name}")
            found = (name, getattr(sk, name))
            break
    if found is None:
        # Try via _pipeline
        for p_name in ["_pipeline", "pipeline", "_pipe"]:
            if hasattr(sk, p_name):
                pipe = getattr(sk, p_name)
                print(f"    SkillExtractor has pipeline-like attr: {p_name} ({type(pipe).__name__})")
                for sub in candidates + ["matcher", "_matcher", "matchers"]:
                    if hasattr(pipe, sub):
                        print(f"    Pipeline has: {sub}")

    print()
    print("=" * 70)
    print("STEP 4 — Direct spaCy + PhraseMatcher test with attr=LOWER")
    print("=" * 70)
    import spacy
    from spacy.matcher import PhraseMatcher

    nlp = spacy.load("en_core_web_lg")
    pm = PhraseMatcher(nlp.vocab, attr="LOWER")

    # Build pattern exactly as matcher.py does
    disabled = [n for n in nlp.pipe_names if n in ("parser", "ner")]
    with nlp.select_pipes(disable=disabled):
        pattern_docs = list(nlp.pipe(["OOP", "object oriented programming"]))
    pm.add("OOP_TEST", pattern_docs)

    test_text = (
        "Important Coursework: Data Structures & Algorithms, OOP, "
        "Web Technologies, Database systems."
    )
    text_doc = nlp(test_text)
    matches = pm(text_doc)
    print(f"  Pattern texts tokenized as: {[[t.text for t in d] for d in pattern_docs]}")
    print(f"  Pattern lower forms: {[[t.lower_ for t in d] for d in pattern_docs]}")
    print(f"  Text 'OOP' token: lower_={text_doc[10].lower_!r}" if len(text_doc) > 10 else "")
    print(f"  PhraseMatcher matches on test text: {len(matches)}")
    for match_id, start, end in matches:
        span = text_doc[start:end]
        print(f"    - '{span.text}' at chars [{span.start_char}:{span.end_char}]")

    print()
    print("=" * 70)
    print("STEP 5 — Full extract on real_cv3 with patched logging")
    print("=" * 70)
    from cv_extractor import ExtractionPipeline

    extractor = ExtractionPipeline()
    extraction = extractor.process(CV_PATH)
    full_result = sk.extract(extraction)

    print(f"  Full real_cv3 skills: {len(full_result.skills)}")
    # Check for any skill that should-have-been-OOP
    print()
    print("  Searching full text for 'OOP' position and what's around it...")
    text = extraction.text
    import re

    for m in re.finditer(r"\bOOP\b", text):
        # Find surrounding 100 chars
        start = max(0, m.start() - 100)
        end = min(len(text), m.end() + 100)
        snippet = text[start:end].replace("\n", " ⏎ ")
        print(f"    OOP at char {m.start()}: ...{snippet}...")

    print()
    print("Done. Compare output of STEP 4 (manual matcher) with the absence of")
    print("OOP in STEP 5 (production extractor). If STEP 4 finds OOP but STEP 5")
    print("doesn't, the issue is downstream of PhraseMatcher (filters or section).")
    print("If STEP 4 also doesn't find OOP, attr=LOWER did NOT take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
