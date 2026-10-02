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
