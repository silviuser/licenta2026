"""Convert Step 3 :class:`TrainingDataset` rows into SBERT-ready examples.

This module is the **deterministic glue** between the Step 3 JSONL on
disk and the sentence-transformers training loop that runs inside the
Step 5 Colab notebook.

It is intentionally **framework-free**:

* No ``torch``, no ``sentence_transformers``, no ``transformers`` imports.
* Pure-Python dataclasses + stdlib JSON only.

Why: the same module is bundled and copied into the Colab environment
by ``scripts/pack_colab_bundle.py`` and imported by the notebook. Keeping
it free of heavy dependencies means the Colab side can ``import
training_data`` without having to pip-install the full ``skill_matcher``
package. Local unit tests can also exercise the converter on a CPU box
with no GPU stack installed.

Train / eval text parity (the non-negotiable contract)
------------------------------------------------------
* Anchor text (the **CV side**) is built once here, by
  :func:`build_anchor_text`. The same formula is used by the future
  :class:`Linker` at inference time (see Step 6) — so the encoder sees
  the same string-shape at train, eval and serve time.
* Positive text (the **ESCO side**) is built by
  :func:`build_positive_text_from_uri`, which delegates to
  :func:`skill_matcher.esco_index.format_concept_text` with the locked
  ``"bounded-a"`` format. **Reusing** that function — rather than
  re-implementing it here — guarantees that the fine-tuned encoder
  optimises against the exact same text distribution as the ESCO index
  it will be queried against (Step 4 §2.6 of the Pre-Flight).

Two emit modes
--------------
* ``"pairs_mnrl"`` — one ``(anchor, positive)`` example per
  :class:`TrainingPair`. Designed for
  ``sentence_transformers.losses.MultipleNegativesRankingLoss``, which
  draws its negatives from other positives in the same mini-batch. The
  step-3 mined hard negatives are **not** emitted in this mode; they
  re-enter the training signal indirectly via batch sampling.
* ``"triplets"`` — one ``(anchor, positive, negative)`` example per
  :class:`HardNegative`. Designed for
  ``sentence_transformers.losses.TripletLoss``. Each row consumes the
  hard negative explicitly. Reserved for the ablation fallback if MNRL
  underperforms — see Step 5 Pre-Flight §3.

Determinism
-----------
:func:`prepare_sbert_examples` returns the result list sorted by
``(cv_id, span_start, span_end, pair_kind, positive_uri,
negative_uri_or_empty)`` so two invocations on identical inputs produce
identical lists. Shuffling is delegated to the caller (so the seeded
shuffle inside the notebook owns the only stochastic step in the data
path).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import structlog

from skill_matcher.dataset import (
    AnyPair,
    HardNegative,
    TrainingDataset,
    TrainingPair,
)
from skill_matcher.esco_index import format_concept_text
from skill_matcher.esco_loader import EscoConcept

logger = structlog.get_logger(__name__)


# Hard upper bound on the joined anchor string (``context_before +
# text_span + context_after``). Step 3 clips each side of the context
# window to ~50 chars at a sentence boundary, so the typical anchor lands
# around 100-150 chars. The 256-char cap is defensive against a future
# Step 3 loosening of the context cap — it stops a runaway long anchor
# from quietly poisoning a batch, fail-loud only via the warning log if
# truncation actually fires.
#
# Promoted from a module-private constant to a public symbol in Step 6
# so :class:`skill_matcher.linker.Linker` can reuse the exact same
# numeric cap when it builds inference-time anchors. Sharing the
# constant means any future change to the training-time anchor length
# is automatically tracked at serving time — drift becomes impossible.
ANCHOR_HARD_CAP_CHARS = 256


# Concept-text format used on the ESCO side of every training pair.
# Locked to ``"bounded-a"`` because that is the format the Step 4
# zero-shot baseline indexed against (DECISIONS.md amendment-log row
# from 2026-05-16). Any divergence here would mean the fine-tuned
# encoder optimises against a text distribution different from the
# index it will be queried against → systematic drift.
_POSITIVE_CONCEPT_FORMAT: Literal["bounded-a"] = "bounded-a"


SBERTMode = Literal["pairs_mnrl", "triplets"]
"""Which kind of example to emit.

