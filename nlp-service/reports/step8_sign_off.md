# Step 8 sign-off (2026-05-17)

## What was delivered

| File | Lines | Purpose |
|------|-------|---------|
| `src/skill_matcher/tuning.py` | ~1100 | Pure-Python three-tier grid search core. Encoder-agnostic, I/O-free. |
| `src/skill_matcher/scorer.py` | 627 | Step 7 Scorer + Step 8 additive `score_to_intermediates` method + `_collect_match_factors` helper. `score()` behaviour preserved. |
| `src/skill_matcher/config.py` | 236 | Step 4 / Step 7 fields + Step 8 schema additions: `required_weight`, `t1_strong_threshold`, `t2_possible_threshold`. Provisional defaults retained until Silviu runs the tuner. |
| `src/skill_matcher/__init__.py` | 140 | Bumped to `__version__ = "0.6.0"`. Exports all Step 8 symbols. |
| `scripts/tune_thresholds.py` | 1066 | CLI driver: `--mode fast` (Linker locked, ~3 min) and `--mode full` (sweep Linker too, ~90 min). Writes 12-section markdown report + JSON companion + optional amendment file. Exit 0 = locked, exit 2 = deferred. |
| `tests/skill_matcher/test_tuning.py` | 531 | Unit tests for the tuning core with synthetic intermediates + one `@pytest.mark.slow` end-to-end CLI invocation. |
| `tests/skill_matcher/test_config_step8.py` | 118 | Pin tests for the three new Step 8 config fields + the projection-ordering validator. |
| `tests/skill_matcher/test_scorer_step8.py` | 400 | Behavioural-equivalence tests: `score_to_intermediates` matches `score()` at production defaults. |
| `reports/step8_decisions_amendment_draft.md` | 100 | Two amendment-row variants (locked / deferred) for `DECISIONS.md` -- Silviu pastes manually. |

## Grid sizes (after fitting the 90-min full-mode budget)

| Tier | Knobs | Combos |
|------|-------|--------|
| Tier 2 (Linker) | drop ∈ {0.40, 0.45, 0.50}, keep ∈ {0.50, 0.55, 0.60}, expansion ∈ {0.65, 0.75, 0.85} -- legal triples only | 27 |
| Tier 1 (Scorer) | per_req_keep × required_weight = 20 × 5 | 100 |
| Tier 0 (Projection) | T1 × T2 = 20 × 25, T2 < T1 | 344 |

Per-Tier-2 inner sweep ≈ **21 s** on the real 280-cell corpus.
Fast-mode total ≈ **3 min** (1 Tier 2 combo + Linker pass).
Full-mode total ≈ **91 min** (27 Tier 2 combos × ~3.4 min each).

## In-session sanity checks (all green)

```
PASS: aggregate perfect match -> 0.8
PASS: projection boundaries (>=t1 strong, ==t2 possible, <t2 no)
PASS: projection rejects t2 >= t1
PASS: aggregate rejects required_weight > 1
PASS: determinism — top-10 metrics identical across two runs (34400 combos each)
PASS: grid_size matches iteration count
PASS: tier2 grid respects 0<=drop<=keep<=expansion<=1
PASS: score_distribution computes percentiles
```

All 8 deliverable files AST-parse cleanly.

## ⚠️ Blocker for full sign-off

The Cowork sandbox bash mount cannot reach the project's actual Python
environment for this session:

1. **Pre-existing files appear truncated in the FUSE mount.** `encoder.py`
   (full version on Windows ~290 lines, mount sees 39 lines / 1924 bytes)
   and `esco_index.py` (mount sees 36 lines / 1748 bytes) are visible
   only as their May-11 docstring stubs. This blocks any
   `from skill_matcher import …` in the sandbox.
2. **Bash python is 3.10**; the project requires 3.11+ (uses `slots=True`
   on dataclasses with newer behaviour).
