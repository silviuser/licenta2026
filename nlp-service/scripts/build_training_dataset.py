"""Build the Module 3 training dataset from the 120 raw training CVs.

This is the **Step 3** end-to-end driver. It turns
``data/training/cvs_raw/train_cv001..120.pdf`` into a deduplicated,
leak-free, weakly-labelled supervised dataset of positive and
hard-negative ``(text_span, esco_uri)`` pairs that Step 5 fine-tunes a
sentence-transformer on.

Pipeline phases
---------------
``A`` Extract     — Module 1 (:class:`cv_extractor.ExtractionPipeline`).
``B`` Dedup       — three tiers (binary SHA-256, text SHA-256, word
                    5-gram Jaccard ≥ 0.85) against the held-out eval
                    corpus at ``tests/fixtures/real_cv1..15.pdf``.
``C`` Skill extract — Module 2 (:class:`skill_extractor.SkillExtractor`).
``D`` Positives   — one :class:`~skill_matcher.dataset.TrainingPair`
                    per ``(URI, span)`` whose Module-2 confidence is
                    at or above ``--min-confidence``.
``E`` Hard negatives — per positive, draw
                    ``--hard-negatives-per-positive`` distractors via
                    the three strategies documented in
                    :mod:`skill_matcher.dataset`.
``F`` Split       — stratified 80/20 by each CV's dominant ESCO L2
                    category; deterministic given the seed.
``G`` Report      — write ``train.jsonl``, ``val.jsonl``,
                    ``stats.json``, ``build_report_<UTC>.md``.

Determinism
-----------
A single ``random.Random(seed)`` instance threads through Phases E
and F. Every glob is wrapped in ``sorted()``. JSONL line order is
controlled by :func:`skill_matcher.dataset._pair_sort_key`. Two
invocations with the same arguments and the same source PDFs produce
byte-identical ``train.jsonl`` / ``val.jsonl`` (modulo the build
timestamp in the header line).

Logging
-------
``structlog`` is used everywhere. Each phase opens and closes with an
``INFO`` event carrying the in/out counts so the build report can
quote them directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from cv_extractor import ExtractionPipeline, ExtractionResult
from cv_extractor.exceptions import CVExtractorError
from skill_extractor import (
    NotACVError,
    SkillExtractionResult,
    SkillExtractor,
    SkillExtractorConfig,
    SkillExtractorError,
    UnsupportedLanguageError,
)
from skill_extractor.esco.loader import EscoLoader
from skill_extractor.overlays.custom import load_custom_overlay
from skill_matcher.context_window import clip_context
from skill_matcher.data.category_map import (
    CUSTOM_CATEGORY_ROOT,
    EscoCategoryMap,
    build_category_map,
)
from skill_matcher.dataset import (
    AnyPair,
    HardNegative,
    NegativeStrategy,
    TrainingDataset,
    TrainingPair,
    compute_pair_id,
    compute_window_pair_id,
    save_training_dataset,
)
from skill_matcher.sliding_window import Window, generate_windows
from skill_matcher.splits import dominant_category, stratified_split

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants and tuning knobs
# ---------------------------------------------------------------------------

# Glob patterns. Both are explicit so an unrelated PDF dropped into
# the directory does not get pulled into the build.
_TRAIN_PDF_GLOB = "train_cv*.pdf"
_EVAL_PDF_GLOB = "real_cv*.pdf"

# Three-tier dedup thresholds.
_JACCARD_THRESHOLD = 0.85
_NGRAM_SIZE = 5  # word 5-grams; see _word_shingles() docstring

# Maximum context-window size on each side of a skill span.
_CONTEXT_WINDOW_CHARS = 50

# Step 5.2 sliding-window parameters. MUST match the values used by the
# Step 4 baseline / Linker at serving time (see
# ``scripts/run_zero_shot_baseline.py`` defaults). If these drift, the
# encoder will be optimised against a different query distribution than
# what serving sees, which is the bug Step 5.2 is meant to fix.
_TRAINING_WINDOW_SIZE_TOKENS = 30
_TRAINING_WINDOW_STRIDE_TOKENS = 15

# Maximum acceptable share of strategy-3 ("random") negatives before
# Sign-Off should be re-examined manually. Surfaced in the build
# report; does NOT abort the build.
_STRATEGY_3_WARNING_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Configuration objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildConfig:
    """All CLI args, frozen so subroutines cannot mutate them."""

    cvs_dir: Path
    eval_fixtures_dir: Path
    out_dir: Path
    min_confidence: float
    hard_negatives_per_positive: int
    val_fraction: float
    seed: int
    resume: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialise as a plain dict for inclusion in the JSONL header."""
        return {
            "cvs_dir": str(self.cvs_dir),
            "eval_fixtures_dir": str(self.eval_fixtures_dir),
            "out_dir": str(self.out_dir),
            "min_confidence": self.min_confidence,
            "hard_negatives_per_positive": self.hard_negatives_per_positive,
            "val_fraction": self.val_fraction,
            "seed": self.seed,
            "resume": self.resume,
        }


# ---------------------------------------------------------------------------
# Phase A — extract
# ---------------------------------------------------------------------------


