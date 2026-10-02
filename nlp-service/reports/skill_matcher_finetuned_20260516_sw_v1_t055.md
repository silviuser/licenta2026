# Module 3 — Step 5 fine-tuned baseline

Generated 2026-05-16 20:19:43 UTC

Run name: **mnrl_sw_v1_20260516_1953**


## 1. Executive summary

* Zero-shot semantic macro F1 (high+medium view): **0.151**
* Fine-tuned semantic macro F1: **0.121**
* Delta: **-0.030** (lift: 0.80×)
* Lexical floor (Module 2): 0.460
* Ensemble (lex ∪ sem) macro F1: **0.399** (BELOW lexical floor)
* Step 6 gate (macro F1 ≥ 0.55): **FAIL**

## 2. Environment

* Base model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
* Fine-tuned checkpoint: `C:\Users\silvi\Desktop\licenta2026\app\nlp-service\models\skill_matcher\mnrl_sw_v1_20260516_1953`
* skill_matcher version: 0.3.1
* Semantic threshold (headline): 0.55
* Top-k per window: 5
* Sliding window: size=30 tokens, stride=15 tokens
* Concept-text format: bounded-a
* ESCO concepts indexed: 14013
* Encoder device: cpu

## 3. Index build timing

* Zero-shot index: warm load in 0.2s (`C:\Users\silvi\Desktop\licenta2026\app\nlp-service\.cache\embeddings\esco_39897b1e723b_bce83eb3ad4f_bounded-a.npz`)
* Fine-tuned index: warm load in 0.2s (`C:\Users\silvi\Desktop\licenta2026\app\nlp-service\.cache\embeddings\esco_f63f31ca54a9_bce83eb3ad4f_bounded-a.npz`)

## 4. Per-CV breakdown

### Per-CV semantic F1

| CV | Zero-shot F1 | Fine-tuned F1 | Delta |
|---|---|---|---|
| real_cv3 | 0.143 | 0.276 | +0.133 |
| real_cv6 | 0.054 | 0.160 | +0.106 |
| real_cv11 | 0.067 | 0.160 | +0.093 |
| real_cv1 | 0.343 | 0.400 | +0.057 |
| real_cv13 | 0.200 | 0.211 | +0.011 |
| real_cv14 | 0.000 | 0.000 | +0.000 |
| real_cv12 | 0.119 | 0.091 | -0.028 |
| real_cv8 | 0.170 | 0.133 | -0.037 |
| real_cv9 | 0.059 | 0.000 | -0.059 |
| real_cv15 | 0.074 | 0.000 | -0.074 |
| real_cv5 | 0.226 | 0.146 | -0.079 |
| real_cv7 | 0.182 | 0.057 | -0.125 |
| real_cv4 | 0.222 | 0.061 | -0.162 |
| real_cv10 | 0.250 | 0.000 | -0.250 |

## 5. Aggregate metrics

### high+medium (headline) view

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Macro F1 delta |
|---|---|---|---|
| Lexical (Module 2) | P=0.645  R=0.371  F1=0.460 | P=0.645  R=0.371  F1=0.460 | +0.000 |
| Semantic | P=0.157  R=0.156  F1=0.151 | P=0.161  R=0.100  F1=0.121 | -0.030 |
| Ensemble (lex ∪ sem) | P=0.303  R=0.437  F1=0.346 | P=0.408  R=0.411  F1=0.399 | +0.053 |

Micro:

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Micro F1 delta |
|---|---|---|---|
| Lexical | P=0.701  R=0.424  F1=0.528 | P=0.701  R=0.424  F1=0.528 | +0.000 |
| Semantic | P=0.151  R=0.160  F1=0.156 | P=0.185  R=0.099  F1=0.129 | -0.027 |
| Ensemble | P=0.313  R=0.494  F1=0.383 | P=0.425  R=0.457  F1=0.440 | +0.057 |

### high (strict) view

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Macro F1 delta |
|---|---|---|---|
| Lexical (Module 2) | P=0.509  R=0.359  F1=0.416 | P=0.509  R=0.359  F1=0.416 | +0.000 |
| Semantic | P=0.129  R=0.153  F1=0.137 | P=0.155  R=0.106  F1=0.124 | -0.013 |
| Ensemble (lex ∪ sem) | P=0.248  R=0.429  F1=0.308 | P=0.332  R=0.408  F1=0.361 | +0.052 |

Micro:

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Micro F1 delta |
|---|---|---|---|
| Lexical | P=0.612  R=0.433  F1=0.507 | P=0.612  R=0.433  F1=0.507 | +0.000 |
| Semantic | P=0.143  R=0.178  F1=0.159 | P=0.177  R=0.111  F1=0.136 | -0.023 |
| Ensemble | P=0.277  R=0.510  F1=0.359 | P=0.375  R=0.471  F1=0.418 | +0.059 |

## 6. Threshold ablation

### Threshold ablation (semantic macro F1, high+medium view)

| Threshold | Zero-shot | Fine-tuned | Delta |
|---|---|---|---|
| 0.40 | 0.114 | 0.133 | +0.018 |
| 0.45 | 0.124 | 0.147 | +0.023 |
| 0.50 | 0.146 | 0.145 | -0.001 |
| 0.55 | 0.151 | 0.121 | -0.030 |
| 0.60 | 0.147 | 0.064 | -0.083 |
| 0.65 | 0.073 | 0.015 | -0.058 |
| 0.70 | 0.016 | 0.005 | -0.011 |
| 0.75 | 0.013 | 0.000 | -0.013 |

## 7. Qualitative analysis

### Qualitative wins (F1 lift >= 0.10)

* **real_cv3**: F1 0.143 -> 0.276 (+0.133)
* **real_cv6**: F1 0.054 -> 0.160 (+0.106)

### Qualitative regressions (F1 drop > 0.05)

* **real_cv10**: F1 0.250 -> 0.000 (-0.250) — investigate whether overfitting to training distribution caused this
* **real_cv15**: F1 0.074 -> 0.000 (-0.074) — investigate whether overfitting to training distribution caused this
* **real_cv4**: F1 0.222 -> 0.061 (-0.162) — investigate whether overfitting to training distribution caused this
* **real_cv5**: F1 0.226 -> 0.146 (-0.079) — investigate whether overfitting to training distribution caused this
* **real_cv7**: F1 0.182 -> 0.057 (-0.125) — investigate whether overfitting to training distribution caused this
* **real_cv9**: F1 0.059 -> 0.000 (-0.059) — investigate whether overfitting to training distribution caused this

## Decision

* **Fine-tuned semantic macro F1**: 0.121 (gate: ≥ 0.55).
* **Fine-tuned ensemble macro F1**: 0.399 (must beat lexical floor 0.460).

**Step 5b — cross-encoder re-ranker.**

Fine-tuned F1 is below 0.45 / 0.55 thresholds. The bi-encoder gap is too wide to close by hyperparameter sweep alone; open a Step 5b Pre-Flight for the cross-encoder design.

