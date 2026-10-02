"""Configuration for the semantic skill matcher (Module 3).

Following the same convention as :mod:`skill_extractor.config`:
environment variables prefixed with ``SKILL_MATCHER_`` override
defaults, all paths resolve relative to the ``nlp-service/``
repository root, and defaults match the values used in the validation
reports.

Step 8 lock (2026-05-17): adds ``required_weight``,
``t1_strong_threshold`` and ``t2_possible_threshold`` fields, and
**bumps the seven tunable knobs to the values produced by
``scripts/tune_thresholds.py --mode full``** against the Step 5
placeholder encoder (macro F1 lift +0.279 vs the Step 7 degenerate
baseline 0.225 -> 0.504). The amendment row is recorded in
``DECISIONS.md``. Re-run the tuner after the Step 5 redo to
recalibrate; T1, T2 and ``per_requirement_keep_threshold`` are all
expected to climb back toward the intended `[0, 1]` range as the
score distribution widens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# This file lives at ``nlp-service/src/skill_matcher/config.py``, so
# going up three parents lands at ``nlp-service/``.
_NLP_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_ROOT = Path(__file__).resolve().parent

DEFAULT_BASE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_MODELS_DIR = _NLP_SERVICE_ROOT / "models" / "skill_matcher"
DEFAULT_EMBEDDING_CACHE_DIR = _NLP_SERVICE_ROOT / ".cache" / "embeddings"


Device = Literal["cpu", "cuda", "auto"]
"""Compute device selector. ``"auto"`` resolves to ``"cuda"`` if a CUDA
device is visible, else ``"cpu"``."""


class SkillMatcherConfig(BaseSettings):
    """Configuration for :class:`skill_matcher.pipeline.SkillMatcher`.

    Environment variable prefix: ``SKILL_MATCHER_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="SKILL_MATCHER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Model selection -------------------------------------------------
    base_model: str = Field(
        default=DEFAULT_BASE_MODEL,
        description=(
            "HuggingFace identifier of the sentence-transformer used as "
            "the encoder. Default is the multilingual MiniLM, selected "
            "for EN+RO coverage and CPU-friendly inference."
        ),
    )
    finetuned_model_path: Path | None = Field(
        default=None,
        description=(
            "Local path to a fine-tuned checkpoint produced by Step 5. "
            "When set, takes precedence over :attr:`base_model`."
        ),
    )
    models_dir: Path = Field(
        default=DEFAULT_MODELS_DIR,
        description=(
            "Directory where fine-tuned checkpoints are stored locally."
        ),
    )
    embedding_cache_dir: Path = Field(
        default=DEFAULT_EMBEDDING_CACHE_DIR,
        description=(
            "Directory used to persist computed embeddings (ESCO index, "
            "per-CV chunk embeddings). Cache keys include the model "
            "identifier to avoid stale-embedding bugs across model swaps."
        ),
    )

    # --- Thresholds (Step 8 lock 2026-05-17, full-mode tuner) ----------
    drop_threshold: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description=(
            "Candidates with semantic similarity below this are emitted "
            "with ``source='lexical_dropped'``. **Step 8 lock "
            "(2026-05-17):** 0.40. **Demo-day override (2026-05-17):** "
            "lowered to 0.35 to recover CV-frequent skills the "
            "placeholder Step 5 encoder under-scores in dense skills-list "
            "contexts (OOP at 0.397, C++ at 0.376, CRUD at 0.388). The "
            "false-positive risk introduced (style sheet languages on "
            "'CSS', database management systems on 'SQL', etc.) is "
            "neutralised by matching suppression rules in "
            "``skill_extractor/data/suppression_rules.yaml``. Revert to "
            "0.40 — or re-tune via ``scripts/tune_thresholds.py`` — "
            "once Step 5 redo delivers a proper encoder."
        ),
    )
    keep_threshold: float = Field(
        default=0.42,  # REWORK-EVAL 2026-06-08: 0.50 missed close cross-lingual synonyms
        ge=0.0,
        le=1.0,
        description=(
            "Candidates with semantic similarity >= this are emitted "
            "with ``source='lexical_kept'`` and used for scoring. "
            "**Step 8 lock (2026-05-17):** 0.50 (down from Step 4's "
            "provisional 0.55). Re-run `scripts/tune_thresholds.py` "
            "after the Step 5 redo -- this value is expected to climb "
            "back toward 0.55+ as the score distribution widens."
        ),
    )
    expansion_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description=(
            "Sliding-window retrieval emits an expansion candidate "
            "only when max cosine sim to any ESCO concept >= this. "
            "**Step 8 lock (2026-05-17):** 0.75 (unchanged from the "
            "Step 4 default; the tuner sweep picked the same value)."
        ),
    )
    per_requirement_keep_threshold: float = Field(
        default=0.085,
        ge=0.0,
        le=1.0,
        description=(
            "Per-requirement match-score floor used by Step 7's Scorer. "
            "Below this bound, a requirement is recorded as unmatched. "
            "**Step 8 lock (2026-05-17):** 0.085 (down from Step 7's "
            "provisional 0.30) -- calibrated for the placeholder "
            "encoder's compressed score range. After Step 5 redo this "
            "is expected to climb to ~0.20-0.30."
        ),
    )

    # --- Step 8 promoted fields (Step 7 implicits made explicit) ------
    required_weight: float = Field(
        default=0.85,  # REWORK-EVAL 2026-06-08: 0.50 capped overall at 50% for required-heavy JDs
        ge=0.0,
        le=1.0,
        description=(
            "Weight of the ``required_score`` component in the Scorer's "
            "final aggregation; the nice-to-have weight is the "
            "complement (``1 - required_weight``). **Step 8 lock "
            "(2026-05-17):** 0.50 (down from Step 7's hard-coded 0.80) "
            "-- the tuner found that 50/50 weighting maximises macro F1 "
            "under the placeholder encoder. Re-run after Step 5 redo "
            "to recalibrate."
        ),
    )
    t1_strong_threshold: float = Field(
        default=0.060,
        ge=0.0,
        le=1.0,
        description=(
            "3-class projection's STRONG cut: "
            "``overall_score >= t1_strong_threshold`` -> ``'strong'``. "
            "**Step 8 lock (2026-05-17):** 0.060 (down from Step 7's "
            "provisional 0.55). This dramatic drop reflects the "
            "placeholder encoder's compressed `[0, ~0.1]` score range; "
            "post-Step-5-redo this is expected to climb back toward "
            "0.4-0.6 as the distribution widens."
        ),
    )
    t2_possible_threshold: float = Field(
        default=0.005,
        ge=0.0,
        le=1.0,
        description=(
            "3-class projection's POSSIBLE cut: "
            "``t2_possible_threshold <= overall_score < t1_strong_threshold`` "
            "-> ``'possible'``. **Step 8 lock (2026-05-17):** 0.005 "
            "(down from Step 7's provisional 0.25). Same placeholder-"
            "encoder caveat as ``t1_strong_threshold``. Invariant: "
            "``t2 < t1`` (validated below)."
        ),
    )

    # --- Expansion behavior --------------------------------------------
    enable_expansion: bool = Field(
        default=True,
        description=(
            "Whether Phase A runs the sliding-window expansion stage "
            "at all. Disabling restricts Module 3 to pure re-scoring "
            "of Module 2 candidates -- useful for ablation studies."
        ),
    )
    expansion_window_size: int = Field(
        default=30,
        ge=5,
        le=200,
        description=(
            "Width of the sliding window (in tokens) used by the "
            "expansion stage. Locked at 30 by the Step 4 baseline."
        ),
    )
    expansion_window_stride: int = Field(
        default=15,
        ge=1,
        le=200,
        description=(
            "Stride (in tokens) between successive sliding windows. "
            "Default 15 is the Step 4 amendment-log lock."
        ),
    )

    # --- Determinism & device ------------------------------------------
    seed: int = Field(
        default=42,
        description=(
            "Random seed applied to ``random``, ``numpy``, ``torch`` "
            "and ``transformers.set_seed`` at pipeline construction."
        ),
    )
    device: Device = Field(
        default="auto",
        description=(
            "Compute device. ``\"auto\"`` resolves at runtime."
        ),
    )

    @model_validator(mode="after")
    def _validate_projection_order(self) -> SkillMatcherConfig:
        """Enforce ``t2_possible_threshold < t1_strong_threshold``.

        Without this guard the 3-class projection would collapse to two
        classes (everything below ``t1`` would fall through to ``"no"``).
        Caught at config-construction time so the operator sees a
        clear error before the tuner / Scorer ever runs.
        """
        if self.t2_possible_threshold >= self.t1_strong_threshold:
            raise ValueError(
                "Projection ordering violated: require "
                "t2_possible_threshold < t1_strong_threshold; got "
                f"t1={self.t1_strong_threshold}, "
                f"t2={self.t2_possible_threshold}."
            )
        return self


# Property-style accessor for the implicit nice_weight invariant.
def nice_weight(cfg: SkillMatcherConfig) -> float:
    """Return ``1 - cfg.required_weight``.

    Free function rather than a pydantic computed field so it doesn't
    appear in the env-overridable schema (the operator should set
    ``SKILL_MATCHER_REQUIRED_WEIGHT`` directly; ``nice_weight`` is
    derived).
    """
    return 1.0 - cfg.required_weight


__all__ = ["Device", "SkillMatcherConfig", "nice_weight"]
