# Module 3 — Step 5 fine-tuned baseline

Generated 2026-05-16 20:17:23 UTC

Run name: **mnrl_sw_v1_20260516_1953**


## 1. Executive summary

* Zero-shot semantic macro F1 (high+medium view): **0.146**
* Fine-tuned semantic macro F1: **0.145**
* Delta: **-0.001** (lift: 0.99×)
* Lexical floor (Module 2): 0.460
* Ensemble (lex ∪ sem) macro F1: **0.317** (BELOW lexical floor)
* Step 6 gate (macro F1 ≥ 0.55): **FAIL**

## 2. Environment

* Base model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
* Fine-tuned checkpoint: `C:\Users\silvi\Desktop\licenta2026\app\nlp-service\models\skill_matcher\mnrl_sw_v1_20260516_1953`
* skill_matcher version: 0.3.1
* Semantic threshold (headline): 0.5
* Top-k per window: 5
* Sliding window: size=30 tokens, stride=15 tokens
* Concept-text format: bounded-a
* ESCO concepts indexed: 14013
* Encoder device: cpu

## 3. Index build timing

* Zero-shot index: warm load in 0.2s (`C:\Users\silvi\Desktop\licenta2026\app\nlp-service\.cache\embeddings\esco_39897b1e723b_bce83eb3ad4f_bounded-a.npz`)
* Fine-tuned index: cold build in 394.0s (`C:\Users\silvi\Desktop\licenta2026\app\nlp-service\.cache\embeddings\esco_f63f31ca54a9_bce83eb3ad4f_bounded-a.npz`)

## 4. Per-CV breakdown

### Per-CV semantic F1

| CV | Zero-shot F1 | Fine-tuned F1 | Delta |
|---|---|---|---|
| real_cv3 | 0.129 | 0.350 | +0.221 |
| real_cv13 | 0.121 | 0.200 | +0.079 |
| real_cv11 | 0.080 | 0.105 | +0.025 |
| real_cv6 | 0.068 | 0.091 | +0.023 |
| real_cv15 | 0.049 | 0.071 | +0.023 |
| real_cv1 | 0.341 | 0.364 | +0.022 |
| real_cv8 | 0.194 | 0.200 | +0.006 |
| real_cv14 | 0.000 | 0.000 | +0.000 |
| real_cv9 | 0.163 | 0.158 | -0.005 |
| real_cv5 | 0.217 | 0.182 | -0.035 |
| real_cv12 | 0.125 | 0.060 | -0.065 |
| real_cv4 | 0.294 | 0.204 | -0.090 |
| real_cv7 | 0.143 | 0.043 | -0.099 |
| real_cv10 | 0.118 | 0.000 | -0.118 |

## 5. Aggregate metrics

### high+medium (headline) view

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Macro F1 delta |
|---|---|---|---|
| Lexical (Module 2) | P=0.645  R=0.371  F1=0.460 | P=0.645  R=0.371  F1=0.460 | +0.000 |
| Semantic | P=0.110  R=0.220  F1=0.146 | P=0.140  R=0.159  F1=0.145 | -0.001 |
| Ensemble (lex ∪ sem) | P=0.189  R=0.453  F1=0.265 | P=0.260  R=0.428  F1=0.317 | +0.052 |

Micro:

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Micro F1 delta |
|---|---|---|---|
| Lexical | P=0.701  R=0.424  F1=0.528 | P=0.701  R=0.424  F1=0.528 | +0.000 |
| Semantic | P=0.116  R=0.239  F1=0.156 | P=0.131  R=0.169  F1=0.148 | -0.008 |
| Ensemble | P=0.205  R=0.514  F1=0.293 | P=0.271  R=0.477  F1=0.346 | +0.052 |

### high (strict) view

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Macro F1 delta |
|---|---|---|---|
| Lexical (Module 2) | P=0.509  R=0.359  F1=0.416 | P=0.509  R=0.359  F1=0.416 | +0.000 |
| Semantic | P=0.095  R=0.214  F1=0.131 | P=0.124  R=0.163  F1=0.139 | +0.008 |
| Ensemble (lex ∪ sem) | P=0.162  R=0.445  F1=0.235 | P=0.228  R=0.428  F1=0.292 | +0.057 |

Micro:

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Micro F1 delta |
|---|---|---|---|
| Lexical | P=0.612  R=0.433  F1=0.507 | P=0.612  R=0.433  F1=0.507 | +0.000 |
| Semantic | P=0.104  R=0.250  F1=0.147 | P=0.119  R=0.178  F1=0.142 | -0.005 |
| Ensemble | P=0.181  R=0.529  F1=0.269 | P=0.241  R=0.495  F1=0.324 | +0.055 |

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

* **real_cv3**: F1 0.129 -> 0.350 (+0.221)

### Qualitative regressions (F1 drop > 0.05)

* **real_cv10**: F1 0.118 -> 0.000 (-0.118) — investigate whether overfitting to training distribution caused this
* **real_cv12**: F1 0.125 -> 0.060 (-0.065) — investigate whether overfitting to training distribution caused this
* **real_cv4**: F1 0.294 -> 0.204 (-0.090) — investigate whether overfitting to training distribution caused this
* **real_cv7**: F1 0.143 -> 0.043 (-0.099) — investigate whether overfitting to training distribution caused this

## Decision

* **Fine-tuned semantic macro F1**: 0.145 (gate: ≥ 0.55).
* **Fine-tuned ensemble macro F1**: 0.317 (must beat lexical floor 0.460).

**Step 5b — cross-encoder re-ranker.**

Fine-tuned F1 is below 0.45 / 0.55 thresholds. The bi-encoder gap is too wide to close by hyperparameter sweep alone; open a Step 5b Pre-Flight for the cross-encoder design.

