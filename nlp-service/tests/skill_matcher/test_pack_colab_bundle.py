"""Fast unit tests for ``scripts/pack_colab_bundle.py``.

The packer reaches into Module 2's ESCO loader (heavy I/O + CSV parse)
and the real Step 3 JSONL files. These tests monkey-patch the loader
seam and synthesise tiny train/val pair files so the suite runs in
under a second without touching the real ESCO bundle.

Covers:

* Every expected file is present inside the bundle.
* The bundle SHA-256 is byte-stable across two consecutive packs from
  identical inputs (determinism gate per Step 5 Pre-Flight §5).
* Missing ``train.jsonl`` raises :class:`FileNotFoundError`.
* Pair-count mismatch vs ``stats.json`` raises :class:`ValueError`.
* Every zip entry has the locked epoch-zero timestamp.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import zipfile
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any

import pytest

from skill_matcher.dataset import (
    HardNegative,
    TrainingDataset,
    TrainingPair,
    compute_pair_id,
    save_training_dataset,
)
from skill_matcher.esco_loader import EscoConcept

# ---------------------------------------------------------------------------
# Import the script as a module
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "pack_colab_bundle.py"


def _load_packer_module() -> types.ModuleType:
    """Load ``pack_colab_bundle.py`` as a module, once.

    The script lives under ``scripts/`` (outside the ``src/`` packages
    layout), so we hand-load it via :mod:`importlib`.
    """
    if "pack_colab_bundle" in sys.modules:
        return sys.modules["pack_colab_bundle"]
    spec = importlib.util.spec_from_file_location(
        "pack_colab_bundle", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pack_colab_bundle"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Synthetic inputs
# ---------------------------------------------------------------------------


def _make_concept(uri: str, label: str) -> EscoConcept:
    return EscoConcept(
        uri=uri,
        pref_label=label,
        alt_labels=(label.lower(),),
        description=f"Definition of {label}.",
        skill_type="knowledge",
        is_custom=False,
    )


def _make_positive(
    *, cv_id: str, span_start: int, esco_uri: str, text_span: str
) -> TrainingPair:
    return TrainingPair(
        pair_id=compute_pair_id(
            cv_id, span_start, span_start + len(text_span), esco_uri, "positive"
        ),
        cv_id=cv_id,
        text_span=text_span,
        span_start=span_start,
        span_end=span_start + len(text_span),
        context_before="",
        context_after="",
        esco_uri=esco_uri,
        surface_form=text_span,
        section="skills",
        language="en",
        module2_confidence=0.9,
    )


def _make_negative_for(
    positive: TrainingPair, *, wrong_uri: str
) -> HardNegative:
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
        context_before="",
        context_after="",
        esco_uri=wrong_uri,
        surface_form=positive.surface_form,
        section=positive.section,
        language=positive.language,
        module2_confidence=positive.module2_confidence,
        negative_strategy="same_category_esco",
        paired_with_positive_id=positive.pair_id,
    )


def _write_dataset(path: Path, pairs: list[Any], split: str) -> None:
    ds = TrainingDataset(
        pairs=pairs,
        split=split,  # type: ignore[arg-type]
        build_timestamp=datetime(2026, 5, 16, tzinfo=UTC),
        build_config={"seed": 42},
        total_cvs_processed=2,
        total_cvs_excluded=0,
    )
    save_training_dataset(ds, path)


@pytest.fixture
def synthetic_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Build a self-contained synthetic input set on disk.

    Lays out:

    * ``tmp/train.jsonl`` — 2 positives + 2 hard negatives.
    * ``tmp/val.jsonl``   — 1 positive + 1 hard negative.
    * ``tmp/stats.json``  — matching n_positives / n_hard_negatives /
      n_train_pairs / n_val_pairs.
    * ``tmp/training_data.py`` — a tiny stub (the packer only copies bytes).

    Also monkey-patches the ESCO loader symbols inside the packer module
    so we do not hit the real ESCO CSV bundle.
    """
    packer = _load_packer_module()

    # Train: 2 positives + 2 negatives (one per positive).
    p1 = _make_positive(
        cv_id="train_cv001",
        span_start=0,
        esco_uri="http://esco/skill/python",
        text_span="Python",
    )
    p2 = _make_positive(
        cv_id="train_cv001",
        span_start=20,
        esco_uri="http://esco/skill/java",
        text_span="Java",
    )
    n1 = _make_negative_for(p1, wrong_uri="http://esco/skill/ruby")
    n2 = _make_negative_for(p2, wrong_uri="http://esco/skill/perl")

    # Val: 1 positive + 1 negative.
    p3 = _make_positive(
        cv_id="val_cv001",
        span_start=0,
        esco_uri="http://esco/skill/python",
        text_span="Python",
    )
    n3 = _make_negative_for(p3, wrong_uri="http://esco/skill/ruby")

    train_jsonl = tmp_path / "train.jsonl"
    val_jsonl = tmp_path / "val.jsonl"
    stats_json = tmp_path / "stats.json"
    training_data_py = tmp_path / "training_data.py"

    _write_dataset(train_jsonl, [p1, p2, n1, n2], split="train")
    _write_dataset(val_jsonl, [p3, n3], split="val")
    stats_json.write_text(
        json.dumps(
            {
                "n_positives": 3,
                "n_hard_negatives": 3,
                "n_train_pairs": 4,
                "n_val_pairs": 2,
                "build_timestamp": "2026-05-16T08:59:53.936468+00:00",
                "config": {"seed": 42, "min_confidence": 0.65},
            }
        ),
        encoding="utf-8",
    )
    training_data_py.write_text("# stub for unit tests\n", encoding="utf-8")

    # Monkey-patch the heavy ESCO loader symbols inside the packer.
    concepts = [
        _make_concept("http://esco/skill/java", "Java"),
        _make_concept("http://esco/skill/perl", "Perl"),
        _make_concept("http://esco/skill/python", "Python"),
        _make_concept("http://esco/skill/ruby", "Ruby"),
    ]
    monkeypatch.setattr(packer, "load_esco_concepts", lambda: concepts)
    monkeypatch.setattr(packer, "compute_esco_file_sha", lambda: "fileesco12hex")
    monkeypatch.setattr(
        packer, "compute_esco_sha", lambda _c: "esco_concept_sha_dead"
    )
    # Freeze the build timestamp so the manifest itself is deterministic
    # for the SHA-stability test.
    frozen = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(packer, "_git_sha_best_effort", lambda: "abc123")

    class _FrozenDatetime:
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return frozen

    monkeypatch.setattr(packer, "datetime", _FrozenDatetime)

    return {
        "train_jsonl": train_jsonl,
        "val_jsonl": val_jsonl,
        "stats_json": stats_json,
        "training_data_py": training_data_py,
        "tmp": tmp_path,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bundle_contains_all_expected_files(synthetic_inputs: dict[str, Path]) -> None:
    """Every entry from the canonical layout must be in the zip."""
    packer = _load_packer_module()
    out_zip = synthetic_inputs["tmp"] / "bundle.zip"

    packer.pack_colab_bundle(
        out_zip=out_zip,
        train_jsonl=synthetic_inputs["train_jsonl"],
        val_jsonl=synthetic_inputs["val_jsonl"],
        stats_json=synthetic_inputs["stats_json"],
        training_data_py=synthetic_inputs["training_data_py"],
    )

    with zipfile.ZipFile(out_zip) as zf:
        names = set(zf.namelist())
    assert names == {
        "train.jsonl",
        "val.jsonl",
        "esco_concepts.json",
        "training_data.py",
        "bundle_manifest.json",
    }


def test_manifest_carries_expected_fields(synthetic_inputs: dict[str, Path]) -> None:
    """The bundle manifest is the provenance contract — check its shape."""
    packer = _load_packer_module()
    out_zip = synthetic_inputs["tmp"] / "bundle.zip"
    packer.pack_colab_bundle(
        out_zip=out_zip,
        train_jsonl=synthetic_inputs["train_jsonl"],
        val_jsonl=synthetic_inputs["val_jsonl"],
        stats_json=synthetic_inputs["stats_json"],
        training_data_py=synthetic_inputs["training_data_py"],
    )

    with zipfile.ZipFile(out_zip) as zf:
        manifest = json.loads(zf.read("bundle_manifest.json").decode("utf-8"))

    assert manifest["mode"] == "pairs_mnrl"
    assert manifest["seed"] == 42
    assert manifest["concept_text_format"] == "bounded-a"
    assert manifest["train_positives"] == 2
    assert manifest["train_hard_negatives"] == 2
    assert manifest["val_positives"] == 1
    assert manifest["val_hard_negatives"] == 1
    assert manifest["esco_concept_sha"] == "esco_concept_sha_dead"
    assert manifest["esco_file_sha"] == "fileesco12hex"
    assert manifest["model_name"].endswith("paraphrase-multilingual-MiniLM-L12-v2")


def test_esco_concepts_payload_carries_pre_rendered_text(
    synthetic_inputs: dict[str, Path],
) -> None:
    """The Colab side must be able to use the concept_text without re-import."""
    packer = _load_packer_module()
    out_zip = synthetic_inputs["tmp"] / "bundle.zip"
    packer.pack_colab_bundle(
        out_zip=out_zip,
        train_jsonl=synthetic_inputs["train_jsonl"],
        val_jsonl=synthetic_inputs["val_jsonl"],
        stats_json=synthetic_inputs["stats_json"],
        training_data_py=synthetic_inputs["training_data_py"],
    )

    with zipfile.ZipFile(out_zip) as zf:
        payload = json.loads(zf.read("esco_concepts.json").decode("utf-8"))

    assert payload["concept_text_format"] == "bounded-a"
    assert payload["n_concepts"] == 4
    for concept in payload["concepts"]:
        assert "concept_text" in concept
        # The bounded-a format always starts with the pref_label.
        assert concept["concept_text"].startswith(concept["pref_label"])


def test_bundle_sha_is_stable_across_two_packs(
    synthetic_inputs: dict[str, Path],
) -> None:
    """Determinism gate — two packs from identical inputs produce identical bytes."""
    packer = _load_packer_module()
    out_a = synthetic_inputs["tmp"] / "a.zip"
    out_b = synthetic_inputs["tmp"] / "b.zip"

    sha_a = packer.pack_colab_bundle(
        out_zip=out_a,
        train_jsonl=synthetic_inputs["train_jsonl"],
        val_jsonl=synthetic_inputs["val_jsonl"],
        stats_json=synthetic_inputs["stats_json"],
        training_data_py=synthetic_inputs["training_data_py"],
    )
    sha_b = packer.pack_colab_bundle(
        out_zip=out_b,
        train_jsonl=synthetic_inputs["train_jsonl"],
        val_jsonl=synthetic_inputs["val_jsonl"],
        stats_json=synthetic_inputs["stats_json"],
        training_data_py=synthetic_inputs["training_data_py"],
    )

    assert sha_a == sha_b
    assert out_a.read_bytes() == out_b.read_bytes()


def test_every_zip_entry_uses_epoch_zero_timestamp(
    synthetic_inputs: dict[str, Path],
) -> None:
    """Defensive: confirm we did not leak an mtime into any ZipInfo."""
    packer = _load_packer_module()
    out_zip = synthetic_inputs["tmp"] / "bundle.zip"
    packer.pack_colab_bundle(
        out_zip=out_zip,
        train_jsonl=synthetic_inputs["train_jsonl"],
        val_jsonl=synthetic_inputs["val_jsonl"],
        stats_json=synthetic_inputs["stats_json"],
        training_data_py=synthetic_inputs["training_data_py"],
    )

    with zipfile.ZipFile(out_zip) as zf:
        for info in zf.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)


