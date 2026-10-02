"""Fast unit tests for :mod:`skill_matcher.training_data`.

Covers the deterministic glue between Step 3's :class:`TrainingDataset`
and the SBERT training loop:

* :func:`build_anchor_text` — joined context window, hard cap.
* :func:`build_positive_text_from_uri` — bounded-a format parity, missing
  URI returns ``None``.
* :func:`prepare_sbert_examples` for both modes, including determinism
  and error paths.

No torch / sentence-transformers imports. The module under test is
pure-Python; these tests are too.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from skill_matcher.dataset import (
    AnyPair,
    HardNegative,
    TrainingDataset,
    TrainingPair,
    compute_pair_id,
)
from skill_matcher.esco_index import format_concept_text
from skill_matcher.esco_loader import EscoConcept
from skill_matcher.training_data import (
    SBERTExample,
    build_anchor_text,
    build_positive_text_from_uri,
    prepare_sbert_examples,
)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_concept(
    *,
    uri: str = "http://data.europa.eu/esco/skill/python",
    pref_label: str = "Python (computer programming)",
    alt_labels: tuple[str, ...] = ("Python", "Python programming"),
    description: str = "A high-level interpreted programming language.",
    skill_type: str = "knowledge",
    is_custom: bool = False,
) -> EscoConcept:
    """Build a synthetic :class:`EscoConcept` with reasonable defaults."""
    return EscoConcept(
        uri=uri,
        pref_label=pref_label,
        alt_labels=alt_labels,
        description=description,
        skill_type=skill_type,  # type: ignore[arg-type]
        is_custom=is_custom,
    )


def _make_positive(
    *,
    cv_id: str = "train_cv001",
    span_start: int = 10,
    span_end: int = 16,
    esco_uri: str = "http://data.europa.eu/esco/skill/python",
    text_span: str = "Python",
    context_before: str = "3 years of ",
    context_after: str = " development experience",
    query_text: str = "",
    window_start: int = -1,
    window_end: int = -1,
) -> TrainingPair:
    """Build a synthetic :class:`TrainingPair`."""
    return TrainingPair(
        pair_id=compute_pair_id(cv_id, span_start, span_end, esco_uri, "positive"),
        cv_id=cv_id,
        text_span=text_span,
        span_start=span_start,
        span_end=span_end,
        context_before=context_before,
        context_after=context_after,
        query_text=query_text,
        window_start=window_start,
        window_end=window_end,
        esco_uri=esco_uri,
        surface_form=text_span,
        section="experience",
        language="en",
        module2_confidence=0.9,
    )


def _make_negative_for(
    positive: TrainingPair,
    *,
    wrong_uri: str = "http://data.europa.eu/esco/skill/ruby",
) -> HardNegative:
    """Build a hard negative paired with ``positive``."""
    hn_id = compute_pair_id(
        positive.cv_id,
        positive.span_start,
        positive.span_end,
        wrong_uri,
        "hard_negative",
    )
    return HardNegative(
        pair_id=hn_id,
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
        negative_strategy="same_category_esco",
        paired_with_positive_id=positive.pair_id,
        distractor_reason="sibling under L2 'computer programming'",
    )


def _make_dataset(pairs: list[AnyPair], *, split: str = "train") -> TrainingDataset:
    """Wrap ``pairs`` in a :class:`TrainingDataset` with minimal provenance."""
    return TrainingDataset(
        pairs=pairs,
        split=split,  # type: ignore[arg-type]
        build_timestamp=datetime(2026, 5, 16, tzinfo=UTC),
        build_config={},
        total_cvs_processed=1,
        total_cvs_excluded=0,
    )


# ---------------------------------------------------------------------------
# build_anchor_text
# ---------------------------------------------------------------------------


def test_build_anchor_text_concatenates_and_strips() -> None:
    """The anchor joins context_before + text_span + context_after."""
    pair = _make_positive(
        context_before="  Worked as a ",
        text_span="Python developer",
        context_after=" for five years.  ",
    )
    assert build_anchor_text(pair) == "Worked as a Python developer for five years."


def test_build_anchor_text_handles_empty_contexts() -> None:
    """Empty surrounding contexts produce just the bare text span."""
    pair = _make_positive(
        context_before="",
        text_span="Python",
        context_after="",
    )
    assert build_anchor_text(pair) == "Python"


def test_build_anchor_text_truncates_above_cap() -> None:
    """Anchors longer than the hard cap are truncated to 256 chars."""
    # 300-char before-context forces truncation.
    pair = _make_positive(
        context_before="x" * 300,
        text_span="Python",
        context_after="",
    )
    anchor = build_anchor_text(pair)
    assert len(anchor) == 256
    assert anchor == "x" * 256


def test_build_anchor_text_works_for_hard_negative() -> None:
    """Anchor builder accepts a :class:`HardNegative` too — same fields."""
    positive = _make_positive()
    negative = _make_negative_for(positive)
    # Same span / context as the paired positive → same anchor string.
    assert build_anchor_text(negative) == build_anchor_text(positive)


def test_build_anchor_text_uses_query_text_when_present() -> None:
    """Step 5.2 — when ``query_text`` is set, it overrides the legacy concat.

    The encoder must see the sliding-window text verbatim, not a
    synthesised context+span+after string. This is the train/serve
    parity contract for Step 5.2.
    """
    pair = _make_positive(
        context_before="legacy before ",
        text_span="Python",
        context_after=" legacy after",
        query_text="Built REST APIs with Python and Django for 4 years at Acme",
        window_start=120,
        window_end=170,
    )
    # query_text wins over context_before + text_span + context_after.
    assert build_anchor_text(pair) == (
        "Built REST APIs with Python and Django for 4 years at Acme"
    )


def test_build_anchor_text_strips_query_text() -> None:
    """A query_text with surrounding whitespace is stripped before use."""
    pair = _make_positive(
        query_text="   leading and trailing   ",
        window_start=10,
        window_end=50,
    )
    assert build_anchor_text(pair) == "leading and trailing"


def test_build_anchor_text_truncates_query_text_above_cap() -> None:
    """A query_text longer than the hard cap is truncated to 256 chars."""
    pair = _make_positive(
        query_text="y" * 300,
        window_start=10,
        window_end=310,
    )
    anchor = build_anchor_text(pair)
    assert len(anchor) == 256
    assert anchor == "y" * 256


# ---------------------------------------------------------------------------
# build_positive_text_from_uri
# ---------------------------------------------------------------------------


def test_build_positive_text_matches_bounded_a() -> None:
    """The positive-text builder must return exactly what bounded-a renders.

    This is the train / eval parity guarantee — the encoder must see the
    same string at training time and at index-build time.
    """
    concept = _make_concept()
    concepts_by_uri = {concept.uri: concept}
    actual = build_positive_text_from_uri(concept.uri, concepts_by_uri)
    expected = format_concept_text(concept, "bounded-a")
    assert actual == expected


def test_build_positive_text_returns_none_on_missing_uri() -> None:
    """Unknown URI → ``None`` so the caller can skip + log."""
    result = build_positive_text_from_uri("missing-uri", {})
    assert result is None


# ---------------------------------------------------------------------------
# prepare_sbert_examples — pairs_mnrl mode
# ---------------------------------------------------------------------------


def test_pairs_mnrl_emits_one_example_per_positive() -> None:
    """``pairs_mnrl`` mode emits exactly one row per :class:`TrainingPair`."""
    positives = [
        _make_positive(cv_id="train_cv001", esco_uri="http://esco/skill/python"),
        _make_positive(cv_id="train_cv002", esco_uri="http://esco/skill/java"),
    ]
    concepts_by_uri = {
        "http://esco/skill/python": _make_concept(uri="http://esco/skill/python"),
        "http://esco/skill/java": _make_concept(
            uri="http://esco/skill/java", pref_label="Java"
        ),
    }
    dataset = _make_dataset(list(positives))

    examples = prepare_sbert_examples(
        dataset=dataset, concepts_by_uri=concepts_by_uri, mode="pairs_mnrl"
    )

    assert len(examples) == 2
    assert all(ex.pair_kind == "pair" for ex in examples)
    assert all(len(ex.texts) == 2 for ex in examples)
    assert all(ex.negative_uri is None for ex in examples)


def test_pairs_mnrl_ignores_hard_negatives() -> None:
    """``pairs_mnrl`` rows come only from positives — hard negatives don't emit."""
    positive = _make_positive()
    negative = _make_negative_for(positive)
    concepts_by_uri = {
        positive.esco_uri: _make_concept(uri=positive.esco_uri),
        negative.esco_uri: _make_concept(uri=negative.esco_uri, pref_label="Ruby"),
    }
    dataset = _make_dataset([positive, negative])

    examples = prepare_sbert_examples(
        dataset=dataset, concepts_by_uri=concepts_by_uri, mode="pairs_mnrl"
    )

    # One example from the one positive; the hard negative is silent.
    assert len(examples) == 1
    assert examples[0].positive_uri == positive.esco_uri