@dataclass
class _CachedExtraction:
    """Wrapper around a Module 1 :class:`ExtractionResult` carrying the
    extra hashes the dedup phase needs."""

    cv_id: str
    source_pdf: Path
    sha256_pdf: str
    sha256_text: str
    extraction: ExtractionResult


def _sha256_file(path: Path) -> str:
    """SHA-256 of the file's binary contents. Used by dedup tier 1."""
    hasher = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 16), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _sha256_text(text: str) -> str:
    """SHA-256 over the NFC-normalised UTF-8 bytes of ``text``.

    NFC normalisation gives stable hashes across Module 1 versions
    that may differ in how they canonicalise diacritics.
    """
    normalised = unicodedata.normalize("NFC", text)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _phase_a_extract(
    pdf_paths: list[Path],
    cvs_text_dir: Path,
    pipeline: ExtractionPipeline,
    resume: bool,
) -> tuple[list[_CachedExtraction], list[tuple[str, str]]]:
    """Run Module 1 on every PDF. Return surviving extractions + drops.

    Drops are ``(cv_id, reason)`` tuples. Extraction failures and the
    Module-1 "not a CV" warning both count as drops.

    Caching: when ``resume=True`` and ``cvs_text_dir/<cv_id>.json``
    already exists with a matching ``sha256_pdf`` we reuse it.
    """
    cvs_text_dir.mkdir(parents=True, exist_ok=True)

    surviving: list[_CachedExtraction] = []
    drops: list[tuple[str, str]] = []

    logger.info("phaseA.start", n_input=len(pdf_paths))

    for pdf_path in pdf_paths:
        cv_id = pdf_path.stem
        sha_pdf = _sha256_file(pdf_path)
        cache_path = cvs_text_dir / f"{cv_id}.json"

        cached: _CachedExtraction | None = None
        if resume and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                if payload.get("sha256_pdf") == sha_pdf:
                    extraction = ExtractionResult.model_validate(
                        payload["extraction"]
                    )
                    cached = _CachedExtraction(
                        cv_id=cv_id,
                        source_pdf=pdf_path,
                        sha256_pdf=sha_pdf,
                        sha256_text=payload["sha256_text"],
                        extraction=extraction,
                    )
                    logger.info("phaseA.cache_hit", cv_id=cv_id)
            except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(
                    "phaseA.cache_miss_invalid",
                    cv_id=cv_id,
                    error=str(exc),
                )

        if cached is None:
            try:
                extraction = pipeline.process(pdf_path)
            except CVExtractorError as exc:
                logger.warning(
                    "phaseA.extract_failed",
                    cv_id=cv_id,
                    error=str(exc),
                )
                drops.append((cv_id, f"extract_failed:{type(exc).__name__}"))
                continue
            except Exception as exc:  # pragma: no cover — defensive
                logger.error(
                    "phaseA.extract_unexpected_error",
                    cv_id=cv_id,
                    error=str(exc),
                )
                drops.append((cv_id, f"extract_unexpected:{type(exc).__name__}"))
                continue

            sha_text = _sha256_text(extraction.text)
            cached = _CachedExtraction(
                cv_id=cv_id,
                source_pdf=pdf_path,
                sha256_pdf=sha_pdf,
                sha256_text=sha_text,
                extraction=extraction,
            )

            cache_payload = {
                "cv_id": cv_id,
                "source_pdf": str(pdf_path),
                "sha256_pdf": sha_pdf,
                "sha256_text": sha_text,
                "extraction": extraction.model_dump(mode="json"),
            }
            cache_path.write_text(
                json.dumps(cache_payload, ensure_ascii=False),
                encoding="utf-8",
            )

        # Hard filter on Module 1's "not a CV" warning.
        if any(
            w.startswith("Document may not be a CV") for w in cached.extraction.warnings
        ):
            drops.append((cv_id, "not_a_cv"))
            logger.info("phaseA.not_a_cv", cv_id=cv_id)
            continue

        surviving.append(cached)

    logger.info(
        "phaseA.end",
        n_input=len(pdf_paths),
        n_surviving=len(surviving),
        n_dropped=len(drops),
    )
    return surviving, drops


# ---------------------------------------------------------------------------
# Phase B — dedup vs eval
# ---------------------------------------------------------------------------


