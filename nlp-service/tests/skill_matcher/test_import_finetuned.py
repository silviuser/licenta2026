"""Fast + slow tests for ``scripts/import_finetuned_model.py``.

Fast tests (always run): exercise the layout / manifest / atomic-write
machinery against synthetic zips. They set ``load_check=False`` so the
real SentenceTransformer never has to load.

Slow test (``@pytest.mark.slow``, skipped if no checkpoint is present):
loads the actual fine-tuned encoder, encodes three strings, asserts the
output shape. This is the Phase Gamma readiness gate — proves the imported
checkpoint is usable by Module 3's encoder.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import zipfile
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Import the script as a module
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "import_finetuned_model.py"
_MODELS_DIR = _REPO_ROOT / "models" / "skill_matcher"


def _load_importer_module() -> types.ModuleType:
    """Hand-load the script as a module since it lives outside ``src/``."""
    if "import_finetuned_model" in sys.modules:
        return sys.modules["import_finetuned_model"]
    spec = importlib.util.spec_from_file_location(
        "import_finetuned_model", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_finetuned_model"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Synthetic zip helpers
# ---------------------------------------------------------------------------


def _write_synthetic_checkpoint_zip(
    *,
    zip_path: Path,
    run_name: str,
    include_manifest: bool = True,
    include_weights: bool = True,
    nested: bool = True,
    manifest_payload: dict[str, Any] | None = None,
) -> None:
    """Build a synthetic SentenceTransformer-shaped checkpoint zip.

    Parameters control which expected artefacts are present, so each
    test can drive the importer down a specific error path.
    """
    if manifest_payload is None:
        manifest_payload = {
            "run_name": run_name,
            "base_model": (
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            ),
            "seed": 42,
            "mode": "pairs_mnrl",
            "concept_text_format": "bounded-a",
            "epochs": 3,
            "batch_size": 32,
            "learning_rate": 2e-5,
        }
    prefix = f"{run_name}/" if nested else ""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if include_manifest:
            zf.writestr(
                f"{prefix}{run_name}_manifest.json",
                json.dumps(manifest_payload, indent=2),
            )
        # A minimal SentenceTransformer-ish config (not actually loadable,
        # but enough for the layout validator).
        zf.writestr(
            f"{prefix}config.json",
            json.dumps({"model_type": "bert", "hidden_size": 384}),
        )
        zf.writestr(
            f"{prefix}sentence_bert_config.json",
            json.dumps({"max_seq_length": 128, "do_lower_case": False}),
        )
        if include_weights:
            # The validator only checks for file presence; content doesn't
            # have to be a real tensor unless load_check=True.
            zf.writestr(f"{prefix}model.safetensors", b"\x00" * 64)


# ---------------------------------------------------------------------------
# Tests — fast suite
# ---------------------------------------------------------------------------


def test_happy_path_extracts_and_updates_latest(tmp_path: Path) -> None:
    """A well-formed zip ends up under <models_dir>/<run_name> + latest.txt."""
    importer = _load_importer_module()
    run_name = "mnrl_v1_20260520_1200"
    zip_path = tmp_path / "checkpoint.zip"
    _write_synthetic_checkpoint_zip(zip_path=zip_path, run_name=run_name)

    models_dir = tmp_path / "models"
    final = importer.import_finetuned_model(
        zip_path=zip_path,
        run_name=run_name,
        models_dir=models_dir,
        load_check=False,
    )

    assert final == models_dir / run_name
    assert final.is_dir()
    assert (final / f"{run_name}_manifest.json").exists()
    assert (final / "model.safetensors").exists()

    latest = models_dir / "latest.txt"
    assert latest.read_text(encoding="utf-8").strip() == run_name


def test_happy_path_works_for_flat_zip(tmp_path: Path) -> None:
    """A zip without the <run_name>/ prefix still imports cleanly."""
    importer = _load_importer_module()
    run_name = "mnrl_v1_20260520_1200"
    zip_path = tmp_path / "checkpoint.zip"
    _write_synthetic_checkpoint_zip(
        zip_path=zip_path, run_name=run_name, nested=False
    )

    models_dir = tmp_path / "models"
    final = importer.import_finetuned_model(
        zip_path=zip_path,
        run_name=run_name,
        models_dir=models_dir,
        load_check=False,
    )

    assert final == models_dir / run_name
    assert (final / f"{run_name}_manifest.json").exists()


def test_missing_zip_raises_file_not_found(tmp_path: Path) -> None:
    """Non-existent zip → clean FileNotFoundError, no side effects."""
    importer = _load_importer_module()
    models_dir = tmp_path / "models"
    with pytest.raises(FileNotFoundError):
        importer.import_finetuned_model(
            zip_path=tmp_path / "nope.zip",
            run_name="run1",
            models_dir=models_dir,
            load_check=False,
        )
    assert not (models_dir / "run1").exists()


def test_invalid_run_name_rejected(tmp_path: Path) -> None:
    """run_names with path separators are rejected before any extraction."""
    importer = _load_importer_module()
    zip_path = tmp_path / "checkpoint.zip"
    _write_synthetic_checkpoint_zip(zip_path=zip_path, run_name="ok")

    with pytest.raises(ValueError, match="path separators"):
        importer.import_finetuned_model(
            zip_path=zip_path,
            run_name="bad/name",
            models_dir=tmp_path / "models",
            load_check=False,
        )


def test_bad_zip_raises_import_error_without_residue(tmp_path: Path) -> None:
    """A non-zip file is detected and leaves nothing behind."""
    importer = _load_importer_module()
    bad = tmp_path / "not_a_zip.bin"
    bad.write_bytes(b"\x00\x01\x02\x03this is not a zip")
    models_dir = tmp_path / "models"

    with pytest.raises(importer.ImportError_, match="Cannot read zip"):
        importer.import_finetuned_model(
            zip_path=bad,
            run_name="run1",
            models_dir=models_dir,
            load_check=False,
        )
    # No final dir, no staging directories left behind.
    assert not (models_dir / "run1").exists()
    leftovers = list(models_dir.glob("import_run1_*"))
    assert leftovers == []


def test_missing_manifest_raises_with_no_residue(tmp_path: Path) -> None:
    """A zip without the manifest fails loud + cleans up."""
    importer = _load_importer_module()
    run_name = "mnrl_v1_20260520_1200"
    zip_path = tmp_path / "checkpoint.zip"
    _write_synthetic_checkpoint_zip(
        zip_path=zip_path, run_name=run_name, include_manifest=False
    )
    models_dir = tmp_path / "models"

    with pytest.raises(importer.ImportError_, match="manifest"):
        importer.import_finetuned_model(
            zip_path=zip_path,
            run_name=run_name,
            models_dir=models_dir,
            load_check=False,
        )
    assert not (models_dir / run_name).exists()
    assert list(models_dir.glob("import_*")) == []


def test_missing_weights_raises_with_no_residue(tmp_path: Path) -> None:
    """A zip without weight files fails loud + cleans up."""
    importer = _load_importer_module()
    run_name = "mnrl_v1_20260520_1200"
    zip_path = tmp_path / "checkpoint.zip"
    _write_synthetic_checkpoint_zip(
        zip_path=zip_path, run_name=run_name, include_weights=False
    )
    models_dir = tmp_path / "models"

    with pytest.raises(importer.ImportError_, match="No model weights"):
        importer.import_finetuned_model(
            zip_path=zip_path,
            run_name=run_name,
            models_dir=models_dir,
            load_check=False,
        )
    assert not (models_dir / run_name).exists()


def test_manifest_missing_required_field_raises(tmp_path: Path) -> None:
    """The manifest must carry every locked-decision field."""
    importer = _load_importer_module()
    run_name = "mnrl_v1_20260520_1200"
    zip_path = tmp_path / "checkpoint.zip"
    _write_synthetic_checkpoint_zip(
        zip_path=zip_path,
        run_name=run_name,
        manifest_payload={"run_name": run_name, "seed": 42},  # missing fields
    )
    models_dir = tmp_path / "models"

    with pytest.raises(importer.ImportError_, match="missing required"):
        importer.import_finetuned_model(
            zip_path=zip_path,
            run_name=run_name,
            models_dir=models_dir,
            load_check=False,
        )


def test_refuses_to_overwrite_existing_run(tmp_path: Path) -> None:
    """Importing onto an already-imported run name fails fast."""
    importer = _load_importer_module()
    run_name = "mnrl_v1_20260520_1200"
    zip_path = tmp_path / "checkpoint.zip"
    _write_synthetic_checkpoint_zip(zip_path=zip_path, run_name=run_name)

    models_dir = tmp_path / "models"
    # First import succeeds.
    importer.import_finetuned_model(
        zip_path=zip_path,
        run_name=run_name,
        models_dir=models_dir,
        load_check=False,
    )
    # Second import refuses.
    with pytest.raises(importer.ImportError_, match="Refusing to overwrite"):
        importer.import_finetuned_model(
            zip_path=zip_path,
            run_name=run_name,
            models_dir=models_dir,
            load_check=False,
        )


def test_latest_txt_updated_atomically(tmp_path: Path) -> None:
    """latest.txt is written via temp + rename — no truncated half-writes."""
    importer = _load_importer_module()
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    # Pre-existing latest.txt content the second import must replace.
    (models_dir / "latest.txt").write_text("previous_run\n", encoding="utf-8")

    run_name = "mnrl_v1_20260520_1200"
    zip_path = tmp_path / "checkpoint.zip"
    _write_synthetic_checkpoint_zip(zip_path=zip_path, run_name=run_name)
    importer.import_finetuned_model(
        zip_path=zip_path,
        run_name=run_name,
        models_dir=models_dir,
        load_check=False,
    )

    assert (models_dir / "latest.txt").read_text(encoding="utf-8").strip() == run_name
    # No leftover tempfiles in the parent dir.
    leftovers = list(models_dir.glob("latest.txt.*"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# Slow suite — real SentenceTransformer load
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_loaded_finetuned_encoder_runs() -> None:
    """Sign-off gate: the imported checkpoint loads + encodes 3 strings.

    Skipped automatically when no fine-tuned checkpoint is present
    (e.g. before Silviu has returned the Phase β zip).
    """
    latest_file = _MODELS_DIR / "latest.txt"
    if not latest_file.exists():
        pytest.skip(
            "No fine-tuned checkpoint imported yet — run "
            "scripts/import_finetuned_model.py first."
        )
    run_name = latest_file.read_text(encoding="utf-8").strip()
    checkpoint_dir = _MODELS_DIR / run_name
    if not checkpoint_dir.is_dir():
        pytest.skip(
            f"latest.txt points to {run_name} but {checkpoint_dir} is missing."
        )

    # Lazy import — keeps the fast suite cheap.
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(str(checkpoint_dir))
    out = model.encode(
        ["Python developer", "Java programming", "Data analyst"],
        normalize_embeddings=True,
    )
    assert out.shape[0] == 3
    # MiniLM-L12 emits 384-dim embeddings.
    assert out.shape[1] == 384
    # L2-norm 1 for every row (within float32 noise).
    norms = (out * out).sum(axis=1)
    assert ((norms - 1.0).__abs__() < 1e-4).all()
