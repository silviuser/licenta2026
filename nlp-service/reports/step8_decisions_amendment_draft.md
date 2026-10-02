# Step 8 -- DECISIONS.md amendment (draft)

> **Status:** Draft. Two amendment rows are provided below. Pick one of
> the two row-1 variants depending on whether `scripts/tune_thresholds.py`'s
> guard-set check passed on your run, then paste both rows into
> `src/skill_matcher/DECISIONS.md`. The script's own report (Section 10)
> contains the equivalent text generated against your live run.

---

## Variant A -- Step 8 locked (guards passed)

```markdown
### Step 8 amendment (2026-05-XX) -- empirical threshold lock

Empirical threshold tuning conducted via
`scripts/tune_thresholds.py --mode {fast|full}`. Best combo (strict
guards passed):

* drop_threshold = **<DROP>**
* keep_threshold = **<KEEP>**
* expansion_threshold = **<EXP>**
* per_requirement_keep_threshold = **<PER_REQ>**
* required_weight = **<REQ_W>** (nice_weight = <1 - REQ_W>)
* t1_strong_threshold = **<T1>**
* t2_possible_threshold = **<T2>**

Macro F1 lift vs Step 7 baseline (0.225): **+<LIFT>**.
Methodology: 3-tier grid search (Tier 2 over Linker thresholds, Tier 1
over Scorer aggregation, Tier 0 over 3-class projection). Reproduction:
`python scripts/tune_thresholds.py --mode {fast|full}` against
`tests/fixtures/eval_corpus`. Numbers are placeholder-encoder snapshots
(see Variant A row 2 below).
```

```markdown
### Step 8 amendment (2026-05-XX) -- placeholder caveat

The locked thresholds reflect the Step 5 placeholder encoder's
compressed `overall_score` distribution (range `[0, ~0.1]` rather than
the intended `[0, 1]`). After the Step 5 redo, **re-run**
`scripts/tune_thresholds.py` on the same fixtures to recalibrate.
Expected direction of change: `t1_strong_threshold`,
`t2_possible_threshold`, and `per_requirement_keep_threshold` all move
upward as the score distribution widens.

The Step 8 deliverable is the *script*, not these specific numbers.
The amendment-row text is regenerated automatically by Section 10 of
the next tuning report, so this row will be superseded -- not edited
-- by the post-Step-5-redo run.
```

---

## Variant B -- Step 8 deferred (guards failed even relaxed)

```markdown
### Step 8 amendment (2026-05-XX) -- calibration deferred

Empirical threshold tuning attempted via
`scripts/tune_thresholds.py --mode {fast|full}`. No combo satisfied
even the relaxed guard set (per-class P/R floors lowered to 0.02; the
distribution-bucket guard disabled). The placeholder encoder's score
distribution is too compressed for the 3-class projection to separate
cleanly under any (T1, T2) inside `[0, 1]` x `[0, 1]` with the
provisional Tier 1 + Tier 2 values.

The provisional defaults from Step 4 / Step 7 **remain in force**:
drop=0.45, keep=0.55, expansion=0.75, per_req_keep=0.30,
required_weight=0.8, T1=0.55, T2=0.25. **Do NOT change `config.py`
defaults from this run.** Re-run `scripts/tune_thresholds.py` after
Step 5 redo; the script and the report ARE the deliverable.
```

```markdown
### Step 8 amendment (2026-05-XX) -- placeholder caveat (deferral path)

Defer rationale: the placeholder encoder squashes the
`req.conf * cand.conf * uri_similarity` product so the
`overall_score` distribution sits in `[0, 0.11]` rather than the
intended `[0, 1]`. Per-class precision/recall floors of 0.02 are
unsatisfiable in that range. After Step 5 redo widens the distribution
toward `[0, 1]`, re-run `tune_thresholds.py` -- expected outcome:
strict guards pass, `config.py` defaults bumped, this deferral row
superseded.
```

---

## Operator checklist

1. Run `python scripts/tune_thresholds.py --mode fast` (then `--mode full`).
2. Read the generated `reports/threshold_tuning_<date>.md` Section 10.
3. If script exit code = 0: paste Variant A rows (filled in from
   Section 10) into `DECISIONS.md`; then update `config.py` defaults
   for the seven knobs to match the locked combo; then update
   `tests/skill_matcher/test_config_step8.py` pin assertions.
4. If script exit code = 2: paste Variant B rows into `DECISIONS.md`;
   leave `config.py` defaults and `test_config_step8.py` unchanged.
5. Commit. Move to Step 9.
