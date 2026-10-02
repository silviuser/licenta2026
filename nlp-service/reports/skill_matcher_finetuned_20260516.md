# Module 3 — Step 5 fine-tuned baseline

Generated 2026-05-16 16:45:03 UTC

Run name: **mnrl_v1_20260516_1610**


## 1. Executive summary

* Zero-shot semantic macro F1 (high+medium view): **0.151**
* Fine-tuned semantic macro F1: **0.144**
* Delta: **-0.007** (lift: 0.95×)
* Lexical floor (Module 2): 0.460
* Ensemble (lex ∪ sem) macro F1: **0.339** (BELOW lexical floor)
* Step 6 gate (macro F1 ≥ 0.55): **FAIL**

## 2. Environment

* Base model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
* Fine-tuned checkpoint: `C:\Users\silvi\Desktop\licenta2026\app\nlp-service\models\skill_matcher\mnrl_v1_20260516_1610`
* skill_matcher version: 0.3.0
* Semantic threshold (headline): 0.55
* Top-k per window: 5
* Sliding window: size=30 tokens, stride=15 tokens
* Concept-text format: bounded-a
* ESCO concepts indexed: 14013
* Encoder device: cpu

## 3. Index build timing

* Zero-shot index: warm load in 0.2s (`C:\Users\silvi\Desktop\licenta2026\app\nlp-service\.cache\embeddings\esco_39897b1e723b_bce83eb3ad4f_bounded-a.npz`)
* Fine-tuned index: cold build in 390.3s (`C:\Users\silvi\Desktop\licenta2026\app\nlp-service\.cache\embeddings\esco_0dbd7e36500e_bce83eb3ad4f_bounded-a.npz`)

## 4. Per-CV breakdown

### Per-CV semantic F1

| CV | Zero-shot F1 | Fine-tuned F1 | Delta |
|---|---|---|---|
| real_cv11 | 0.067 | 0.148 | +0.081 |
| real_cv4 | 0.222 | 0.286 | +0.063 |
| real_cv1 | 0.343 | 0.390 | +0.047 |
| real_cv3 | 0.143 | 0.182 | +0.039 |
| real_cv6 | 0.054 | 0.082 | +0.028 |
| real_cv15 | 0.074 | 0.095 | +0.021 |
| real_cv12 | 0.119 | 0.138 | +0.019 |
| real_cv9 | 0.059 | 0.065 | +0.006 |
| real_cv14 | 0.000 | 0.000 | +0.000 |
| real_cv13 | 0.200 | 0.174 | -0.026 |
| real_cv10 | 0.250 | 0.222 | -0.028 |
| real_cv8 | 0.170 | 0.067 | -0.104 |
| real_cv5 | 0.226 | 0.118 | -0.108 |
| real_cv7 | 0.182 | 0.043 | -0.138 |

## 5. Aggregate metrics

### high+medium (headline) view

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Macro F1 delta |
|---|---|---|---|
| Lexical (Module 2) | P=0.645  R=0.371  F1=0.460 | P=0.645  R=0.371  F1=0.460 | +0.000 |
| Semantic | P=0.157  R=0.156  F1=0.151 | P=0.147  R=0.156  F1=0.144 | -0.007 |
| Ensemble (lex ∪ sem) | P=0.303  R=0.437  F1=0.346 | P=0.300  R=0.416  F1=0.339 | -0.007 |

Micro:

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Micro F1 delta |
|---|---|---|---|
| Lexical | P=0.701  R=0.424  F1=0.528 | P=0.701  R=0.424  F1=0.528 | +0.000 |
| Semantic | P=0.151  R=0.160  F1=0.156 | P=0.146  R=0.148  F1=0.147 | -0.009 |
| Ensemble | P=0.313  R=0.494  F1=0.383 | P=0.310  R=0.469  F1=0.373 | -0.010 |

### high (strict) view

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Macro F1 delta |
|---|---|---|---|
| Lexical (Module 2) | P=0.509  R=0.359  F1=0.416 | P=0.509  R=0.359  F1=0.416 | +0.000 |
| Semantic | P=0.129  R=0.153  F1=0.137 | P=0.120  R=0.152  F1=0.128 | -0.009 |
| Ensemble (lex ∪ sem) | P=0.248  R=0.429  F1=0.308 | P=0.243  R=0.404  F1=0.297 | -0.011 |

Micro:

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Micro F1 delta |
|---|---|---|---|
| Lexical | P=0.612  R=0.433  F1=0.507 | P=0.612  R=0.433  F1=0.507 | +0.000 |
| Semantic | P=0.143  R=0.178  F1=0.159 | P=0.134  R=0.159  F1=0.145 | -0.014 |
| Ensemble | P=0.277  R=0.510  F1=0.359 | P=0.269  R=0.476  F1=0.344 | -0.015 |

## 6. Threshold ablation

### Threshold ablation (semantic macro F1, high+medium view)

| Threshold | Zero-shot | Fine-tuned | Delta |
|---|---|---|---|
| 0.40 | 0.114 | 0.122 | +0.008 |
| 0.45 | 0.124 | 0.136 | +0.012 |
| 0.50 | 0.146 | 0.153 | +0.007 |
| 0.55 | 0.151 | 0.144 | -0.007 |
| 0.60 | 0.147 | 0.132 | -0.015 |
| 0.65 | 0.073 | 0.096 | +0.023 |
| 0.70 | 0.016 | 0.064 | +0.048 |
| 0.75 | 0.013 | 0.049 | +0.036 |

## 7. Qualitative analysis

### Qualitative wins (F1 lift >= 0.10)

*None.*

### Qualitative regressions (F1 drop > 0.05)

* **real_cv5**: F1 0.226 -> 0.118 (-0.108) — investigate whether overfitting to training distribution caused this
* **real_cv7**: F1 0.182 -> 0.043 (-0.138) — investigate whether overfitting to training distribution caused this
* **real_cv8**: F1 0.170 -> 0.067 (-0.104) — investigate whether overfitting to training distribution caused this

## Decision

* **Fine-tuned semantic macro F1**: 0.144 (gate: ≥ 0.55).
* **Fine-tuned ensemble macro F1**: 0.339 (must beat lexical floor 0.460).

**Step 5b — cross-encoder re-ranker.**

Fine-tuned F1 is below 0.45 / 0.55 thresholds. The bi-encoder gap is too wide to close by hyperparameter sweep alone; open a Step 5b Pre-Flight for the cross-encoder design.

