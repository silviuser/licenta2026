# Module 3 — Step 5.5 diagnostic report

_Generated 2026-05-16, seed 42._

## Executive summary

**H₁ is not strongly supported by Lens B.** The single number: in vs out gap on `mnrl_sw_v1` is +0.0205, which falls inside the noise band for our sample size. **Prescribed next step:** Option 2 — Step 5b cross-encoder is the cheapest next probe.


## Environment

* Eval corpus size: 15 CVs
* CVs skipped (extraction failure or no labels): real_cv2
* Runs analysed: mnrl_v1_20260516_1610, mnrl_sw_v1_20260516_1953
* On-disk `train.jsonl` build timestamp: 2026-05-16T19:43:28.434439+00:00
> train.jsonl build_timestamp is the 19:43 build (mnrl_sw_v1's training data). Lens A coverage against `mnrl_v1` is best-effort — the 08:59 build it trained on was overwritten on disk.

## Lens A — Training-set coverage of eval URIs

* Total distinct eval URIs (high+medium): **140**
* Overlap with `train.jsonl` positives:     **34**
* Coverage ratio:                            **24.3 %**
* Training URI set size:                     320
* `train.jsonl` build timestamp:             2026-05-16T19:43:28.434439+00:00

Per-CV breakdown:

| CV | gold | in training | unseen |
|---|---:|---:|---:|
| real_cv1 | 14 | 11 | 3 |
| real_cv10 | 5 | 2 | 3 |
| real_cv11 | 13 | 4 | 9 |
| real_cv12 | 29 | 13 | 16 |
| real_cv13 | 12 | 0 | 12 |
| real_cv14 | 11 | 0 | 11 |
| real_cv15 | 12 | 0 | 12 |
| real_cv2 | 16 | 7 | 9 |
| real_cv3 | 19 | 10 | 9 |
| real_cv4 | 23 | 9 | 14 |
| real_cv5 | 27 | 15 | 12 |
| real_cv6 | 14 | 3 | 11 |
| real_cv7 | 20 | 6 | 14 |
| real_cv8 | 22 | 11 | 11 |
| real_cv9 | 22 | 9 | 13 |

> train.jsonl build_timestamp is the 19:43 build (mnrl_sw_v1's training data). Lens A coverage against `mnrl_v1` is best-effort — the 08:59 build it trained on was overwritten on disk.

## Lens B — Per-URI rank attribution

* Records analysed: **164** across 14 CVs (1 skipped: real_cv2).

|  | In `mnrl_sw` training | NOT in `mnrl_sw` training |
|---|---:|---:|
| URIs analysed                       | 90 | 74 |
| Mean Δsim after `mnrl_v1`           | -0.0739 | -0.0355 |
| Mean Δsim after `mnrl_sw_v1`        | -0.0515 | -0.0721 |
| URIs with improved sim (`mnrl_v1`)  | 23.3 % | 33.8 % |
| URIs with improved sim (`mnrl_sw`)  | 30.0 % | 21.6 % |

> in_training_v1 uses the on-disk train.jsonl as a proxy for mnrl_v1's training set (the 08:59 build it actually trained on was overwritten by the 19:43 build).

## Lens C — False-positive attribution

### Encoder: `mnrl_sw_v1_20260516_1953` (total FPs = 106)

* Mean training frequency of FP URIs:    **0.65**
* Median training frequency of FP URIs: **0.0**

| training freq bin | FP count |
|---|---:|
| [0, 1) | 97 |
| [1, 3) | 3 |
| [3, 6) | 0 |
| [6, 11) | 5 |
| [11, 26) | 1 |
| [26, 101) | 0 |
| [101, ∞) | 0 |

### Encoder: `mnrl_v1_20260516_1610` (total FPs = 211)

* Mean training frequency of FP URIs:    **1.88**
* Median training frequency of FP URIs: **0.0**

| training freq bin | FP count |
|---|---:|
| [0, 1) | 192 |
| [1, 3) | 7 |
| [3, 6) | 5 |
| [6, 11) | 3 |
| [11, 26) | 1 |
| [26, 101) | 1 |
| [101, ∞) | 2 |

### Encoder: `zero_shot` (total FPs = 219)

* Mean training frequency of FP URIs:    **1.15**
* Median training frequency of FP URIs: **0.0**

| training freq bin | FP count |
|---|---:|
| [0, 1) | 191 |
| [1, 3) | 13 |
| [3, 6) | 4 |
| [6, 11) | 4 |
| [11, 26) | 4 |
| [26, 101) | 3 |
| [101, ∞) | 0 |


## Lens D — Hard-negative quality audit

Cosine similarity between anchor and labelled concept, measured with the **zero-shot** encoder.

| group | n | mean | median | P25 | P75 |
|---|---:|---:|---:|---:|---:|
| hard negatives | 183 | 0.1578 | 0.1436 | 0.0831 | 0.2251 |
| positives (ref) | 200 | 0.3282 | 0.3200 | 0.2390 | 0.4186 |

Mean gap (positives − negatives): **+0.1705**

## Lens E — Concept-text alignment audit

Verdict: **ALIGNED** (0 of 5 samples differ).

All sampled URIs produced byte-identical concept text on both the training side and the index side. The train↔eval text contract is intact.

## Lens F — Training dynamics inspection

### `mnrl_sw_v1_20260516_1953`

* Final-row MRR@10:        0.1604
* Peak MRR@10:             0.1604 (epoch 3)
* Manifest `final_val_mrr@10`: 0.1604
* Monotonic increasing:    True
* Final-vs-peak gap:       +0.0000

| epoch | val MRR@10 |
|---:|---:|
| 1 | 0.1190 |
| 2 | 0.1535 |
| 3 | 0.1604 |

### `mnrl_v1_20260516_1610`

* Final-row MRR@10:        0.4397
* Peak MRR@10:             0.4397 (epoch 3)
* Manifest `final_val_mrr@10`: 0.4397
* Monotonic increasing:    True
* Final-vs-peak gap:       +0.0000

| epoch | val MRR@10 |
|---:|---:|
| 1 | 0.2941 |
| 2 | 0.4116 |
| 3 | 0.4397 |


## Synthesis

- Lens A — coverage is 24.3 %. A large minority of eval gold URIs were never labelled as positives at training time; bias amplification is plausible (supports H₁).
- Lens B — gap = +0.0205; in-training mean Δ = -0.0515, out-of-training mean Δ = -0.0721. Inspect direction relative to expectation.
- Lens B — `mnrl_v1` mirror: in-training Δ = -0.0739, out Δ = -0.0355, gap -0.0383.
- Lens D — hard negatives mean cosine = 0.1578, positives = 0.3282; mean gap +0.1705.
- Lens E — train↔index text alignment intact.
- Lens F — `mnrl_sw_v1_20260516_1953`: final MRR 0.1604, peak 0.1604 (rising at final epoch); monotonic=True.
- Lens F — `mnrl_v1_20260516_1610`: final MRR 0.4397, peak 0.4397 (rising at final epoch); monotonic=True.

## Prescription (auto-generated, ranked)

**Option 1 — Step 5c (data-side): rebuild training positives from a less-biased supervisor.**
What: rebuild `train.jsonl` so positives come from (a) lexical-only Module 2 *plus* (b) gold-truth eval-corpus URIs from a held-OUT slice of training CVs (not eval CVs), then re-run Step 5 fine-tuning. Cost: ~6-10 h Silviu time, 1 Colab session. Expected F1 gain: medium-to-large if Lens A coverage < 70 % and Lens B shows asymmetry. Risk: data quality of new positives — needs manual spot-check. Feeds Step 5c prompt.

**Option 2 — Step 5b (architecture-side): cross-encoder re-ranker.**
What: train a cross-encoder on the same `train.jsonl`, deploy on top of the lexical+zero-shot retriever as a re-ranker. Cost: ~4-6 h Silviu, 1-2 Colab sessions. Expected F1 gain: small-to-medium if bias amplification is *not* the dominant failure mode. Risk: inherits the same bias if Lens B confirmed asymmetry — Option 1 should run first in that case. Feeds Step 5b prompt.

**Option 3 — pivot to Step 6 with the zero-shot encoder.**
What: accept that the bi-encoder ceiling is below the F1 gate and proceed to Linker/Scorer with the zero-shot baseline as the semantic component. Cost: 0 extra Colab. Expected F1 gain: zero — but ensures thesis progress. Risk: thesis chapter has to defend the failed Step 5; honest write-up turns it into a methodological contribution ("naive distantly-supervised fine-tuning amplifies supervisor bias when the supervisor is the augmentation target").

## Recommendation

**Option 2 (Step 5b cross-encoder).** Lens B does NOT show the asymmetry that would indicate bias amplification, so the regression is more consistent with a bi-encoder capacity limit. A cross-encoder over the same data is the cheapest probe of that limit.

## Thesis-narrative implication

Either outcome supports the thesis chapter:
* If H₁ is confirmed (Option 1 path): Step 5 becomes a documented methodological finding — naive distantly-supervised fine-tuning amplifies supervisor bias when the supervisor is the augmentation target. The thesis is *stronger* with this caveat than without it.
* If H₀ is supported (Option 2 path): Step 5 documents that bi-encoder fine-tuning on the current corpus is insufficient and motivates the cross-encoder swap.
* If Lens E shows drift: Step 5 documents a process gap that the cross-encoder swap can also exploit once fixed.

The defence answer in all three cases is the same shape: *we measured before we acted, and the prescription follows from the measurement.*

## Appendix — unseen-URI list (Lens A, coverage < 70 %)



### real_cv1 (3 unseen)

* `CUST:cpp`

* `CUST:object-oriented-programming`

* `http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389`



### real_cv10 (3 unseen)

* `CUST:c`

* `CUST:html-css`

* `CUST:javascript`



### real_cv11 (9 unseen)

* `CUST:cpp`

* `CUST:deepseek-api`

* `CUST:openai-api`

* `CUST:react`

* `CUST:spring-boot`

* `CUST:vite`

* `http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389`

* `http://data.europa.eu/esco/skill/a8d07b5a-c1a1-42c6-9d53-db9c7a2ca996`

* `http://data.europa.eu/esco/skill/d8829a1d-dbde-435b-b921-29d6462f35c9`



### real_cv12 (16 unseen)

* `CUST:blender`

* `CUST:c`

* `CUST:canva`

* `CUST:cmake`

* `CUST:cpp`

* `CUST:full-stack`

* `CUST:glsl`

* `CUST:jira`

* `CUST:lang:romanian`

* `CUST:opengl`

* `CUST:pytorch`

* `CUST:react`

* `CUST:unity`

* `CUST:vite`

* `http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389`

* `http://data.europa.eu/esco/skill/5608d5a0-6d5e-43b7-be37-616501729bb4`



### real_cv13 (12 unseen)

* `CUST:3d-printing`

* `CUST:agile`

* `CUST:azure`

* `CUST:code-review`

* `CUST:docker`

* `CUST:frontend-development`

* `CUST:git`

* `CUST:javascript`

* `CUST:mysql`

* `CUST:nextjs`

* `CUST:react`

* `CUST:react-query`



### real_cv14 (11 unseen)

* `CUST:arduino`

* `CUST:automation`

* `CUST:cybersecurity`

* `CUST:databases`

* `CUST:generative-ai`

* `CUST:iot`

* `CUST:java`

* `CUST:llm`

* `CUST:rag`

* `CUST:rpa`

* `CUST:sql`



### real_cv15 (12 unseen)

* `CUST:bug-bounty`

* `CUST:cybersecurity`

* `CUST:data-manipulation`

* `CUST:data-visualization`

* `CUST:incident-response`

* `CUST:pandas`

* `CUST:programming`

* `CUST:python`

* `CUST:scripting`

* `CUST:siem`

* `CUST:soc-analyst`

* `CUST:threat-detection`



### real_cv2 (9 unseen)

* `CUST:canva`

* `CUST:cpp`

* `CUST:data-structures`

* `CUST:data-visualization`

* `CUST:oop`

* `CUST:signal-processing`

* `CUST:streamlit`

* `http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389`

* `http://data.europa.eu/esco/skill/7fb699d9-182a-430e-b7a0-6d8ed05c284b`



### real_cv3 (9 unseen)

* `CUST:cpp`

* `CUST:crud`

* `CUST:html-css`

* `CUST:react`

* `CUST:tailwind`

* `CUST:visual-studio-ide`

* `CUST:vscode`

* `CUST:webpack`

* `http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389`



### real_cv4 (14 unseen)

* `CUST:beautifulsoup`

* `CUST:cpp`

* `CUST:django`

* `CUST:flask`

* `CUST:git`

* `CUST:kotlin`

* `CUST:mongodb`

* `CUST:openai-api`

* `CUST:random-forest`

* `CUST:selenium`

* `CUST:tensorflow`

* `CUST:web-scraping`

* `http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389`

* `http://data.europa.eu/esco/skill/d8829a1d-dbde-435b-b921-29d6462f35c9`



### real_cv5 (12 unseen)

* `CUST:c`

* `CUST:cpp`

* `CUST:data-structures`

* `CUST:full-stack`

* `CUST:git`

* `CUST:operating-systems`

* `CUST:react`

* `CUST:real-time-systems`

* `CUST:secure-coding`

* `CUST:visual-studio-ide`

* `http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389`

* `http://data.europa.eu/esco/skill/d8829a1d-dbde-435b-b921-29d6462f35c9`



### real_cv6 (11 unseen)

* `CUST:cpp`

* `CUST:dax`

* `CUST:gbm`

* `CUST:pandas`

* `CUST:power-bi`

* `CUST:pytorch`

* `CUST:random-forest`

* `CUST:scikit-learn`

* `CUST:sql`

* `http://data.europa.eu/esco/skill/1c460d2d-90c6-4fc9-ad49-febb6e15605a`

* `http://data.europa.eu/esco/skill/ecc4552a-92c5-4222-b18d-faf5ac841080`



### real_cv7 (14 unseen)

* `CUST:burp-suite`

* `CUST:lang:french`

* `CUST:lang:japanese`

* `CUST:nmap`

* `CUST:penetration-testing`

* `CUST:react`

* `CUST:secure-coding`

* `CUST:tailwind`

* `CUST:threat-modeling`

* `CUST:vulnerability-assessment`

* `http://data.europa.eu/esco/skill/1ce4cddd-4a74-458e-a2d4-152ca939475a`

* `http://data.europa.eu/esco/skill/50597e96-9b6a-4736-ac79-dd80f36c0269`

* `http://data.europa.eu/esco/skill/7bf4539a-3f2e-4485-876b-1c9306b181af`

* `http://data.europa.eu/esco/skill/902fb91c-3113-4004-9b4f-79aa86b638b7`



### real_cv8 (11 unseen)

* `CUST:cpp`

* `CUST:html-css`

* `CUST:lang:romanian`

* `CUST:langchain`

* `CUST:langgraph`

* `CUST:llm`

* `CUST:mcp`

* `CUST:playwright`

* `CUST:selenium`

* `http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389`

* `http://data.europa.eu/esco/skill/867137fb-ff1b-4ca3-99f3-cb6969aa2c68`



### real_cv9 (13 unseen)

* `CUST:cpp`

* `CUST:django`

* `CUST:full-stack`

* `CUST:numpy`

* `CUST:pandas`

* `CUST:scikit-learn`

* `CUST:sql`

* `CUST:uml`

* `http://data.europa.eu/esco/skill/02e22093-3436-46a8-8dc5-b041bc4800cc`

* `http://data.europa.eu/esco/skill/19a8293b-8e95-4de3-983f-77484079c389`

* `http://data.europa.eu/esco/skill/3a2d5b45-56e4-4f5a-a55a-4a4a65afdc43`

* `http://data.europa.eu/esco/skill/76ef6ed3-1658-4a1a-9593-204d799c6d0c`

* `http://data.europa.eu/esco/skill/98301d4a-2cc3-439d-8d7f-0b6ac76302bb`


