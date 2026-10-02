# skill_extractor — Module 2 of HR Helper NLP service

Symbolic, interpretable baseline that maps free-text CV content to
[ESCO](https://esco.ec.europa.eu/) skill URIs. Consumes the output of
Module 1 (`cv_extractor.ExtractionResult`) and produces a typed
`SkillExtractionResult` with per-skill URI, surface form, span(s) in
the source text, the CV section the skill was found in, a confidence
score, and a frequency count.

This module is the **interpretable baseline** of the HR Helper system.
Module 3 will build a fine-tuned sentence-transformer on top of it for
the semantic CV ↔ JD matching task; this baseline gives us the
*"why was this candidate scored this way?"* answer that GDPR / HR /
anti-bias review explicitly requires.

## Usage

```python
from pathlib import Path
from cv_extractor import ExtractionPipeline
from skill_extractor import SkillExtractor

# Module 1: PDF → ExtractionResult
extraction = ExtractionPipeline().process(Path("cv.pdf"))

# Module 2: ExtractionResult → SkillExtractionResult
skills = SkillExtractor().extract(extraction)

for s in skills.skills:
    print(f"{s.preferred_label:40s}  {s.section:12s}  conf={s.confidence:.2f}  freq={s.frequency}")
```

You can also pass `(text, language)` directly when you have raw text:

```python
result = SkillExtractor().extract(("I write Python and SQL daily.", "en"))
```

## Architectural decisions

### 1. ESCO as the taxonomy

* Official EU standard, maintained by the European Commission and
  updated yearly.
* Multilingual (we ship the English v1.2.1 bundle; Romanian and 27
  other languages are available).
* Free for commercial use (CC-BY-4.0 with attribution).
* Each skill has a stable URI we can quote in audit logs.
* Alternatives considered: Lightcast (formerly EMSI) requires a
  commercial licence; O\*NET is US-centric and lacks Romanian
  translations; SkillsTax is small.

### 2. PhraseMatcher on `LEMMA`, not embeddings

A spaCy `PhraseMatcher` runs in `O(text-length)` and is deterministic.
Every hit has a traceable surface form, a canonical URI and a textual
explanation. **That's exactly what HR / GDPR review requires from an
automated screening system**: "we scored candidate X high on Python
because we matched the token `Python` in their Skills section against
ESCO URI `…/python-computer-programming`."

We match on the `LEMMA` attribute so simple inflections work
(`developing` → `develop`). For lower-resource pipelines (tests use
`spacy.blank`) the attr is configurable via
`SkillExtractorConfig.phrase_attr` and falls back to `LOWER`.

### 3. Symbolic filters layered on top of the matcher

The matcher produces high-recall, low-precision hits. We add two
deterministic, side-effect-free filters:

* **Negation filter** (`filters/negation.py`): regex-anchored against
  the 50 characters immediately preceding a match. Drops things like
  "no experience with X", "nu am lucrat cu X". Per-language English
  and Romanian regex unions; diacritics are stripped before matching
  so Romanian patterns can stay plain ASCII.
* **NER disambiguation** (`filters/disambiguation.py`): drops matches
  whose span overlaps a `spaCy` `ORG`/`GPE`/`LOC`/`PERSON`/`FAC`/`NORP`
  entity *outside the Skills section*. A curated tech whitelist
  (~120 entries: Python, Java, AWS, …) prevents the obvious
  misclassifications. Inside the Skills section we trust the matcher
  unconditionally — NER models trained on running prose are
  notoriously unreliable on dense, comma-separated skill listings.

Both filters are framework-agnostic dataclasses; the pipeline pulls
NER entities out of the spaCy `Doc` and passes them in as plain
`EntitySpan` objects. This is what lets us unit-test the filters with
no spaCy at all.

### 4. Section detection by dictionary lookup

`sections/detector.py` matches each line of the CV against a curated
dictionary of ~65 English and Romanian section header strings
(`Skills`, `Experience`, `Competențe`, `Limbi străine`, …). The line
is normalised — lower-cased, trailing punctuation stripped, diacritics
removed — before lookup so `COMPETENȚE:`, `Competente`,
`competențe ──` all match the same entry.

Why not an ML classifier? CV section detection is a textbook
high-precision deterministic task: 95 % of CV authors use a small set
of headers verbatim. A classifier would add training data, version
skew and opacity for negligible recall gain. The thesis defence wants
explainability.

### 5. Confidence scoring (formula + justification)

The confidence score `c` for a detected skill is

```
c = clamp( w_section × w_match × s(f) / s(1) ,   0, 1 )

with  s(f) = 1 + ln(1 + f)
```

* **`w_section`** ∈ \[0.5, 1.0\]: how canonical the section is.
  `skills=1.0`, `experience=languages=0.9`, `education=0.7`,
  `profile=other=0.5`. A skill listed under `Skills` is the most
  canonical evidence; a skill name appearing in a `Summary` blurb is
  the least.
* **`w_match`** ∈ \[0.7, 1.0\]: how surface-faithful the match is.
  `exact=1.0` (matched the canonical `preferredLabel`),
  `alt=0.85` (matched one of the curated `altLabels`),
  `lemma=0.7` (matched only via lemmatisation, different surface form).
* **`s(f)`**: logarithmic saturation on frequency. Listing a skill
  ten times is not ten times more credible than listing it once;
  diminishing returns are the right model. The divisor `s(1) = 1 +
  ln 2 ≈ 1.693` anchors the baseline so a single (exact, skills) hit
  lands at exactly `c = 1.0` before clamping.
* **Clamp**: confidence over 1 means *saturated*, not *wrong* — that's
  by design.

All four weight tables live in `SkillExtractorConfig` and are
auditable, not hard-coded.

### 6. ESCO matcher cache

Building the PhraseMatcher over ~13 939 skills (~25 000 patterns once
we include `altLabels` overlaid by the language-skills collection)
takes ~10–60 s the first time. We persist the tokenised patterns as
spaCy `DocBin` bytes plus a small pickle metadata sidecar; the cache
filename embeds an 8-char SHA-256 prefix of the source CSVs, so
updating the ESCO bundle automatically invalidates the cache.
Subsequent runs reload the cache in well under a second.

The cache is in `nlp-service/.cache/skill_extractor/` (gitignored).

## What this module **does not** do

* It does not match CVs against Job Descriptions. That's Module 3.
* It does not compute semantic similarity / embeddings. Module 3.
* It does not fine-tune any model. Module 3.
* It does not expose a REST API. A future microservice layer will
  wrap it; the package itself is deliberately framework-agnostic and
  contains no `import fastapi` / `import flask` calls.
* It does not parse PDFs. It consumes the post-processed text from
  Module 1 (`cv_extractor.ExtractionResult`).

## Known limitations

These are the limitations Module 3 is designed to address. Quoting
them up-front in the thesis defence is the cleanest way to motivate
the fine-tuned sentence-transformer.

1. **Recall is weak on natural-language formulations.** A candidate
   who writes *"developed asynchronous distributed messaging systems"*
   will not get credited for Kafka / RabbitMQ / SQS because none of
   those literal tokens appear. Module 3's semantic encoder closes
   this gap.
2. **List-form negation is not caught.** *"No experience with X, Y,
   and Z"* — the regex is anchored, so only `X` (immediately adjacent
   to the negation) is dropped; `Y` and `Z` slip through. Documented
   trade-off: catching list-form negation would require dependency
   parsing and produce too many false positives on lists that *do*
   end with positive content ("no experience with X, but excellent
   with Z").
3. **Proficiency level is not modelled.** *"Junior Python"* and
   *"Senior Python"* both surface as `Python (computer programming)`
   with the same confidence. Module 3 (or a follow-on classifier) can
   close this.
4. **ESCO v1.2.1 lags the IT job market.** Niche modern stacks
   (LLMOps, vector DBs, Mojo, …) have no URI yet. They appear as
   `lemma`-only matches on broader ESCO knowledge skills, or not at
   all.
5. **Romanian CVs are matched cross-lingually.** We ship only the
   English ESCO bundle; Romanian CVs are tokenised by
   `ro_core_news_lg` but matched against the English `preferredLabel`
   / `altLabels`. This is fine for IT skills (English loanwords are
   ubiquitous in Romanian CVs) but degrades recall on soft skills and
   non-IT vocabulary. Loading `skills_ro.csv` is a future extension.

## Layout

```
src/skill_extractor/
├── __init__.py            # public API: SkillExtractor, SkillExtractionResult, …
├── pipeline.py            # SkillExtractor orchestrator
├── models.py              # pydantic v2 result models + DTOs
├── exceptions.py          # SkillExtractorError + 4 subclasses
├── config.py              # SkillExtractorConfig + NOT_A_CV_WARNING constant
├── esco/
│   ├── loader.py          # parses skills_en.csv + language overlay
│   ├── matcher.py         # EscoMatcherBuilder + compute_match_kind
│   └── cache.py           # on-disk pickle cache + esco-hash invalidation
├── sections/
│   └── detector.py        # EN + RO header → section label
├── filters/
│   ├── negation.py        # anchored regex unions, per language
│   └── disambiguation.py  # NER overlap + tech whitelist
└── scoring/
    └── confidence.py      # documented log-saturation formula
```

## Running the tests

```powershell
.\.venv\Scripts\Activate.ps1

# Unit tests only (fast, no spaCy model needed):
pytest tests\skill_extractor -m "not slow" --no-cov

# Full suite including end-to-end on real CV PDFs (requires
# en_core_web_lg + ro_core_news_lg installed):
python -m spacy download en_core_web_lg
python -m spacy download ro_core_news_lg
pytest tests\skill_extractor

# Coverage report (gated at ≥ 85 %):
pytest tests\skill_extractor --cov=skill_extractor --cov-report=term-missing
```

The first `pytest` run that touches the real ESCO bundle will build
the PhraseMatcher (~10–30 s for English, ~30–60 s for Romanian).
Subsequent runs reload from `.cache/skill_extractor/` in under a
second.