def _word_shingles(text: str, n: int = _NGRAM_SIZE) -> set[str]:
    """Return the set of word n-grams from ``text``.

    Word-level shingles (rather than character-level) are robust to
    whitespace and capitalisation variation but still sensitive to
    paragraph reordering — which is exactly the property we want for
    "is this a near-duplicate CV?".
    """
    tokens = re.findall(r"\w+", text.lower())
    if len(tokens) < n:
        # Very short documents — collapse into a single-shingle set so
        # they still produce a Jaccard score.
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Set Jaccard similarity. Handles empty sets gracefully."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _phase_b_dedup(
    surviving: list[_CachedExtraction],
    eval_pdfs: list[Path],
    eval_cache_dir: Path,
    pipeline: ExtractionPipeline,
    resume: bool,
) -> tuple[list[_CachedExtraction], list[tuple[str, str, str]]]:
    """Three-tier deduplication against the eval corpus.

    Returns the subset of ``surviving`` that passed all three tiers,
    plus the rejection log as ``(train_cv_id, reason, details)``
    tuples.
    """
    logger.info(
        "phaseB.start",
        n_train=len(surviving),
        n_eval=len(eval_pdfs),
    )

    # ---- Pre-compute eval-side hashes and shingles --------------------
    eval_cache_dir.mkdir(parents=True, exist_ok=True)
    eval_sha_pdf: dict[str, str] = {}     # eval_id -> sha
    eval_sha_text: dict[str, str] = {}    # eval_id -> sha
    eval_shingles: dict[str, set[str]] = {}

    for eval_pdf in eval_pdfs:
        eval_id = eval_pdf.stem
        sha_pdf = _sha256_file(eval_pdf)
        cache_path = eval_cache_dir / f"{eval_id}.json"

        extraction: ExtractionResult | None = None
        if resume and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                if payload.get("sha256_pdf") == sha_pdf:
                    extraction = ExtractionResult.model_validate(payload["extraction"])
            except (OSError, json.JSONDecodeError, KeyError, ValueError):
                extraction = None

        if extraction is None:
            try:
                extraction = pipeline.process(eval_pdf)
            except CVExtractorError as exc:
                # Cannot text-dedup against this eval CV. Tier 1
                # (binary SHA) still runs because the SHA is computed
                # above without reading the PDF interior. Tiers 2 + 3
                # (text SHA, Jaccard) silently skip this eval CV.
                #
                # Why not raise: the canonical failure mode is "OCR
                # needed, Poppler not installed" — a per-environment
                # config issue that should NOT block the build. The
                # contamination risk is mitigated by the fact that the
                # Kaggle training corpus and the eval CVs come from
                # disjoint sources (livecareer.com scrape vs. private
                # LinkedIn scrapes).
                logger.warning(
                    "phaseB.eval_extract_failed_tier1_only",
                    eval_id=eval_id,
                    error=str(exc),
                    note=(
                        "Tier 2 (text SHA) and tier 3 (Jaccard) skipped "
                        "for this eval CV. Tier 1 (binary SHA) still "
                        "active. Install Poppler to recover full dedup."
                    ),
                )
                eval_sha_pdf[eval_id] = sha_pdf
                continue

            cache_path.write_text(
                json.dumps(
                    {
                        "eval_id": eval_id,
                        "sha256_pdf": sha_pdf,
                        "sha256_text": _sha256_text(extraction.text),
                        "extraction": extraction.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        eval_sha_pdf[eval_id] = sha_pdf
        eval_sha_text[eval_id] = _sha256_text(extraction.text)
        eval_shingles[eval_id] = _word_shingles(extraction.text)

    # ---- Run the three tiers against every training CV ---------------
    survivors: list[_CachedExtraction] = []
    rejections: list[tuple[str, str, str]] = []

    eval_sha_pdf_set = set(eval_sha_pdf.values())
    eval_sha_text_set = set(eval_sha_text.values())

    for cached in surviving:
        # Tier 1: binary SHA-256.
        if cached.sha256_pdf in eval_sha_pdf_set:
            match_eval = next(
                eid for eid, h in eval_sha_pdf.items() if h == cached.sha256_pdf
            )
            rejections.append((cached.cv_id, "binary_sha_match", match_eval))
            logger.info(
                "phaseB.tier1_match",
                cv_id=cached.cv_id,
                eval_id=match_eval,
            )
            continue

        # Tier 2: text SHA-256.
        if cached.sha256_text in eval_sha_text_set:
            match_eval = next(
                eid for eid, h in eval_sha_text.items() if h == cached.sha256_text
            )
            rejections.append((cached.cv_id, "text_sha_match", match_eval))
            logger.info(
                "phaseB.tier2_match",
                cv_id=cached.cv_id,
                eval_id=match_eval,
            )
            continue

        # Tier 3: word 5-gram Jaccard ≥ threshold.
        train_shingles = _word_shingles(cached.extraction.text)
        max_score = 0.0
        max_eval_id = ""
        for eval_id, eshingles in eval_shingles.items():
            score = _jaccard(train_shingles, eshingles)
            if score > max_score:
                max_score = score
                max_eval_id = eval_id
        if max_score >= _JACCARD_THRESHOLD:
            rejections.append(
                (
                    cached.cv_id,
                    "jaccard_near_dup",
                    f"{max_eval_id}:{max_score:.3f}",
                )
            )
            logger.info(
                "phaseB.tier3_match",
                cv_id=cached.cv_id,
                eval_id=max_eval_id,
                score=round(max_score, 3),
            )
            continue

        survivors.append(cached)

    logger.info(
        "phaseB.end",
        n_train=len(surviving),
        n_surviving=len(survivors),
        n_rejected=len(rejections),
    )
    return survivors, rejections


# ---------------------------------------------------------------------------
# Phase C — Module 2 skill extraction
# ---------------------------------------------------------------------------


def _phase_c_skill_extract(
    survivors: list[_CachedExtraction],
    cv_skills_dir: Path,
    extractor: SkillExtractor,
    resume: bool,
) -> dict[str, SkillExtractionResult]:
    """Run Module 2 on every surviving CV.

    Persists the full :class:`SkillExtractionResult` JSON dump to
    ``cv_skills_dir/<cv_id>.json`` for traceability.
    """
    cv_skills_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, SkillExtractionResult] = {}

    logger.info("phaseC.start", n=len(survivors))

    for cached in survivors:
        cache_path = cv_skills_dir / f"{cached.cv_id}.json"

        result: SkillExtractionResult | None = None
        if resume and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                if payload.get("sha256_text") == cached.sha256_text:
                    result = SkillExtractionResult.model_validate(
                        payload["skill_result"]
                    )
                    logger.info("phaseC.cache_hit", cv_id=cached.cv_id)
            except (OSError, json.JSONDecodeError, KeyError, ValueError):
                result = None

        if result is None:
            try:
                result = extractor.extract(cached.extraction)
            except (NotACVError, UnsupportedLanguageError) as exc:
                logger.warning(
                    "phaseC.skipped",
                    cv_id=cached.cv_id,
                    reason=type(exc).__name__,
                )
                continue
            except SkillExtractorError as exc:
                logger.error(
                    "phaseC.extract_failed",
                    cv_id=cached.cv_id,
                    error=str(exc),
                )
                continue

            cache_path.write_text(
                json.dumps(
                    {
                        "cv_id": cached.cv_id,
                        "sha256_text": cached.sha256_text,
                        "skill_result": result.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        results[cached.cv_id] = result

    logger.info("phaseC.end", n_input=len(survivors), n_output=len(results))
    return results


# ---------------------------------------------------------------------------
# Phase D — positives
# ---------------------------------------------------------------------------


@dataclass
class _PositiveContext:
    """Internal carrier used by Phase E to look up paired-positive info."""

    positive: TrainingPair
    cv_text: str
    dominant_l2: str


def _windows_containing_span(
    windows: list[Window], span_start: int, span_end: int
) -> list[Window]:
    """Return every window whose ``[start, end)`` covers the span.

    Step 5.2 — used to emit one training pair per (span, window) combo so
    the encoder sees the span in every contextual window the Linker
    would generate at serving time.

    If no window strictly covers the span (rare; happens when a span
    straddles a stride boundary at the very edge of the text), returns
    the single nearest window so we never silently drop a positive.
    """
    covering = [w for w in windows if w.start <= span_start and w.end >= span_end]
    if covering:
        return covering
    if not windows:
        return []
    # Fallback: nearest window by char-offset distance to the span start.
    nearest = min(windows, key=lambda w: abs(w.start - span_start))
    return [nearest]


def _phase_d_positives(
    survivors: list[_CachedExtraction],
    skill_results: dict[str, SkillExtractionResult],
    min_confidence: float,
) -> list[_PositiveContext]:
    """Emit one :class:`TrainingPair` per ``(URI, span, window)`` occurrence.

    Step 5.2 redesign — for each Module-2 ``SkillMatch`` span, we now
    look up every sliding window that contains it (size 30 tokens,
    stride 15) and emit one positive pair per (span, window) combo.
    The pair's :attr:`TrainingPair.query_text` carries the **exact**
    window text, identical to what
    :func:`skill_matcher.sliding_window.generate_windows` produces at
    serving time. This closes the train/serve task mismatch that
    caused the Phase Gamma regression (Step 5 round 1: val MRR@10 0.44 ->
    eval F1 0.144).

    The legacy ``context_before`` / ``text_span`` / ``context_after``
    fields are still populated for traceability and for
    backward-compat with downstream consumers that haven't migrated to
    ``query_text``.

    Returns a list of :class:`_PositiveContext` wrappers carrying both
    the pair and ancillary info Phase E needs (the CV text for span
    look-ups, and a placeholder for the dominant-L2 we will fill in
    Phase F).
    """
    cv_by_id = {c.cv_id: c for c in survivors}
    positives: list[_PositiveContext] = []

    logger.info(
        "phaseD.start",
        n_cvs=len(survivors),
        min_confidence=min_confidence,
        window_size_tokens=_TRAINING_WINDOW_SIZE_TOKENS,
        window_stride_tokens=_TRAINING_WINDOW_STRIDE_TOKENS,
    )

    n_skills_seen = 0
    n_window_pairs = 0
    n_spans_without_window = 0
    for cv_id, sk_result in skill_results.items():
        cached = cv_by_id[cv_id]
        cv_text = cached.extraction.text

        # Pre-compute sliding windows once per CV (~ms).
        windows = generate_windows(
            cv_text,
            window_size_tokens=_TRAINING_WINDOW_SIZE_TOKENS,
            stride_tokens=_TRAINING_WINDOW_STRIDE_TOKENS,
        )

        for skill in sk_result.skills:
            n_skills_seen += 1
            if skill.confidence < min_confidence:
                continue
            for span_start, span_end in skill.spans:
                # Defensive: spans should always be valid by Module 2's
                # validator, but the text may have been re-extracted
                # between cache writes.
                if span_end > len(cv_text):
                    logger.warning(
                        "phaseD.span_out_of_range",
                        cv_id=cv_id,
                        span=(span_start, span_end),
                        text_len=len(cv_text),
                    )
                    continue
                text_span = cv_text[span_start:span_end]
                if not text_span.strip():
                    continue

                covering = _windows_containing_span(windows, span_start, span_end)
                if not covering:
                    # Empty CV / no windows generated. Skip silently.
                    n_spans_without_window += 1
                    continue

                # Legacy context fields populated once per span; they
                # describe the span itself, not the windows.
                context = clip_context(
                    cv_text, span_start, span_end, max_chars=_CONTEXT_WINDOW_CHARS
                )

                for window in covering:
                    query_text = cv_text[window.start:window.end]
                    pair_id = compute_window_pair_id(
                        cv_id=cv_id,
                        window_start=window.start,
                        window_end=window.end,
                        span_start=span_start,
                        span_end=span_end,
                        esco_uri=skill.esco_uri,
                        pair_type="positive",
                    )
                    pair = TrainingPair(
                        pair_id=pair_id,
                        cv_id=cv_id,
                        text_span=text_span,
                        span_start=span_start,
                        span_end=span_end,
                        context_before=context.before,
                        context_after=context.after,
                        query_text=query_text,
                        window_start=window.start,
                        window_end=window.end,
                        esco_uri=skill.esco_uri,
                        surface_form=skill.matched_text,
                        section=skill.section,
                        language=sk_result.language,
                        module2_confidence=skill.confidence,
                    )
                    positives.append(
                        _PositiveContext(
                            positive=pair,
                            cv_text=cv_text,
                            dominant_l2="",
                        )
                    )
                    n_window_pairs += 1

    logger.info(
        "phaseD.end",
        n_skills_seen=n_skills_seen,
        n_positives=len(positives),
        n_window_pairs=n_window_pairs,
        n_spans_without_window=n_spans_without_window,
    )
    return positives


# ---------------------------------------------------------------------------
# Phase E — hard negatives
# ---------------------------------------------------------------------------


@dataclass
class _FPCatalogueEntry:
    span_lemma: str
    wrong_uri: str
    family: str
    reason: str


def _load_fp_catalogue(path: Path) -> list[_FPCatalogueEntry]:
    """Parse ``known_false_positives.yaml`` into a list of entries."""
    if not path.exists():
        logger.warning("phaseE.fp_catalogue_missing", path=str(path))
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries: list[_FPCatalogueEntry] = []
    for row in raw.get("entries", []):
        entries.append(
            _FPCatalogueEntry(
                span_lemma=str(row["span_lemma"]),
                wrong_uri=str(row["wrong_uri"]),
                family=str(row.get("family", "unknown")),
                reason=str(row.get("reason", "")),
            )
        )
    logger.info("phaseE.fp_catalogue_loaded", n_entries=len(entries))
    return entries


def _select_fp_distractor(
    positive: TrainingPair,
    catalogue: list[_FPCatalogueEntry],
    rng: random.Random,
) -> tuple[str, str] | None:
    """Pick one FP-catalogue distractor for the given positive.

    Returns ``(wrong_uri, reason)`` or ``None`` if no entry matches.
    Matching is case-insensitive on ``span_lemma`` against the positive's
    surface form.
    """
    surface_lower = positive.surface_form.lower()
    text_span_lower = positive.text_span.lower()
    candidates = [
        e
        for e in catalogue
        if (
            e.span_lemma.lower() == surface_lower
            or e.span_lemma.lower() == text_span_lower
        )
        and e.wrong_uri != positive.esco_uri
    ]
    if not candidates:
        return None
    chosen = rng.choice(candidates)
    return (
        chosen.wrong_uri,
        f"FP family '{chosen.family}': {chosen.reason}",
    )


def _select_category_sibling(
    positive: TrainingPair,
    category_map: EscoCategoryMap,
    rng: random.Random,
) -> tuple[str, str] | None:
    """Pick a sibling-URI distractor under the same L2 ancestor."""
    siblings = category_map.siblings(positive.esco_uri)
    if not siblings:
        return None
    chosen = rng.choice(siblings)
    ancestor = category_map.uri_to_l2.get(positive.esco_uri, "")
    if ancestor == CUSTOM_CATEGORY_ROOT:
        reason = "sibling under synthetic CUST: category"
    else:
        reason = f"sibling under L2 ancestor {ancestor}"
    return chosen, reason


def _phase_e_hard_negatives(
    positives_ctx: list[_PositiveContext],
    category_map: EscoCategoryMap,
    fp_catalogue: list[_FPCatalogueEntry],
    full_uri_universe: list[str],
    n_per_positive: int,
    rng: random.Random,
) -> list[HardNegative]:
    """Generate hard negatives for every positive.

    Strategy mix per positive:

    1. Attempt strategy 1 (same-category sibling). If a sibling exists,
       always include at least one strategy-1 negative.
    2. Attempt strategy 2 (FP catalogue). If it matches, always include
       at least one strategy-2 negative.
    3. Fill remaining slots with strategy 1 first, then strategy 3
       (random) only if strategy 1 and 2 are both exhausted.
    """
    if n_per_positive < 1:
        return []

    negatives: list[HardNegative] = []

    # Step 5.2 — dedupe by (cv, span, uri) before mining. With the
    # sliding-window positives a single span produces N positives (one
    # per containing window), but hard negatives don't need to be
    # multiplied: same distractor URIs apply regardless of which window
    # contains the span. Mining 3 negatives per *unique span* preserves
    # the strategy distribution from Step 5 round 1 (~10k negatives)
    # instead of letting it inflate to 3 * N_windows * N_positives.
    seen_spans: set[tuple[str, int, int, str]] = set()
    deduped_positives: list[_PositiveContext] = []
    for pctx in positives_ctx:
        span_key = (
            pctx.positive.cv_id,
            pctx.positive.span_start,
            pctx.positive.span_end,
            pctx.positive.esco_uri,
        )
        if span_key in seen_spans:
            continue
        seen_spans.add(span_key)
        deduped_positives.append(pctx)

    logger.info(
        "phaseE.start",
        n_positives=len(positives_ctx),
        n_unique_spans=len(deduped_positives),
        n_per_positive=n_per_positive,
    )

    strategy_counter: Counter[NegativeStrategy] = Counter()

    for pctx in deduped_positives:
        positive = pctx.positive
        picked: list[tuple[str, str, NegativeStrategy]] = []

        # Anchor strategy 2 if available (highest anti-error signal).
        fp_pick = _select_fp_distractor(positive, fp_catalogue, rng)
        if fp_pick is not None:
            picked.append((fp_pick[0], fp_pick[1], "module2_fp_catalogue"))

        # Anchor strategy 1.
        cat_pick = _select_category_sibling(positive, category_map, rng)
        if cat_pick is not None:
            picked.append((cat_pick[0], cat_pick[1], "same_category_esco"))

        # Fill remaining slots — prefer additional strategy 1 picks,
        # fall through to strategy 3 only as a last resort.
        already_chosen_uris = {p[0] for p in picked}
        while len(picked) < n_per_positive:
            siblings = [
                s
                for s in category_map.siblings(positive.esco_uri)
                if s not in already_chosen_uris
            ]
            if siblings:
                chosen = rng.choice(siblings)
                ancestor = category_map.uri_to_l2.get(positive.esco_uri, "")
                reason = (
                    "sibling under synthetic CUST: category"
                    if ancestor == CUSTOM_CATEGORY_ROOT
                    else f"sibling under L2 ancestor {ancestor}"
                )
                picked.append((chosen, reason, "same_category_esco"))
                already_chosen_uris.add(chosen)
                continue

            # Strategy 3 fallback — random URI different from the positive.
            fallback = rng.choice(full_uri_universe)
            tries = 0
            while (
                fallback in already_chosen_uris or fallback == positive.esco_uri
            ) and tries < 16:
                fallback = rng.choice(full_uri_universe)
                tries += 1
            picked.append(
                (fallback, "random fallback from full ESCO ∪ CUST universe", "random_in_corpus")  # noqa: RUF001
            )
            already_chosen_uris.add(fallback)

        # Truncate just in case we over-picked.
        for wrong_uri, reason, strategy in picked[:n_per_positive]:
            hn_pair_id = compute_pair_id(
                cv_id=positive.cv_id,
                span_start=positive.span_start,
                span_end=positive.span_end,
                esco_uri=wrong_uri,
                pair_type="hard_negative",
            )
            negatives.append(
                HardNegative(
                    pair_id=hn_pair_id,
                    cv_id=positive.cv_id,
                    text_span=positive.text_span,
                    span_start=positive.span_start,
                    span_end=positive.span_end,
                    context_before=positive.context_before,
                    context_after=positive.context_after,
                    esco_uri=wrong_uri,
                    surface_form=positive.surface_form,
                    section=positive.section,
                    language=positive.language,
                    module2_confidence=positive.module2_confidence,
                    negative_strategy=strategy,
                    paired_with_positive_id=positive.pair_id,
                    distractor_reason=reason,
                )
            )
            strategy_counter[strategy] += 1

    logger.info(
        "phaseE.end",
        n_negatives=len(negatives),
        strategy_distribution=dict(strategy_counter),
    )
    return negatives


# ---------------------------------------------------------------------------
# Phase F — stratified split
# ---------------------------------------------------------------------------


def _compute_dominant_l2(
    skill_result: SkillExtractionResult,
    category_map: EscoCategoryMap,
) -> str:
    """Return the L2 ancestor with the most matches in this CV.

    Thin wrapper around :func:`skill_matcher.splits.dominant_category`
    that adapts the Module-2 result shape (a
    :class:`SkillExtractionResult` carrying a list of ``SkillMatch``).
    """
    return dominant_category(
        skill_uris=[m.esco_uri for m in skill_result.skills],
        uri_to_category=category_map.uri_to_l2,
    )


# ---------------------------------------------------------------------------
# Phase G — write outputs
# ---------------------------------------------------------------------------


def _phase_g_write(
    out_dir: Path,
    config: BuildConfig,
    timestamp: datetime,
    train_pairs: list[AnyPair],
    val_pairs: list[AnyPair],
    train_cv_ids: set[str],
    val_cv_ids: set[str],
    excluded_log: list[tuple[str, str, str]],
    stats: dict[str, Any],
) -> tuple[Path, Path, Path, Path]:
    """Materialise all of Step 3's output files."""
    pairs_dir = out_dir / "pairs"
    pairs_dir.mkdir(parents=True, exist_ok=True)

    train_path = pairs_dir / "train.jsonl"
    val_path = pairs_dir / "val.jsonl"
    stats_path = pairs_dir / "stats.json"
    report_path = (
        out_dir / f"build_report_{timestamp.strftime('%Y%m%d_%H%M%S')}.md"
    )

    save_training_dataset(
        TrainingDataset(
            pairs=train_pairs,
            split="train",
            build_timestamp=timestamp,
            build_config=config.to_dict(),
            total_cvs_processed=len(train_cv_ids),
            total_cvs_excluded=0,
        ),
        train_path,
    )
    save_training_dataset(
        TrainingDataset(
            pairs=val_pairs,
            split="val",
            build_timestamp=timestamp,
            build_config=config.to_dict(),
            total_cvs_processed=len(val_cv_ids),
            total_cvs_excluded=0,
        ),
        val_path,
    )

    stats_path.write_text(
        json.dumps(stats, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # Excluded log is amended (not overwritten) so multi-run audits are
    # preserved; we still seed a "run started at" line so the reader
    # can identify which rows belong to which build.
    excluded_path = out_dir / "dedup_excluded.txt"
    with excluded_path.open("a", encoding="utf-8") as fp:
        fp.write(f"# --- run @ {timestamp.isoformat()} ---\n")
        for cv_id, reason, details in excluded_log:
            fp.write(f"{cv_id},{reason},{details}\n")

    _write_build_report(report_path, config, timestamp, stats)

    return train_path, val_path, stats_path, report_path


def _write_build_report(
    path: Path,
    config: BuildConfig,
    timestamp: datetime,
    stats: dict[str, Any],
) -> None:
    """Render the per-run Markdown build report."""
    lines: list[str] = []
    lines.append(f"# Training-dataset build — {timestamp.isoformat()}")
    lines.append("")
    lines.append("## Invocation")
    lines.append("")
    lines.append("```powershell")
    lines.append(
        "python scripts\\build_training_dataset.py "
        + " ".join(f"--{k.replace('_', '-')} {v}" for k, v in config.to_dict().items())
    )
    lines.append("```")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    for key, value in sorted(stats.items()):
        if isinstance(value, (int, float, str, bool)):
            lines.append(f"- **{key}**: {value}")
    lines.append("")
    if "strategy_distribution" in stats:
        lines.append("## Hard-negative strategy distribution")
        lines.append("")
        for strategy, count in sorted(stats["strategy_distribution"].items()):
            lines.append(f"- `{strategy}`: {count}")
        lines.append("")
    if "language_distribution" in stats:
        lines.append("## Language distribution (positives)")
        lines.append("")
        for lang, count in sorted(stats["language_distribution"].items()):
            lines.append(f"- `{lang}`: {count}")
        lines.append("")
    if "section_distribution" in stats:
        lines.append("## Section distribution (positives)")
        lines.append("")
        for section, count in sorted(stats["section_distribution"].items()):
            lines.append(f"- `{section}`: {count}")
        lines.append("")
    if "top_l2_categories" in stats:
        lines.append("## Top-20 ESCO L2 categories (positives)")
        lines.append("")
        for category, count in stats["top_l2_categories"]:
            lines.append(f"- `{category}`: {count}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def build(config: BuildConfig) -> dict[str, Any]:
    """Run all phases end-to-end. Return the stats dict for the report."""
    rng = random.Random(config.seed)
    timestamp = datetime.now(tz=UTC)

    cvs_text_dir = config.out_dir / "cvs_text"
    cv_skills_dir = config.out_dir / "cv_skills"
    eval_cache_dir = cvs_text_dir / "_eval_cache"

    pdf_paths = sorted(config.cvs_dir.glob(_TRAIN_PDF_GLOB))
    eval_pdfs = sorted(
        (config.eval_fixtures_dir).glob(_EVAL_PDF_GLOB)
    )

    if not pdf_paths:
        raise FileNotFoundError(
            f"No training PDFs found under {config.cvs_dir} (pattern "
            f"{_TRAIN_PDF_GLOB})."
        )
    if not eval_pdfs:
        raise FileNotFoundError(
            f"No eval PDFs found under {config.eval_fixtures_dir} (pattern "
            f"{_EVAL_PDF_GLOB})."
        )

    pipeline = ExtractionPipeline()
    extractor = SkillExtractor()

    # --- Phases A and B ----------------------------------------------------
    a_survivors, a_drops = _phase_a_extract(
        pdf_paths, cvs_text_dir, pipeline, config.resume
    )
    b_survivors, b_rejections = _phase_b_dedup(
        a_survivors, eval_pdfs, eval_cache_dir, pipeline, config.resume
    )

    excluded_log: list[tuple[str, str, str]] = []
    for cv_id, reason in a_drops:
        excluded_log.append((cv_id, reason, ""))
    for row in b_rejections:
        excluded_log.append(row)

    # --- Phase C ----------------------------------------------------------
    skill_results = _phase_c_skill_extract(
        b_survivors, cv_skills_dir, extractor, config.resume
    )

    # --- Build the ESCO category map (uses Module 2's ESCO loader path) --
    esco_config = SkillExtractorConfig()
    custom_overlay = load_custom_overlay(esco_config.custom_concepts_path)
    custom_uris = [c.concept_uri for c in custom_overlay.concepts]
    category_map = build_category_map(esco_config.esco_dir, custom_uris)

    # Full ESCO + CUST URI universe (set union) — used by strategy 3.
    esco_skills = EscoLoader(esco_config).load()
    full_uri_universe = sorted({s.concept_uri for s in esco_skills} | set(custom_uris))

    # --- Phase D ----------------------------------------------------------
    positives_ctx = _phase_d_positives(
        b_survivors, skill_results, config.min_confidence
    )

    # --- Phase E ----------------------------------------------------------
    fp_catalogue = _load_fp_catalogue(
        config.out_dir / "known_false_positives.yaml"
    )
    negatives = _phase_e_hard_negatives(
        positives_ctx,
        category_map,
        fp_catalogue,
        full_uri_universe,
        config.hard_negatives_per_positive,
        rng,
    )

    # --- Phase F — stratified split --------------------------------------
    cv_to_l2 = {
        cv_id: _compute_dominant_l2(sk, category_map)
        for cv_id, sk in skill_results.items()
    }
    contributing_cv_ids = sorted({p.positive.cv_id for p in positives_ctx})
    train_cvs, val_cvs = stratified_split(
        contributing_cv_ids, cv_to_l2, config.val_fraction, rng
    )

    train_pairs: list[AnyPair] = []
    val_pairs: list[AnyPair] = []
    for pctx in positives_ctx:
        if pctx.positive.cv_id in val_cvs:
            val_pairs.append(pctx.positive)
        else:
            train_pairs.append(pctx.positive)
    for neg in negatives:
        if neg.cv_id in val_cvs:
            val_pairs.append(neg)
        else:
            train_pairs.append(neg)

    # --- Phase G — stats + report -----------------------------------------
    positives_only = [p.positive for p in positives_ctx]
    language_distribution = Counter(p.language for p in positives_only)
    section_distribution = Counter(p.section for p in positives_only)
    l2_distribution = Counter(
        category_map.uri_to_l2.get(p.esco_uri, "") for p in positives_only
    )
    strategy_distribution = Counter(n.negative_strategy for n in negatives)

    n_pos = len(positives_only)
    n_neg = len(negatives)
    stats: dict[str, Any] = {
        "build_timestamp": timestamp.isoformat(),
        "n_input_pdfs": len(pdf_paths),
        "n_excluded_phaseA": len(a_drops),
        "n_excluded_phaseB": len(b_rejections),
        "n_surviving_cvs": len(b_survivors),
        "n_cvs_contributing_positives": len(contributing_cv_ids),
        "n_positives": n_pos,
        "n_hard_negatives": n_neg,
        "neg_to_pos_ratio": round(n_neg / n_pos, 3) if n_pos else 0,
        "n_train_pairs": len(train_pairs),
        "n_val_pairs": len(val_pairs),
        "n_train_cvs": len(train_cvs),
        "n_val_cvs": len(val_cvs),
        "strategy_3_share": round(
            strategy_distribution["random_in_corpus"] / max(n_neg, 1), 3
        ),
        "strategy_3_warning_threshold": _STRATEGY_3_WARNING_THRESHOLD,
        "strategy_distribution": dict(strategy_distribution),
        "language_distribution": dict(language_distribution),
        "section_distribution": dict(section_distribution),
        "top_l2_categories": l2_distribution.most_common(20),
        "config": config.to_dict(),
    }

    train_path, val_path, stats_path, report_path = _phase_g_write(
        config.out_dir,
        config,
        timestamp,
        train_pairs,
        val_pairs,
        train_cvs,
        val_cvs,
        excluded_log,
        stats,
    )
    stats["train_jsonl_path"] = str(train_path)
    stats["val_jsonl_path"] = str(val_path)
    stats["stats_json_path"] = str(stats_path)
    stats["build_report_path"] = str(report_path)

    logger.info(
        "build.done",
        n_positives=n_pos,
        n_hard_negatives=n_neg,
        report=str(report_path),
    )
    return stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> BuildConfig:
    parser = argparse.ArgumentParser(
        description="Build the Module 3 training dataset (Step 3).",
    )
    parser.add_argument("--cvs-dir", type=Path, required=True)
    parser.add_argument("--eval-fixtures-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument("--hard-negatives-per-positive", type=int, default=3)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true")
    ns = parser.parse_args(argv)
    return BuildConfig(
        cvs_dir=ns.cvs_dir.resolve(),
        eval_fixtures_dir=ns.eval_fixtures_dir.resolve(),
        out_dir=ns.out_dir.resolve(),
        min_confidence=float(ns.min_confidence),
        hard_negatives_per_positive=int(ns.hard_negatives_per_positive),
        val_fraction=float(ns.val_fraction),
        seed=int(ns.seed),
        resume=bool(ns.resume),
    )


def main(argv: list[str] | None = None) -> int:
    """Script entry point. Returns the process exit code."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ]
    )
    config = _parse_args(sys.argv[1:] if argv is None else argv)
    t0 = time.monotonic()
    stats = build(config)
    duration_s = time.monotonic() - t0
    logger.info("build.elapsed_seconds", value=round(duration_s, 1))
    print(json.dumps(stats, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover — script entry point
    raise SystemExit(main())
