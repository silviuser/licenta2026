"""Pack the Step 5 Colab training bundle.

Produces a single deterministic ``colab_bundle.zip`` containing
everything the Colab notebook needs to fine-tune
``paraphrase-multilingual-MiniLM-L12-v2`` on the Step 3 pairs:

* ``train.jsonl``       — verbatim copy of ``data/training/pairs/train.jsonl``.
* ``val.jsonl``         — verbatim copy of ``data/training/pairs/val.jsonl``.
* ``esco_concepts.json``— ESCO + custom-overlay concept set with the
  pre-rendered ``bounded-a`` concept text per row, so the Colab side
  does not need to import ``skill_matcher`` to produce identical
  positive-side strings.
* ``training_data.py``  — verbatim copy of
  ``src/skill_matcher/training_data.py``. Bundled rather than re-
  implemented in the notebook so the Colab side has one code path.
* ``bundle_manifest.json`` — provenance (counts, hashes, timestamps).

Determinism
-----------
The bundle is byte-stable across re-runs on identical inputs. Three
guarantees:

1. Every :class:`zipfile.ZipInfo` is constructed with
   ``date_time=(1980, 1, 1, 0, 0, 0)`` — the zip-epoch zero. No file-
   system mtimes leak in.
2. Files are added in lexicographic name order.
3. ``esco_concepts.json`` and ``bundle_manifest.json`` are serialised
   with ``json.dumps(..., sort_keys=True, indent=2, ensure_ascii=False)``.

A unit test ``tests/skill_matcher/test_pack_colab_bundle.py`` asserts
SHA-256 stability across two packs from the same inputs.

CLI
---
Run from ``nlp-service/``::

    python scripts/pack_colab_bundle.py --out-zip colab_bundle.zip

The script refuses to build if:

* either pairs JSONL file is missing,
* the rendered ``esco_concepts.json`` would exceed 50 MB (sanity cap),
* ``stats.json`` pair counts disagree with the JSONL pair counts.

These are hard fail-loud errors, not warnings — the bundle is a
training-time artefact and a silent corruption here would only surface
~45 min later, on Silviu's Colab session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

# stdout reconfigure for Windows cp1252 console (Romanian filenames break it)
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, OSError):
    pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

import structlog  # noqa: E402

from skill_matcher.dataset import TrainingDataset, load_training_dataset  # noqa: E402
from skill_matcher.esco_index import format_concept_text  # noqa: E402
from skill_matcher.esco_loader import (  # noqa: E402
    EscoConcept,
    compute_esco_file_sha,
    compute_esco_sha,
    load_esco_concepts,
)

logger = structlog.get_logger("pack_colab_bundle")


BundleMode = Literal["pairs_mnrl", "triplets"]


# ---------------------------------------------------------------------------
# Constants — match the locked Step 5 decisions
# ---------------------------------------------------------------------------

_BASE_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_SEED = 42
_CONCEPT_TEXT_FORMAT = "bounded-a"
_DEFAULT_TRAIN_JSONL = _REPO_ROOT / "data" / "training" / "pairs" / "train.jsonl"
_DEFAULT_VAL_JSONL = _REPO_ROOT / "data" / "training" / "pairs" / "val.jsonl"
_DEFAULT_STATS_JSON = _REPO_ROOT / "data" / "training" / "pairs" / "stats.json"
_DEFAULT_TRAINING_DATA_PY = (
    _REPO_ROOT / "src" / "skill_matcher" / "training_data.py"
)

_BUNDLE_FILES = (
    "train.jsonl",
    "val.jsonl",
    "esco_concepts.json",
    "training_data.py",
    "bundle_manifest.json",
)
"""Canonical bundle layout — sorted alphabetically by the packer."""

_ESCO_CONCEPTS_SIZE_CAP_BYTES = 50 * 1024 * 1024  # 50 MB sanity cap.

_ZIP_EPOCH_DATE_TIME = (1980, 1, 1, 0, 0, 0)
"""Fixed timestamp for every zip entry — guarantees byte-stable archives."""


# ---------------------------------------------------------------------------
# ESCO concept payload
# ---------------------------------------------------------------------------


def _serialise_concept(concept: EscoConcept) -> dict[str, Any]:
    """Project an :class:`EscoConcept` to a JSON-serialisable dict.

    Includes the **pre-rendered** ``concept_text`` (bounded-a) so the
    Colab side can build SBERT examples without depending on the
    ``skill_matcher`` package.
    """
    return {
        "uri": concept.uri,
        "pref_label": concept.pref_label,
        "alt_labels": list(concept.alt_labels),
        "description": concept.description,
        "skill_type": concept.skill_type,
        "is_custom": concept.is_custom,
        "concept_text": format_concept_text(concept, _CONCEPT_TEXT_FORMAT),
    }


def _build_esco_concepts_json(concepts: list[EscoConcept]) -> bytes:
    """Render the ESCO concept payload as deterministic UTF-8 JSON bytes.

    ``load_esco_concepts()`` already returns the list URI-sorted; we
    redundantly sort again here so a callee that hands us an unsorted
    list still gets byte-stable output.
    """
    payload = {
        "concept_text_format": _CONCEPT_TEXT_FORMAT,
        "n_concepts": len(concepts),
        "concepts": [
            _serialise_concept(c) for c in sorted(concepts, key=lambda c: c.uri)
        ],
    }
    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)
    return text.encode("utf-8")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _git_sha_best_effort() -> str | None:
    """Return the current HEAD SHA, or ``None`` if git isn't available.

    Best-effort: we never let a missing git binary or a non-repo cwd
    fail the pack. The manifest carries ``null`` instead.
    """
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        return out.strip() or None
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return None


def _compute_pair_counts(
    train_jsonl: Path, val_jsonl: Path
) -> tuple[int, int, int, int]:
    """Return ``(train_positives, train_hard_negatives, val_positives, val_hard_negatives)``.

    Loads each split via :func:`load_training_dataset` so the count is
    derived from the parsed pair list (not from a naive line count that
    would include the header row).
    """
    train_ds = load_training_dataset(train_jsonl)
    val_ds = load_training_dataset(val_jsonl)

    def _split_counts(ds: TrainingDataset) -> tuple[int, int]:
        pos = sum(1 for p in ds.pairs if p.pair_type == "positive")
        neg = sum(1 for p in ds.pairs if p.pair_type == "hard_negative")
        return pos, neg

    train_pos, train_neg = _split_counts(train_ds)
    val_pos, val_neg = _split_counts(val_ds)
    return train_pos, train_neg, val_pos, val_neg


def _assert_stats_match(
    *,
    stats_json: Path,
    train_positives: int,
    train_hard_negatives: int,
    val_positives: int,
    val_hard_negatives: int,
) -> dict[str, Any]:
    """Cross-check the parsed pair counts against ``stats.json``.

    Fails loud if any of the four counts disagrees. Returns the parsed
    stats dict on success so the caller can fold provenance into the
    manifest.
    """
    if not stats_json.exists():
        raise FileNotFoundError(
            f"stats.json not found at {stats_json}; rerun build_training_dataset.py "
            "to regenerate Step 3 provenance."
        )
    stats: dict[str, Any] = json.loads(stats_json.read_text(encoding="utf-8"))

    expected_positives = int(stats["n_positives"])
    expected_negatives = int(stats["n_hard_negatives"])
    expected_train = int(stats["n_train_pairs"])
    expected_val = int(stats["n_val_pairs"])

    actual_positives = train_positives + val_positives
    actual_negatives = train_hard_negatives + val_hard_negatives
    actual_train = train_positives + train_hard_negatives
    actual_val = val_positives + val_hard_negatives

    mismatches: list[str] = []
    if actual_positives != expected_positives:
        mismatches.append(
            f"positives: parsed={actual_positives} stats={expected_positives}"
        )
    if actual_negatives != expected_negatives:
        mismatches.append(
            f"hard_negatives: parsed={actual_negatives} stats={expected_negatives}"
        )
    if actual_train != expected_train:
        mismatches.append(
            f"train_pairs: parsed={actual_train} stats={expected_train}"
        )
    if actual_val != expected_val:
        mismatches.append(f"val_pairs: parsed={actual_val} stats={expected_val}")

    if mismatches:
        raise ValueError(
            "Pair-count mismatch between JSONL and stats.json: "
            + "; ".join(mismatches)
            + ". Refusing to pack; rebuild the dataset."
        )
    return stats


def _build_manifest(
    *,
    mode: BundleMode,
    train_positives: int,
    train_hard_negatives: int,
    val_positives: int,
    val_hard_negatives: int,
    esco_sha: str,
    esco_file_sha: str,
    stats: dict[str, Any],
) -> bytes:
    """Render the bundle manifest as deterministic JSON bytes."""
    manifest = {
        "schema_version": 1,
        "model_name": _BASE_MODEL_NAME,
        "seed": _SEED,
        "mode": mode,
        "concept_text_format": _CONCEPT_TEXT_FORMAT,
        "train_positives": train_positives,
        "train_hard_negatives": train_hard_negatives,
        "val_positives": val_positives,
        "val_hard_negatives": val_hard_negatives,
        "esco_concept_sha": esco_sha,
        "esco_file_sha": esco_file_sha,
        "step3_build_timestamp": stats.get("build_timestamp"),
        "step3_config": stats.get("config", {}),
        "build_timestamp_utc": datetime.now(tz=UTC).isoformat(),
        "git_sha": _git_sha_best_effort(),
    }
    text = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False)
    return text.encode("utf-8")


# ---------------------------------------------------------------------------
# Packer
# ---------------------------------------------------------------------------


def _add_bytes(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    """Append a file to the zip with a fixed-epoch ZipInfo.

    ``ZipInfo.date_time = (1980, 1, 1, 0, 0, 0)`` is the zip-epoch zero;
    using it for every entry strips system-dependent mtime leakage so
    the resulting archive is byte-stable across re-runs.
    """
    info = zipfile.ZipInfo(filename=name, date_time=_ZIP_EPOCH_DATE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o644 & 0xFFFF) << 16  # rw-r--r--
    zf.writestr(info, data)


def pack_colab_bundle(
    *,
    out_zip: Path,
    mode: BundleMode = "pairs_mnrl",
    train_jsonl: Path = _DEFAULT_TRAIN_JSONL,
    val_jsonl: Path = _DEFAULT_VAL_JSONL,
    stats_json: Path = _DEFAULT_STATS_JSON,
    training_data_py: Path = _DEFAULT_TRAINING_DATA_PY,
) -> str:
    """Build the Colab bundle and return its SHA-256 hex digest.

    Parameters
    ----------
    out_zip
        Destination zip path. Parent directories are created on demand.
    mode
        Recorded in the manifest; defaults to ``"pairs_mnrl"`` per the
        Step 5 Pre-Flight.
    train_jsonl, val_jsonl, stats_json
        Step 3 outputs. Default to the canonical locations under
        ``nlp-service/data/training/pairs/``.
    training_data_py
        The module to bundle for the Colab side. Defaults to
        ``src/skill_matcher/training_data.py``.

    Returns
    -------
    str
        SHA-256 of the produced zip, hex-encoded. Printed by the CLI and
        recorded by the unit test.

    Raises
    ------
    FileNotFoundError
        If any input path is missing.
    ValueError
        If pair counts disagree with ``stats.json``, or the rendered
        ``esco_concepts.json`` exceeds the 50 MB sanity cap.
    """
    # Refuse-to-build: input presence.
    for path, label in (
        (train_jsonl, "train.jsonl"),
        (val_jsonl, "val.jsonl"),
        (stats_json, "stats.json"),
        (training_data_py, "training_data.py"),
    ):
        if not path.exists():
            raise FileNotFoundError(f"Required input missing: {label} at {path}")

    if mode not in ("pairs_mnrl", "triplets"):
        raise ValueError(f"Unknown mode {mode!r}; expected pairs_mnrl or triplets.")

    # Pair-count cross-check.
    (
        train_positives,
        train_hard_negatives,
        val_positives,
        val_hard_negatives,
    ) = _compute_pair_counts(train_jsonl, val_jsonl)
    stats = _assert_stats_match(
        stats_json=stats_json,
        train_positives=train_positives,
        train_hard_negatives=train_hard_negatives,
        val_positives=val_positives,
        val_hard_negatives=val_hard_negatives,
    )

    # ESCO payload + sanity cap.
    concepts = load_esco_concepts()
    esco_bytes = _build_esco_concepts_json(concepts)
    if len(esco_bytes) > _ESCO_CONCEPTS_SIZE_CAP_BYTES:
        raise ValueError(
            f"esco_concepts.json is {len(esco_bytes)} bytes, exceeds "
            f"{_ESCO_CONCEPTS_SIZE_CAP_BYTES} byte cap. Refusing to pack."
        )

    esco_sha = compute_esco_sha(concepts)
    esco_file_sha = compute_esco_file_sha()

    manifest_bytes = _build_manifest(
        mode=mode,
        train_positives=train_positives,
        train_hard_negatives=train_hard_negatives,
        val_positives=val_positives,
        val_hard_negatives=val_hard_negatives,
        esco_sha=esco_sha,
        esco_file_sha=esco_file_sha,
        stats=stats,
    )

    # Verbatim file bytes.
    train_bytes = train_jsonl.read_bytes()
    val_bytes = val_jsonl.read_bytes()
    training_data_bytes = training_data_py.read_bytes()

    # Assemble: write to a temp zip first, then atomic rename.
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="colab_bundle_", suffix=".zip", dir=out_zip.parent, delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            payloads = {
                "train.jsonl": train_bytes,
                "val.jsonl": val_bytes,
                "esco_concepts.json": esco_bytes,
                "training_data.py": training_data_bytes,
                "bundle_manifest.json": manifest_bytes,
            }
            # Defensive: assert layout in sync with _BUNDLE_FILES so
            # adding a new file requires updating both.
            if set(payloads) != set(_BUNDLE_FILES):
                raise RuntimeError(
                    "Bundle payload set drifted from _BUNDLE_FILES; update both."
                )
            for name in sorted(payloads):
                _add_bytes(zf, name, payloads[name])

        # Atomic move (same filesystem because we used dir=out_zip.parent).
        shutil.move(str(tmp_path), str(out_zip))
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    bundle_sha = hashlib.sha256(out_zip.read_bytes()).hexdigest()
    logger.info(
        "pack_colab_bundle.done",
        out_zip=str(out_zip),
        size_bytes=out_zip.stat().st_size,
        sha256=bundle_sha,
        mode=mode,
        train_positives=train_positives,
        train_hard_negatives=train_hard_negatives,
        val_positives=val_positives,
        val_hard_negatives=val_hard_negatives,
        n_concepts=len(concepts),
        esco_concept_sha=esco_sha,
    )
    return bundle_sha


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pack the Step 5 Colab fine-tuning bundle."
    )
    parser.add_argument(
        "--out-zip",
        type=Path,
        default=Path("colab_bundle.zip"),
        help=(
            "Destination zip path (default: ./colab_bundle.zip relative "
            "to the cwd you invoked the script from)."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("pairs_mnrl", "triplets"),
        default="pairs_mnrl",
        help=(
            "Training mode recorded in the bundle manifest. Defaults to "
            "pairs_mnrl per Step 5 Pre-Flight §3."
        ),
    )
    parser.add_argument(
        "--train-jsonl",
        type=Path,
        default=_DEFAULT_TRAIN_JSONL,
        help="Override the Step 3 train.jsonl path.",
    )
    parser.add_argument(
        "--val-jsonl",
        type=Path,
        default=_DEFAULT_VAL_JSONL,
        help="Override the Step 3 val.jsonl path.",
    )
    parser.add_argument(
        "--stats-json",
        type=Path,
        default=_DEFAULT_STATS_JSON,
        help="Override the Step 3 stats.json path.",
    )
    parser.add_argument(
        "--training-data-py",
        type=Path,
        default=_DEFAULT_TRAINING_DATA_PY,
        help="Override the src/skill_matcher/training_data.py path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle_sha = pack_colab_bundle(
        out_zip=args.out_zip,
        mode=args.mode,
        train_jsonl=args.train_jsonl,
        val_jsonl=args.val_jsonl,
        stats_json=args.stats_json,
        training_data_py=args.training_data_py,
    )
    print(f"Bundle SHA-256: {bundle_sha}")
    print(f"Bundle path:    {args.out_zip.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