def test_pairs_mnrl_skips_positive_with_missing_uri() -> None:
    """A positive whose URI is unknown is logged + skipped, not crashed."""
    p_known = _make_positive(esco_uri="http://esco/skill/known")
    p_missing = _make_positive(
        cv_id="train_cv002",
        span_start=5,
        span_end=12,
        esco_uri="http://esco/skill/missing",
    )
    concepts_by_uri = {"http://esco/skill/known": _make_concept(uri="http://esco/skill/known")}
    dataset = _make_dataset([p_known, p_missing])

    examples = prepare_sbert_examples(
        dataset=dataset, concepts_by_uri=concepts_by_uri, mode="pairs_mnrl"
    )

    assert len(examples) == 1
    assert examples[0].positive_uri == "http://esco/skill/known"


# ---------------------------------------------------------------------------
# prepare_sbert_examples — triplets mode
# ---------------------------------------------------------------------------


def test_triplets_emits_one_row_per_hard_negative() -> None:
    """``triplets`` mode emits one row per :class:`HardNegative`."""
    positive = _make_positive()
    n1 = _make_negative_for(positive, wrong_uri="http://esco/skill/ruby")
    n2 = _make_negative_for(positive, wrong_uri="http://esco/skill/perl")
    concepts_by_uri = {
        positive.esco_uri: _make_concept(uri=positive.esco_uri),
        "http://esco/skill/ruby": _make_concept(uri="http://esco/skill/ruby", pref_label="Ruby"),
        "http://esco/skill/perl": _make_concept(uri="http://esco/skill/perl", pref_label="Perl"),
    }
    dataset = _make_dataset([positive, n1, n2])

    examples = prepare_sbert_examples(
        dataset=dataset, concepts_by_uri=concepts_by_uri, mode="triplets"
    )

    assert len(examples) == 2
    assert all(ex.pair_kind == "triplet" for ex in examples)
    assert all(len(ex.texts) == 3 for ex in examples)
    assert {ex.negative_uri for ex in examples} == {
        "http://esco/skill/ruby",
        "http://esco/skill/perl",
    }
    # Every triplet carries the same positive uri (it was the same positive).
    assert {ex.positive_uri for ex in examples} == {positive.esco_uri}


