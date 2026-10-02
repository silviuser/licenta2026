# Module 3 — Step 5 fine-tuned baseline

Generated 2026-05-16 19:28:45 UTC

Run name: **mnrl_v1_20260516_1610**


## 1. Executive summary

* Zero-shot semantic macro F1 (high+medium view): **0.146**
* Fine-tuned semantic macro F1: **0.153**
* Delta: **+0.007** (lift: 1.05×)
* Lexical floor (Module 2): 0.460
* Ensemble (lex ∪ sem) macro F1: **0.279** (BELOW lexical floor)
* Step 6 gate (macro F1 ≥ 0.55): **FAIL**

## 2. Environment

* Base model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
* Fine-tuned checkpoint: `C:\Users\silvi\Desktop\licenta2026\app\nlp-service\models\skill_matcher\mnrl_v1_20260516_1610`
* skill_matcher version: 0.3.0
* Semantic threshold (headline): 0.5
* Top-k per window: 5
* Sliding window: size=30 tokens, stride=15 tokens
* Concept-text format: bounded-a
* ESCO concepts indexed: 14013
* Encoder device: cpu

## 3. Index build timing

* Zero-shot index: warm load in 0.2s (`C:\Users\silvi\Desktop\licenta2026\app\nlp-service\.cache\embeddings\esco_39897b1e723b_bce83eb3ad4f_bounded-a.npz`)
* Fine-tuned index: warm load in 0.2s (`C:\Users\silvi\Desktop\licenta2026\app\nlp-service\.cache\embeddings\esco_0dbd7e36500e_bce83eb3ad4f_bounded-a.npz`)

## 4. Per-CV breakdown

### Per-CV semantic F1

| CV | Zero-shot F1 | Fine-tuned F1 | Delta |
|---|---|---|---|
| real_cv9 | 0.163 | 0.279 | +0.116 |
| real_cv3 | 0.129 | 0.218 | +0.089 |
| real_cv1 | 0.341 | 0.417 | +0.075 |
| real_cv11 | 0.080 | 0.150 | +0.070 |
| real_cv10 | 0.118 | 0.167 | +0.049 |
| real_cv13 | 0.121 | 0.167 | +0.045 |
| real_cv15 | 0.049 | 0.056 | +0.007 |
| real_cv14 | 0.000 | 0.000 | +0.000 |
| real_cv6 | 0.068 | 0.054 | -0.014 |
| real_cv12 | 0.125 | 0.105 | -0.020 |
| real_cv5 | 0.217 | 0.159 | -0.058 |
| real_cv8 | 0.194 | 0.133 | -0.060 |
| real_cv4 | 0.294 | 0.197 | -0.097 |
| real_cv7 | 0.143 | 0.037 | -0.106 |

## 5. Aggregate metrics

### high+medium (headline) view

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Macro F1 delta |
|---|---|---|---|
| Lexical (Module 2) | P=0.645  R=0.371  F1=0.460 | P=0.645  R=0.371  F1=0.460 | +0.000 |
| Semantic | P=0.110  R=0.220  F1=0.146 | P=0.126  R=0.212  F1=0.153 | +0.007 |
| Ensemble (lex ∪ sem) | P=0.189  R=0.453  F1=0.265 | P=0.212  R=0.437  F1=0.279 | +0.015 |

Micro:

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Micro F1 delta |
|---|---|---|---|
| Lexical | P=0.701  R=0.424  F1=0.528 | P=0.701  R=0.424  F1=0.528 | +0.000 |
| Semantic | P=0.116  R=0.239  F1=0.156 | P=0.117  R=0.214  F1=0.151 | -0.005 |
| Ensemble | P=0.205  R=0.514  F1=0.293 | P=0.214  R=0.490  F1=0.298 | +0.005 |

### high (strict) view

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Macro F1 delta |
|---|---|---|---|
| Lexical (Module 2) | P=0.509  R=0.359  F1=0.416 | P=0.509  R=0.359  F1=0.416 | +0.000 |
| Semantic | P=0.095  R=0.214  F1=0.131 | P=0.106  R=0.209  F1=0.137 | +0.006 |
| Ensemble (lex ∪ sem) | P=0.162  R=0.445  F1=0.235 | P=0.176  R=0.425  F1=0.245 | +0.009 |

Micro:

| Source | Zero-shot P / R / F1 | Fine-tuned P / R / F1 | Micro F1 delta |
|---|---|---|---|
| Lexical | P=0.612  R=0.433  F1=0.507 | P=0.612  R=0.433  F1=0.507 | +0.000 |
| Semantic | P=0.104  R=0.250  F1=0.147 | P=0.105  R=0.226  F1=0.144 | -0.003 |
| Ensemble | P=0.181  R=0.529  F1=0.269 | P=0.187  R=0.500  F1=0.273 | +0.003 |

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

* **real_cv9**: F1 0.163 -> 0.279 (+0.116)

### Qualitative regressions (F1 drop > 0.05)

* **real_cv4**: F1 0.294 -> 0.197 (-0.097) — investigate whether overfitting to training distribution caused this
* **real_cv5**: F1 0.217 -> 0.159 (-0.058) — investigate whether overfitting to training distribution caused this
* **real_cv7**: F1 0.143 -> 0.037 (-0.106) — investigate whether overfitting to training distribution caused this
* **real_cv8**: F1 0.194 -> 0.133 (-0.060) — investigate whether overfitting to training distribution caused this

## Decision

* **Fine-tuned semantic macro F1**: 0.153 (gate: ≥ 0.55).
* **Fine-tuned ensemble macro F1**: 0.279 (must beat lexical floor 0.460).

**Step 5b — cross-encoder re-ranker.**

Fine-tuned F1 is below 0.45 / 0.55 thresholds. The bi-encoder gap is too wide to close by hyperparameter sweep alone; open a Step 5b Pre-Flight for the cross-encoder design.

