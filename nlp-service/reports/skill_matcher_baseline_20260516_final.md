# Module 3 — Zero-Shot Baseline Report

_Generated: 2026-05-16T14:03:12.045784+00:00_

## 1. Executive summary

Zero-shot semantic retrieval reaches **macro F1 = 0.151** on the 15-CV held-out eval corpus at threshold 0.55 (gold view: `high + medium`). Module 2 lexical floor (May 2026 patch round) is F1 = 0.766. The Step 4 baseline establishes the floor against which Step 5 fine-tuning will be measured.

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
- **elapsed_seconds**: `0.25`
- **n_concepts**: `14013`
- **embedding_dim**: `384`
- **concept_text_format**: `bounded-a`

## 4. Per-CV breakdown

| CV | windows | gold(h) | gold(h+m) | Lex P/R/F1 (h+m) | Sem P/R/F1 (h) | Sem P/R/F1 (h+m) |
|---|---|---|---|---|---|---|
| real_cv1 | 18 | 14 | 14 | 0.875 / 0.500 / 0.636 | 0.286 / 0.429 / 0.343 | 0.286 / 0.429 / 0.343 |
| real_cv10 | 8 | 4 | 5 | 1.000 / 0.200 / 0.333 | 0.000 / 0.000 / 0.000 | 0.333 / 0.200 / 0.250 |
| real_cv11 | 17 | 10 | 13 | 0.556 / 0.385 / 0.455 | 0.000 / 0.000 / 0.000 | 0.059 / 0.077 / 0.067 |
| real_cv12 | 34 | 26 | 29 | 0.583 / 0.483 / 0.528 | 0.105 / 0.154 / 0.125 | 0.105 / 0.138 / 0.119 |
| real_cv13 | 8 | 8 | 12 | 0.000 / 0.000 / 0.000 | 0.250 / 0.250 / 0.250 | 0.250 / 0.167 / 0.200 |
| real_cv14 | 14 | 8 | 11 | 0.200 / 0.091 / 0.125 | 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 |
| real_cv15 | 12 | 8 | 12 | 0.167 / 0.083 / 0.111 | 0.067 / 0.125 / 0.087 | 0.067 / 0.083 / 0.074 |
| real_cv3 | 19 | 18 | 19 | 1.000 / 0.579 / 0.733 | 0.130 / 0.167 / 0.146 | 0.130 / 0.158 / 0.143 |
| real_cv4 | 23 | 20 | 23 | 0.933 / 0.609 / 0.737 | 0.308 / 0.200 / 0.242 | 0.308 / 0.174 / 0.222 |
| real_cv5 | 22 | 27 | 27 | 0.933 / 0.519 / 0.667 | 0.200 / 0.259 / 0.226 | 0.200 / 0.259 / 0.226 |
| real_cv6 | 25 | 12 | 14 | 0.308 / 0.286 / 0.296 | 0.043 / 0.083 / 0.057 | 0.043 / 0.071 / 0.054 |
| real_cv7 | 27 | 19 | 20 | 0.714 / 0.500 / 0.588 | 0.167 / 0.211 / 0.186 | 0.167 / 0.200 / 0.182 |
| real_cv8 | 24 | 20 | 22 | 0.909 / 0.455 / 0.606 | 0.160 / 0.200 / 0.178 | 0.160 / 0.182 / 0.170 |
| real_cv9 | 20 | 14 | 22 | 0.846 / 0.500 / 0.629 | 0.083 / 0.071 / 0.077 | 0.083 / 0.045 / 0.059 |

## 5. Aggregate metrics

### View: `high` (threshold=0.55, top_k=5)

| Source | Macro P/R/F1 | Micro P/R/F1 |
|---|---|---|
| Lexical (Module 2) | 0.509 / 0.359 / 0.416 | 0.612 / 0.433 / 0.507 |
| Semantic (Module 3 expansion) | 0.129 / 0.153 / 0.137 | 0.143 / 0.178 / 0.159 |
| Ensemble (lex ∪ sem) | 0.248 / 0.429 / 0.308 | 0.277 / 0.510 / 0.359 |

### View: `high_plus_medium` (threshold=0.55, top_k=5)

| Source | Macro P/R/F1 | Micro P/R/F1 |
|---|---|---|
| Lexical (Module 2) | 0.645 / 0.371 / 0.460 | 0.701 / 0.424 / 0.528 |
| Semantic (Module 3 expansion) | 0.157 / 0.156 / 0.151 | 0.151 / 0.160 / 0.156 |
| Ensemble (lex ∪ sem) | 0.303 / 0.437 / 0.346 | 0.313 / 0.494 / 0.383 |

## 6. Threshold ablation (gold view: `high + medium`)

| Threshold | Macro P | Macro R | Macro F1 |
|---|---|---|---|
| 0.40 | 0.075 | 0.252 | 0.114 |
| 0.45 | 0.084 | 0.246 | 0.124 |
| 0.50 | 0.110 | 0.220 | 0.146 |
| 0.55 | 0.157 | 0.156 | 0.151 |
| 0.60 | 0.392 | 0.109 | 0.147 |
| 0.65 | 0.478 | 0.046 | 0.073 |
| 0.70 | 0.614 | 0.010 | 0.016 |
| 0.75 | 0.756 | 0.008 | 0.013 |

## 7. Top-k ablation

_Top-k ablation requires re-running retrieval; not free at report-render time. Run the CLI with different `--top-k` values to populate this section per-row, or use `--ablation` for the full ablation pass._

## 9. Qualitative failure modes

_To populate manually: pick 5+ examples where a gold URI was NOT retrieved at any threshold and document the CV span vs the missed URI's preferred label, plus a one-line hypothesis. This feeds Step 6 expansion-stage design (Linker)._

## 10. Conclusion

Zero-shot macro F1 of 0.151 establishes the Step 4 floor. Step 5 fine-tuning proceeds regardless of this number (per DECISIONS.md D7); only post-fine-tune F1 < 0.55 triggers the conditional Step 5b cross-encoder.
