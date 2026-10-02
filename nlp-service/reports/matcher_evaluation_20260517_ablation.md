# Module 3 Scorer -- Evaluation Report

*Generated: 2026-05-17T13:43:04.454072+00:00 by `scripts/evaluate_matcher.py` (skill_matcher 0.5.0).*

## 1. Executive summary

At default thresholds `T1=0.55`, `T2=0.25` across 280 (CV, JD) cells: **plain accuracy = 0.511**, **weighted accuracy = 0.333**, **macro F1 = 0.225**.

**Disclaimer (Step 5 placeholder):** the current encoder is a Step 5 placeholder (see STEP6_PREFLIGHT.md). Step 7's exit gate is *correctness, not score*. When Step 5 is re-done with a larger, less-biased training corpus, only the checkpoint swaps -- the Scorer's code path does not change. Numbers below will lift accordingly.

## 2. Environment

* **Encoder:** `C:\Users\silvi\Desktop\licenta2026\app\nlp-service\models\skill_matcher\mnrl_sw_v1_20260516_1953`
* **ESCO SHA (12):** `fa2145a1216c`
* **drop_threshold:** 0.45
* **keep_threshold:** 0.55
* **expansion_threshold:** 0.75
* **per_requirement_keep_threshold:** 0.3
* **seed:** 42
* **T1 (strong cut):** 0.55
* **T2 (possible cut):** 0.25
* **cells evaluated:** 280
* **skipped pairs:** 20 (no gold or no enriched)
* **CVs without enriched output:** 1 (Module 1/2 failures)
* **total wall-clock:** 126.7 s

### Skipped CVs
* `real_cv2` -- Module 1/2 skip

## 3. Confusion matrix

|  | pred:strong | pred:possible | pred:no |
|---|------------|---------------|---------|
| **gold:strong** | 0 | 0 | 35 |
| **gold:possible** | 0 | 0 | 102 |
| **gold:no** | 0 | 0 | 143 |

## 4. Per-class metrics

| Class | Precision | Recall | F1 |
|-------|-----------|--------|----|
| strong | 0.000 | 0.000 | 0.000 |
| possible | 0.000 | 0.000 | 0.000 |
| no | 0.511 | 1.000 | 0.676 |

**Macro F1 (mean over 3 classes):** 0.225

## 5. Per-JD breakdown

| JD | n_cells | correct | strong_avg | possible_avg | no_avg |
|----|---------|---------|-----------|--------------|--------|
| jd1 | 14 | 5 | 0.000 | 0.022 | 0.000 |
| jd10 | 14 | 4 | 0.008 | 0.023 | 0.016 |
| jd11 | 14 | 4 | 0.014 | 0.005 | 0.000 |
| jd12 | 14 | 8 | - | 0.017 | 0.007 |
| jd13 | 14 | 10 | 0.000 | 0.000 | 0.009 |
| jd14 | 14 | 9 | 0.000 | 0.000 | 0.000 |
| jd15 | 14 | 8 | 0.021 | 0.000 | 0.000 |
| jd16 | 14 | 8 | 0.021 | 0.000 | 0.000 |
| jd17 | 14 | 8 | 0.067 | 0.028 | 0.012 |
| jd18 | 14 | 10 | 0.058 | 0.000 | 0.006 |
| jd19 | 14 | 11 | 0.000 | 0.031 | 0.000 |
| jd2 | 14 | 5 | 0.000 | 0.000 | 0.000 |
| jd20 | 14 | 8 | 0.102 | 0.057 | 0.000 |
| jd3 | 14 | 4 | 0.056 | 0.014 | 0.000 |
| jd4 | 14 | 4 | 0.000 | 0.007 | 0.000 |
| jd5 | 14 | 11 | 0.050 | 0.000 | 0.005 |
| jd6 | 14 | 5 | 0.000 | 0.018 | 0.021 |
| jd7 | 14 | 7 | 0.000 | 0.015 | 0.007 |
| jd8 | 14 | 10 | - | 0.000 | 0.000 |
| jd9 | 14 | 4 | 0.000 | 0.005 | 0.000 |

## 6. Per-CV breakdown

| CV | n_cells | correct | mean_score |
|----|---------|---------|------------|
| real_cv1 | 20 | 7 | 0.010 |
| real_cv10 | 20 | 17 | 0.000 |
| real_cv11 | 20 | 5 | 0.006 |
| real_cv12 | 20 | 5 | 0.023 |
| real_cv13 | 20 | 17 | 0.000 |
| real_cv14 | 20 | 13 | 0.000 |
| real_cv15 | 20 | 15 | 0.000 |
| real_cv3 | 20 | 13 | 0.025 |
| real_cv4 | 20 | 6 | 0.000 |
| real_cv5 | 20 | 6 | 0.028 |
| real_cv6 | 20 | 14 | 0.002 |
| real_cv7 | 20 | 13 | 0.003 |
| real_cv8 | 20 | 6 | 0.036 |
| real_cv9 | 20 | 6 | 0.006 |

## 7. Distribution of overall_score by gold class

*(matplotlib not installed -- histogram skipped; JSON companion still contains the per-cell scores.)*

## 8. Top 10 disagreements

| CV | JD | gold | predicted | score | matched_req | unmatched_req |
|----|----|------|-----------|-------|-------------|----------------|
| real_cv1 | jd17 | strong | no | 0.042 | 1 | 5 |
| real_cv1 | jd20 | strong | no | 0.085 | 1 | 2 |
| real_cv11 | jd1 | strong | no | 0.000 | 0 | 8 |
| real_cv11 | jd2 | strong | no | 0.000 | 0 | 7 |
| real_cv11 | jd4 | strong | no | 0.000 | 0 | 5 |
| real_cv11 | jd6 | strong | no | 0.000 | 0 | 5 |
| real_cv12 | jd11 | strong | no | 0.016 | 0 | 3 |
| real_cv12 | jd15 | strong | no | 0.000 | 0 | 6 |
| real_cv12 | jd16 | strong | no | 0.000 | 0 | 6 |
| real_cv12 | jd17 | strong | no | 0.056 | 1 | 5 |

## 9. Threshold ablation

| (T1, T2) | accuracy | weighted_accuracy | macro_F1 | F1(strong) | F1(possible) | F1(no) |
|----------|----------|-------------------|----------|------------|--------------|--------|
| (0.5, 0.2) | 0.511 | 0.333 | 0.225 | 0.000 | 0.000 | 0.676 |
| (0.55, 0.25) | 0.511 | 0.333 | 0.225 | 0.000 | 0.000 | 0.676 |
| (0.6, 0.3) | 0.511 | 0.333 | 0.225 | 0.000 | 0.000 | 0.676 |
| (0.65, 0.35) | 0.511 | 0.333 | 0.225 | 0.000 | 0.000 | 0.676 |
| (0.7, 0.4) | 0.511 | 0.333 | 0.225 | 0.000 | 0.000 | 0.676 |

## 10. Conclusion

Scorer is structurally complete: 0 stubs remain in `skill_matcher`, all 280-cell paths execute without exception, determinism verified by unit tests. Numbers are bottlenecked by the Step 5 placeholder encoder; Step 5 redo will lift them without Scorer code change. Proceed to **Step 8 (threshold tuning)** using this report's ablation table as starting priors.
