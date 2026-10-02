# Module 3 — Zero-Shot Baseline Report

_Generated: 2026-05-16T13:58:34.045860+00:00_

## 1. Executive summary

Zero-shot semantic retrieval reaches **macro F1 = 0.134** on the 15-CV held-out eval corpus at threshold 0.55 (gold view: `high + medium`). Module 2 lexical floor (May 2026 patch round) is F1 = 0.766. The Step 4 baseline establishes the floor against which Step 5 fine-tuning will be measured.

## 2. Environment

- **python_version**: `3.11.9`
- **model_name**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **embedding_dim**: `384`
- **device**: `cpu`
- **concept_counts**: `{'total': 14013, 'custom': 74, 'knowledge': 3219, 'skill/competence': 10435, 'language': 359}`
- **esco_file_sha**: `bce83eb3ad4f`
- **skill_matcher_version**: `0.2.0`
- **seed**: `42`

## 3. Index build

- **cold_build**: `False`
- **elapsed_seconds**: `0.265`
- **n_concepts**: `14013`
- **embedding_dim**: `384`
- **concept_text_format**: `b`

## 4. Per-CV breakdown

| CV | windows | gold(h) | gold(h+m) | Lex P/R/F1 (h+m) | Sem P/R/F1 (h) | Sem P/R/F1 (h+m) |
|---|---|---|---|---|---|---|
| real_cv1 | 18 | 14 | 14 | 0.875 / 0.500 / 0.636 | 0.333 / 0.571 / 0.421 | 0.333 / 0.571 / 0.421 |
| real_cv10 | 8 | 4 | 5 | 1.000 / 0.200 / 0.333 | 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 |
| real_cv11 | 17 | 10 | 13 | 0.556 / 0.385 / 0.455 | 0.045 / 0.100 / 0.063 | 0.091 / 0.154 / 0.114 |
| real_cv12 | 34 | 26 | 29 | 0.583 / 0.483 / 0.528 | 0.094 / 0.192 / 0.127 | 0.094 / 0.172 / 0.122 |
| real_cv13 | 8 | 8 | 12 | 0.000 / 0.000 / 0.000 | 0.133 / 0.250 / 0.174 | 0.133 / 0.167 / 0.148 |
| real_cv14 | 14 | 8 | 11 | 0.200 / 0.091 / 0.125 | 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 |
| real_cv15 | 12 | 8 | 12 | 0.167 / 0.083 / 0.111 | 0.043 / 0.125 / 0.065 | 0.043 / 0.083 / 0.057 |
| real_cv3 | 19 | 18 | 19 | 1.000 / 0.579 / 0.733 | 0.036 / 0.056 / 0.043 | 0.036 / 0.053 / 0.043 |
| real_cv4 | 23 | 20 | 23 | 0.933 / 0.609 / 0.737 | 0.217 / 0.250 / 0.233 | 0.217 / 0.217 / 0.217 |
| real_cv5 | 22 | 27 | 27 | 0.933 / 0.519 / 0.667 | 0.256 / 0.407 / 0.314 | 0.256 / 0.407 / 0.314 |
| real_cv6 | 25 | 12 | 14 | 0.308 / 0.286 / 0.296 | 0.024 / 0.083 / 0.038 | 0.024 / 0.071 / 0.036 |
| real_cv7 | 27 | 19 | 20 | 0.714 / 0.500 / 0.588 | 0.081 / 0.158 / 0.107 | 0.081 / 0.150 / 0.105 |
| real_cv8 | 24 | 20 | 22 | 0.909 / 0.455 / 0.606 | 0.161 / 0.250 / 0.196 | 0.161 / 0.227 / 0.189 |
| real_cv9 | 20 | 14 | 22 | 0.846 / 0.500 / 0.629 | 0.059 / 0.071 / 0.065 | 0.118 / 0.091 / 0.103 |

## 5. Aggregate metrics

### View: `high` (threshold=0.55, top_k=5)

| Source | Macro P/R/F1 | Micro P/R/F1 |
|---|---|---|
| Lexical (Module 2) | 0.509 / 0.359 / 0.416 | 0.612 / 0.433 / 0.507 |
| Semantic (Module 3 expansion) | 0.106 / 0.180 / 0.132 | 0.118 / 0.212 / 0.151 |
| Ensemble (lex ∪ sem) | 0.201 / 0.442 / 0.274 | 0.220 / 0.524 / 0.310 |

### View: `high_plus_medium` (threshold=0.55, top_k=5)

| Source | Macro P/R/F1 | Micro P/R/F1 |
|---|---|---|
| Lexical (Module 2) | 0.645 / 0.371 / 0.460 | 0.701 / 0.424 / 0.528 |
| Semantic (Module 3 expansion) | 0.113 / 0.169 / 0.134 | 0.123 / 0.189 / 0.149 |
| Ensemble (lex ∪ sem) | 0.236 / 0.450 / 0.306 | 0.248 / 0.506 / 0.333 |

## 6. Threshold ablation (gold view: `high + medium`)

| Threshold | Macro P | Macro R | Macro F1 |
|---|---|---|---|
| 0.40 | 0.068 | 0.239 | 0.105 |
| 0.45 | 0.073 | 0.236 | 0.110 |
| 0.50 | 0.083 | 0.216 | 0.119 |
| 0.55 | 0.113 | 0.169 | 0.134 |
| 0.60 | 0.326 | 0.117 | 0.129 |
| 0.65 | 0.424 | 0.067 | 0.096 |
| 0.70 | 0.508 | 0.035 | 0.052 |
| 0.75 | 0.728 | 0.018 | 0.028 |

## 7. Top-k ablation

_Top-k ablation requires re-running retrieval; not free at report-render time. Run the CLI with different `--top-k` values to populate this section per-row, or use `--ablation` for the full ablation pass._

## 9. Qualitative failure modes

_To populate manually: pick 5+ examples where a gold URI was NOT retrieved at any threshold and document the CV span vs the missed URI's preferred label, plus a one-line hypothesis. This feeds Step 6 expansion-stage design (Linker)._

## 10. Conclusion

Zero-shot macro F1 of 0.134 establishes the Step 4 floor. Step 5 fine-tuning proceeds regardless of this number (per DECISIONS.md D7); only post-fine-tune F1 < 0.55 triggers the conditional Step 5b cross-encoder.