def test_triplets_skips_negative_with_unknown_uri() -> None:
    """A hard negative whose URI is unknown is silently dropped."""
    positive = _make_positive()
    n_known = _make_negative_for(positive, wrong_uri="http://esco/skill/ruby")
    n_missing = _make_negative_for(positive, wrong_uri="http://esco/skill/missing")
    concepts_by_uri = {
        positive.esco_uri: _make_concept(uri=positive.esco_uri),
        "http://esco/skill/ruby": _make_concept(uri="http://esco/skill/ruby", pref_label="Ruby"),
    }
    dataset = _make_dataset([positive, n_known, n_missing])

    examples = prepare_sbert_examples(
        dataset=dataset, concepts_by_uri=concepts_by_uri, mode="triplets"
    )

    assert len(examples) == 1
    assert examples[0].negative_uri == "http://esco/skill/ruby"


def test_triplets_skips_positive_with_no_negatives() -> None:
    """If a positive has zero paired negatives, no triplet is produced."""
    positive = _make_positive()
    concepts_by_uri = {positive.esco_uri: _make_concept(uri=positive.esco_uri)}
    dataset = _make_dataset([positive])

    examples = prepare_sbert_examples(
        dataset=dataset, concepts_by_uri=concepts_by_uri, mode="triplets"
    )

    assert examples == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def _examples_hash(examples: list[SBERTExample]) -> str:
    """Stable hash of an example list, independent of object identity."""
    h = hashlib.sha256()
    for ex in examples:
        parts = (
            ex.pair_kind,
            ex.cv_id,
            ex.positive_uri,
            ex.negative_uri or "",
            *ex.texts,
        )
        h.update("\x1f".join(parts).encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


def test_pairs_mnrl_is_deterministic() -> None:
    """Two invocations on identical inputs produce identical results."""
    p1 = _make_positive(cv_id="train_cv001", esco_uri="http://esco/skill/python")
    p2 = _make_positive(cv_id="train_cv002", esco_uri="http://esco/skill/java")
    concepts_by_uri = {
        p1.esco_uri: _make_concept(uri=p1.esco_uri),
        p2.esco_uri: _make_concept(uri=p2.esco_uri, pref_label="Java"),
    }
    # Construct two datasets where the pair list order is different — the
    # output should still be byte-identical thanks to the internal sort.
    ds_a = _make_dataset([p1, p2])
    ds_b = _make_dataset([p2, p1])

    out_a = prepare_sbert_examples(
        dataset=ds_a, concepts_by_uri=concepts_by_uri, mode="pairs_mnrl"
    )
    out_b = prepare_sbert_examples(
        dataset=ds_b, concepts_by_uri=concepts_by_uri, mode="pairs_mnrl"
    )

    assert _examples_hash(out_a) == _examples_hash(out_b)


def test_triplets_is_deterministic() -> None:
    """Triplet mode is order-independent in its input too."""
    positive = _make_positive()
    n1 = _make_negative_for(positive, wrong_uri="http://esco/skill/ruby")
    n2 = _make_negative_for(positive, wrong_uri="http://esco/skill/perl")
    concepts_by_uri = {
        positive.esco_uri: _make_concept(uri=positive.esco_uri),
        n1.esco_uri: _make_concept(uri=n1.esco_uri, pref_label="Ruby"),
        n2.esco_uri: _make_concept(uri=n2.esco_uri, pref_label="Perl"),
    }
    ds_a = _make_dataset([positive, n1, n2])
    ds_b = _make_dataset([n2, n1, positive])

    out_a = prepare_sbert_examples(
        dataset=ds_a, concepts_by_uri=concepts_by_uri, mode="triplets"
    )
    out_b = prepare_sbert_examples(
        dataset=ds_b, concepts_by_uri=concepts_by_uri, mode="triplets"
    )

    assert _examples_hash(out_a) == _examples_hash(out_b)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_unknown_mode_raises_value_error() -> None:
    """Defensive: unknown mode → ``ValueError`` with the offending value."""
    positive = _make_positive()
    concepts_by_uri = {positive.esco_uri: _make_concept(uri=positive.esco_uri)}
    dataset = _make_dataset([positive])

    with pytest.raises(ValueError, match="Unknown SBERT mode"):
        prepare_sbert_examples(
            dataset=dataset,
            concepts_by_uri=concepts_by_uri,
            mode="not_a_mode",  # type: ignore[arg-type]
        )


def test_empty_positives_raises_value_error() -> None:
    """A dataset with zero positives is a clear miswiring → fail loud."""
    positive = _make_positive()
    negative = _make_negative_for(positive)
    # Build a dataset that has the hard negative but NOT the positive.
    dataset = _make_dataset([negative])

    with pytest.raises(ValueError, match="no TrainingPair rows"):
        prepare_sbert_examples(
            dataset=dataset,
            concepts_by_uri={positive.esco_uri: _make_concept(uri=positive.esco_uri)},
            mode="pairs_mnrl",
        )
