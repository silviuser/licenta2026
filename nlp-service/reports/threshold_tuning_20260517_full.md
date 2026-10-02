# Module 3 -- Threshold Tuning Report (Step 8)

*Generated: 2026-05-17T16:25:19.722179+00:00 by `scripts/tune_thresholds.py` (skill_matcher 0.6.0).*

## 1. Executive summary

**Best combo passed all strict guards.** Macro F1 = **0.504** (Step 7 baseline 0.225; lift = +0.279). Plain accuracy = 0.604, weighted accuracy = 0.494.

**Placeholder caveat (mandatory).** These thresholds reflect the Step 5 placeholder encoder, whose ``overall_score`` distribution is compressed to ``[0, ~0.1]`` (see Section 7). After the Step 5 redo, re-run this script on the same fixtures; T1, T2, and the per-requirement keep threshold are expected to move upward as the score range widens. The script -- not these numbers -- is the Step 8 deliverable.

## 2. Environment

* **Mode:** `full`
* **Encoder:** `C:\Users\silvi\Desktop\licenta2026\app\nlp-service\models\skill_matcher\mnrl_sw_v1_20260516_1953`
* **ESCO SHA (12):** `fa2145a1216c`
* **Gold cells:** 300
* **Skipped CVs (Module 1/2):** 0
* **Grid sizes:** Tier 2 = 27, Tier 1 = 100, Tier 0 = 344; combos evaluated = 928800
* **Wall-clock (Tier 1 + Tier 0 sweep):** 2928.9 s
* **Wall-clock (Tier 2 Linker passes):** 2918.7 s
* **Objective:** `macro_f1`

## 3. Best combination

| Knob | Value (strict-best) |
|------|-----------------|
| drop_threshold | 0.4000 |
| keep_threshold | 0.5000 |
| expansion_threshold | 0.7500 |
| per_requirement_keep_threshold | 0.0850 |
| required_weight | 0.5000 |
| t1 (strong cut) | 0.0600 |
| t2 (possible cut) | 0.0050 |

## 4. Confusion matrix at best combo

|  | pred:strong | pred:possible | pred:no |
|---|------------|---------------|---------|
| **gold:strong** | 8 | 16 | 11 |
| **gold:possible** | 5 | 45 | 52 |
| **gold:no** | 4 | 23 | 116 |

### Per-class precision / recall / F1

| Class | Precision | Recall | F1 |
|-------|-----------|--------|----|
| strong | 0.471 | 0.229 | 0.308 |
| possible | 0.536 | 0.441 | 0.484 |
| no | 0.648 | 0.811 | 0.720 |

## 5. Tier 2 traversal

| (drop, keep, expansion) | elapsed (s) |
|--------------------------|-------------|
| (0.40, 0.50, 0.65) | 209.1 |
| (0.40, 0.50, 0.75) | 168.3 |
| (0.40, 0.50, 0.85) | 107.8 |
| (0.40, 0.55, 0.65) | 110.4 |
| (0.40, 0.55, 0.75) | 108.0 |
| (0.40, 0.55, 0.85) | 106.0 |
| (0.40, 0.60, 0.65) | 114.2 |
| (0.40, 0.60, 0.75) | 107.0 |
| (0.40, 0.60, 0.85) | 107.7 |
| (0.45, 0.50, 0.65) | 112.5 |
| (0.45, 0.50, 0.75) | 92.8 |
| (0.45, 0.50, 0.85) | 87.6 |
| (0.45, 0.55, 0.65) | 96.1 |
| (0.45, 0.55, 0.75) | 91.1 |
| (0.45, 0.55, 0.85) | 90.2 |
| (0.45, 0.60, 0.65) | 94.7 |
| (0.45, 0.60, 0.75) | 93.2 |
| (0.45, 0.60, 0.85) | 87.4 |
| (0.50, 0.50, 0.65) | 88.8 |
| (0.50, 0.50, 0.75) | 86.8 |
| (0.50, 0.50, 0.85) | 82.5 |
| (0.50, 0.55, 0.65) | 89.2 |
| (0.50, 0.55, 0.75) | 85.6 |
| (0.50, 0.55, 0.85) | 89.2 |
| (0.50, 0.60, 0.65) | 87.6 |
| (0.50, 0.60, 0.75) | 91.9 |
| (0.50, 0.60, 0.85) | 112.8 |
| (0.40, 0.50, 0.75) | 120.2 |

## 6. Top-10 combinations (by macro_f1)

