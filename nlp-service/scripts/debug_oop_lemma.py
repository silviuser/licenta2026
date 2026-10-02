"""Diagnose the OOP non-match by inspecting spaCy lemmas directly.

Hypothesis: spaCy's lemmatiser returns a different ``lemma_`` for the
standalone acronym ``OOP`` (used to build the PhraseMatcher pattern)
versus ``OOP`` seen in CV context (used at match time). PhraseMatcher
with ``attr="LEMMA"`` then has nothing to match against.

This script prints the lemma_ in both contexts. If they differ, the
root cause is confirmed.

Run::

    cd C:\\Users\\silvi\\Desktop\\licenta2026\\app\\nlp-service
    .\\.venv\\Scripts\\Activate.ps1
    python scripts\\debug_oop_lemma.py
"""

from __future__ import annotations

import spacy


def main() -> int:
    print("Loading en_core_web_lg...")
    nlp = spacy.load("en_core_web_lg")
    print(f"  pipe components: {nlp.pipe_names}\n")

    test_terms = ["OOP", "CRUD", "API", "REST", "SQL"]
    cv_context = (
        "Important Coursework: Data Structures & Algorithms, "
        "OOP, Web Technologies, Database systems. "
        "Skills: SQL, REST API, CRUD operations."
    )

    print("=" * 70)
    print("Pattern-side lemmas (matcher.py uses nlp.pipe with parser+ner disabled)")
    print("=" * 70)
    # This mimics the matcher's pattern build path exactly
    disabled = [n for n in nlp.pipe_names if n in ("parser", "ner")]
    with nlp.select_pipes(disable=disabled):
        pattern_docs = list(nlp.pipe(test_terms))
    for term, doc in zip(test_terms, pattern_docs, strict=True):
        for tok in doc:
            print(f"  pattern '{term}': text={tok.text!r:8s} lemma_={tok.lemma_!r:8s} "
                  f"pos_={tok.pos_:6s} tag_={tok.tag_:6s}")

    print()
    print("=" * 70)
    print("Text-side lemmas (full nlp() on the CV context)")
    print("=" * 70)
    full_doc = nlp(cv_context)
    for tok in full_doc:
        if tok.text in test_terms:
            print(f"  text '{tok.text}': lemma_={tok.lemma_!r:8s} "
                  f"pos_={tok.pos_:6s} tag_={tok.tag_:6s}")

    print()
    print("=" * 70)
    print("Direct match comparison (this is what PhraseMatcher with attr=LEMMA checks)")
    print("=" * 70)
    pattern_lemmas = {}
    for term, doc in zip(test_terms, pattern_docs, strict=True):
        pattern_lemmas[term] = [t.lemma_ for t in doc]

    text_lemmas = {}
    for tok in full_doc:
        if tok.text in test_terms:
            text_lemmas.setdefault(tok.text, []).append(tok.lemma_)

    for term in test_terms:
        plemma = pattern_lemmas.get(term, [])
        tlemma = text_lemmas.get(term, [])
        will_match = bool(set(plemma) & set(tlemma))
        status = "✅ MATCH" if will_match else "❌ NO MATCH"
        print(f"  {term:6s}  pattern lemma={plemma}  text lemma={tlemma}  → {status}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