def test_missing_train_jsonl_raises_file_not_found(
    synthetic_inputs: dict[str, Path],
) -> None:
    """Refuse-to-build: the user's hand must hit a clear error early."""
    packer = _load_packer_module()
    bogus = synthetic_inputs["tmp"] / "does_not_exist.jsonl"
    out_zip = synthetic_inputs["tmp"] / "bundle.zip"
    with pytest.raises(FileNotFoundError, match=r"train\.jsonl"):
        packer.pack_colab_bundle(
            out_zip=out_zip,
            train_jsonl=bogus,
            val_jsonl=synthetic_inputs["val_jsonl"],
            stats_json=synthetic_inputs["stats_json"],
            training_data_py=synthetic_inputs["training_data_py"],
        )
    assert not out_zip.exists()


def test_stats_mismatch_raises_value_error(
    synthetic_inputs: dict[str, Path],
) -> None:
    """Wrong stats.json counts → fail-loud ValueError; no zip written."""
    # Overwrite stats.json with wrong numbers.
    synthetic_inputs["stats_json"].write_text(
        json.dumps(
            {
                "n_positives": 99,  # actual is 3
                "n_hard_negatives": 3,
                "n_train_pairs": 4,
                "n_val_pairs": 2,
            }
        ),
        encoding="utf-8",
    )

    packer = _load_packer_module()
    out_zip = synthetic_inputs["tmp"] / "bundle.zip"
    with pytest.raises(ValueError, match="positives"):
        packer.pack_colab_bundle(
            out_zip=out_zip,
            train_jsonl=synthetic_inputs["train_jsonl"],
            val_jsonl=synthetic_inputs["val_jsonl"],
            stats_json=synthetic_inputs["stats_json"],
            training_data_py=synthetic_inputs["training_data_py"],
        )
    assert not out_zip.exists()


def test_unknown_mode_raises_value_error(
    synthetic_inputs: dict[str, Path],
) -> None:
    """A typo in --mode must not silently produce a wrong-labelled bundle."""
    packer = _load_packer_module()
    out_zip = synthetic_inputs["tmp"] / "bundle.zip"
    with pytest.raises(ValueError, match="Unknown mode"):
        packer.pack_colab_bundle(
            out_zip=out_zip,
            mode="not_a_mode",  # type: ignore[arg-type]
            train_jsonl=synthetic_inputs["train_jsonl"],
            val_jsonl=synthetic_inputs["val_jsonl"],
            stats_json=synthetic_inputs["stats_json"],
            training_data_py=synthetic_inputs["training_data_py"],
        )