| # | macro F1 | weighted F1 | combo (drop/keep/exp/perReq/wReq/T1/T2) | guards |
|---|----------|-------------|------------------------------------------|--------|
| 1 | 0.504 | 0.583 | 0.40/0.50/0.75/0.085/0.50/0.060/0.005 | passed |
| 2 | 0.504 | 0.583 | 0.40/0.50/0.85/0.085/0.50/0.060/0.005 | passed |
| 3 | 0.502 | 0.580 | 0.40/0.50/0.65/0.085/0.50/0.060/0.005 | passed |
| 4 | 0.502 | 0.580 | 0.40/0.50/0.75/0.010/0.50/0.060/0.005 | passed |
| 5 | 0.502 | 0.580 | 0.40/0.50/0.75/0.035/0.50/0.060/0.005 | passed |
| 6 | 0.502 | 0.580 | 0.40/0.50/0.75/0.060/0.50/0.060/0.005 | passed |
| 7 | 0.502 | 0.580 | 0.40/0.50/0.85/0.010/0.50/0.060/0.005 | passed |
| 8 | 0.502 | 0.580 | 0.40/0.50/0.85/0.035/0.50/0.060/0.005 | passed |
| 9 | 0.502 | 0.580 | 0.40/0.50/0.85/0.060/0.50/0.060/0.005 | passed |
| 10 | 0.502 | 0.588 | 0.45/0.50/0.65/0.010/0.90/0.100/0.005 | passed |

## 7. Score-distribution snapshot at best combo

| Stratum | n | min | P25 | P50 | P75 | P90 | P95 | P99 | max | mean |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 280 | 0.0000 | 0.0000 | 0.0000 | 0.0248 | 0.0485 | 0.0636 | 0.0955 | 0.1085 | 0.0140 |
| strong | 35 | 0.0000 | 0.0000 | 0.0268 | 0.0553 | 0.0729 | 0.0783 | 0.0806 | 0.0811 | 0.0313 |
| possible | 102 | 0.0000 | 0.0000 | 0.0000 | 0.0307 | 0.0481 | 0.0571 | 0.0957 | 0.0969 | 0.0173 |
| no | 143 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0297 | 0.0469 | 0.0871 | 0.1085 | 0.0073 |

## 8. Guard outcomes

* **11739 / 928800 combos passed the strict guard set** (per-class precision/recall >= 0.05, all three classes predicted, T2 < T1, distribution buckets non-empty).
* The relaxed-guard fallback found a passing combo (precision/recall floors lowered to 0.02; distribution-bucket guard removed).

## 9. Comparison vs Step 7 baseline

| Metric | Step 7 baseline | Step 8 best |
|--------|-----------------|-------------|
| macro F1 | 0.225 | 0.504 (strict-best) |
| plain accuracy | 0.511 | 0.604 |
| F1(strong) | 0.000 | 0.308 |
| F1(possible) | 0.000 | 0.484 |
| F1(no) | 0.676 | 0.720 |

## 10. Proposed `DECISIONS.md` amendment

Append the following two rows to `DECISIONS.md`:

```markdown
### Step 8 amendment (2026-05-17) -- empirical threshold lock

Empirical threshold tuning conducted via `scripts/tune_thresholds.py --mode full`. Best combo (strict guards passed):

* drop_threshold = **0.4000**
* keep_threshold = **0.5000**
* expansion_threshold = **0.7500**
* per_requirement_keep_threshold = **0.0850**
* required_weight = **0.5000** (nice_weight = 0.5000)
* t1_strong_threshold = **0.0600**
* t2_possible_threshold = **0.0050**

Macro F1 lift vs Step 7 baseline: +0.279.

### Step 8 amendment (2026-05-17) -- placeholder caveat

The locked thresholds reflect the Step 5 placeholder encoder's compressed `overall_score` distribution (range `[0, ~0.1]`). After the Step 5 redo, re-run `scripts/tune_thresholds.py` to recalibrate; expected direction of change: T1, T2, and per_requirement_keep_threshold all move upward as the distribution widens toward `[0, 1]`.
```

## 11. Conclusion

Step 8 LOCKED. New defaults proposed in Section 10 -- paste into `src/skill_matcher/DECISIONS.md` and update `src/skill_matcher/config.py` defaults to match. Re-run after Step 5 redo to recalibrate.

## 12. Re-run after Step 5 redo

When the Step 5 encoder is re-trained on a larger / less-biased corpus, re-run this script with no changes:

```
python scripts/tune_thresholds.py --eval-corpus-dir tests/fixtures/eval_corpus --out-report reports/threshold_tuning_<NEW_DATE>.md --mode full
```

The grid is identical; only the score distribution changes. Expected: T1 and T2 move upward, per_req_keep moves upward, macro F1 lifts substantially.
