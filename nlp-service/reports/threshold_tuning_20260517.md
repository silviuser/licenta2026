# Module 3 -- Threshold Tuning Report (Step 8)

*Generated: 2026-05-17T15:34:20.116480+00:00 by `scripts/tune_thresholds.py` (skill_matcher 0.6.0).*

## 1. Executive summary

**Best combo passed all strict guards.** Macro F1 = **0.453** (Step 7 baseline 0.225; lift = +0.228). Plain accuracy = 0.564, weighted accuracy = 0.464.

**Placeholder caveat (mandatory).** These thresholds reflect the Step 5 placeholder encoder, whose ``overall_score`` distribution is compressed to ``[0, ~0.1]`` (see Section 7). After the Step 5 redo, re-run this script on the same fixtures; T1, T2, and the per-requirement keep threshold are expected to move upward as the score range widens. The script -- not these numbers -- is the Step 8 deliverable.

## 2. Environment

* **Mode:** `fast`
* **Encoder:** `C:\Users\silvi\Desktop\licenta2026\app\nlp-service\models\skill_matcher\mnrl_sw_v1_20260516_1953`
* **ESCO SHA (12):** `fa2145a1216c`
* **Gold cells:** 300
* **Skipped CVs (Module 1/2):** 0
* **Grid sizes:** Tier 2 = 1, Tier 1 = 100, Tier 0 = 344; combos evaluated = 34400
* **Wall-clock (Tier 1 + Tier 0 sweep):** 198.3 s
* **Wall-clock (Tier 2 Linker passes):** 345.5 s
* **Objective:** `macro_f1`

## 3. Best combination

| Knob | Value (strict-best) |
|------|-----------------|
| drop_threshold | 0.4500 |
| keep_threshold | 0.5500 |
| expansion_threshold | 0.7500 |
| per_requirement_keep_threshold | 0.1850 |
| required_weight | 0.9000 |
| t1 (strong cut) | 0.0600 |
| t2 (possible cut) | 0.0050 |

## 4. Confusion matrix at best combo

|  | pred:strong | pred:possible | pred:no |
|---|------------|---------------|---------|
| **gold:strong** | 10 | 7 | 18 |
| **gold:possible** | 12 | 25 | 65 |
| **gold:no** | 6 | 14 | 123 |

### Per-class precision / recall / F1

| Class | Precision | Recall | F1 |
|-------|-----------|--------|----|
| strong | 0.357 | 0.286 | 0.317 |
| possible | 0.543 | 0.245 | 0.338 |
| no | 0.597 | 0.860 | 0.705 |

## 5. Tier 2 traversal

| (drop, keep, expansion) | elapsed (s) |
|--------------------------|-------------|
| (0.45, 0.55, 0.75) | 187.7 |
| (0.45, 0.55, 0.75) | 157.8 |

## 6. Top-10 combinations (by macro_f1)

| # | macro F1 | weighted F1 | combo (drop/keep/exp/perReq/wReq/T1/T2) | guards |
|---|----------|-------------|------------------------------------------|--------|
| 1 | 0.453 | 0.523 | 0.45/0.55/0.75/0.185/0.90/0.060/0.005 | passed |
| 2 | 0.453 | 0.523 | 0.45/0.55/0.75/0.135/0.90/0.060/0.005 | passed |
| 3 | 0.453 | 0.523 | 0.45/0.55/0.75/0.160/0.90/0.060/0.005 | passed |
| 4 | 0.451 | 0.521 | 0.45/0.55/0.75/0.010/0.90/0.060/0.005 | passed |
| 5 | 0.451 | 0.521 | 0.45/0.55/0.75/0.035/0.90/0.060/0.005 | passed |
| 6 | 0.451 | 0.521 | 0.45/0.55/0.75/0.060/0.90/0.060/0.005 | passed |
| 7 | 0.451 | 0.521 | 0.45/0.55/0.75/0.085/0.90/0.060/0.005 | passed |
| 8 | 0.451 | 0.521 | 0.45/0.55/0.75/0.110/0.90/0.060/0.005 | passed |
| 9 | 0.450 | 0.515 | 0.45/0.55/0.75/0.285/0.90/0.060/0.005 | passed |
| 10 | 0.447 | 0.518 | 0.45/0.55/0.75/0.185/0.80/0.060/0.005 | passed |

## 7. Score-distribution snapshot at best combo

| Stratum | n | min | P25 | P50 | P75 | P90 | P95 | P99 | max | mean |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 280 | 0.0000 | 0.0000 | 0.0000 | 0.0096 | 0.0596 | 0.0891 | 0.1169 | 0.1573 | 0.0148 |
| strong | 35 | 0.0000 | 0.0000 | 0.0000 | 0.0685 | 0.1079 | 0.1239 | 0.1467 | 0.1573 | 0.0369 |
| possible | 102 | 0.0000 | 0.0000 | 0.0000 | 0.0274 | 0.0714 | 0.0912 | 0.0963 | 0.1138 | 0.0184 |
| no | 143 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0318 | 0.0585 | 0.0784 | 0.1112 | 0.0069 |

## 8. Guard outcomes

* **487 / 34400 combos passed the strict guard set** (per-class precision/recall >= 0.05, all three classes predicted, T2 < T1, distribution buckets non-empty).
* The relaxed-guard fallback found a passing combo (precision/recall floors lowered to 0.02; distribution-bucket guard removed).

## 9. Comparison vs Step 7 baseline

| Metric | Step 7 baseline | Step 8 best |
|--------|-----------------|-------------|
| macro F1 | 0.225 | 0.453 (strict-best) |
| plain accuracy | 0.511 | 0.564 |
| F1(strong) | 0.000 | 0.317 |
| F1(possible) | 0.000 | 0.338 |
| F1(no) | 0.676 | 0.705 |

## 10. Proposed `DECISIONS.md` amendment

Append the following two rows to `DECISIONS.md`:

```markdown
### Step 8 amendment (2026-05-17) -- empirical threshold lock

Empirical threshold tuning conducted via `scripts/tune_thresholds.py --mode fast`. Best combo (strict guards passed):

* drop_threshold = **0.4500**
* keep_threshold = **0.5500**
* expansion_threshold = **0.7500**
* per_requirement_keep_threshold = **0.1850**
* required_weight = **0.9000** (nice_weight = 0.1000)
* t1_strong_threshold = **0.0600**
* t2_possible_threshold = **0.0050**

Macro F1 lift vs Step 7 baseline: +0.228.

### Step 8 amendment (2026-05-17) -- placeholder caveat

The locked thresholds reflect the Step 5 placeholder encoder's compressed `overall_score` distribution (range `[0, ~0.1]`). After the Step 5 redo, re-run `scripts/tune_thresholds.py` to recalibrate; expected direction of change: T1, T2, and per_requirement_keep_threshold all move upward as the distribution widens toward `[0, 1]`.
```

## 11. Conclusion

Step 8 LOCKED. New defaults proposed in Section 10 -- paste into `src/skill_matcher/DECISIONS.md` and update `src/skill_matcher/config.py` defaults to match. Re-run after Step 5 redo to recalibrate.

## 12. Re-run after Step 5 redo

When the Step 5 encoder is re-trained on a larger / less-biased corpus, re-run this script with no changes:

```
python scripts/tune_thresholds.py --eval-corpus-dir tests/fixtures/eval_corpus --out-report reports/threshold_tuning_<NEW_DATE>.md --mode fast
```

The grid is identical; only the score distribution changes. Expected: T1 and T2 move upward, per_req_keep moves upward, macro F1 lifts substantially.
