"""Tests for the Step 3 training-dataset machinery.

Covers:

* :mod:`skill_matcher.dataset` — pydantic validation, JSONL round-trip,
  deterministic ordering, malformed-row tolerance.
* :mod:`skill_matcher.context_window` — sentence-boundary clipping.
* :mod:`skill_matcher.data.category_map` — sibling resolution and
  the synthetic custom-URI bucket.
* The stratified-split helper inside
  :mod:`scripts.build_training_dataset`.

Fast tests run by default (``pytest -m "not slow"``). The single slow
test at the bottom is the sign-off gate for Step 3: it loads the real
``data/training/pairs/{train,val}.jsonl`` and asserts the quantitative
thresholds and zero-eval-overlap invariant.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from skill_matcher.context_window import ContextWindow, clip_context
from skill_matcher.data.category_map import (
    CUSTOM_CATEGORY_ROOT,
    EscoCategoryMap,
)
from skill_matcher.dataset import (
    HardNegative,
    TrainingDataset,
    TrainingPair,
    compute_pair_id,
    load_training_dataset,
    save_training_dataset,
)
from skill_matcher.splits import dominant_category, stratified_split

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NLP_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_PAIRS_DIR = _NLP_SERVICE_ROOT / "data" / "training" / "pairs"


def _make_positive(
    *,
    cv_id: str = "train_cv001",
    span_start: int = 10,
    span_end: int = 16,
    esco_uri: str = "http://data.europa.eu/esco/skill/python",
    surface_form: str = "Python",
    section: str = "skills",
    language: str = "en",
    module2_confidence: float = 0.92,
    text_span: str | None = None,
    query_text: str = "",
    window_start: int = -1,
    window_end: int = -1,
) -> TrainingPair:
    """Factory for a well-formed :class:`TrainingPair`.

    The Step 5.2 fields (``query_text`` / ``window_start`` / ``window_end``)
    default to the legacy sentinel values so older tests that don't pass
    them produce dataset shapes identical to Step 5 round 1.
    """
    span_text = text_span or surface_form
    return TrainingPair(
        pair_id=compute_pair_id(cv_id, span_start, span_end, esco_uri, "positive"),
        cv_id=cv_id,
        text_span=span_text,
        span_start=span_start,
        span_end=span_end,
        context_before="3 years of",
        context_after="development",
        query_text=query_text,
        window_start=window_start,
        window_end=window_end,
        esco_uri=esco_uri,
        surface_form=surface_form,
        section=section,  # type: ignore[arg-type]
        language=language,  # type: ignore[arg-type]
        module2_confidence=module2_confidence,
    )


def _make_negative_for(positive: TrainingPair, *, wrong_uri: str) -> HardNegative:
    """Factory for a hard negative paired with a positive."""
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
        distractor_reason="sibling under L2 ancestor X",
    )


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


def test_training_pair_constructs_with_defaults() -> None:
    """A fully-populated positive pair round-trips through pydantic."""
    pair = _make_positive()
    dumped = pair.model_dump(mode="json")
    reloaded = TrainingPair.model_validate(dumped)
    assert reloaded == pair
    assert reloaded.pair_type == "positive"


def test_training_pair_rejects_confidence_above_one() -> None:
    """``module2_confidence`` must live in ``[0.0, 1.0]``."""
    with pytest.raises(ValidationError):
        _make_positive(module2_confidence=1.4)


def test_training_pair_rejects_negative_span_end() -> None:
    """``span_end > span_start`` is enforced by the cross-field validator."""
    with pytest.raises(ValidationError):
        _make_positive(span_start=10, span_end=10)


def test_hard_negative_requires_strategy_and_paired_id() -> None:
    """``HardNegative`` cannot be constructed without the extra fields."""
    pos = _make_positive()
    with pytest.raises(ValidationError):
        # Intentionally missing negative_strategy + paired_with_positive_id.
        HardNegative(  # type: ignore[call-arg]
            pair_id="x" * 16,
            cv_id=pos.cv_id,
            text_span=pos.text_span,
            span_start=pos.span_start,
            span_end=pos.span_end,
            esco_uri="http://data.europa.eu/esco/skill/ruby",
            surface_form=pos.surface_form,
            section=pos.section,
            language=pos.language,
            module2_confidence=pos.module2_confidence,
        )


def test_training_dataset_constructs_with_mixed_pairs() -> None:
    """Datasets accept the discriminated union of positives + negatives."""
    pos = _make_positive()
    neg = _make_negative_for(pos, wrong_uri="http://data.europa.eu/esco/skill/ruby")
    ds = TrainingDataset(
        pairs=[pos, neg],
        split="train",
        build_timestamp=datetime.now(tz=UTC),
        build_config={"min_confidence": 0.65},
        total_cvs_processed=1,
        total_cvs_excluded=0,
    )
    assert len(ds.pairs) == 2
    types = {p.pair_type for p in ds.pairs}
    assert types == {"positive", "hard_negative"}


# ---------------------------------------------------------------------------
# JSONL round-trip
# ---------------------------------------------------------------------------


def test_save_load_roundtrip_is_byte_identical(tmp_path: Path) -> None:
    """Saving twice with the same input produces byte-identical files."""
    pos = _make_positive()
    neg = _make_negative_for(pos, wrong_uri="http://data.europa.eu/esco/skill/ruby")
    ds = TrainingDataset(
        pairs=[pos, neg, pos, neg],  # duplicates allowed; sort key handles them
        split="train",
        build_timestamp=datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC),
        build_config={"min_confidence": 0.65, "seed": 42},
        total_cvs_processed=1,
        total_cvs_excluded=0,
    )
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    save_training_dataset(ds, path_a)
    save_training_dataset(ds, path_b)
    assert path_a.read_bytes() == path_b.read_bytes()

    reloaded = load_training_dataset(path_a)
    assert reloaded.split == "train"
    assert reloaded.total_cvs_processed == 1
    assert reloaded.total_cvs_excluded == 0
    # pairs preserve their on-disk order, which is the sort key order
    assert all(p.pair_type in ("positive", "hard_negative") for p in reloaded.pairs)


def test_save_load_empty_dataset(tmp_path: Path) -> None:
    """An empty dataset still produces a valid JSONL header line."""
    ds = TrainingDataset(
        pairs=[],
        split="val",
        build_timestamp=datetime.now(tz=UTC),
        build_config={},
        total_cvs_processed=0,
        total_cvs_excluded=0,
    )
    path = tmp_path / "empty.jsonl"
    save_training_dataset(ds, path)
    text = path.read_text(encoding="utf-8").splitlines()
    assert len(text) == 1  # header only
    reloaded = load_training_dataset(path)
    assert reloaded.pairs == []
    assert reloaded.split == "val"


def test_load_rejects_too_many_malformed_rows(tmp_path: Path) -> None:
    """Loading raises if > 5 % of pair rows are malformed."""
    path = tmp_path / "bad.jsonl"
    header = {
        "record_kind": "header",
        "split": "train",
        "build_timestamp": datetime.now(tz=UTC).isoformat(),
        "build_config": {},
        "total_cvs_processed": 0,
        "total_cvs_excluded": 0,
        "pair_count": 0,
    }
    lines = [json.dumps(header)]
    for _ in range(20):
        # Each line lacks required fields, so pydantic will reject it.
        lines.append(json.dumps({"record_kind": "pair", "cv_id": "x"}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed rows"):
        load_training_dataset(path)


def test_load_skips_blank_lines_quietly(tmp_path: Path) -> None:
    """Blank lines are skipped without counting against the malformed cap."""
    pos = _make_positive()
    ds = TrainingDataset(
        pairs=[pos],
        split="train",
        build_timestamp=datetime.now(tz=UTC),
        build_config={},
        total_cvs_processed=1,
        total_cvs_excluded=0,
    )
    path = tmp_path / "with_blanks.jsonl"
    save_training_dataset(ds, path)
    # Append a couple of blank lines manually.
    with path.open("a", encoding="utf-8") as fp:
        fp.write("\n\n   \n")
    reloaded = load_training_dataset(path)
    assert len(reloaded.pairs) == 1


# ---------------------------------------------------------------------------
# Context-window helper
# ---------------------------------------------------------------------------


def test_clip_context_respects_max_chars() -> None:
    """Window widths never exceed ``max_chars`` on either side."""
    text = "x" * 200 + " Python " + "y" * 200
    span_start = 201
    span_end = 207
    cw = clip_context(text, span_start, span_end, max_chars=50)
    assert len(cw.before) <= 50
    assert len(cw.after) <= 50


def test_clip_context_clips_to_sentence_boundary() -> None:
    """Sentence-final punctuation truncates the window on the left."""
    text = "I built websites. Used Python daily. Always tested."
    # Find the span of "Python".
    span_start = text.index("Python")
    span_end = span_start + len("Python")
    cw = clip_context(text, span_start, span_end, max_chars=80)
    # "I built websites." is the previous sentence — must NOT appear.
    assert "websites" not in cw.before.lower()
    # The current sentence's prefix should be present.
    assert "used" in cw.before.lower()
    # The right side ends at the period after "daily".
    assert "always" not in cw.after.lower()


def test_clip_context_at_document_start() -> None:
    """Spans at the very beginning produce empty ``before``."""
    text = "Python developer with 5 years experience."
    cw = clip_context(text, 0, 6, max_chars=50)
    assert cw.before == ""
    assert "developer" in cw.after.lower()


def test_clip_context_rejects_invalid_span() -> None:
    """Out-of-range spans raise :class:`ValueError`."""
    with pytest.raises(ValueError):
        clip_context("short", 0, 10)


def test_clip_context_returns_named_dataclass() -> None:
    """Return type is :class:`ContextWindow` with the expected attrs."""
    cw = clip_context("Python here.", 0, 6, max_chars=20)
    assert isinstance(cw, ContextWindow)
    assert hasattr(cw, "before")
    assert hasattr(cw, "after")


# ---------------------------------------------------------------------------
# Category-map helper
# ---------------------------------------------------------------------------


def _toy_category_map() -> EscoCategoryMap:
    """Three categories, six leaves — enough to exercise sibling logic."""
    return EscoCategoryMap(
        uri_to_l2={
            "esco:python": "esco:L2:programming",
            "esco:ruby": "esco:L2:programming",
            "esco:java": "esco:L2:programming",
            "esco:psql": "esco:L2:databases",
            "esco:mysql": "esco:L2:databases",
            "esco:listening": "esco:L2:softskills",
            "CUST:fastapi": CUSTOM_CATEGORY_ROOT,
            "CUST:react": CUSTOM_CATEGORY_ROOT,
        },
        l2_to_children={
            "esco:L2:programming": ["esco:java", "esco:python", "esco:ruby"],
            "esco:L2:databases": ["esco:mysql", "esco:psql"],
            "esco:L2:softskills": ["esco:listening"],
            CUSTOM_CATEGORY_ROOT: ["CUST:fastapi", "CUST:react"],
        },
    )


def test_category_map_siblings_excludes_self() -> None:
    """``siblings`` returns category peers without the URI itself."""
    cmap = _toy_category_map()
    siblings = cmap.siblings("esco:python")
    assert "esco:python" not in siblings
    assert set(siblings) == {"esco:ruby", "esco:java"}


def test_category_map_singleton_category_has_no_siblings() -> None:
    """A leaf alone under its L2 has no siblings to draw from."""
    cmap = _toy_category_map()
    assert cmap.siblings("esco:listening") == []


def test_category_map_custom_root_groups_custom_uris() -> None:
    """``CUST:`` URIs sibling each other under the synthetic root."""
    cmap = _toy_category_map()
    assert set(cmap.siblings("CUST:fastapi")) == {"CUST:react"}
    assert cmap.uri_to_l2["CUST:fastapi"] == CUSTOM_CATEGORY_ROOT


def test_category_map_unknown_uri_returns_empty() -> None:
    """Asking about an unknown URI returns an empty list, not an exception."""
    cmap = _toy_category_map()
    assert cmap.siblings("esco:does-not-exist") == []


# ---------------------------------------------------------------------------
# Pair-id determinism
# ---------------------------------------------------------------------------


def test_compute_pair_id_is_deterministic_and_short() -> None:
    """Same inputs → same id; output is 16 hex chars."""
    a = compute_pair_id("train_cv001", 10, 16, "esco:python", "positive")
    b = compute_pair_id("train_cv001", 10, 16, "esco:python", "positive")
    assert a == b
    assert len(a) == 16
    assert all(c in "0123456789abcdef" for c in a)


def test_compute_pair_id_changes_with_pair_type() -> None:
    """Positive and negative on the same triple get distinct ids."""
    pos = compute_pair_id("train_cv001", 10, 16, "esco:python", "positive")
    neg = compute_pair_id("train_cv001", 10, 16, "esco:python", "hard_negative")
    assert pos != neg


# ---------------------------------------------------------------------------
# Stratified split helper (pure, lives in skill_matcher.splits)
# ---------------------------------------------------------------------------


def test_stratified_split_proportions_within_tolerance() -> None:
    """Each category receives a near-20 % val slice, deterministic."""
    rng = random.Random(42)
    cv_ids = [f"cv{i:03d}" for i in range(30)]
    cv_to_category: dict[str, str] = {}
    for i, cv_id in enumerate(cv_ids):
        # 10 each of cat_a / cat_b / cat_c.
        cv_to_category[cv_id] = ("cat_a", "cat_b", "cat_c")[i % 3]

    train, val = stratified_split(cv_ids, cv_to_category, 0.2, rng)
    assert train.isdisjoint(val)
    assert train | val == set(cv_ids)
    # 20 % of 10 = 2 per category; per-category invariant
    per_cat_val = Counter(cv_to_category[c] for c in val)
    for category, count in per_cat_val.items():
        assert count == 2, f"category {category} got {count} val CVs"


def test_stratified_split_singleton_category_goes_to_train() -> None:
    """Categories with fewer than 2 CVs cannot contribute to val."""
    rng = random.Random(42)
    cv_ids = ["a", "b", "c", "d", "e"]
    cv_to_category = {
        "a": "x",
        "b": "x",
        "c": "x",
        "d": "x",
        "e": "lonely",
    }
    train, val = stratified_split(cv_ids, cv_to_category, 0.2, rng)
    assert "e" in train
    assert "e" not in val


def test_stratified_split_is_deterministic_given_seed() -> None:
    """Two splits with the same seed and inputs produce identical sets."""
    cv_ids = [f"cv{i:03d}" for i in range(20)]
    cv_to_cat = {c: "a" if i % 2 == 0 else "b" for i, c in enumerate(cv_ids)}
    t1, v1 = stratified_split(cv_ids, cv_to_cat, 0.2, random.Random(42))
    t2, v2 = stratified_split(cv_ids, cv_to_cat, 0.2, random.Random(42))
    assert t1 == t2
    assert v1 == v2


def test_dominant_category_picks_majority() -> None:
    """``dominant_category`` returns the category with the most URIs."""
    uri_to_cat = {
        "u:python": "prog",
        "u:ruby": "prog",
        "u:psql": "db",
        "u:listening": "softskill",
    }
    skill_uris = ["u:python", "u:ruby", "u:psql", "u:listening"]
    assert dominant_category(skill_uris, uri_to_cat) == "prog"


def test_dominant_category_ties_break_lexicographically() -> None:
    """Two-way ties resolve to the lexicographically smaller category."""
    uri_to_cat = {"u:a": "alpha", "u:b": "beta"}
    assert dominant_category(["u:a", "u:b"], uri_to_cat) == "alpha"


def test_dominant_category_empty_returns_fallback() -> None:
    """No mapped URIs → the explicit fallback string."""
    assert dominant_category([], {}, fallback="__none__") == "__none__"


# ---------------------------------------------------------------------------
# Sign-off gate — slow invariants over the real dataset
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_real_training_dataset_invariants() -> None:
    """Sign-off gate for Step 3.

    Loads the real ``train.jsonl`` and ``val.jsonl`` and asserts every
    Step-3 quantitative threshold plus the zero-overlap contamination
    invariant against the eval corpus.

    Skipped automatically when the dataset files do not exist on disk
    so the slow marker still runs in CI for a fresh checkout without
    blocking on a build the developer has not run yet.
    """
    train_path = _PAIRS_DIR / "train.jsonl"
    val_path = _PAIRS_DIR / "val.jsonl"
    if not train_path.exists() or not val_path.exists():
        pytest.skip(
            "Real training JSONL files are missing — "
            "run scripts/build_training_dataset.py first."
        )

    train = load_training_dataset(train_path)
    val = load_training_dataset(val_path)
    all_pairs = train.pairs + val.pairs
    positives = [p for p in all_pairs if p.pair_type == "positive"]
    negatives = [p for p in all_pairs if p.pair_type == "hard_negative"]

    assert positives, "Expected at least one positive pair"
    assert negatives, "Expected at least one hard-negative pair"
    assert len(positives) >= 2000, (
        f"Only {len(positives)} positives; threshold is 2000."
    )
    ratio = len(negatives) / len(positives)
    # Step 5.2 — datasets built with sliding-window queries emit one
    # positive per (span, containing window) combo, so the same span
    # produces N positives. Hard negatives are mined once per unique
    # span (see Phase E dedupe), which drops the negatives/positives
    # ratio below the Step 5 round-1 floor of 3. Detect Step 5.2
    # datasets by presence of ``query_text`` on the first positive and
    # relax the lower bound to 0.5.
    is_window_mode = bool(positives[0].query_text) if positives else False
    if is_window_mode:
        assert 0.5 <= ratio <= 5.0, (
            f"Step 5.2 window-mode dataset: ratio {ratio:.2f} "
            f"out of expected [0.5, 5.0]."
        )
        # Also verify that >=95% of positives carry a non-empty
        # query_text — catches Phase D regressions that silently drop
        # the sliding-window path.
        with_query = sum(1 for p in positives if p.query_text)
        fraction = with_query / len(positives)
        assert fraction >= 0.95, (
            f"Only {fraction:.2%} of positives have query_text — "
            f"Phase D sliding-window logic regressed."
        )
    else:
        assert 3.0 <= ratio <= 5.0, (
            f"Negative/positive ratio {ratio:.2f} out of [3, 5]."
        )

    # Contamination invariant: zero overlap with eval CV ids.
    eval_cv_ids = {f"real_cv{i}" for i in range(1, 16)}
    train_cv_ids = {p.cv_id for p in all_pairs}
    assert train_cv_ids.isdisjoint(eval_cv_ids), (
        "Training corpus contains eval CV ids — contamination detected."
    )
    assert all(cv_id.startswith("train_") for cv_id in train_cv_ids), (
        "Every training CV id must start with 'train_'."
    )

    # Every URI must live in one of three namespaces:
    #   * an ESCO concept URI from the loaded taxonomy bundle,
    #   * a ``CUST:`` URI from Module 2's custom_concepts.json overlay,
    #   * a ``CUST:lang:<language>`` URI synthesised on the fly by
    #     Module 2's language-section parser (e.g. "Dutch (B2)").
    # The third namespace is NOT enumerable in advance — it depends on
    # which languages appear in the source CVs — so we accept it by
    # prefix.
    #
    # The skill_extractor imports are deferred to the slow test so the
    # fast layer does not pull in spaCy / lingua / pymupdf transitively.
    from skill_extractor import SkillExtractorConfig
    from skill_extractor.esco.loader import EscoLoader
    from skill_extractor.overlays.custom import load_custom_overlay
    from skill_extractor.pipeline import LANGUAGE_URI_PREFIX

    esco_config = SkillExtractorConfig()
    esco_skills = EscoLoader(esco_config).load()
    custom_overlay = load_custom_overlay(esco_config.custom_concepts_path)
    enumerable_uris = (
        {s.concept_uri for s in esco_skills}
        | {c.concept_uri for c in custom_overlay.concepts}
    )
    for pair in positives:
        uri = pair.esco_uri
        is_known = (
            uri in enumerable_uris
            or uri.startswith(LANGUAGE_URI_PREFIX)
        )
        assert is_known, (
            f"Positive URI {uri!r} not in ESCO / CUST / "
            f"{LANGUAGE_URI_PREFIX}* namespaces."
        )

    # Every hard negative's URI must differ from the URI of its
    # paired positive — that is the whole point.
    pos_by_id = {p.pair_id: p for p in positives}
    for neg in negatives:
        assert isinstance(neg, HardNegative)  # narrow for mypy
        paired = pos_by_id.get(neg.paired_with_positive_id)
        assert paired is not None, (
            f"HardNegative {neg.pair_id!r} references unknown positive "
            f"{neg.paired_with_positive_id!r}."
        )
        assert neg.esco_uri != paired.esco_uri, (
            f"HardNegative {neg.pair_id!r} shares URI with its paired positive."
        )