* ``"pairs_mnrl"`` → list of ``(anchor, positive)`` pairs, one per
  :class:`TrainingPair`.
* ``"triplets"`` → list of ``(anchor, positive, negative)`` triplets,
  one per :class:`HardNegative` (so one positive can spawn 0-N triplets).
"""


@dataclass(frozen=True, slots=True)
class SBERTExample:
    """A single training row ready to be wrapped in :class:`InputExample`.

    ``frozen=True`` because the list returned by
    :func:`prepare_sbert_examples` is hashed in unit tests (determinism
    assertion); ``slots=True`` for cheap construction at 10 000+ rows.

    Attributes
    ----------
    texts
        For ``pair_kind="pair"``: ``[anchor, positive]``.
        For ``pair_kind="triplet"``: ``[anchor, positive, negative]``.
    label
        ``None`` for ranking losses (MNRL, TripletLoss). Reserved for a
        future regression-style loss; not set by this module.
    pair_kind
        Discriminator. Must agree with ``len(texts)``.
    cv_id
        Source CV identifier. Carried for traceability and for
        ablation-style filtering at the notebook level; the training
        loop ignores it.
    positive_uri
        ESCO URI of the labelled positive concept for this row.
        Traceability only.
    negative_uri
        ESCO URI of the hard-negative concept for triplets; ``None`` for
        ``pair_kind="pair"`` rows.
    """

    texts: tuple[str, ...]
    label: float | None
    pair_kind: Literal["pair", "triplet"]
    cv_id: str
    positive_uri: str
    negative_uri: str | None


# ---------------------------------------------------------------------------
# Text builders
# ---------------------------------------------------------------------------


def build_anchor_text(pair: AnyPair) -> str:
    """Build the CV-side anchor string for a training pair.

    Two modes, selected automatically per pair:

    1. **Sliding-window mode** (Step 5.2 onwards): when ``pair.query_text``
       is non-empty, it is the *exact* output of
       :func:`skill_matcher.sliding_window.generate_windows` for the
       window containing this pair's matched span. Used verbatim as the
       anchor — train and serve see identical query shapes.
    2. **Legacy anchor mode** (Step 5 round 1): when ``pair.query_text``
       is empty (older JSONL files), fall back to
       ``(context_before + text_span + context_after).strip()``. Kept
       so older datasets remain loadable for ablation comparison.

    Both modes cap the result at :data:`ANCHOR_HARD_CAP_CHARS` (256)
    chars — defensive against a future Step-3 loosening of either
    context window or sliding-window cap.
    """
    if pair.query_text:
        # Sliding-window mode. Strip leading/trailing whitespace because
        # `generate_windows` returns the original text slice including
        # any prefix/suffix whitespace at the window boundary.
        text = pair.query_text.strip()
    else:
        # Legacy anchor mode — Step 5 round 1 dataset shape.
        text = f"{pair.context_before}{pair.text_span}{pair.context_after}".strip()

    if len(text) > ANCHOR_HARD_CAP_CHARS:
        logger.warning(
            "training_data.anchor_truncated",
            cv_id=pair.cv_id,
            span_start=pair.span_start,
            span_end=pair.span_end,
            original_length=len(text),
            cap=ANCHOR_HARD_CAP_CHARS,
            mode="query_text" if pair.query_text else "legacy_anchor",
        )
        text = text[:ANCHOR_HARD_CAP_CHARS]
    return text


def build_positive_text_from_uri(
    uri: str, concepts_by_uri: dict[str, EscoConcept]
) -> str | None:
    """Render the bounded-a concept text for the given ESCO ``uri``.

    Delegates to :func:`skill_matcher.esco_index.format_concept_text` so
    the same code path that built the Step 4 ESCO index builds the
    positive side of every training pair. This is the train / eval
    parity guarantee.

    Parameters
    ----------
    uri
        ESCO URI (``http://data.europa.eu/esco/skill/...``) or custom
        overlay URI (``CUST:...``).
    concepts_by_uri
        Mapping from URI to :class:`EscoConcept`, typically produced by
        ``{c.uri: c for c in load_esco_concepts()}``.

    Returns
    -------
    str | None
        The rendered concept text, or ``None`` if ``uri`` is not in
        ``concepts_by_uri``. Caller is expected to log + skip in the
        ``None`` case rather than crashing the build.
    """
    concept = concepts_by_uri.get(uri)
    if concept is None:
        return None
    return format_concept_text(concept, _POSITIVE_CONCEPT_FORMAT)


# ---------------------------------------------------------------------------
# Pair → SBERTExample
# ---------------------------------------------------------------------------


def _negatives_by_positive_id(
    pairs: list[AnyPair],
) -> dict[str, list[HardNegative]]:
    """Group hard negatives by their ``paired_with_positive_id``.

    Single pass over the pair list, O(N). The returned mapping's value
    lists are sorted by ``(span_start, esco_uri)`` so triplet emission
    order is deterministic.
    """
    grouped: dict[str, list[HardNegative]] = defaultdict(list)
    for p in pairs:
        if isinstance(p, HardNegative):
            grouped[p.paired_with_positive_id].append(p)
    # Sort each bucket for determinism.
    for key in grouped:
        grouped[key].sort(key=lambda n: (n.span_start, n.esco_uri))
    return grouped


def _emit_pair_example(
    positive: TrainingPair,
    concepts_by_uri: dict[str, EscoConcept],
) -> SBERTExample | None:
    """Build one ``(anchor, positive)`` :class:`SBERTExample`, or ``None``.

    ``None`` is returned (and the miss is logged) when the positive's
    ``esco_uri`` is absent from ``concepts_by_uri`` — i.e. the ESCO
    bundle at training time no longer carries this URI. This is rare in
    practice (Module 2's labels are drawn from the same ESCO source
    used for the index) but we keep the build robust to a future ESCO
    refresh.
    """
    positive_text = build_positive_text_from_uri(positive.esco_uri, concepts_by_uri)
    if positive_text is None:
        logger.warning(
            "training_data.positive_uri_unknown",
            cv_id=positive.cv_id,
            esco_uri=positive.esco_uri,
            pair_id=positive.pair_id,
        )
        return None
    anchor_text = build_anchor_text(positive)
    return SBERTExample(
        texts=(anchor_text, positive_text),
        label=None,
        pair_kind="pair",
        cv_id=positive.cv_id,
        positive_uri=positive.esco_uri,
        negative_uri=None,
    )


def _emit_triplet_examples(
    positive: TrainingPair,
    negatives: list[HardNegative],
    concepts_by_uri: dict[str, EscoConcept],
) -> list[SBERTExample]:
    """Build one ``(anchor, positive, negative)`` row per hard negative.

    Skips (with a structured warning) any negative whose ``esco_uri``
    is absent from ``concepts_by_uri``. Returns an empty list when no
    triplet could be emitted for this positive.
    """
    if not negatives:
        return []

    positive_text = build_positive_text_from_uri(positive.esco_uri, concepts_by_uri)
    if positive_text is None:
        logger.warning(
            "training_data.positive_uri_unknown",
            cv_id=positive.cv_id,
            esco_uri=positive.esco_uri,
            pair_id=positive.pair_id,
        )
        return []
    anchor_text = build_anchor_text(positive)

    rows: list[SBERTExample] = []
    for neg in negatives:
        negative_text = build_positive_text_from_uri(neg.esco_uri, concepts_by_uri)
        if negative_text is None:
            logger.warning(
                "training_data.negative_uri_unknown",
                cv_id=neg.cv_id,
                esco_uri=neg.esco_uri,
                pair_id=neg.pair_id,
                paired_with_positive_id=neg.paired_with_positive_id,
            )
            continue
        rows.append(
            SBERTExample(
                texts=(anchor_text, positive_text, negative_text),
                label=None,
                pair_kind="triplet",
                cv_id=positive.cv_id,
                positive_uri=positive.esco_uri,
                negative_uri=neg.esco_uri,
            )
        )
    return rows


def _example_sort_key(example: SBERTExample) -> tuple[str, str, str, str]:
    """Sort key for the final example list — see module docstring.

    Order: ``(cv_id, pair_kind, positive_uri, negative_uri_or_empty)``.
    ``negative_uri`` is normalised to ``""`` for pair rows so ``None`` /
    ``str`` mixed comparisons are avoided under ``mypy --strict``.
    """
    return (
        example.cv_id,
        example.pair_kind,
        example.positive_uri,
        example.negative_uri or "",
    )


def prepare_sbert_examples(
    *,
    dataset: TrainingDataset,
    concepts_by_uri: dict[str, EscoConcept],
    mode: SBERTMode,
) -> list[SBERTExample]:
    """Convert a :class:`TrainingDataset` into a list of SBERT-ready rows.

    Parameters
    ----------
    dataset
        The loaded Step 3 dataset (train **or** val split). Must contain
        :class:`TrainingPair` rows; may also contain :class:`HardNegative`
        rows (only used when ``mode="triplets"``).
    concepts_by_uri
        ESCO concept lookup. Usually built as
        ``{c.uri: c for c in load_esco_concepts()}``.
    mode
        ``"pairs_mnrl"`` (default for Step 5) or ``"triplets"``.

    Returns
    -------
    list[SBERTExample]
        Deterministically sorted by ``_example_sort_key``. Caller is
        responsible for shuffling with a seeded RNG before feeding into
        a :class:`DataLoader`.

    Raises
    ------
    ValueError
        If ``mode`` is not one of the locked values, or if the dataset
        has no :class:`TrainingPair` rows (a clear miswiring signal).
    """
    if mode not in ("pairs_mnrl", "triplets"):
        raise ValueError(
            f"Unknown SBERT mode {mode!r}; expected 'pairs_mnrl' or 'triplets'."
        )

    positives = [p for p in dataset.pairs if isinstance(p, TrainingPair)]
    if not positives:
        raise ValueError(
            "Dataset contains no TrainingPair rows; cannot build SBERT examples."
        )

    examples: list[SBERTExample] = []

    if mode == "pairs_mnrl":
        skipped = 0
        for positive in positives:
            row = _emit_pair_example(positive, concepts_by_uri)
            if row is None:
                skipped += 1
                continue
            examples.append(row)
        logger.info(
            "training_data.prepared",
            mode=mode,
            split=dataset.split,
            positives_in=len(positives),
            examples_out=len(examples),
            skipped_missing_uri=skipped,
        )
    else:  # mode == "triplets"
        negatives_by_pos_id = _negatives_by_positive_id(dataset.pairs)
        skipped_positives = 0
        for positive in positives:
            negatives = negatives_by_pos_id.get(positive.pair_id, [])
            triplets = _emit_triplet_examples(
                positive, negatives, concepts_by_uri
            )
            if not triplets:
                skipped_positives += 1
                continue
            examples.extend(triplets)
        logger.info(
            "training_data.prepared",
            mode=mode,
            split=dataset.split,
            positives_in=len(positives),
            triplets_out=len(examples),
            skipped_positives_no_triplets=skipped_positives,
        )

    examples.sort(key=_example_sort_key)
    return examples


__all__ = [
    "ANCHOR_HARD_CAP_CHARS",
    "SBERTExample",
    "SBERTMode",
    "build_anchor_text",
    "build_positive_text_from_uri",
    "prepare_sbert_examples",
]