3. **The project's `.venv` is not visible to bash.** No way to invoke
   the real `pytest`, `mypy`, or `ruff` from this session.

Consequence: I **could not run** in this session:

- `mypy --strict src/skill_matcher`
- `ruff check src/skill_matcher tests/skill_matcher scripts/tune_thresholds.py`
- `pytest -m "not slow" tests/skill_matcher --cov=skill_matcher --cov-fail-under=85`
- The actual `--mode fast` / `--mode full` tuning sweeps
- The byte-identical determinism check (two `--mode fast` runs)

The pure-Python tuning core was independently validated by importing it
via bash + Python 3.10 (bypassing `skill_matcher.__init__`), and the
8-group sanity check above passed.

## Operator handoff -- what Silviu needs to do

From PowerShell in `C:\Users\silvi\Desktop\licenta2026\app\nlp-service`:

```powershell
.\.venv\Scripts\Activate.ps1

# 1. Quality gates
mypy --strict src\skill_matcher
ruff check src\skill_matcher tests\skill_matcher scripts\tune_thresholds.py

# 2. Fast unit + integration tests (no encoder needed)
pytest -m "not slow" tests\skill_matcher\test_tuning.py
pytest -m "not slow" tests\skill_matcher\test_config_step8.py
pytest -m "not slow" tests\skill_matcher\test_scorer_step8.py
pytest -m "not slow" tests\skill_matcher --cov=skill_matcher --cov-fail-under=85

# 3. Existing Step 7 tests still pass (no regression in score())
pytest -m "not slow" tests\skill_matcher\test_scorer.py

# 4. Fast tuning run (~3-5 min)
python scripts\tune_thresholds.py `
  --eval-corpus-dir tests\fixtures\eval_corpus `
  --out-report reports\threshold_tuning_20260517.md `
  --mode fast

# 5. Full tuning run (~90 min — leave it running, come back later)
python scripts\tune_thresholds.py `
  --eval-corpus-dir tests\fixtures\eval_corpus `
  --out-report reports\threshold_tuning_20260517_full.md `
  --mode full `
  --write-decisions

# 6. Two consecutive --mode fast runs for the byte-identical determinism gate
python scripts\tune_thresholds.py --mode fast --out-report reports\det_a.md
python scripts\tune_thresholds.py --mode fast --out-report reports\det_b.md
fc.exe /b reports\det_a.md reports\det_b.md  # should report "no differences"

# 7. Slow end-to-end tuning test (after the script ran clean)
pytest -m slow tests\skill_matcher\test_tuning.py
```

After step 4 / 5:

- If exit code 0: paste Variant A from `reports/step8_decisions_amendment_draft.md`
  into `src/skill_matcher/DECISIONS.md`, fill the `<DROP>` / `<KEEP>` /
  ... placeholders from Section 10 of the generated report. Update
  `config.py` defaults to match (the seven knobs) and update
  `test_config_step8.py::test_step8_provisional_defaults_for_new_fields`
  to pin the new values.
- If exit code 2: paste Variant B (deferred). Do NOT change `config.py`
  defaults or the pin tests. Calibration moves to post-Step-5-redo.

## File access (computer:// links)

- [tuning.py](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\src\skill_matcher\tuning.py)
- [scorer.py](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\src\skill_matcher\scorer.py)
- [config.py](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\src\skill_matcher\config.py)
- [__init__.py](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\src\skill_matcher\__init__.py)
- [tune_thresholds.py](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\scripts\tune_thresholds.py)
- [test_tuning.py](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\tests\skill_matcher\test_tuning.py)
- [test_config_step8.py](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\tests\skill_matcher\test_config_step8.py)
- [test_scorer_step8.py](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\tests\skill_matcher\test_scorer_step8.py)
- [step8_decisions_amendment_draft.md](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\reports\step8_decisions_amendment_draft.md)
- [step8_sign_off.md](computer://C:\Users\silvi\Desktop\licenta2026\app\nlp-service\reports\step8_sign_off.md)
