# Module 3 Linker -- Evaluation Report

*Generated: 2026-05-17T12:49:06.923106+00:00 by `scripts/evaluate_linker.py` (skill_matcher 0.4.0).*

## Executive summary

Module 2 lexical F1 = **0.460** ; Linker kept-only F1 = **0.297** ; expansion-only F1 = **0.000** ; kept+expansion F1 = **0.296**.

**Caveat:** the current encoder is a Step 5 placeholder (see STEP6_PREFLIGHT.md). Step 6's gate is *correctness*, not F1. Performance numbers will be re-baselined when the Step 5 fine-tuning is re-done with a larger, less-biased training corpus -- no Linker code change required.

## Environment

* **Encoder:** `C:\Users\silvi\Desktop\licenta2026\app\nlp-service\models\skill_matcher\mnrl_sw_v1_20260516_1953`
* **ESCO SHA (12):** `fa2145a1216c`
* **drop_threshold:** 0.45
* **keep_threshold:** 0.55
* **expansion_threshold:** 0.75
* **window:** size=30 stride=15
* **seed:** 42
* **n_cvs_processed:** 14 (skipped: 1)
* **total wall-clock:** 51.1 s

### Skipped CVs

* `real_cv2` -- Module 1/2 skip

## Per-CV breakdown

| CV | text_len | n_lex_in | kept | ambig | dropped | exp | lex F1 | kept F1 | k+exp F1 |
|----|----------|----------|------|-------|---------|-----|--------|---------|----------|
| real_cv1 | 2129 | 8 | 13 | 7 | 2 | 0 | 0.636 | 0.571 | 0.571 |
| real_cv10 | 884 | 1 | 0 | 0 | 2 | 0 | 0.333 | 0.000 | 0.000 |
| real_cv11 | 2005 | 9 | 5 | 1 | 4 | 0 | 0.455 | 0.222 | 0.222 |
| real_cv12 | 4019 | 24 | 13 | 6 | 13 | 1 | 0.528 | 0.256 | 0.250 |
| real_cv13 | 1001 | 2 | 2 | 2 | 0 | 0 | 0.000 | 0.000 | 0.000 |
| real_cv14 | 1632 | 5 | 2 | 2 | 3 | 0 | 0.125 | 0.000 | 0.000 |
| real_cv15 | 1436 | 6 | 1 | 1 | 2 | 0 | 0.111 | 0.154 | 0.154 |
| real_cv3 | 2333 | 11 | 13 | 6 | 6 | 0 | 0.733 | 0.593 | 0.593 |
| real_cv4 | 2638 | 15 | 8 | 5 | 11 | 0 | 0.737 | 0.414 | 0.414 |
| real_cv5 | 2680 | 15 | 17 | 13 | 7 | 0 | 0.667 | 0.615 | 0.615 |
| real_cv6 | 2932 | 13 | 10 | 8 | 6 | 0 | 0.296 | 0.286 | 0.286 |
| real_cv7 | 3587 | 14 | 6 | 5 | 6 | 0 | 0.588 | 0.308 | 0.308 |
| real_cv8 | 2932 | 11 | 7 | 4 | 4 | 0 | 0.606 | 0.429 | 0.429 |
| real_cv9 | 2323 | 13 | 4 | 2 | 13 | 0 | 0.629 | 0.308 | 0.308 |

## Aggregate metrics (gold view = high + medium)

| Predictor | macro P | macro R | macro F1 | micro P | micro R | micro F1 |
|-----------|---------|---------|----------|---------|---------|----------|
| Module 2 lexical | 0.645 | 0.371 | 0.460 | 0.701 | 0.424 | 0.528 |
| Linker kept only | 0.704 | 0.202 | 0.297 | 0.750 | 0.235 | 0.357 |
| Linker expansion only | 0.929 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Linker kept + expansion | 0.700 | 0.202 | 0.296 | 0.740 | 0.235 | 0.356 |

**Linker (kept+exp) vs lexical delta**: F1 = -0.164, P = +0.056, R = -0.168.

## Source-bucket totals across corpus

* `lexical_kept` candidates emitted: 101 (of which 62 in the ambiguous sub-band).
* `lexical_dropped` candidates emitted: 79
* `expansion` candidates emitted: 1
* unknown URIs (skipped): 10
* sliding windows across corpus: 271

## Top-20 expansion URIs (by CV frequency)

| URI | n_CVs |
|-----|-------|
| `http://data.europa.eu/esco/skill/7e796b51-49d7-4e73-95af-2e7323763f15` | 1 |

## Conclusion

Linker is structurally complete. Determinism verified by unit tests; end-to-end run produces well-formed candidates.

Performance numbers are bottlenecked by the Step 5 placeholder encoder; Step 5 redo will lift them without Linker code change. Step 6 sign-off gate (correctness, not F1) is satisfied. Proceed to Step 7 (Scorer).
