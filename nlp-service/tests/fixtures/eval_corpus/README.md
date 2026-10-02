# Module 3 — Evaluation Corpus

This directory holds the **held-out evaluation set** for Module 3
(`skill_matcher`). All metrics reported in any Module 3 validation
report are computed against the artefacts under this directory.

The eval corpus is **never used for training** — the training corpus
(Step 3 of the Module 3 plan) lives elsewhere.

## Layout

```
eval_corpus/
├── README.md         (this file)
├── jds_raw/          ← raw LinkedIn-scraped .txt JDs (immutable input)
├── jds/              ← .yaml fixtures (output of scripts/convert_jds.py)
├── cv_labels/        ← .yaml gold skill labels per CV
└── fit_matrix.csv    ← recruiter-style (CV × JD) fit judgments
```

The CV PDFs themselves live one level up at
`nlp-service/tests/fixtures/real_cv*.pdf` — shared with the Module 2
validation suite so we don't duplicate the binaries.

## Workflow

### 1. Adding a new JD

1. Copy-paste the announcement body from LinkedIn / eJobs / pagină
   Careers into a new file `jds_raw/jd<N>.txt`. The first non-empty
   line is treated as the title; the rest is the raw body. No header
   or schema needed.
2. From `nlp-service/`, run:

   ```bash
   python scripts/convert_jds.py
   ```

   This regenerates every `jds/jd<N>.yaml`. The converter does
   best-effort extraction of `required_skills` and
   `nice_to_have_skills` from common section headers; it catches
   ~70-80% — verify by eye.
3. Edit the generated `jds/jd<N>.yaml` and fill in:
   - `category` (`swe` | `data` | `devops` | `qa` | `frontend` |
     `backend` | `non_tech`)
   - `seniority` (`junior` | `mid` | `senior` | `unspecified`)
   - `location` (e.g. `"Bucharest"`, `"Remote"`)
   - Correct `required_skills` / `nice_to_have_skills` if the regex
     missed entries
4. Re-run pytest to confirm the loader still parses everything.

### 2. Adding a new CV

1. Drop the (anonymised) PDF at `tests/fixtures/real_cv<N>.pdf`.
2. Create `cv_labels/real_cv<N>.yaml` by reading the PDF and listing
   the gold ESCO / custom skills you expect Module 3 to find. Use any
   existing `real_cv*.yaml` as a template.
3. Add a row to `fit_matrix.csv` with the new CV ID and a fit judgment
   for every JD column.

### 3. Updating the fit matrix

`fit_matrix.csv` is a flat CSV — `cv_id` column first, one column per
JD ID, cells filled with `strong`, `possible`, `no`, or empty. Open it
in Excel / LibreOffice / your favourite editor. Empty cells are
"unjudged" (skipped at metric time, not counted as `no`).

The recruiter mindset: *"If I had this CV for this job, would I shortlist
it for interview?"* → **strong** if yes-definitely, **possible** if
maybe-on-a-slow-day, **no** if not.

## Schemas

### `jds/jd*.yaml`

```yaml
id: jd1
title: "Software Engineer - Mid Level"
language: en             # en | ro
location: "Bucharest"
category: swe            # swe | data | devops | qa | frontend | backend | non_tech
seniority: mid           # junior | mid | senior | unspecified
source_anonymized: ""    # optional firma anonimizată
raw_text: |
  Full original announcement body, multiline literal.
required_skills:
  - "Python"
  - "REST API design"
nice_to_have_skills:
  - "Docker"
notes: ""
```

### `cv_labels/real_cv*.yaml`

```yaml
cv_id: real_cv1
gold_skills:
  - skill_uri: "http://data.europa.eu/esco/skill/<uuid>"
    label: "Python (computer programming)"
    confidence_expected: high   # high | medium
skills_definitely_not_in_cv:
  - "securities (financial)"
notes: ""
```

`confidence_expected = high` means the skill is unambiguous and
explicitly named (e.g. `"5 years of Python"`); `medium` means the
skill is implied or partially evidenced (e.g. `"worked on data
pipelines"` → SQL).

### `fit_matrix.csv`

```
cv_id,jd1,jd2,jd3,...
real_cv1,strong,no,possible,...
real_cv2,no,strong,no,...
```

Values: `strong`, `possible`, `no`, or empty. Case-insensitive at
load time.

## Why this layout?

* `jds_raw/` and `jds/` are deliberately separate. `jds_raw/` is the
  *immutable input* (raw LinkedIn copy-paste, kept as the source of
  truth for the announcement body); `jds/` is the *processed output*
  (structured fixtures). If we ever change the YAML schema, we re-run
  `scripts/convert_jds.py` and the YAML is regenerated automatically.
* CV labels live alongside JDs under `eval_corpus/` rather than at the
  top level so the entire eval corpus can be moved or copied as one
  unit.
* `fit_matrix.csv` is CSV — not YAML / JSON — because a human will
  fill it in Excel, and an Excel-friendly format wins here. The
  loader normalises mixed-case and trims whitespace.

## How completion is enforced

`tests/skill_matcher/test_eval_corpus.py::test_real_corpus_complete`
is marked `@pytest.mark.slow` and asserts the full ingestion is done
(15 CVs labelled, ≥10 JDs, fit matrix fully populated). Run it
explicitly when you finish data ingestion:

```bash
pytest -m slow tests/skill_matcher/test_eval_corpus.py
```

That test passing is the Step 2 sign-off gate.
